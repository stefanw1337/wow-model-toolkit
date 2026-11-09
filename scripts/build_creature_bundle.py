"""Consolidate additive creature patches, models and timed PCM voice events."""
import argparse
import hashlib
import json
import re
import shutil
import struct
import wave
from pathlib import Path
import mpyq
from assets import DBC, digest, display_overlays, member, pack, read_client_files, require
from sound_events import append_events, validate_events
from validate import read, validate
from mpq_read import read_file


def build(config, output, editor):
    cfg = json.loads(Path(config).read_text(encoding='utf-8-sig'))
    out = Path(output).resolve()
    require(not out.exists(), 'Use a fresh output directory')
    out.mkdir(parents=True); stage = out / 'archive'; stage.mkdir()
    base_patches = []
    for name in cfg['merge_patches']:
        path = Path(cfg['client']) / 'Data' / cfg['locale'] / name
        with path.open('rb') as stream:
            archive = mpyq.MPQArchive(stream)
            for raw in archive.files:
                if raw.startswith(b'('):
                    continue
                relative = member(raw.decode())
                target = stage / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(read_file(archive,raw))
        base_patches.append(dict(path=str(path), sha256=digest(path)))
    replacements = []
    for item in cfg['models']:
        build_dir = Path(item['build'])
        model_cfg = json.loads((build_dir / 'build-config.json').read_text())
        report = json.loads((build_dir / 'validation.json').read_text())
        for source in (build_dir / 'archive' / 'Creature').rglob('*'):
            if source.is_file():
                target = stage / source.relative_to(build_dir / 'archive')
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
        if item.get('display_ids'):
            replacements.append(dict(display_ids=item['display_ids'], model_path=model_cfg['model_path'], model=report['model'], display_scale=item.get('display_scale',1.0)))
    overlay = display_overlays(cfg['client'], cfg['locale'], replacements, stage)
    sound_path = 'DBFilesClient/SoundEntries.dbc'
    original, archive = read_client_files(cfg['client'], cfg['locale'], [sound_path])[sound_path]
    sounds = DBC(original)
    require(sounds.fields == 30, 'Expected Wrath SoundEntries layout')
    original_count = len(sounds.rows)
    next_id = max(sounds.value(r, 0) for r in sounds.rows) + 1
    manifest_root = Path(cfg['audio'])
    manifest = json.loads((manifest_root / 'manifest.json').read_text())
    sound_reports = []
    for creature in cfg['sounds']:
        events = []
        for group in creature['groups']:
            selected = [r for r in manifest if re.search(group['pattern'], r['name']) and (not group.get('bank') or group['bank'] in r['source'])]
            require(0 < len(selected) <= 10, 'Expected 1-10 sound samples for ' + group['name'])
            row = bytearray(sounds.stride)
            sounds.set(row, 0, next_id); sounds.set(row, 1, 10)
            sounds.set(row, 2, sounds.add_string('D3_' + creature['name'] + '_' + group['name']))
            directory = 'Sound/Creature/Custom/D3/' + creature['name']
            sounds.set(row, 23, sounds.add_string(directory.replace('/', '\\')))
            struct.pack_into('<f', row, 24 * 4, 1.0)
            struct.pack_into('<f', row, 26 * 4, 5.0)
            struct.pack_into('<f', row, 27 * 4, 40.0)
            files = []
            for i, sample in enumerate(selected):
                source = manifest_root / sample['wav']
                with wave.open(str(source), 'rb') as wav:
                    require(wav.getsampwidth() == 2 and wav.getcomptype() == 'NONE' and wav.getnchannels() == 1, 'Expected mono PCM16 creature sound')
                name = group['name'] + f'_{i + 1:02}.wav'
                target = stage / directory / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
                sounds.set(row, 3 + i, sounds.add_string(name)); sounds.set(row, 13 + i, 1)
                files.append(dict(file=directory + '/' + name, source_name=sample['name']))
            sounds.rows.append(row)
            events.append(dict(sound_id=next_id, times=group['times']))
            sound_reports.append(dict(creature=creature['name'], group=group['name'], sound_id=next_id, files=files, times=group['times']))
            next_id += 1
        model_path = stage / member(creature['model'])
        append_events(model_path, events)
        decoded = read(model_path)
        validate_events(model_path.read_bytes(), decoded['sequences'])
    require(sounds.rows[:original_count] == DBC(original).rows, 'Existing SoundEntries changed')
    (stage / sound_path).write_bytes(sounds.encode())
    overlay['base_sha256'][sound_path] = hashlib.sha256(original).hexdigest()
    overlay['base_archives'][sound_path] = archive
    reports = {}
    for model in stage.rglob('*.m2'):
        reports[str(model.relative_to(stage))] = validate(model)
        decoded = read(model)
        require((stage / decoded['texture']).is_file(), 'Missing model texture')
        for event in validate_events(model.read_bytes(), decoded['sequences']):
            sounds.find(event['sound_id'])
    result = dict(display_overlay=overlay, models=reports, sounds=sound_reports, merged_patches=base_patches, in_game_verified=False)
    result['package'] = pack(stage, out / cfg['patch_name'], editor)
    (out / 'build-config.json').write_text(json.dumps(cfg, indent=2))
    (out / 'validation.json').write_text(json.dumps(result, indent=2))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('config'); parser.add_argument('--out', required=True); parser.add_argument('--editor', required=True)
    args = parser.parse_args()
    result = build(args.config, args.out, args.editor)
    print(json.dumps(dict(mpq=result['package']['mpq'], verified_files=result['package']['archive_members_verified'])))
