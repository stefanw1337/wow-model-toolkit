"""Fixes after the first in-game look: loincloth follows the thighs, and body attachments sit on the new surface."""
import numpy as np

CLOTH_REGIONS = (4, 5)
WAIST, THIGH_LEFT, THIGH_RIGHT = 3, 8, 6
HANDS_AND_HEAD = {0, 1, 2, 5, 6, 11, 17, 18, 19, 20, 21, 22, 35, 36}


def cloth_follows_thighs(scene, reach=0.85):
    cloth = [v for v in scene['vertices'] if v.get('region') in CLOTH_REGIONS]
    top = max(v['position'][2] for v in cloth)
    bottom = min(v['position'][2] for v in cloth)
    for v in cloth:
        x, y, z = v['position']
        down = min(1.0, max(0.0, (top - z) / (top - bottom))) * reach
        side = min(1.0, max(0.0, 0.5 + y / 0.5))
        parts = {WAIST: 1 - down, THIGH_LEFT: down * side, THIGH_RIGHT: down * (1 - side)}
        parts = sorted(((b, w) for b, w in parts.items() if w > 0.004), key=lambda p: -p[1])
        weights = [round(w * 255) for _, w in parts]
        weights[0] += 255 - sum(weights)
        v['bones'] = [b for b, _ in parts] + [0] * (4 - len(parts))
        v['weights'] = weights + [0] * (4 - len(weights))


def surface_radius(points, z, direction, band=0.12, cone=0.5):
    near = points[np.abs(points[:, 2] - z) < band]
    flat = near[:, :2]
    lengths = np.linalg.norm(flat, axis=1) + 1e-9
    facing = (flat @ direction) / lengths > np.cos(cone)
    return float((flat[facing] @ direction).max()) if facing.any() else None


def attachments_on_surface(scene, old_vertices, old_attachments):
    new_points = np.array([v['position'] for v in scene['vertices']])
    old_points = np.array([v['position'] for v in old_vertices])
    moved = []
    for a, original in zip(scene['attachments'], old_attachments):
        a = dict(a)
        if a['id'] not in HANDS_AND_HEAD:
            x, y = original['position'][:2]
            z = a['position'][2]
            flat = np.array([x, y])
            if np.linalg.norm(flat) > 0.05:
                direction = flat / np.linalg.norm(flat)
                old_r = surface_radius(old_points, z, direction)
                new_r = surface_radius(new_points, z, direction)
                if old_r is not None and new_r is not None:
                    shift = direction * (new_r - old_r)
                    a['position'] = [x + shift[0], y + shift[1], z]
        moved.append(a)
    scene['attachments'] = moved


BACK, HIPS, FRONT = {26, 27, 28, 30, 31}, {32, 33}, {15, 34}
BODY_REGION = 1
TORSO_BONES = {1, 2, 3, 4, 5, 6, 8, 16, 17}


def attachments_on_body(scene, originals, margin=0.06):
    body = np.array([v['position'] for v in scene['vertices']
                     if v.get('region') == BODY_REGION and v['bones'][0] in TORSO_BONES])
    placed = []
    for a, original in zip(scene['attachments'], originals):
        a = dict(a)
        x, y, z = a['position']
        oy = original['position'][1]
        if a['id'] in BACK | FRONT:
            band = 0.3 if a['id'] in BACK else 0.12
            near = body[(np.abs(body[:, 2] - z) < band) & (np.abs(body[:, 1] - oy) < 0.25)]
            if len(near):
                x = near[:, 0].min() - margin if a['id'] in BACK else near[:, 0].max() + margin
                y = oy
        elif a['id'] in HIPS:
            near = body[(np.abs(body[:, 2] - z) < 0.12) & (np.abs(body[:, 0] - x) < 0.25)]
            if len(near):
                y = (near[:, 1].max() + margin) if oy > 0 else (near[:, 1].min() - margin)
        a['position'] = [x, y, z]
        placed.append(a)
    scene['attachments'] = placed


def scaled_attachments(scene, factor, ids):
    bones = {a['bone'] for a in scene['attachments'] if a['id'] in ids}
    for b in bones:
        ch = scene['bones'][b]['channels']
        sc = ch.get('scale')
        if sc:
            sc['keys'] = [(t, [tuple(c * factor for c in v) for v in vals]) for t, vals in sc['keys']]
        else:
            ch['scale'] = {'interp': 0, 'global': -1,
                           'keys': [([0], [(factor, factor, factor)]) for _ in scene['sequences']]}


def tucked_cloth(scene, back=0.04):
    cloth = [v for v in scene['vertices'] if v.get('region') in CLOTH_REGIONS]
    top = max(v['position'][2] for v in cloth)
    for v in cloth:
        v['position'][0] -= back * max(0.0, 1 - (top - v['position'][2]) / 0.6)


PLATE = 5


def cloth_under_plate(scene, gap=0.03, reach=0.8):
    verts = scene['vertices']
    plate = np.array([v['position'] for v in verts if v['bones'][0] == PLATE and v['weights'][0] > 200])
    cloth = [v for v in verts if v.get('region') in CLOTH_REGIONS]
    plate_bottom = plate[:, 2].min()
    bottom = min(v['position'][2] for v in cloth)
    for v in cloth:
        x, y, z = v['position']
        near = plate[(np.abs(plate[:, 2] - z) < 0.06) & (np.abs(plate[:, 1] - y) < 0.12)]
        if len(near) and x > near[:, 0].max() - gap:
            v['position'][0] = float(near[:, 0].max() - gap)
        down = min(1.0, max(0.0, (plate_bottom + 0.05 - z) / (plate_bottom + 0.05 - bottom))) * reach
        side = min(1.0, max(0.0, 0.5 + y / 0.5))
        parts = {PLATE: 1 - down, THIGH_LEFT: down * side, THIGH_RIGHT: down * (1 - side)}
        parts = sorted(((b, w) for b, w in parts.items() if w > 0.004), key=lambda p: -p[1])
        weights = [round(w * 255) for _, w in parts]
        weights[0] += 255 - sum(weights)
        v['bones'] = [b for b, _ in parts] + [0] * (4 - len(parts))
        v['weights'] = weights + [0] * (4 - len(weights))


SKIP_SURFACE = {0, 1, 2, 11, 17, 18, 19, 20, 21, 22, 35, 36}


def attachments_outside(scene, margin=0.05):
    verts = [v for v in scene['vertices'] if v.get('region') in (1, 3)]
    P = np.array([v['position'] for v in verts])
    N = np.array([v['normal'] for v in verts])
    moved = []
    for a in scene['attachments']:
        a = dict(a)
        if a['id'] not in SKIP_SURFACE:
            p = np.array(a['position'])
            k = int(np.argmin(np.linalg.norm(P - p, axis=1)))
            depth = float((p - P[k]) @ N[k])
            if depth < margin:
                a['position'] = (p + N[k] * (margin - depth)).tolist()
        moved.append(a)
    scene['attachments'] = moved


def attachments_outside_in_stand(scene, bone_matrices, skin, margin=0.05, pose_id=0):
    stand = next(i for i, s in enumerate(scene['sequences']) if s['id'] == pose_id and s.get('variation', 0) == 0)
    M = bone_matrices(scene, stand, 0)
    P = skin(scene, M)
    keep = np.array([v.get('region') in (1, 3) for v in scene['vertices']])
    N = np.array([M[v['bones'][0]][:3, :3] @ np.array(v['normal']) for v in scene['vertices']])
    P, N = P[keep], N[keep] / np.linalg.norm(N[keep], axis=1, keepdims=True)
    moved = []
    for a in scene['attachments']:
        a = dict(a)
        if a['id'] not in SKIP_SURFACE:
            m = M[a['bone']]
            q = (m @ np.append(a['position'], 1))[:3]
            k = int(np.argmin(np.linalg.norm(P - q, axis=1)))
            depth = float((q - P[k]) @ N[k])
            if depth < margin:
                q = P[k] + N[k] * margin
                a['position'] = (np.linalg.inv(m) @ np.append(q, 1))[:3].tolist()
        moved.append(a)
    scene['attachments'] = moved


def attachments_outside_in_poses(scene, bone_matrices, skin, poses=(0, 25, 26, 27, 4, 5), rounds=2, margin=0.06):
    for _ in range(rounds):
        for pose in poses:
            attachments_outside_in_stand(scene, bone_matrices, skin, margin, pose)


def lowered_attachments(scene, ids, drop):
    scene['attachments'] = [dict(a, position=[a['position'][0], a['position'][1], a['position'][2] - drop])
                            if a['id'] in ids else a for a in scene['attachments']]


def hip_plates_inward(scene, hots, amount=0.08, back=0.0):
    names = [b['name'] for b in hots['bones']]
    plates = {names.index('Bone_HipPlate_L'), names.index('Bone_HipPlate_R')}
    flags = []
    for region in hots['regions']:
        if region['material'] == 0 or region['index'] == 5:
            continue
        for v in region['vertices']:
            flags.append(v['bones'][int(np.argmax(v['weights']))] in plates)
    for flag, v in zip(flags, scene['vertices']):
        if flag:
            y = v['position'][1]
            v['position'][1] = y - np.sign(y) * amount
            v['position'][0] -= back
