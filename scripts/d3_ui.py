"""Strict reader for extracted Diablo III UI v471 and TEX v47 atlas records.

The disk layout is verified against the local retail assets. WhiteoutLib's
UIControlData/UIStyle type descriptions informed the investigation; these disk
records inline fixed strings instead of using the current runtime layout.
Unknown property IDs and script names are retained, never executed.
"""
import hashlib
import math
import struct
from pathlib import Path


class Binary:
    def __init__(self, data):
        self.data = data

    def unpack(self, fmt, offset):
        size = struct.calcsize('<' + fmt)
        if offset < 0 or offset + size > len(self.data):
            raise ValueError('Truncated UI/atlas record')
        return struct.unpack_from('<' + fmt, self.data, offset)

    def string(self, offset, size):
        self.unpack(str(size) + 's', offset)
        raw = self.data[offset:offset + size]
        if b'\0' not in raw:
            raise ValueError('Unterminated fixed string')
        return raw.split(b'\0', 1)[0].decode('utf-8')

    def table(self, offset, stride):
        count, start, size = self.unpack('3I', offset)
        if count > 100000 or size != count * stride:
            raise ValueError('Unsupported table stride or count')
        start += 16
        if count and (start < 200 or start + size > len(self.data)):
            raise ValueError('Table outside input file')
        return range(start, start + size, stride)


def style(reader, offset):
    values = {}
    for name, delta, stride, fmt in [('strings', 520, 264, None),
                                    ('integers', 544, 16, 'i'),
                                    ('floats', 568, 16, 'f')]:
        items = {}
        for p in reader.table(offset + delta, stride):
            key = str(reader.unpack('Q', p)[0])
            value = reader.string(p + 8, 256) if fmt is None else reader.unpack(fmt, p + 8)[0]
            if key in items or isinstance(value, float) and not math.isfinite(value):
                raise ValueError('Duplicate or nonfinite style property')
            items[key] = value
        values[name] = items
    return dict(name=reader.string(offset + 8, 512), **values)


def read_ui(path):
    path = Path(path)
    data = path.read_bytes()
    r = Binary(data)
    if r.unpack('II', 0) != (0xDEADBEEF, 471):
        raise ValueError('Only D3 UI v471 is supported')
    controls = []
    for p in r.table(32, 1856):
        name = r.string(p + 16, 512)
        parent = r.string(p + 536, 512)
        controls.append(dict(index=r.unpack('I', p)[0], name=name, parent=parent,
                             path=parent + '.' + name if parent else name,
                             control_type=r.unpack('I', p + 1048)[0],
                             style=style(r, p + 1056),
                             unconverted_tail_hex=data[p + 1712:p + 1856].hex()))
    paths = {c['path'] for c in controls}
    if len(paths) != len(controls):
        raise ValueError('Duplicate control path')
    for c in controls:
        if c['parent'] and c['parent'] not in paths:
            raise ValueError('Missing parent: ' + c['parent'])
    return dict(format='d3-ui-intermediate-v1', name=path.stem, version=471,
                source=str(path.resolve()), sha256=hashlib.sha256(data).hexdigest(),
                controls=controls, styles=[style(r, p) for p in r.table(56, 656)],
                limitations=['Script callbacks are names only; no D3 code is executed.',
                             'Animation and child-style behavior require manual adaptation.'])


def atlas_entries(path):
    """Read only the TEX header and named rectangle table, not its pixel payload."""
    path = Path(path)
    with path.open('rb') as f:
        header = f.read(648)
        r = Binary(header)
        if r.unpack('II', 0) != (0xDEADBEEF, 47):
            raise ValueError('Only D3 TEX v47 is supported')
        width, height = r.unpack('2I', 36)
        count, offset, size = r.unpack('3I', 536)
        if size != count * 80 or count > 100000 or not 0 < width <= 8192 or not 0 < height <= 8192:
            raise ValueError('Invalid TEX atlas table')
        if not count:
            return []
        if offset + 16 < 648 or offset + 16 + size > path.stat().st_size:
            raise ValueError('Atlas table outside file')
        f.seek(offset + 16)
        r = Binary(f.read(size))
    entries = []
    for i in range(count):
        name = r.string(i * 80, 64)
        u0, v0, u1, v1 = r.unpack('4f', i * 80 + 64)
        if not (0 <= u0 < u1 <= 1 and 0 <= v0 < v1 <= 1):
            raise ValueError('Invalid atlas rectangle')
        entries.append(dict(name=name, source=str(path.resolve()),
                            uv=[u0, v0, u1, v1],
                            pixels=[round(u0 * width), round(v0 * height), round(u1 * width), round(v1 * height)]))
    return entries
