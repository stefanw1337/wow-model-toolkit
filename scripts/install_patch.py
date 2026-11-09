"""Install a verified additive MPQ; never overwrite an existing file."""
import argparse
import json
import shutil
import subprocess
from pathlib import Path
from assets import digest,read_client_files,require,install_name
import hashlib
from datetime import datetime


def install(build,client):
    build=Path(build).resolve();client=Path(client).resolve()
    cfg=json.loads((build/'build-config.json').read_text())
    report=json.loads((build/'validation.json').read_text())
    require((client/'Wow.exe').is_file(),'Expected a WoW client directory')
    # Avoid installing during a running session: archives are loaded at startup.
    running=subprocess.run(['tasklist','/FO','CSV','/NH'],capture_output=True,text=True,check=True).stdout.lower()
    require('"wow.exe"' not in running and '"wow_rce_fix2.exe"' not in running,'Close WoW before installing')
    name=Path(report['package']['mpq']).name
    source=build/name;require(digest(source)==report['package']['sha256'],'MPQ checksum mismatch')
    locale=cfg.get('locale','enGB')
    require(locale.isalnum() and len(locale)==4,'Invalid locale')
    installed_name=install_name(cfg.get('install_name',name),locale,cfg.get('install_in_data_root',False))
    destination=(client/'Data' if cfg.get('install_in_data_root',False) else client/'Data'/locale)/installed_name
    require(destination.parent.is_dir(),'Client locale directory not found')
    require(not destination.exists(),'Destination already exists; no file was changed')
    overlay=report.get('display_overlay')
    if overlay:
        latest=read_client_files(client,locale,list(overlay['base_sha256']))
        for name,expected in overlay['base_sha256'].items():
            require(hashlib.sha256(latest[name][0]).hexdigest()==expected,'Client DBC changed since this patch was built; rebuild before installing')
    merged=report.get('merged_patches',[])
    authorized=set(cfg.get('merge_patches',[]))
    old_paths=[]
    for entry in merged:
        old=Path(entry['path']).resolve()
        require(old.parent==(client/'Data'/locale).resolve() and old.name in authorized,'Unexpected consolidation source')
        require(old!=destination and digest(old)==entry['sha256'],'Consolidation source changed')
        old_paths.append(old)
    with source.open('rb') as src,destination.open('xb') as dst:shutil.copyfileobj(src,dst)
    require(digest(destination)==report['package']['sha256'],'Installed checksum mismatch')
    result=dict(installed_file=str(destination),sha256=digest(destination),existing_archives_modified=False,in_game_verified=False,uninstall='Close WoW and remove only this installed file.')
    if old_paths:
        backup=client/'AddonPatchBackups'/datetime.now().strftime('%Y%m%d-%H%M%S')
        require(not backup.exists(),'Backup directory already exists')
        backup.mkdir(parents=True)
        moved=[]
        try:
            for old in old_paths:
                saved=backup/old.name
                require(not saved.exists(),'Backup destination already exists')
                shutil.move(str(old),str(saved));moved.append((old,saved))
            if overlay:
                latest=read_client_files(client,locale,list(overlay['base_sha256']))
                for name in latest:
                    require(latest[name][0]==(build/'archive'/name).read_bytes(),'Another patch overrides the consolidated DBC')
        except Exception:
            for old,saved in reversed(moved):shutil.move(str(saved),str(old))
            destination.unlink()
            raise
        result['superseded_addons_backup']=str(backup)
        result['uninstall']='Close WoW, remove this installed file, and restore the backed-up addon MPQs to Data/'+locale+'.'
    (build/'installation.json').write_text(json.dumps(result,indent=2))
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('build');p.add_argument('--client',required=True);a=p.parse_args()
    print(json.dumps(install(a.build,a.client),indent=2))
