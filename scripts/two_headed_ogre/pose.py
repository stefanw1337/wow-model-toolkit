import numpy as np
from m2_read import decode_quaternion


def quat_matrix(q):
    x, y, z, w = np.asarray(q, float) / np.linalg.norm(q)
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def sample(channel, seq_index, t, globals_, default, rotation=False):
    if not channel:
        return np.array(default, float)
    if channel.get('global', -1) >= 0:
        times, values = channel['keys'][0]
        dur = globals_[channel['global']] or 1
        t = t % dur
    else:
        times, values = channel['keys'][seq_index]
    if not times:
        return np.array(default, float)
    vals = [decode_quaternion(v) if rotation else v for v in values]
    if t <= times[0] or len(times) == 1:
        return np.array(vals[0], float)
    if t >= times[-1]:
        return np.array(vals[-1], float)
    k = np.searchsorted(times, t) - 1
    a = (t - times[k]) / max(1, times[k + 1] - times[k])
    if channel['interp'] == 0:
        return np.array(vals[k], float)
    v0, v1 = np.array(vals[k], float), np.array(vals[k + 1], float)
    if rotation and v0 @ v1 < 0:
        v1 = -v1
    out = v0 * (1 - a) + v1 * a
    return out / np.linalg.norm(out) if rotation else out


def bone_matrices(scene, seq_index, t):
    mats = []
    g = scene.get('global_sequences', [])
    for bone in scene['bones']:
        ch = bone['channels']
        p = np.array(bone['pivot'])
        tr = sample(ch.get('translation'), seq_index, t, g, [0, 0, 0])
        rot = sample(ch.get('rotation'), seq_index, t, g, [0, 0, 0, 1], True)
        sc = sample(ch.get('scale'), seq_index, t, g, [1, 1, 1])
        m = np.eye(4)
        m[:3, :3] = quat_matrix(rot) @ np.diag(sc)
        m[:3, 3] = p + tr - m[:3, :3] @ p
        if bone['parent'] >= 0:
            m = mats[bone['parent']] @ m
        mats.append(m)
    return mats


def skin(scene, mats):
    out = []
    for v in scene['vertices']:
        p = np.append(v['position'], 1)
        acc = np.zeros(3)
        for b, w in zip(v['bones'], v['weights']):
            if w:
                acc += w / 255 * (mats[b] @ p)[:3]
        out.append(acc)
    return np.array(out)
