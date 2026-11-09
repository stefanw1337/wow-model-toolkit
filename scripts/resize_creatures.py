"""Scale selected creature displays in a self-contained addon MPQ.

Only CreatureDisplayInfo scale fields change. Models, animations, sounds and
unselected display records are preserved byte-for-byte.
"""
import argparse
import json
import math
import struct
from pathlib import Path
import mpyq
from assets import DBC, digest, member, pack, require
from mpq_read import read_file


def build(source, output, factors, editor):
    source = Path(source).resolve(); out = Path(output).resolve()
    require(not out.exists(), 'Use a fresh output directory')
    require(factors and all(math.isfinite(v) and 0 < v <= 10 for v in factors.values()), 'Invalid scale factors')
    out.mkdir(parents=True); stage = out / 'archive'; stage.mkdir()
    original = {}
    with source.open('rb') as stream:
        archive = mpyq.MPQArchive(stream)
        for raw in archive.files:
            if raw.startswith(b'('): continue
            name = member(raw.decode()); data = read_file(archive, raw)
            target = stage / name; target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data); original[name] = data
    require(any(n.startswith('Creature/Custom/') for n in original), 'Expected a custom creature addon')
    name = 'DBFilesClient/CreatureDisplayInfo.dbc'
    dbc = DBC(original[name]); require(dbc.fields == 16, 'Expected Wrath CreatureDisplayInfo layout')
    before = [bytes(r) for r in dbc.rows]; changes = []
    for display, factor in factors.items():
        row = dbc.find(display); old = struct.unpack_from('<f', row, 16)[0]
        new = old * factor
        require(math.isfinite(new) and 0 < new <= 100, 'Resulting display scale out of range')
        struct.pack_into('<f', row, 16, new)
        changes.append(dict(display_id=display, previous_scale=old, factor=factor, new_scale=new))
    for old, row in zip(before, dbc.rows):
        expected = bytearray(old)
        if dbc.value(row, 0) in factors: expected[16:20] = row[16:20]
        require(expected == row, 'Unexpected display field changed')
    (stage / name).write_bytes(dbc.encode())
    for path, data in original.items():
        if path != name: require((stage / path).read_bytes() == data, 'Unexpected archive member changed')
    report = dict(source=str(source), previous_sha256=digest(source), changes=changes,
                  changed_members=[name], in_game_verified=False)
    report['package'] = pack(stage, out / source.name, editor)
    (out / 'validation.json').write_text(json.dumps(report, indent=2))
    (out / 'build-config.json').write_text(json.dumps(dict(locale='enGB', install_name=source.name,
        source=str(source), scale_factors=factors), indent=2))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source'); parser.add_argument('--out', required=True)
    parser.add_argument('--factor', action='append', required=True, help='DisplayID=multiplier')
    parser.add_argument('--editor', required=True)
    args = parser.parse_args()
    pairs = [p.split('=', 1) for p in args.factor]
    factors = {int(k): float(v) for k, v in pairs}
    require(len(factors) == len(pairs), 'Duplicate display ID')
    result = build(args.source, args.out, factors, args.editor)
    print(json.dumps(dict(changes=result['changes'], mpq=result['package']['mpq']), indent=2))
