"""Package a user-supplied song at the client's existing tavern music paths."""
import argparse
import json
import subprocess
from pathlib import Path
from assets import DBC, digest, member, read_client_files, require
from mpq_music import pack_music


def build(source, output, client, encoder, locale='enGB'):
    source = Path(source).resolve()
    out = Path(output).resolve()
    require(source.is_file(), 'Source song not found')
    require(not out.exists(), 'Use a fresh output directory')
    out.mkdir(parents=True)
    encoded = out / 'tavern-jingle-client.mp3'
    # Strip attached artwork and metadata, retaining only a compatible audio stream.
    subprocess.run([str(encoder), '-nostdin', '-v', 'error', '-i', str(source),
                    '-map', '0:a:0', '-map_metadata', '-1', '-vn', '-c:a', 'libmp3lame',
                    '-ar', '44100', '-ac', '2', '-b:a', '192k', str(encoded)], check=True)
    subprocess.run([str(encoder), '-nostdin', '-v', 'error', '-i', str(encoded), '-f', 'null', '-'], check=True)
    name = 'DBFilesClient/SoundEntries.dbc'
    data, archive = read_client_files(client, locale, [name])[name]
    sounds = DBC(data)
    paths = {}
    groups = []
    for row in sounds.rows:
        if sounds.value(row, 1) != 28 or not sounds.string(row, 2).lower().startswith('zone-tavern'):
            continue
        files = []
        for field in range(3, 13):
            if sounds.value(row, field):
                path = member(sounds.string(row, 23).rstrip('/\\') + '/' + sounds.string(row, field))
                require(path.lower().endswith('.mp3'), 'Unexpected tavern file format')
                paths.setdefault(path.lower(), path)
                files.append(path)
        groups.append(dict(id=sounds.value(row, 0), name=sounds.string(row, 2), files=files))
    require(paths, 'No tavern music entries found')
    read_client_files(client, locale, list(paths.values()))
    package = pack_music({path: encoded for path in paths.values()}, out / 'patch-TavernMusic.MPQ')
    report = dict(package=package, groups=groups, source=str(source), source_sha256=digest(source),
                  converted_audio_sha256=digest(encoded), dbc_files_included=False, in_game_verified=False)
    (out / 'validation.json').write_text(json.dumps(report, indent=2))
    (out / 'build-config.json').write_text(json.dumps(dict(client=client, locale=locale,
        patch_name='patch-TavernMusic.MPQ', install_name='patch-T.MPQ', install_in_data_root=True, source=str(source)), indent=2))
    lines = ['# Tavern music replacement', '', 'Source: ' + str(source), '',
             'One user-supplied song replaces the following existing tavern music files.',
             'No DBC edits. Playback timing and pauses remain controlled by WoW.',
             'Locations and events sharing these files also use the replacement.',
             'D3 world music must keep these paths excluded.', '']
    for group in groups:
        lines += ['## ' + group['name'], ''] + ['- ' + p for p in group['files']] + ['']
    (out / 'TAVERN-MAPPING.md').write_text('\n'.join(lines))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source'); parser.add_argument('--out', required=True)
    parser.add_argument('--client', required=True); parser.add_argument('--encoder', required=True)
    parser.add_argument('--locale', default='enGB')
    args = parser.parse_args()
    result = build(args.source, args.out, args.client, Path(args.encoder).resolve(), args.locale)
    print(json.dumps(dict(mpq=result['package']['mpq'], verified_files=result['package']['archive_members_verified'])))
