"""Read Diablo III APP v260, ANI and TEX v47 assets without modifying inputs.

APP/ANI field layout reference: Taylor Mouse's April 2014 Max importers.
TEX layout reference: Fernando Sahmkow's WhiteoutLib (see CREDITS.md).
Unsupported versions and invalid offsets fail explicitly.
"""
from pathlib import Path
import struct as S
import bisect
import io


def require(condition, message):
    if not condition:
        raise ValueError(message)


class Reader:
    def __init__(self, path):
        self.path = Path(path)
        self.data = self.path.read_bytes()
        require(self.data[:4] == bytes.fromhex('efbeadde'), 'Expected D3 SNO magic: ' + str(path))
        self.version = self.unpack('I', 4)[0]

    def unpack(self, fmt, offset):
        require(0 <= offset <= len(self.data) - S.calcsize('<' + fmt), 'Out-of-bounds SNO read')
        return S.unpack_from('<' + fmt, self.data, offset)

    def string(self, offset, length=64):
        require(offset + length <= len(self.data), 'Out-of-bounds string')
        return self.data[offset:offset + length].split(b'\0')[0].decode('utf-8')

    def span(self, offset, size):
        offset += 16
        require(offset >= 16 and offset + size <= len(self.data), 'Out-of-bounds SNO span')
        return offset


def appearance(path):
    r = Reader(path)
    require(r.version == 260, 'Only APP v260 is supported')
    count, offset, size = r.unpack('3I', 36)
    require((count > 0 and size % count == 0) or (count == 0 and size == 0), 'Invalid APP bone table')
    stride = size // count if count else 0
    require(not count or stride >= 204, 'Truncated bone record')
    offset = r.span(offset, size)
    bones = []
    for i in range(count):
        p = offset + i * stride
        parent = r.unpack('i', p + 64)[0]
        require(-1 <= parent < i, 'Expected parent-before-child APP bones')
        bones.append(dict(name=r.string(p), parent=parent,
                          transforms=[r.unpack('8f', p + 108 + k * 32) for k in range(3)]))
    count, offset, size = r.unpack('3I', 168)
    require(count and size % count == 0, 'Invalid APP subsets')
    stride = size // count
    offset = r.span(offset, size)
    meshes = []
    for i in range(count):
        p = offset + i * stride
        fields = r.unpack('13I', p)
        nv, vo, vs = fields[1:4]
        wo, ws = fields[6:8]
        ni, io_, ins = fields[10:13]
        require(vs == nv * 44 and ws == (nv * 24 if bones else 0) and ins == ni * 2 and ni % 3 == 0,
                'Unsupported vertex/weight/index layout')
        vo, wo, io_ = r.span(vo, vs), r.span(wo, ws), r.span(io_, ins)
        vertices = []
        for j in range(nv):
            vp = vo + j * 44
            uv = r.unpack('2H', vp + 24)
            pairs = r.unpack('IfIfIf', wo + j * 24) if bones else ()
            weights = [(pairs[k], pairs[k + 1]) for k in range(0, len(pairs), 2) if pairs[k + 1] > 0]
            require((not bones or weights) and all(b < len(bones) and 0 < w <= 1.001 for b, w in weights), 'Invalid skin weights')
            vertices.append(dict(position=r.unpack('3f', vp),
                                 normal=[(x - 127) / 127 for x in r.unpack('3B', vp + 12)],
                                 uv=[(uv[0] - 32767) / 512, (uv[1] - 32767) / 512], weights=weights))
        indices = r.unpack(str(ni) + 'H', io_)
        require(max(indices, default=0) < nv, 'Invalid triangle index')
        meshes.append(dict(name=r.string(p + 92, 128), source_name=r.string(p + 220, 128),
                           vertices=vertices, triangles=[indices[k:k + 3] for k in range(0, ni, 3)]))
    return dict(bones=bones, meshes=meshes)


def animation(path):
    r = Reader(path)
    # The locally supplied Max importer uses this layout for the shipped ANI files.
    require(r.version == 118, 'Only ANI v118 is supported, got ' + str(r.version))
    count, offset, size = r.unpack('3I', 192)
    require(size == count * 64 and 0 < count <= 256, 'Unsupported ANI bone table')
    offset = r.span(offset, size)
    names = [r.string(offset + i * 64) for i in range(count)]
    frames = r.unpack('I', 216)[0]
    require(0 < frames <= 100000, 'Invalid ANI duration')
    tracks = {name: {} for name in names}
    for field, header, fmt in [('translation', 220, 'I3f'), ('rotation', 240, 'I4h'), ('scale', 256, 'If')]:
        offset, size = r.unpack('2I', header)
        require(size == count * 24, 'Unsupported ANI track table')
        offset = r.span(offset, size)
        for i, name in enumerate(names):
            n, off, sz = r.unpack('3I', offset + i * 24)
            require(sz == n * S.calcsize('<' + fmt), 'Invalid keyframe stride')
            off = r.span(off, sz)
            keys = [r.unpack(fmt, off + j * S.calcsize('<' + fmt)) for j in range(n)]
            require(all(0 <= k[0] < frames for k in keys), 'Keyframe outside animation')
            require(all(a[0] < b[0] for a, b in zip(keys, keys[1:])), 'Unsorted keyframes')
            if field == 'rotation':
                keys = [(k[0], *(x / 32767 for x in k[1:])) for k in keys]
            tracks[name][field] = keys
    return dict(name=r.string(76), frames=frames, tracks=tracks)


def texture(path):
    """Decode the largest BC1/BC2/BC3 mip to a Pillow image."""
    from PIL import Image
    r = Reader(path)
    require(r.version == 47, 'Only TEX v47 is supported')
    fmt, width, height, depth = r.unpack('4I', 32)
    require(fmt in (9, 10, 11, 12) and depth == 1 and 0 < width <= 8192 and 0 < height <= 8192,
            'Unsupported TEX format/dimensions')
    offset, size = r.unpack('2I', 56)
    blocks = ((width + 3) // 4) * ((height + 3) // 4)
    block_size = 8 if fmt in (9, 10) else 16
    require(size == blocks * block_size and offset + 16 + size <= len(r.data), 'Invalid TEX mip payload')
    payload = r.data[offset + 16:offset + 16 + size]
    # TEX stores each BC field in a separate contiguous stream.
    widths = [4, 4] if block_size == 8 else [8, 4, 4] if fmt == 11 else [2, 6, 4, 4]
    output = bytearray(size)
    source_base = dest_base = 0
    for width_ in widths:
        for i in range(blocks):
            output[i * block_size + dest_base:i * block_size + dest_base + width_] = payload[source_base + i * width_:source_base + (i + 1) * width_]
        source_base += blocks * width_
        dest_base += width_
    fourcc = b'DXT1' if block_size == 8 else b'DXT3' if fmt == 11 else b'DXT5'
    header = S.pack('<7I', 124, 0x81007, height, width, size, 0, 1) + bytes(44)
    header += S.pack('<II4s5I', 32, 4, fourcc, 0, 0, 0, 0, 0) + S.pack('<5I', 0x1000, 0, 0, 0, 0)
    return Image.open(io.BytesIO(b'DDS ' + header + output)).convert('RGBA')
