"""Install a checksum-matched custom Z addon with backup and an atomic replacement."""
import argparse,datetime,json,os,shutil,subprocess
from pathlib import Path
from assets import digest,require

def install(build,client):
    build=Path(build).resolve();client=Path(client).resolve()
    report=json.loads((build/'validation.json').read_text());source=Path(report['package']['mpq'])
    require(source.name=='patch-enGB-Z.MPQ','Expected combined enGB Z addon')
    target=client/'Data/enGB/patch-enGB-Z.MPQ'
    require(digest(source)==report['package']['sha256'],'Build checksum changed')
    require(digest(target)==report['previous_sha256'],'Installed addon changed since build')
    tasks=subprocess.check_output(['tasklist','/FO','CSV','/NH'],text=True).lower()
    require(not any('"'+n+'"' in tasks for n in ('wow.exe','wow_rce_fix2.exe')),'Close WoW before installation')
    backup=client/'AddonPatchBackups'/('login-death-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
    backup.mkdir(parents=True,exist_ok=False);shutil.copy2(target,backup/target.name)
    require(digest(backup/target.name)==report['previous_sha256'],'Backup verification failed')
    stage=target.with_suffix('.MPQ.pending');require(not stage.exists(),'Pending update already exists')
    shutil.copyfile(source,stage);require(digest(stage)==digest(source),'Staged checksum mismatch');os.replace(stage,target)
    result=dict(installed_file=str(target),sha256=digest(target),backup=str(backup/target.name))
    (build/'installation.json').write_text(json.dumps(result,indent=2));return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('build');p.add_argument('--client',required=True);a=p.parse_args()
    print(json.dumps(install(a.build,a.client),indent=2))
