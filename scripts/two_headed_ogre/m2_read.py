import struct as S
from pathlib import Path

SEQ, BONE, VERT, ATT = 64, 88, 48, 40


def decode_quaternion(values):
    return [(v + 32768) / 32767 if v < 0 else (v - 32767) / 32767 for v in values]


class M2:
    def __init__(self, path):
        self.path = Path(path)
        self.data = self.path.read_bytes()
        if self.data[:4] == b'MD21':
            self.data = self.data[8:8 + S.unpack_from('<I', self.data, 4)[0]]
        magic, self.version = S.unpack_from('<4sI', self.data, 0)
        if magic != b'MD20' or self.version not in (264, 272):
            raise ValueError(f'Unsupported M2 {magic} {self.version}')
        self.sequences = self._sequences()
        self.anim_files = {}

    def u(self, fmt, offset, data=None):
        return S.unpack_from('<' + fmt, self.data if data is None else data, offset)

    def array(self, header):
        return self.u('II', header)

    def _sequences(self):
        count, offset = self.array(28)
        rows = []
        for i in range(count):
            o = offset + i * SEQ
            sid, var, duration = self.u('HHI', o)
            speed, flags = self.u('fI', o + 8)
            minimum, maximum, radius = self.u('3f', o + 32), self.u('3f', o + 44), self.u('f', o + 56)[0]
            alias_next = self.u('hH', o + 60)[1]
            rows.append(dict(index=i, id=sid, variation=var, duration=duration, movespeed=speed, flags=flags,
                             minimum=list(minimum), maximum=list(maximum), radius=radius, alias=alias_next))
        return rows

    def data_index(self, seq_index):
        seen = set()
        while self.sequences[seq_index]['flags'] & 0x40 and seq_index not in seen:
            seen.add(seq_index)
            seq_index = self.sequences[seq_index]['alias']
        return seq_index

    def source(self, seq_index):
        seq = self.sequences[seq_index]
        if seq['flags'] & 0x20:
            return self.data
        if seq_index not in self.anim_files:
            name = f"{self.path.stem}{seq['id']:04d}-{seq['variation']:02d}.anim"
            anim = self.path.with_name(name)
            self.anim_files[seq_index] = anim.read_bytes() if anim.exists() else None
        return self.anim_files[seq_index]

    def track(self, header, fmt, seq_index):
        interp, global_seq, nt, ot, nv, ov = self.u('HhIIII', header)
        if global_seq >= 0:
            if nt == 0:
                return interp, [], []
            times_count, times_offset = self.u('II', ot)
            values_count, values_offset = self.u('II', ov)
            src = self.data
        else:
            data_seq = self.data_index(seq_index)
            if data_seq >= nt:
                return interp, [], []
            times_count, times_offset = self.u('II', ot + 8 * data_seq)
            values_count, values_offset = self.u('II', ov + 8 * data_seq)
            src = self.source(data_seq)
            if src is None or times_count == 0:
                return interp, [], []
        size = S.calcsize('<' + fmt)
        times = list(S.unpack_from(f'<{times_count}I', src, times_offset))
        values = [S.unpack_from('<' + fmt, src, values_offset + i * size) for i in range(values_count)]
        return interp, times, values

    def bones(self):
        count, offset = self.array(44)
        rows = []
        for i in range(count):
            o = offset + i * BONE
            key, flags, parent, submesh = self.u('iIhH', o)
            rows.append(dict(index=i, key=key, flags=flags, parent=parent, pivot=list(self.u('3f', o + 76)),
                             tracks=dict(translation=o + 16, rotation=o + 36, scale=o + 56)))
        return rows

    def vertices(self):
        count, offset = self.array(60)
        rows = []
        for i in range(count):
            o = offset + i * VERT
            p = self.u('3f', o)
            w = self.u('4B', o + 12)
            b = self.u('4B', o + 16)
            n = self.u('3f', o + 20)
            uv = self.u('2f', o + 32)
            rows.append(dict(position=list(p), weights=list(w), bones=list(b), normal=list(n), uv=list(uv)))
        return rows

    def attachments(self):
        count, offset = self.array(240)
        return [dict(id=self.u('I', offset + i * ATT)[0], bone=self.u('H', offset + i * ATT + 4)[0],
                     position=list(self.u('3f', offset + i * ATT + 8))) for i in range(count)]

    def attachment_lookup(self):
        count, offset = self.array(248)
        return list(self.u(f'{count}h', offset)) if count else []

    def key_bone_lookup(self):
        count, offset = self.array(52)
        return list(self.u(f'{count}h', offset)) if count else []

    def textures(self):
        count, offset = self.array(80)
        rows = []
        for i in range(count):
            kind, flags, n, o = self.u('IIII', offset + i * 16)
            rows.append(dict(type=kind, flags=flags, name=self.data[o:o + n].rstrip(b'\0').decode('latin1')))
        return rows

    def event_times(self, header, seq_index):
        interp, global_seq, nt, ot = self.u('HhII', header)
        if global_seq >= 0:
            if nt == 0:
                return []
            count, offset = self.u('II', ot)
            return list(S.unpack_from(f'<{count}I', self.data, offset))
        data_seq = self.data_index(seq_index)
        if data_seq >= nt:
            return []
        count, offset = self.u('II', ot + 8 * data_seq)
        src = self.source(data_seq)
        if src is None or count == 0:
            return []
        return list(S.unpack_from(f'<{count}I', src, offset))

    def events(self):
        count, offset = self.array(256)
        result = []
        for i in range(count):
            o = offset + i * 36
            ident, data, bone, x, y, z = self.u('4sII3f', o)
            interp, global_seq = self.u('Hh', o + 24)
            times = [self.event_times(o + 24, seq) for seq in range(len(self.sequences))]
            result.append(dict(identifier=ident, data=data, bone=bone, position=[x, y, z], global_seq=global_seq,
                               times=times))
        return result

    def colors(self):
        count, offset = self.array(72)
        result = []
        for i in range(count):
            tracks = {}
            for field, fmt, delta, default in (('color', '3f', 0, (1.0, 1.0, 1.0)), ('alpha', 'h', 20, (32767,))):
                header = offset + i * 40 + delta
                interp = self.u('H', header)[0]
                keys = []
                for seq in range(len(self.sequences)):
                    _, times, values = self.track(header, fmt, seq)
                    keys.append((times, values) if values else ([0], [default]))
                tracks[field] = dict(interp=interp, keys=keys)
            result.append(tracks)
        return result

    def lookup(self, header):
        count, offset = self.array(header)
        return list(self.u(f'{count}h', offset)) if count else []

    def materials(self):
        count, offset = self.array(112)
        return [self.u('HH', offset + i * 4) for i in range(count)]


class Skin:
    def __init__(self, path):
        self.data = Path(path).read_bytes()
        u = lambda f, o: S.unpack_from('<' + f, self.data, o)
        magic, ni, oi, nt, ot, npr, opr, ns, os_, nb, ob, self.bone_max = u('4sIIIIIIIIIII', 0)
        self.indices = list(u(f'{ni}H', oi))
        self.triangles = list(u(f'{nt}H', ot))
        self.submeshes = []
        for i in range(ns):
            o = os_ + i * 48
            sid, level, vs, vc, is_, ic, bc, bci, binf, cbi = u('10H', o)
            self.submeshes.append(dict(id=sid, vertex_start=vs + (level << 16), vertex_count=vc,
                                       index_start=is_ + (level << 16), index_count=ic))
        self.batches = []
        for i in range(nb):
            o = ob + i * 24
            flags, prio, shader, section, geoset, color, material, layer, tcount, tcombo = u('BbHHHhHHHH', o)
            self.batches.append(dict(section=section, material=material, texture_count=tcount, texture_combo=tcombo,
                                     layer=layer, shader=shader, flags=flags, color=color))
