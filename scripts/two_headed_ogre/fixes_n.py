import numpy as np

from physics import decode_quaternion, encode_quaternion
from pose import bone_matrices, skin

HAIR_BONES = range(142, 152)
FOOT_BONES = {29, 30, 50, 51}
FEET = ((30, 51), (29, 50))
BACK = (26, 27, 28, 30)
BACK_GAP = 0.07
BACK_POSES = (0, 4, 5, 25, 26, 17)


def sequence_index(scene, anim_id):
    return next(i for i, s in enumerate(scene['sequences']) if s['id'] == anim_id)


def smoothed(values, loop, width):
    q = np.array([decode_quaternion(v) for v in values], float)
    for k in range(1, len(q)):
        if q[k] @ q[k - 1] < 0:
            q[k] = -q[k]
    kernel = np.exp(-0.5 * (np.arange(-2 * width, 2 * width + 1) / width) ** 2)
    out = np.zeros_like(q)
    n = len(q)
    for k in range(n):
        acc = np.zeros(4)
        for o, w in zip(range(-2 * width, 2 * width + 1), kernel):
            j = (k + o) % n if loop else min(max(k + o, 0), n - 1)
            acc += w * (q[j] if q[j] @ q[k] >= 0 else -q[j])
        out[k] = acc / np.linalg.norm(acc)
    return [tuple(encode_quaternion(v)) for v in out]


def calmer_hair(scene, width=2):
    for bone in HAIR_BONES:
        channel = scene['bones'][bone]['channels'].get('rotation')
        if not channel:
            continue
        keys = []
        for times, values in channel['keys']:
            if len(values) < 5:
                keys.append((times, values))
                continue
            ends = np.array(decode_quaternion(values[0])) @ np.array(decode_quaternion(values[-1]))
            keys.append((times, smoothed(values, abs(ends) > 0.995, width)))
        channel['keys'] = keys


def reversals(scene, bone=145, anim_id=0):
    from physics import Evaluator
    ev = Evaluator(scene)
    rest = np.array(scene['bones'][bone]['pivot']) - np.array(scene['bones'][scene['bones'][bone]['parent']]['pivot'])
    out = []
    for i, s in enumerate(scene['sequences']):
        if s['id'] != anim_id:
            continue
        ds = []
        for t in range(0, s['duration'], 33):
            d = ev.matrix(bone, i, t)[:3, :3] @ rest
            ds.append(d / np.linalg.norm(d))
        ds = np.array(ds)
        out.append(int((np.diff(np.sign(np.diff(ds[:, 1]))) != 0).sum()))
    return out


def flat_feet(scene):
    stand = sequence_index(scene, 0)
    posed = skin(scene, bone_matrices(scene, stand, 0))
    bind = np.array([v['position'] for v in scene['vertices']])
    for foot, toe in FEET:
        ids = [i for i, v in enumerate(scene['vertices']) if v['bones'][0] in (foot, toe)]
        sole = posed[ids]
        heel_part = sole[sole[:, 0] < np.percentile(sole[:, 0], 15)]
        toe_part = sole[sole[:, 0] > np.percentile(sole[:, 0], 85)]
        heel = heel_part[heel_part[:, 2].argmin()]
        tip = toe_part[toe_part[:, 2].argmin()]
        angle = np.arctan2(tip[2] - heel[2], tip[0] - heel[0])
        pivot = np.array(scene['bones'][foot]['pivot'])
        c, s = np.cos(angle), np.sin(angle)
        turn = np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
        for i, v in enumerate(scene['vertices']):
            share = sum(w for b, w in zip(v['bones'], v['weights']) if b in (foot, toe)) / 255
            if share:
                moved = turn @ (bind[i] - pivot) + pivot
                v['position'] = (bind[i] + share * (moved - bind[i])).tolist()
    posed = skin(scene, bone_matrices(scene, stand, 0))
    lift = -float(posed[:, 2].min())
    for v in scene['vertices']:
        v['position'][2] += lift
    for b in scene['bones']:
        b['pivot'] = [b['pivot'][0], b['pivot'][1], b['pivot'][2] + lift]
    for a in scene['attachments']:
        a['position'] = [a['position'][0], a['position'][1], a['position'][2] + lift]
    for e in scene.get('events', []):
        e['position'] = [e['position'][0], e['position'][1], e['position'][2] + lift]
    return lift


def attachment_world(matrices, attachment):
    return (matrices[attachment['bone']] @ np.append(attachment['position'], 1))[:3]


def back_closer(scene):
    poses = [sequence_index(scene, p) for p in BACK_POSES]
    frames = []
    for si in poses:
        duration = scene['sequences'][si]['duration']
        for t in (0, duration // 3, 2 * duration // 3):
            m = bone_matrices(scene, si, t)
            frames.append((m, skin(scene, m)))
    stand_m, stand_p = frames[0]
    report = {}
    for a in scene['attachments']:
        if a['id'] not in BACK:
            continue
        start = np.array(a['position'])
        here = attachment_world(stand_m, a)
        target = stand_p[np.linalg.norm(stand_p - here, axis=1).argmin()]
        inverse = np.linalg.inv(stand_m[a['bone']])
        local_target = (inverse @ np.append(target, 1))[:3]
        best = start
        for f in np.linspace(0, 1, 41):
            trial = start + f * (local_target - start)
            a['position'] = trial.tolist()
            if all(np.linalg.norm(p - attachment_world(m, a), axis=1).min() >= BACK_GAP for m, p in frames):
                best = trial
            else:
                break
        a['position'] = best.tolist()
        bone = scene['bones'][a['bone']]
        bone['pivot'] = (np.array(bone['pivot']) + best - start).tolist()
        report[a['id']] = round(float(np.linalg.norm(best - start)), 3)
    return report


HAND_ATTACHMENTS = {'L': (2, 21), 'R': (1, 22, 35)}
HAND_ATTACHMENT_IDS = {'L': 2, 'R': 1}


def fist_and_grip(scene, side, sides):
    stand = sequence_index(scene, 0)
    matrices = bone_matrices(scene, stand, 0)
    posed = skin(scene, matrices)
    fingers = list(sides[side]['fingers'].values())
    fingers += [f + 10 for f in fingers]
    first = np.array([v['bones'][0] for v in scene['vertices']])
    fist = posed[np.isin(first, fingers)].mean(0)
    grip = next(a for a in scene['attachments'] if a['id'] == HAND_ATTACHMENT_IDS[side])
    return fist, attachment_world(matrices, grip), matrices


def grips_like(scene, reference, sides):
    moved = {}
    for side, ids in HAND_ATTACHMENTS.items():
        ref_fist, ref_grip, _ = fist_and_grip(reference, side, sides)
        fist, grip, matrices = fist_and_grip(scene, side, sides)
        delta_world = (ref_grip - ref_fist) - (grip - fist)
        for a in scene['attachments']:
            if a['id'] not in ids:
                continue
            bone = scene['bones'][a['bone']]
            parent = matrices[bone['parent']][:3, :3]
            delta = np.linalg.solve(parent, delta_world)
            a['position'] = (np.array(a['position']) + delta).tolist()
            bone['pivot'] = (np.array(bone['pivot']) + delta).tolist()
            moved[a['id']] = np.round(delta_world, 3).tolist()
    return moved


def per_sequence_scales(scene, bones):
    changed = []
    for index in bones:
        channel = scene['bones'][index]['channels'].get('scale')
        if not channel or channel.get('global', -1) < 0:
            continue
        times, values = channel['keys'][0]
        value = values[0]
        channel['keys'] = [([0], [value]) for _ in scene['sequences']]
        channel['global'] = -1
        channel['interp'] = 0
        changed.append(index)
    return changed


def back_closer_at_rest(scene, ids, gap=0.05, poses=(0, 25, 26, 17)):
    frames = []
    for anim in poses:
        si = sequence_index(scene, anim)
        duration = scene['sequences'][si]['duration']
        for t in (0, duration // 3, 2 * duration // 3):
            m = bone_matrices(scene, si, t)
            frames.append((m, skin(scene, m)))
    stand_m, stand_p = frames[0]
    report = {}
    for a in scene['attachments']:
        if a['id'] not in ids:
            continue
        start = np.array(a['position'])
        here = attachment_world(stand_m, a)
        target = stand_p[np.linalg.norm(stand_p - here, axis=1).argmin()]
        local_target = (np.linalg.inv(stand_m[a['bone']]) @ np.append(target, 1))[:3]
        best = start
        for f in np.linspace(0, 1, 41):
            trial = start + f * (local_target - start)
            a['position'] = trial.tolist()
            if all(np.linalg.norm(p - attachment_world(m, a), axis=1).min() >= gap for m, p in frames):
                best = trial
            else:
                break
        a['position'] = best.tolist()
        bone = scene['bones'][a['bone']]
        bone['pivot'] = (np.array(bone['pivot']) + best - start).tolist()
        report[a['id']] = round(float(np.linalg.norm(best - start)), 3)
    return report
