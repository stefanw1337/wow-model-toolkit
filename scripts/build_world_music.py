"""Build one world-and-tavern MPQ from a reviewable, explicit music mapping."""
import argparse
import hashlib
import json
import subprocess
import shutil
import wave
from collections import Counter
from pathlib import Path
from assets import DBC, digest, member, read_client_files, require
from mpq_music import pack_music


def build(config, output, encoder, audio_cache=None):
    cfg = json.loads(Path(config).read_text())
    out = Path(output).resolve()
    require(not out.exists(), 'Use a fresh output directory')
    out.mkdir(parents=True); audio = out / 'audio'; audio.mkdir()
    compiled = {}
    for theme, tracks in cfg['themes'].items():
        compiled[theme] = []
        for track in tracks:
            sources = [Path(p) for p in track.get('sources', [track.get('source')])]
            key = hashlib.sha256(''.join(digest(p) for p in sources).encode()).hexdigest()
            encoded = audio / (key + '.mp3')
            cached = Path(audio_cache) / encoded.name if audio_cache else None
            if not encoded.exists() and cached and cached.is_file():
                shutil.copyfile(cached, encoded)
            if not encoded.exists():
                if track.get('encoded'):
                    encoded.write_bytes(sources[0].read_bytes())
                else:
                    source = sources[0]
                    if len(sources) > 1:
                        source = audio / (key + '.wav')
                        with wave.open(str(source), 'wb') as writer:
                            fmt = None
                            for file in sources:
                                with wave.open(str(file), 'rb') as reader:
                                    current = (reader.getnchannels(), reader.getsampwidth(), reader.getframerate())
                                    require(fmt is None or fmt == current, 'WAV concatenation format mismatch')
                                    if fmt is None:
                                        fmt = current
                                        writer.setnchannels(fmt[0]); writer.setsampwidth(fmt[1]); writer.setframerate(fmt[2])
                                    writer.writeframes(reader.readframes(reader.getnframes()))
                    subprocess.run([str(encoder), '-nostdin', '-v', 'error', '-i', str(source), '-map', '0:a:0',
                        '-vn', '-map_metadata', '-1', '-c:a', 'libmp3lame', '-ar', '44100', '-ac', '2', '-b:a', '192k', str(encoded)], check=True)
            subprocess.run([str(encoder), '-nostdin', '-v', 'error', '-i', str(encoded), '-f', 'null', '-'], check=True)
            compiled[theme].append((track['name'], encoded))
        print('Encoded: ' + theme, flush=True)
    counts = Counter(); files = {}; mappings = []
    for row in sorted(cfg['assignments'], key=lambda r: r['path'].lower()):
        path = member(row['path']); theme = row['theme']
        require(path.lower() not in {p.lower() for p in files}, 'Conflicting music target: ' + path)
        if row.get('track_name'):
            selected = [t for t in compiled[theme] if t[0] == row['track_name']]
            require(len(selected) == 1, 'Missing or ambiguous assigned track: ' + row['track_name'])
            name, encoded = selected[0]
        else:
            name, encoded = compiled[theme][counts[theme] % len(compiled[theme])]
        counts[theme] += 1
        files[path] = encoded
        mappings.append(dict(**row, track=name))
    names = ['DBFilesClient/SoundEntries.dbc', 'DBFilesClient/ZoneMusic.dbc', 'DBFilesClient/ZoneIntroMusicTable.dbc', 'DBFilesClient/AreaTable.dbc']
    data = read_client_files(cfg['client'], cfg['locale'], names)
    sounds, zones, intros, areas = [DBC(data[n][0]) for n in names]
    by_path = {r['path'].lower(): r for r in mappings}
    sound_map = {}; uncovered = []
    referenced = {zones.value(r, k) for r in zones.rows for k in (6, 7)} | {intros.value(r, 2) for r in intros.rows}
    for row in sounds.rows:
        sid = sounds.value(row, 0)
        paths = []
        for field in range(3, 13):
            if sounds.value(row, field):
                path = (sounds.string(row, 23).rstrip('/\\') + '/' + sounds.string(row, field)).replace('\\', '/')
                if not Path(path).suffix: path += '.mp3'
                if path.lower() in by_path:
                    paths.append(by_path[path.lower()])
                elif sid in referenced:
                    uncovered.append(dict(id=sid, name=sounds.string(row, 2), path=path))
        if paths: sound_map[sid] = paths
    # Explicitly retained event/placeholder audio is not regular world music.
    unexpected = [r for r in uncovered if not any(t in (r['name'] + ' ' + r['path']).lower()
                  for t in ('brewfest', 'darkmoon', 'dmf_', 'disco', 'undead dance', 'midsummer', 'tempmono', 'do not change'))]
    require(not unexpected, 'Unmapped ZoneMusic/ZoneIntroMusicTable references: ' + repr(unexpected))
    zone_rows = []
    for row in zones.rows:
        ids = [zones.value(row, k) for k in (6, 7)]
        selected = [m for sid in ids for m in sound_map.get(sid, [])]
        zone_rows.append(dict(id=zones.value(row, 0), name=zones.string(row, 1),
            sound_ids=ids, themes=sorted({m['theme'] for m in selected}), tracks=sorted({m['track'] for m in selected})))
    intro_rows = []
    for row in intros.rows:
        sid = intros.value(row, 2); selected = sound_map.get(sid, [])
        intro_rows.append(dict(id=intros.value(row, 0), name=intros.string(row, 1), sound_id=sid,
            themes=sorted({m['theme'] for m in selected}), tracks=sorted({m['track'] for m in selected})))
    zone_index = {r['id']: r for r in zone_rows}; intro_index = {r['id']: r for r in intro_rows}
    area_rows = []
    for row in areas.rows:
        zone = zone_index.get(areas.value(row, 8), {}); intro = intro_index.get(areas.value(row, 9), {})
        area_rows.append(dict(id=areas.value(row, 0), name=areas.string(row, 11), parent=areas.value(row, 2),
            themes=sorted(set(zone.get('themes', []) + intro.get('themes', []))),
            zone_music_id=areas.value(row, 8), intro_id=areas.value(row, 9)))
    package = pack_music(files, out / cfg['patch_name'])
    report = dict(package=package, mappings=mappings, zone_music=zone_rows, intro_music=intro_rows,
        areas=area_rows, intentionally_unchanged=uncovered, repaired_missing_paths=cfg['missing_original_paths'],
        dbc_files_included=False, in_game_verified=False)
    (out / 'validation.json').write_text(json.dumps(report, indent=2))
    cfg['install_in_data_root'] = True
    cfg['install_name'] = 'patch-M.MPQ'
    (out / 'build-config.json').write_text(json.dumps(cfg, indent=2))
    lines = ['# Complete world and tavern music mapping', '',
        'Classic, The Burning Crusade and Wrath. Existing playback rules remain unchanged.',
        'Taverns use Tavern Jingle by stefanw1337. Capital cities use Tristram. No DBC tables are replaced.',
        'Paths shared by multiple locations play the same replacement. Areas without a direct music assignment may inherit parent or WMO music.',
        'Existing festival/event exceptions and invalid placeholders are listed in validation.json. This is not an in-game playback audit.', '',
        '## Themes', '', '| Theme | D3 / user tracks | Replaced paths |', '| --- | --- | --- |']
    for theme, tracks in compiled.items():
        lines.append('| ' + theme + ' | ' + ', '.join(t[0] for t in tracks) + ' | ' + str(counts[theme]) + ' |')
    lines += ['', '## Areas with a direct assignment', '', '| Area | Theme |', '| --- | --- |']
    for area in sorted(area_rows, key=lambda r: r['name']):
        if area['themes']: lines.append('| ' + area['name'] + ' | ' + ', '.join(area['themes']) + ' |')
    lines += ['', '## ZoneMusic entries (includes dungeon and raid interiors)', '', '| Entry | Theme |', '| --- | --- |']
    for row in zone_rows:
        lines.append('| ' + row['name'] + ' | ' + ', '.join(row['themes']) + ' |')
    lines += ['', '## Exact replacements', ''] + ['- ' + r['path'] + ' → ' + r['track'] for r in mappings]
    (out / 'MUSIC-MAPPING.md').write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps(dict(mpq=package['mpq'], paths=len(files), unique_tracks=package['unique_audio_blocks'])))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('config'); parser.add_argument('--out', required=True); parser.add_argument('--encoder', required=True)
    parser.add_argument('--audio-cache')
    args = parser.parse_args()
    build(args.config, args.out, Path(args.encoder).resolve(), args.audio_cache)
