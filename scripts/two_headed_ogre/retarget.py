"""Pose the HotS Cho'Gall mesh onto the WoW Cho'Gall skeleton and build a writer scene."""
import copy
import numpy as np

SIDES = {'L': dict(clav=16, arm=25, fore=35, hand=56, fingers=dict(A=60, B=59, C=61, D=58, Thumb=62),
                   thigh=8, calf=24, foot=30, toe=51, neck=18, head=27, jaw=48, hotshead='Gall'),
         'R': dict(clav=17, arm=26, fore=43, hand=57, fingers=dict(A=64, B=63, C=65, D=66, Thumb=67),
                   thigh=6, calf=22, foot=29, toe=50, neck=19, head=28, jaw=49, hotshead='Cho')}


def bone_map():
    m = {'Bone_Root': 1, 'Bone_Spine': 2, 'Bone_Torso': 4, 'Bone_Lat_R': 4, 'Bone_Lat_L': 4, 'Bone_Belly': 4,
         'Bone_Hip': 3, 'Bone_BellyPlate': 5, 'Bone_Skirt_L_01': 7, 'Bone_Skirt_R_01': 7,
         'Bone_Skirt_L_02': 23, 'Bone_Skirt_R_02': 23}
    for side, s in SIDES.items():
        h = s['hotshead']
        m.update({f'Bone_Clavicle_{side}': s['clav'], f'Bone_Breast_{side}': 4, f'Bone_Arm_{side}': s['arm'],
                  f'Bone_Shoulder_Twist_{side}': s['arm'], f'Bone_ArmFore_{side}': s['fore'],
                  f'Bone_ArmForeTwist_{side}': s['fore'], f'Bone_ArmHand_{side}': s['hand'],
                  f'Bone_LegThigh_{side}': s['thigh'], f'Bone_LegCalf_{side}': s['calf'],
                  f'Bone_LegFoot_{side}': s['foot'], f'Bone_LegToe_{side}': s['toe'],
                  f'Bone_HipPlate_{side}': 3, f'Bone_Buttock_{side}': s['thigh'],
                  f'Bone_Neck{h}': s['neck'], f'Bone_Head{h}': s['head'], f'Bone_Jaw{h}': s['jaw']})
        for finger, upper in s['fingers'].items():
            m[f'Bone_Arm{"Thumb" if finger == "Thumb" else "Finger" + finger}_Upper_{side}'] = upper
            m[f'Bone_Arm{"Thumb" if finger == "Thumb" else "Finger" + finger}_Lower_{side}'] = upper + 10
    m['Bone_ShoulderPlate'] = SIDES['R']['arm']
    return m


CHAINS = [('Bone_Arm_{s}', 'Bone_ArmFore_{s}', 'arm', 'fore'),
          ('Bone_ArmFore_{s}', 'Bone_ArmHand_{s}', 'fore', 'hand'),
          ('Bone_ArmHand_{s}', 'Bone_ArmFingerB_Upper_{s}', 'hand', ('fingers', 'B')),
          ('Bone_LegThigh_{s}', 'Bone_LegCalf_{s}', 'thigh', 'calf'),
          ('Bone_LegCalf_{s}', 'Bone_LegFoot_{s}', 'calf', 'foot')]


def to_wow(p):
    p = np.asarray(p, float)
    return np.stack([-p[..., 1], p[..., 0], p[..., 2]], -1)


def align(a, b):
    a = a / np.linalg.norm(a)
    b = b / np.linalg.norm(b)
    v = np.cross(a, b)
    c = float(a @ b)
    if np.linalg.norm(v) < 1e-9:
        return np.eye(3)
    k = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + k + k @ k * (1 / (1 + c))


def retarget(wow, hots, scale, skip_regions=(5,), extra_map=None, abduct=0.0):
    names = [b['name'] for b in hots['bones']]
    index = {n: i for i, n in enumerate(names)}
    parents = [b['parent'] for b in hots['bones']]
    joints = np.array([to_wow(np.linalg.inv(m)[:3, 3]) for m in hots['inverse_bind']]) * scale
    pivots = np.array([b['pivot'] for b in wow['bones']])
    mapping = bone_map()
    mapping.update(extra_map or {})

    target = {}
    for side, s in SIDES.items():
        for a, b, wa, wb in CHAINS:
            wb_index = s[wb[0]][wb[1]] if isinstance(wb, tuple) else s[wb]
            direction = pivots[wb_index] - pivots[s[wa]]
            if wa == 'arm' and abduct:
                outward = np.array([0.0, 1.0 if side == 'L' else -1.0, 0.0])
                axis = np.cross(direction, outward)
                axis /= np.linalg.norm(axis)
                angle = np.radians(abduct)
                k = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
                direction = (np.eye(3) + np.sin(angle) * k + (1 - np.cos(angle)) * k @ k) @ direction
            target[index[a.format(s=side)]] = direction

    rotation = [None] * len(names)
    posed = np.zeros_like(joints)
    for i in range(len(names)):
        p = parents[i]
        parent_rot = rotation[p] if p >= 0 else np.eye(3)
        posed[i] = joints[i] if p < 0 else posed[p] + parent_rot @ (joints[i] - joints[p])
        if i in target:
            child = next(c for c in range(len(names)) if parents[c] == i and
                         names[c] in [x[1].format(s=names[i][-1]) for x in CHAINS if x[0].format(s=names[i][-1]) == names[i]])
            rotation[i] = align(parent_rot @ (joints[child] - joints[i]), target[i]) @ parent_rot
        else:
            rotation[i] = parent_rot

    def wow_bone(i):
        while i >= 0 and names[i] not in mapping:
            i = parents[i]
        return mapping[names[i]] if i >= 0 else 1

    vertices, triangles = [], []
    for region in hots['regions']:
        if region['material'] == 0 or region['index'] in skip_regions:
            continue
        base = len(vertices)
        for v in region['vertices']:
            pos = to_wow(v['position']) * scale
            nrm = to_wow(v['normal'])
            new_pos, new_nrm, total = np.zeros(3), np.zeros(3), 0
            influence = {}
            for b, w in zip(v['bones'], v['weights']):
                if not w:
                    continue
                new_pos += w * (rotation[b] @ (pos - joints[b]) + posed[b])
                new_nrm += w * (rotation[b] @ nrm)
                total += w
                wb = wow_bone(b)
                influence[wb] = influence.get(wb, 0) + w
            new_pos /= total
            new_nrm /= np.linalg.norm(new_nrm)
            top = sorted(influence.items(), key=lambda x: -x[1])[:4]
            weights = [round(w * 255 / sum(x[1] for x in top)) for _, w in top]
            weights[0] += 255 - sum(weights)
            bones = [b for b, _ in top] + [0] * (4 - len(top))
            weights += [0] * (4 - len(weights))
            vertices.append(dict(position=new_pos.tolist(), normal=new_nrm.tolist(), uv=v['uv'],
                                 bones=bones, weights=weights, region=region['index']))
        triangles += [(a + base, b + base, c + base) for a, b, c in region['triangles']]

    new_pivots = pivots.copy()
    moved = {}
    for name, wb in mapping.items():
        if name in index and wb not in moved:
            moved[wb] = posed[index[name]]
    parents_wow = [b['parent'] for b in wow['bones']]
    shift = np.zeros_like(pivots)
    for i in range(len(pivots)):
        if i in moved:
            new_pivots[i] = moved[i]
            shift[i] = moved[i] - pivots[i]
        else:
            p = parents_wow[i]
            while p >= 0 and p not in moved:
                p = parents_wow[p]
            shift[i] = shift[p] if p >= 0 else np.array([0, 0, 0.])
            new_pivots[i] = pivots[i] + shift[i]

    scene = copy.copy(wow)
    scene['bones'] = [dict(b, pivot=new_pivots[i].tolist()) for i, b in enumerate(wow['bones'])]
    scene['attachments'] = [dict(a, position=(np.array(a['position']) + shift[a['bone']]).tolist())
                            for a in wow['attachments']]
    scene['vertices'] = vertices
    scene['textures'] = [dict(type=0, flags=0, path='Creature\\ChoGallHotS\\ChoGallHotS.blp')]
    scene['materials'] = [dict(blend='opaque')]
    scene['groups'] = [dict(triangles=triangles, texture=0, material=0)]
    P = np.array([v['position'] for v in vertices])
    scene['bounds'] = dict(minimum=P.min(0).tolist(), maximum=P.max(0).tolist(),
                           radius=float(np.linalg.norm(P - (P.min(0) + P.max(0)) / 2, axis=1).max()))
    return scene, dict(joints=joints, posed=posed, pivots=pivots, new_pivots=new_pivots)
