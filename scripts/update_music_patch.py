"""Update only the project's D3 music addon, preserving checksum-matched backups."""
import argparse
from datetime import datetime
import json
import os
import shutil
import subprocess
from pathlib import Path
from assets import digest, require


def update(build, client, previous_sha256, retire_sha256=None):
    build = Path(build).resolve(); client = Path(client).resolve()
    report = json.loads((build / 'validation.json').read_text())
    name = Path(report['package']['mpq']).name
    require(name in ('patch-D3music.MPQ','patch-M.MPQ'), 'This updater only manages the D3 music addon')
    source = build / name; target = client / 'Data' / 'patch-M.MPQ'
    require((client / 'Wow.exe').is_file(), 'Invalid client directory')
    require(digest(source) == report['package']['sha256'], 'New music archive checksum mismatch')
    require(digest(target) == previous_sha256, 'Installed music changed; inspect before updating')
    running = subprocess.run(['tasklist', '/FO', 'CSV', '/NH'], capture_output=True, text=True, check=True).stdout.lower()
    require('"wow.exe"' not in running and '"wow_rce_fix2.exe"' not in running, 'Close WoW before updating music')
    retired = client / 'Data' / 'patch-TavernMusic.MPQ'
    if retire_sha256:
        require(digest(retired) == retire_sha256, 'Separate tavern patch checksum mismatch')
    backup = client / 'AddonPatchBackups' / ('music-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
    require(not backup.exists(), 'Backup directory already exists')
    backup.mkdir(parents=True)
    saved = backup / target.name
    shutil.copy2(target, saved)
    require(digest(saved) == previous_sha256, 'Backup checksum mismatch')
    staged = backup / 'new-music.pending'
    shutil.copyfile(source, staged)
    require(digest(staged) == report['package']['sha256'], 'Staged copy checksum mismatch')
    moved = False
    try:
        if retire_sha256:
            shutil.move(str(retired), str(backup / retired.name)); moved = True
        os.replace(staged, target)
        require(digest(target) == report['package']['sha256'], 'Installed music checksum mismatch')
    except Exception:
        shutil.copy2(saved, target)
        if moved:
            shutil.move(str(backup / retired.name), str(retired))
        raise
    result = dict(installed_file=str(target), sha256=digest(target), backup=str(backup),
        retired_separate_tavern_patch=moved, original_game_archives_modified=False, in_game_verified=False)
    (build / 'installation.json').write_text(json.dumps(result, indent=2))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('build'); parser.add_argument('--client', required=True)
    parser.add_argument('--previous-sha256', required=True); parser.add_argument('--retire-tavern-sha256')
    args = parser.parse_args()
    print(json.dumps(update(args.build, args.client, args.previous_sha256, args.retire_tavern_sha256), indent=2))
