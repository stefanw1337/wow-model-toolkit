"""Sample Heroes of the Storm .m3a sequences as model-space bone matrices."""
import sys
from pathlib import Path
import numpy as np

M3ADDON = str(Path(__file__).resolve().parents[2] / 'tools' / 'm3addon')
ANIMS = None


def _m3():
    if M3ADDON not in sys.path:
        sys.path.insert(0, M3ADDON)
    import m3
    return m3


def quat_matrix(x, y, z, w):
    n = np.sqrt(x * x + y * y + z * z + w * w)
    x, y, z, w = x / n, y / n, z / n, w / n
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def matrix_of(m):
    return np.array([[getattr(getattr(m.matrix, col), row) for col in 'xyzw'] for row in 'xyzw'])


class Anims:
    def __init__(self, path=None):
        m3 = _m3()
        self.model = m3.loadModel(path or ANIMS, checkExpectedValue=False)
        self.names = [b.name for b in self.model.bones]
        self.parents = [b.parent for b in self.model.bones]
        self.inverse_bind = [matrix_of(m) for m in self.model.absoluteInverseBoneRestPositions]
        self.sequences = {s.name: i for i, s in enumerate(self.model.sequences)}

    def duration(self, name):
        s = self.model.sequences[self.sequences[name]]
        return s.animEndInMS - s.animStartInMS

    def keys(self, name):
        model = self.model
        group = model.sequenceTransformationGroups[self.sequences[name]]
        found = {}
        for index in group.stcIndices:
            stc = model.sequenceTransformationCollections[index]
            lists = [stc.sdev, stc.sd2v, stc.sd3v, stc.sd4q, stc.sdcc, stc.sdr3, stc.unknownRef8, stc.sds6,
                     stc.sdu6, stc.unknownRef11, stc.sdu3, stc.sdfg, stc.sdmb]
            for anim_id, ref in zip(stc.animIds, stc.animRefs):
                entry = lists[ref >> 16][ref & 0xFFFF]
                found.setdefault(anim_id, (list(entry.frames), list(entry.keys)))
        return found

    @staticmethod
    def _sample(track, t, rotation):
        times, values = track
        if t <= times[0] or len(times) == 1:
            k, a = 0, 0.0
        elif t >= times[-1]:
            k, a = len(times) - 1, 0.0
        else:
            k = int(np.searchsorted(times, t)) - 1
            a = (t - times[k]) / max(1, times[k + 1] - times[k])
        if rotation:
            v0 = np.array([values[k].x, values[k].y, values[k].z, values[k].w])
            if not a:
                return v0
            v1 = np.array([values[k + 1].x, values[k + 1].y, values[k + 1].z, values[k + 1].w])
            if v0 @ v1 < 0:
                v1 = -v1
            v = v0 * (1 - a) + v1 * a
            return v / np.linalg.norm(v)
        v0 = np.array([values[k].x, values[k].y, values[k].z])
        if not a:
            return v0
        v1 = np.array([values[k + 1].x, values[k + 1].y, values[k + 1].z])
        return v0 * (1 - a) + v1 * a

    def world(self, name, t, keys=None):
        keys = keys if keys is not None else self.keys(name)
        out = []
        for i, bone in enumerate(self.model.bones):
            loc = keys.get(bone.location.header.animId)
            rot = keys.get(bone.rotation.header.animId)
            scl = keys.get(bone.scale.header.animId)
            iv = bone.location.initValue
            p = self._sample(loc, t, False) if loc else np.array([iv.x, iv.y, iv.z])
            iq = bone.rotation.initValue
            q = self._sample(rot, t, True) if rot else np.array([iq.x, iq.y, iq.z, iq.w])
            isc = bone.scale.initValue
            s = self._sample(scl, t, False) if scl else np.array([isc.x, isc.y, isc.z])
            m = np.eye(4)
            m[:3, :3] = quat_matrix(*q) @ np.diag(s)
            m[:3, 3] = p
            out.append(out[self.parents[i]] @ m if self.parents[i] >= 0 else m)
        return out

    def deltas(self, name, t, keys=None):
        return [w @ ib for w, ib in zip(self.world(name, t, keys), self.inverse_bind)]
