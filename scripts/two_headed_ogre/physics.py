"""Bake swinging hair and beards into ordinary M2 keyframes: new bone chains hang from a head or jaw, and their
rotation for every animation comes from a spring simulation that follows the parent's movement."""
import numpy as np
from m2_writer import encode_quaternion
from pose import quat_matrix
from m2_read import decode_quaternion

RIGID = {'Bone_Hair_01': 2}
CHAINS = (('Bone_HeadCho', 28, ['Bone_Hair_01', 'Bone_Hair_02', 'Bone_Hair_03', 'Bone_Hair_04'],
           'SC2Physics_Bone_Hair_04'),
          ('Bone_JawGall', 48, ['Bone_BeardGall_01', 'Bone_BeardGall_02'], 'SC2Physics_Bone_BeardGall_01'),
          ('Bone_JawCho', 49, ['Bone_BeardCho_R_01', 'Bone_BeardCho_R_02'], 'SC2Physics_Bone_BeardCho_R_02'),
          ('Bone_JawCho', 49, ['Bone_BeardCho_L_01', 'Bone_BeardCho_L_02'], 'SC2Physics_Bone_BeardCho_L_02'))
FPS = 30


class Evaluator:
    def __init__(self, scene):
        self.scene = scene
        self.decoded = {}

    def values(self, bone, field, key):
        ident = (bone, field, key)
        if ident not in self.decoded:
            ch = self.scene['bones'][bone]['channels'][field]
            times, vals = ch['keys'][key]
            if field == 'rotation':
                vals = [decode_quaternion(v) for v in vals]
            self.decoded[ident] = (np.array(times, float), np.array(vals, float))
        return self.decoded[ident]

    def sample(self, bone, field, si, t, default):
        ch = self.scene['bones'][bone]['channels'].get(field)
        if not ch:
            return np.array(default, float)
        if ch.get('global', -1) >= 0:
            dur = self.scene['global_sequences'][ch['global']] or 1
            times, vals = self.values(bone, field, 0)
            t = t % dur
        else:
            times, vals = self.values(bone, field, si)
        if len(times) == 0:
            return np.array(default, float)
        if t <= times[0] or len(times) == 1:
            return vals[0]
        if t >= times[-1]:
            return vals[-1]
        k = int(np.searchsorted(times, t)) - 1
        a = (t - times[k]) / max(1.0, times[k + 1] - times[k])
        if ch['interp'] == 0:
            return vals[k]
        v0, v1 = vals[k], vals[k + 1]
        if field == 'rotation' and v0 @ v1 < 0:
            v1 = -v1
        out = v0 * (1 - a) + v1 * a
        return out / np.linalg.norm(out) if field == 'rotation' else out

    def matrix(self, bone, si, t):
        b = self.scene['bones'][bone]
        p = np.array(b['pivot'])
        tr = self.sample(bone, 'translation', si, t, [0, 0, 0])
        rot = self.sample(bone, 'rotation', si, t, [0, 0, 0, 1])
        sc = self.sample(bone, 'scale', si, t, [1, 1, 1])
        m = np.eye(4)
        m[:3, :3] = quat_matrix(rot) @ np.diag(sc)
        m[:3, 3] = p + tr - m[:3, :3] @ p
        return self.matrix(b['parent'], si, t) @ m if b['parent'] >= 0 else m


def planned(first_index):
    extra, chains, index = {}, [], first_index
    for _, parent, names, tip in CHAINS:
        bones = []
        for name in names:
            extra[name] = index
            bones.append(index)
            index += 1
        chains.append((parent, names, tip, bones))
    return extra, chains


def quat_from_matrix(m):
    t = np.trace(m)
    if t > 0:
        s = np.sqrt(t + 1) * 2
        return np.array([(m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s, (m[1, 0] - m[0, 1]) / s, s / 4])
    i = int(np.argmax(np.diag(m)))
    j, k = (i + 1) % 3, (i + 2) % 3
    s = np.sqrt(1 + m[i, i] - m[j, j] - m[k, k]) * 2
    q = np.zeros(4)
    q[i] = s / 4
    q[j] = (m[j, i] + m[i, j]) / s
    q[k] = (m[k, i] + m[i, k]) / s
    q[3] = (m[k, j] - m[j, k]) / s
    return q


def align(a, b):
    a = a / np.linalg.norm(a)
    b = b / np.linalg.norm(b)
    v = np.cross(a, b)
    c = float(a @ b)
    if np.linalg.norm(v) < 1e-9:
        return np.eye(3)
    k = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + k + k @ k * (1 / (1 + c))


COLLIDER_BONES = {1, 2, 3, 4, 5, 16, 17, 25, 26}


def collider(scene, count=700):
    picks = [(np.array(v['position']), v['bones'][0], np.array(v['normal'])) for v in scene['vertices']
             if v.get('region') == 1 and v['bones'][0] in COLLIDER_BONES and v['weights'][0] > 180]
    step = max(1, len(picks) // count)
    return picks[::step]


def add_chains(scene, info, hots, chains, stiffness=90.0, damping=14.0, sway=0.04, sag=0.0, radius=0.11, max_turn=10.0):
    names = [b['name'] for b in hots['bones']]
    posed = info['posed']
    for parent, chain_names, tip_name, indices in chains:
        joints = [posed[names.index(n)] for n in chain_names] + [posed[names.index(tip_name)]]
        for k, idx in enumerate(indices):
            assert idx == len(scene['bones'])
            scene['bones'].append(dict(key=-1, flags=512, parent=parent if k == 0 else indices[k - 1],
                                       pivot=list(map(float, joints[k])), channels={}))
    for parent, chain_names, tip_name, indices in chains:
        joints = [np.array(scene['bones'][i]['pivot']) for i in indices] + [posed[names.index(tip_name)]]
        segments = [joints[k + 1] - joints[k] for k in range(len(indices))]
        lengths = [np.linalg.norm(s) for s in segments]
        evaluator = Evaluator(scene)
        body = collider(scene)
        body_points = np.array([p for p, _, _ in body])
        body_bones = [b for _, b, _ in body]
        body_normals = [n for _, _, n in body]
        keys = []
        for si, seq in enumerate(scene['sequences']):
            duration = max(seq['duration'], 1)
            times = list(range(0, duration, int(1000 / FPS))) + [duration]
            loops = not seq.get('flags', 32) & 1 and seq['duration'] > 0
            pace = min(1.0, max(0.0, seq['movespeed'] / 7.0))
            droop = sag * (1 - pace) ** 1.5
            wind = 0.5 * pace
            stiffness_now = stiffness * (1 - 0.45 * pace)
            damping_now = damping * (1 - 0.55 * pace)
            cycles = 2 if loops else 1
            tips = None
            last = {}
            velocity = [np.zeros(3) for _ in indices]
            rows = []
            for cycle in range(cycles):
                rows = []
                previous = None
                for t in times:
                    frame = evaluator.matrix(parent, si, t)
                    posed_body = {}
                    for bone in set(body_bones):
                        posed_body[bone] = evaluator.matrix(bone, si, t)
                    obstacles = np.array([(posed_body[b] @ np.append(p, 1))[:3] for p, b in zip(body_points, body_bones)])
                    outward = np.array([posed_body[b][:3, :3] @ n for n, b in zip(body_normals, body_bones)])
                    outward /= np.linalg.norm(outward, axis=1, keepdims=True)
                    dt = (t - previous) / 1000 if previous is not None else 0
                    previous = t
                    rotations = []
                    world = frame
                    for k, idx in enumerate(indices):
                        joint = (world @ np.append(joints[k], 1))[:3]
                        if k < RIGID.get(chain_names[0], 0):
                            rotations.append(np.eye(3))
                            tips = (tips or [])[:k] + [(world @ np.append(joints[k + 1], 1))[:3]] + (tips or [])[k + 1:]
                            continue
                        wobble = sway * np.sin(2 * np.pi * (t / 2600.0 + 0.3 * k))
                        reach = sum(lengths[:k + 1])
                        target = (frame @ np.append(joints[k + 1], 1))[:3] + frame[:3, :3] @ np.array(
                            [0, wobble * reach, 0]) + np.array([-wind * reach, 0, -droop * reach])
                        if tips is None or len(tips) <= k:
                            tips = (tips or []) + [target.copy()]
                        if dt > 0:
                            accel = stiffness_now * (target - tips[k]) - damping_now * velocity[k]
                            velocity[k] = velocity[k] + accel * dt
                            tips[k] = tips[k] + velocity[k] * dt
                        direction = tips[k] - joint
                        direction = direction / np.linalg.norm(direction) * lengths[k]
                        tips[k] = joint + direction
                        for share in (1.0, 0.5):
                            point = joint + direction * share
                            gaps = np.linalg.norm(obstacles - point, axis=1)
                            nearest = int(np.argmin(gaps))
                            if gaps[nearest] > 0.3:
                                continue
                            away = outward[nearest]
                            clearance = float((point - obstacles[nearest]) @ away)
                            if clearance < radius:
                                push = min(radius - clearance, 0.12)
                                tips[k] = tips[k] + away * push / share
                                velocity[k] = velocity[k] - min(0.0, float(velocity[k] @ away)) * away
                        direction = tips[k] - joint
                        direction = direction / np.linalg.norm(direction)
                        if k in last and dt > 0:
                            limit = np.radians(max_turn) * dt / (1 / FPS)
                            angle = float(np.arccos(np.clip(direction @ last[k], -1, 1)))
                            if angle > limit:
                                axis = np.cross(last[k], direction)
                                if np.linalg.norm(axis) > 1e-9:
                                    axis /= np.linalg.norm(axis)
                                    kx = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
                                    direction = (np.eye(3) + np.sin(limit) * kx + (1 - np.cos(limit)) * kx @ kx) @ last[k]
                                    velocity[k] = velocity[k] * 0.5
                        last[k] = direction
                        direction = direction * lengths[k]
                        tips[k] = joint + direction
                        local = np.linalg.inv(world[:3, :3]) @ direction
                        rot = align(segments[k], local)
                        rotations.append(rot)
                        step = np.eye(4)
                        step[:3, :3] = rot
                        step[:3, 3] = joints[k] - rot @ joints[k]
                        world = world @ step
                    rows.append(rotations)
            keys.append((times, rows))
        for k, idx in enumerate(indices):
            per_seq = []
            for times, rows in keys:
                quats = []
                previous_q = None
                for rotations in rows:
                    q = quat_from_matrix(rotations[k])
                    q /= np.linalg.norm(q)
                    if previous_q is not None and q @ previous_q < 0:
                        q = -q
                    previous_q = q
                    quats.append(tuple(encode_quaternion(q)))
                per_seq.append((times, quats))
            scene['bones'][idx]['channels']['rotation'] = {'interp': 1, 'global': -1, 'keys': per_seq}
