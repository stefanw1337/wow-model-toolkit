"""Build an independent music MPQ from explicit SoundEntries IDs and decoded WAVs.

Only existing MP3 paths are replaced. No DBC files are included, allowing this
package to coexist with creature and sound-event overlays.
"""
import argparse
import hashlib
import json
import shutil
import subprocess
import wave
from pathlib import Path
from assets import DBC, member, pack, read_client_files, require


def build(config, output, encoder, editor):
    cfg = json.loads(Path(config).read_text(encoding='utf-8-sig'))
    out = Path(output).resolve()
    require(not out.exists(), 'Use a fresh output directory')
    out.mkdir(parents=True)
    stage = out / 'archive'
    stage.mkdir()
    cache = out / 'encoded'
    cache.mkdir()
    names = ['DBFilesClient/SoundEntries.dbc', 'DBFilesClient/ZoneMusic.dbc', 'DBFilesClient/AreaTable.dbc']
    source = read_client_files(cfg['client'], cfg.get('locale', 'enGB'), names)
    sounds, zones, areas = [DBC(source[n][0]) for n in names]
    assignments = {}
    report_groups = []
    for group in cfg['groups']:
        tracks = []
        for ti, track in enumerate(group['tracks']):
            inputs = [Path(p).resolve() for p in track['sources']]
            key = hashlib.sha256(b''.join(p.read_bytes() for p in inputs)).hexdigest()
            encoded = cache / (key + '.mp3')
            if not encoded.exists():
                combined = cache / (key + '.wav')
                with wave.open(str(combined), 'wb') as writer:
                    fmt = None
                    for path in inputs:
                        with wave.open(str(path), 'rb') as reader:
                            current = (reader.getnchannels(), reader.getsampwidth(), reader.getframerate())
                            require(current[1] == 2 and reader.getcomptype() == 'NONE', 'Expected PCM16 source')
                            require(fmt is None or current == fmt, 'Incompatible concatenated WAV formats')
                            if fmt is None:
                                fmt = current
                                writer.setnchannels(fmt[0]); writer.setsampwidth(fmt[1]); writer.setframerate(fmt[2])
                            writer.writeframes(reader.readframes(reader.getnframes()))
                subprocess.run([str(encoder), '-nostdin', '-v', 'error', '-i', str(combined), '-codec:a', 'libmp3lame', '-b:a', '192k', '-ar', '44100', str(encoded)], check=True)
                # Decode the complete result to catch truncated or invalid MP3 data.
                subprocess.run([str(encoder), '-nostdin', '-v', 'error', '-i', str(encoded), '-f', 'null', '-'], check=True)
            tracks.append((track['name'], encoded))
        paths = set()
        for sound_id in group['sound_ids']:
            row = sounds.find(sound_id)
            require(sounds.value(row, 1) == 28, 'Only music SoundEntries may be replaced')
            for field in range(3, 13):
                if sounds.value(row, field):
                    path = member(sounds.string(row, 23).rstrip('/\\') + '/' + sounds.string(row, field))
                    require(path.lower().endswith('.mp3'), 'Expected existing MP3 path')
                    if path.lower() not in {p.lower() for p in paths}:
                        paths.add(path)
        for i, path in enumerate(sorted(paths, key=str.lower)):
            name, encoded = tracks[i % len(tracks)]
            require(path.lower() not in assignments, 'Music path occurs in multiple groups: ' + path)
            assignments[path.lower()] = dict(path=path, track=name)
            target = stage / path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(encoded, target)
        affected_sounds = {sounds.value(r, 0) for r in sounds.rows if any(
            sounds.value(r, k) and (sounds.string(r, 23).rstrip('/\\') + '/' + sounds.string(r, k)).replace('\\', '/').lower() in {p.lower() for p in paths}
            for k in range(3, 13))}
        affected_zones = {zones.value(r, 0) for r in zones.rows if zones.value(r, 6) in affected_sounds or zones.value(r, 7) in affected_sounds}
        affected_areas = [dict(id=areas.value(r, 0), name=areas.string(r, 11), parent=areas.value(r, 2)) for r in areas.rows if areas.value(r, 8) in affected_zones]
        report_groups.append(dict(name=group['name'], tracks=[t[0] for t in tracks], paths=sorted(paths), area_table_matches=affected_areas))
    # Every replacement must refer to an actual file in this client.
    read_client_files(cfg['client'], cfg.get('locale', 'enGB'), [r['path'] for r in assignments.values()])
    name = cfg['patch_name']
    require(member(name) == name and '/' not in name and name.lower().endswith('.mpq'), 'Invalid MPQ name')
    result = dict(groups=report_groups, replacements=list(assignments.values()), dbc_files_included=False, in_game_verified=False)
    result['package'] = pack(stage, out / name, editor)
    (out / 'validation.json').write_text(json.dumps(result, indent=2))
    cfg['install_in_data_root'] = True
    cfg['install_name'] = 'patch-M.MPQ'
    (out / 'build-config.json').write_text(json.dumps(cfg, indent=2))
    lines = ['# D3 music mapping', '', 'Only existing music files are replaced. Shared file paths also affect other locations.', 'AreaTable matches below are confirmed client references; WMO interiors and scripted playback can also share these files.', '']
    for group in report_groups:
        lines += ['## ' + group['name'], '', 'Tracks: ' + ', '.join(group['tracks']), '', 'Confirmed AreaTable locations: ' + ', '.join(a['name'] for a in group['area_table_matches']), '']
    lines += ['## Exact file replacements', ''] + [r['path'] + ' -> ' + r['track'] for r in assignments.values()]
    (out / 'MUSIC-MAPPING.md').write_text('\n'.join(lines), encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('config'); parser.add_argument('--out', required=True)
    parser.add_argument('--encoder', required=True); parser.add_argument('--editor', required=True)
    args = parser.parse_args()
    result = build(args.config, args.out, args.encoder, args.editor)
    print(json.dumps(dict(mpq=result['package']['mpq'], verified_files=result['package']['archive_members_verified'])))
