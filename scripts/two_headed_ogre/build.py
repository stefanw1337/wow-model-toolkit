import argparse
import copy
import hashlib
import os
import shutil
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent)]

import assets  # noqa: E402
import carry_anims  # noqa: E402
import fit_body  # noqa: E402
import hots_anim  # noqa: E402
import m3_scene  # noqa: E402
from m2_model_writer import write  # noqa: E402
from wow_scene import scene_from_m2  # noqa: E402

HOTS_MODEL = 'storm_hero_chogall_base.m3'
HOTS_ANIMS = 'storm_hero_chogall_requiredanims.m3a'
HOTS_DIFFUSE = 'storm_hero_chogall_base_diff.dds'
TUNING = HERE.parents[1] / 'examples' / 'two-headed-ogre' / 'tuning.json'

SHIELD_BONE = 132
ARMOR_ATTACHMENTS = (5, 6, 11)
OFF_HAND_GRIP_SHIFT = (0.06, -0.08, 0.04)
MAIN_HAND_GRIP_SHIFT = (0.03, 0.11, -0.10)
OFF_HAND_OUTWARD_DEGREES = 45
HELD_ITEM_DIRECTION = (0.93, -0.1, -0.33)
HELD_GRIP = 47
CHOGALL_TEXTURES = {11: 'Creature\\ChoGall\\ChoGallTop.blp', 12: 'Creature\\ChoGall\\ChoGallBottom.blp'}
HELD_ITEM_REACH = 0.1
WEAPON_BONES = (106, 107, SHIELD_BONE, 115, 116, 117, 118, 119, 133, 134, 135, 136, 137)
WEAPON_SCALE = 2.4 / 2.21
SHIELD_SCALE = 1.85 / 2.21
SHIELD_BONES = (SHIELD_BONE, 117)
EYELID_SECTIONS = (1, 2, 4, 5)
SKIRT_DEPTH = 0.035
SKIRT_REACH = 0.15
SKIRT_TORSO_DEPTH = 0.3
SKIRT_TORSO_LOW, SKIRT_TORSO_HIGH, SKIRT_TORSO_HALF_WIDTH = 1.2, 2.0, 0.7
SKIRT_BACK = -0.15
WOW_CARRY_SHIFT = (0.0, -0.45, 0.0)
SKIRT_OVERLAP = 0.015


def shield_like_weapons(scene):
    reference = scene['bones'][117]['channels']['scale']
    scene['bones'][SHIELD_BONE]['channels']['scale'] = {**reference, 'keys': list(reference['keys'])}


def off_hand_grip_like_ogre(scene, side='L', attachment_id=2, grip_shift=OFF_HAND_GRIP_SHIFT):
    from pose import bone_matrices
    from fixes_n import sequence_index, fist_and_grip
    from retarget import SIDES
    fist, grip, matrices = fist_and_grip(scene, side, SIDES)
    hand = scene['bones'][SIDES[side]['hand']]
    size = np.linalg.norm(fist - (matrices[SIDES[side]['hand']] @ np.append(hand['pivot'], 1))[:3])
    shift = size * np.asarray(grip_shift)
    grip_attachment = next(a for a in scene['attachments'] if a['id'] == attachment_id)
    bone = scene['bones'][grip_attachment['bone']]
    delta = np.linalg.solve(matrices[bone['parent']][:3, :3], shift)
    grip_attachment['position'] = (np.array(grip_attachment['position']) + delta).tolist()
    bone['pivot'] = (np.array(bone['pivot']) + delta).tolist()
    return np.round(shift, 3).tolist()


def holding_variant(scene, name):
    from pose import bone_matrices
    from fixes_n import sequence_index
    from m2_writer import encode_quaternion
    held = copy.deepcopy(scene)
    held['name'] = name
    grip = next(a for a in held['attachments'] if a['id'] == 2)
    bone = held['bones'][grip['bone']]
    stand = sequence_index(held, 0)
    best = None
    for sign in (1, -1):
        quaternion = (0.0, sign * np.sqrt(0.5), 0.0, np.sqrt(0.5))
        bone['channels']['rotation'] = {'interp': 0, 'global': -1,
                                        'keys': [([0], [tuple(encode_quaternion(quaternion))]) for _ in held['sequences']]}
        matrix = bone_matrices(held, stand, 0)[grip['bone']][:3, :3]
        hanging = -matrix[:, 2] / np.linalg.norm(matrix[:, 2])
        if best is None or hanging[0] > best[0]:
            best = (hanging[0], sign, copy.deepcopy(bone['channels']['rotation']), np.round(hanging, 2).tolist())
    bone['channels']['rotation'] = best[2]
    from m2_read import decode_quaternion
    from pose import quat_matrix
    parent = bone_matrices(held, stand, 0)[bone['parent']][:3, :3]
    parent = parent / np.linalg.norm(parent, axis=0)
    side = 1 if grip['position'][1] > 0 else -1
    angle = np.radians(OFF_HAND_OUTWARD_DEGREES) * side
    yaw = np.array([[np.cos(angle), -np.sin(angle), 0], [np.sin(angle), np.cos(angle), 0], [0, 0, 1]])
    local = quat_matrix(decode_quaternion(best[2]['keys'][0][1][0]))
    turned = parent.T @ yaw @ parent @ local
    w = np.sqrt(max(0.0, 1 + np.trace(turned))) / 2
    q = (np.array([turned[2, 1] - turned[1, 2], turned[0, 2] - turned[2, 0], turned[1, 0] - turned[0, 1]]) / (4 * w)).tolist()
    bone['channels']['rotation']['keys'] = [([0], [tuple(encode_quaternion((*q, w)))]) for _ in held['sequences']]
    matrix = bone_matrices(held, stand, 0)[grip['bone']][:3, :3]
    pointing = -matrix[:, 2] / np.linalg.norm(matrix[:, 2])
    return held, np.round(pointing, 2).tolist()


def held_item_body(scene, name):
    from pose import bone_matrices, quat_matrix
    from fixes_n import sequence_index
    from m2_writer import encode_quaternion
    from m2_read import decode_quaternion
    held = copy.deepcopy(scene)
    held['name'] = name
    grip = next(a for a in held['attachments'] if a['id'] == 2)
    bone = held['bones'][grip['bone']]
    stand = sequence_index(held, 0)
    matrices = bone_matrices(held, stand, 0)
    parent = matrices[bone['parent']][:3, :3]
    parent = parent / np.linalg.norm(parent, axis=0)
    world = matrices[grip['bone']][:3, :3]
    world = world / np.linalg.norm(world, axis=0)
    hanging = -world[:, 2]
    side = 1 if grip['position'][1] > 0 else -1
    target = np.array(HELD_ITEM_DIRECTION) * (1, side, 1)
    target = target / np.linalg.norm(target)
    axis = np.cross(hanging, target)
    sine, cosine = np.linalg.norm(axis), float(hanging @ target)
    axis = axis / sine
    k = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
    turn = np.eye(3) + sine * k + (1 - cosine) * k @ k
    rotation = bone['channels'].get('rotation')
    local = quat_matrix(decode_quaternion(rotation['keys'][0][1][0])) if rotation and rotation['keys'][0][1] else np.eye(3)
    turned = parent.T @ turn @ parent @ local
    w = np.sqrt(max(0.0, 1 + np.trace(turned))) / 2
    q = (np.array([turned[2, 1] - turned[1, 2], turned[0, 2] - turned[2, 0], turned[1, 0] - turned[0, 1]]) / (4 * w)).tolist()
    bone['channels']['rotation'] = {'interp': 0, 'global': -1,
                                    'keys': [([0], [tuple(encode_quaternion((*q, w)))]) for _ in held['sequences']]}
    check = bone_matrices(held, stand, 0)[grip['bone']][:3, :3]
    return held, np.round(-check[:, 2] / np.linalg.norm(check[:, 2]), 2).tolist()


def rotation_between(start, end):
    axis = np.cross(start, end)
    sine, cosine = np.linalg.norm(axis), float(start @ end)
    if sine < 1e-9:
        return np.eye(3)
    axis = axis / sine
    k = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
    return np.eye(3) + sine * k + (1 - cosine) * k @ k


def add_held_grip(scene):
    from pose import bone_matrices, quat_matrix
    from fixes_n import sequence_index
    from m2_writer import encode_quaternion
    from m2_read import decode_quaternion
    grip = next(a for a in scene['attachments'] if a['id'] == 2)
    source = scene['bones'][grip['bone']]
    stand = sequence_index(scene, 0)
    matrices = bone_matrices(scene, stand, 0)
    parent = matrices[source['parent']][:3, :3]
    parent = parent / np.linalg.norm(parent, axis=0)
    world = matrices[grip['bone']][:3, :3]
    world = world / np.linalg.norm(world, axis=0)
    side = 1 if grip['position'][1] > 0 else -1
    target = np.array(HELD_ITEM_DIRECTION) * (1, side, 1)
    target = target / np.linalg.norm(target)
    turn = rotation_between(-world[:, 0], target)
    rotation = source['channels'].get('rotation')
    local = quat_matrix(decode_quaternion(rotation['keys'][0][1][0])) if rotation and rotation['keys'][0][1] else np.eye(3)
    turned = parent.T @ turn @ parent @ local
    w = np.sqrt(max(0.0, 1 + np.trace(turned))) / 2
    q = (np.array([turned[2, 1] - turned[1, 2], turned[0, 2] - turned[2, 0], turned[1, 0] - turned[0, 1]]) / (4 * w)).tolist()
    bone = copy.deepcopy(source)
    bone['key'] = -1
    bone['channels']['rotation'] = {'interp': 0, 'global': -1,
                                    'keys': [([0], [tuple(encode_quaternion((*q, w)))]) for _ in scene['sequences']]}
    scene['bones'].append(bone)
    index = len(scene['bones']) - 1
    scene['attachments'] = [a for a in scene['attachments'] if a['id'] != HELD_GRIP]
    reach = np.linalg.solve(bone_matrices(scene, stand, 0)[index][:3, :3], target * HELD_ITEM_REACH)
    held = dict(copy.deepcopy(grip), id=HELD_GRIP, bone=index)
    held['position'] = (np.array(grip['position']) + reach).tolist()
    scene['attachments'].append(held)
    check = bone_matrices(scene, stand, 0)[index][:3, :3]
    check = check / np.linalg.norm(check, axis=0)
    return np.round(-check[:, 0], 2).tolist(), np.round(check[:, 2], 2).tolist()


def portrait_cameras(heads, height):
    target = np.asarray(heads)
    paper_doll = height / 2.81
    return [dict(type=1, fov=0.92, far=27.78, near=0.222, position=[4.88 * paper_doll, 0.0, 1.44 * paper_doll],
                 target=[0.0, 0.0, 1.42 * paper_doll]),
            dict(type=0, fov=0.9, far=27.78, near=0.222, position=(target + (1.25, -0.62, 0.05)).tolist(),
                 target=target.tolist())]


def without_armor_spots(scene):
    scene['attachments'] = [a for a in scene['attachments'] if a['id'] not in ARMOR_ATTACHMENTS]


def smaller_weapons(scene):
    for index in WEAPON_BONES:
        channel = scene['bones'][index]['channels']['scale']
        factor = SHIELD_SCALE if index in SHIELD_BONES else WEAPON_SCALE
        channel['keys'] = [(times, [tuple(c * factor for c in v) for v in values])
                           for times, values in channel['keys']]


def vertex_normals(positions, triangles):
    normals = np.zeros_like(positions)
    for a, b, c in triangles:
        n = np.cross(positions[b] - positions[a], positions[c] - positions[a])
        for i in (a, b, c):
            normals[i] += n
    return normals / (np.linalg.norm(normals, axis=1, keepdims=True) + 1e-12)


def ray_hits(origin, direction, triangles):
    a, b, c = triangles[:, 0], triangles[:, 1], triangles[:, 2]
    e1, e2 = b - a, c - a
    h = np.cross(direction, e2)
    det = (e1 * h).sum(1)
    ok = np.abs(det) > 1e-12
    f = np.where(ok, 1 / np.where(ok, det, 1), 0)
    s = origin - a
    u = f * (s * h).sum(1)
    q = np.cross(s, e1)
    v = f * (q * direction).sum(1)
    t = f * (e2 * q).sum(1)
    hit = ok & (u >= 0) & (v >= 0) & (u + v <= 1) & (t > 1e-4)
    return t[hit]


CRACK_REACH = 0.03


def close_cracks(scene):
    vertices = scene['vertices']
    positions = np.array([v['position'] for v in vertices])
    keys = [tuple(np.round(p, 4)) for p in positions]
    visible = [t for g in scene['groups'] if g['color'] not in (1, 3) for t in g['triangles']]
    parent = {}

    def root(k):
        parent.setdefault(k, k)
        while parent[k] != k:
            parent[k] = parent[parent[k]]
            k = parent[k]
        return k

    edges = {}
    for t in visible:
        for a, b in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
            parent[root(keys[a])] = root(keys[b])
            edges.setdefault(frozenset((keys[a], keys[b])), []).append((a, b))
    open_edges = [pairs[0] for pairs in edges.values() if len(pairs) == 1]
    by_key = {}
    for i, k in enumerate(keys):
        by_key.setdefault(k, []).append(i)
    starts = positions[[a for a, _ in open_edges]]
    ends = positions[[b for _, b in open_edges]]
    piece_ids = {}
    piece_of = lambda k: piece_ids.setdefault(root(k), len(piece_ids))
    pieces = np.array([piece_of(keys[a]) for a, _ in open_edges])
    moved = {}
    for k in sorted({keys[i] for edge in open_edges for i in edge}):
        point = np.array(k)
        span = ends - starts
        along = np.clip(np.einsum('ij,ij->i', point - starts, span) / np.maximum(np.einsum('ij,ij->i', span, span),
                                                                                  1e-12), 0, 1)
        nearest = starts + span * along[:, None]
        gap = np.linalg.norm(nearest - point, axis=1)
        gap[pieces == piece_of(k)] = np.inf
        best = int(np.argmin(gap))
        if not 1e-5 < gap[best] < CRACK_REACH:
            continue
        a, b = open_edges[best]
        donor = vertices[a if along[best] < 0.5 else b]
        moved[k] = (nearest[best], donor)
    for k, (target, donor) in moved.items():
        for i in by_key[k]:
            vertices[i] = dict(vertices[i], position=target.tolist(), bones=list(donor['bones']),
                               weights=list(donor['weights']))
    return len(moved)


BACK_SHEATHS = (26, 27, 28, 30, 31)
SHEATH_MARGIN = 0.05
SHEATH_WIDTH = 0.7
SHEATH_LENGTH = 0.9


def sheaths_outside(scene):
    positions = np.array([v['position'] for v in scene['vertices']])
    moved = []
    for attachment in scene['attachments']:
        if attachment['id'] not in BACK_SHEATHS:
            continue
        x, y, z = attachment['position']
        along = (np.abs(positions[:, 1] - y) < SHEATH_WIDTH) & (np.abs(positions[:, 2] - z) < SHEATH_LENGTH)
        if not along.any():
            continue
        outside = float(positions[along, 0].min()) - SHEATH_MARGIN
        if outside < x:
            attachment['position'] = [outside, y, z]
            moved.append((attachment['id'], round(x - outside, 2)))
    return moved


CARRIED_WEAPON_BONES = (106, 107, 115, 116, 117, 118, 119)
MAIN_HAND_BONE = 133


def carried_weapons_like_held(scene):
    held = scene['bones'][MAIN_HAND_BONE]['channels'].get('scale')
    if not held:
        return []
    pivots = {a['bone']: a['position'] for a in scene['attachments']}
    scaled = []
    for index in CARRIED_WEAPON_BONES:
        bone = scene['bones'][index]
        if bone['channels'].get('scale') or index not in pivots:
            continue
        bone['channels']['scale'] = copy.deepcopy(held)
        bone['pivot'] = list(pivots[index])
        scaled.append(index)
    return scaled


BACKING_DEPTH = 0.01
BACKING_BACK = -0.1
BACKING_LOW = 1.2


def backing(scene):
    vertices = scene['vertices']
    positions = np.array([v['position'] for v in vertices])
    body = [g for g in scene['groups'] if g['color'] < 0]
    normals = vertex_normals(positions, [t for g in body for t in g['triangles']])
    copies = {}
    added = 0
    for group in body:
        extra = []
        for t in group['triangles']:
            centre = positions[list(t)].mean(0)
            if centre[0] > BACKING_BACK or centre[2] < BACKING_LOW:
                continue
            inner = []
            for i in t:
                if i not in copies:
                    vertices.append(dict(vertices[i], position=(positions[i] - normals[i] * BACKING_DEPTH).tolist()))
                    copies[i] = len(vertices) - 1
                inner.append(copies[i])
            extra.append(tuple(inner))
            added += 1
        group['triangles'] = group['triangles'] + extra
    return added


def skirts(scene):
    vertices = scene['vertices']
    positions = np.array([v['position'] for v in vertices])
    key = lambda i: tuple(np.round(positions[i], 4))
    body = [g for g in scene['groups'] if g['color'] < 0]
    visible = [t for g in scene['groups'] if g['color'] not in (1, 3) for t in g['triangles']]
    corners = positions[np.array(visible)]
    normals = vertex_normals(positions, [t for g in body for t in g['triangles']])
    edges = {}
    for t in visible:
        for a, b in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
            edges.setdefault(frozenset((key(a), key(b))), []).append((a, b))
    depth = {}

    def inner(i):
        if i not in depth:
            near = np.linalg.norm(corners - positions[i], axis=2).min(1) > 1e-3
            hits = ray_hits(positions[i], -normals[i], corners[near])
            hits = hits[hits < SKIRT_REACH]
            torso = SKIRT_TORSO_LOW < positions[i][2] < SKIRT_TORSO_HIGH and abs(positions[i][1]) < SKIRT_TORSO_HALF_WIDTH \
                and positions[i][0] < SKIRT_BACK
            depth[i] = hits.min() + SKIRT_OVERLAP if len(hits) else SKIRT_TORSO_DEPTH if torso else SKIRT_DEPTH
        return positions[i] - normals[i] * depth[i]

    added = 0
    for group in body:
        extra = []
        for t in group['triangles']:
            for a, b in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
                if len(edges[frozenset((key(a), key(b)))]) != 1:
                    continue
                ends = []
                for i in (a, b):
                    vertices.append(dict(vertices[i], position=inner(i).tolist()))
                    ends.append(len(vertices) - 1)
                extra += [(b, a, ends[0]), (b, ends[0], ends[1]), (a, b, ends[0]), (ends[0], b, ends[1])]
                added += 1
        group['triangles'] = group['triangles'] + extra
    reached = [d for d in depth.values() if d != SKIRT_DEPTH]
    print(f'skirt depth: {len(reached)} of {len(depth)} edge vertices reach a surface, deepest {max(reached):.3f}')
    return added


OGRE_TEXTURE = 'Creature\\TwoHeadedOgre\\TwoHeadedOgreMale.blp'
HIP_ATTACHMENTS, HIP_SIDE = (32, 33), 0.51


def hips_closer(scene):
    for attachment in scene['attachments']:
        if attachment['id'] in HIP_ATTACHMENTS:
            y = attachment['position'][1]
            attachment['position'][1] = HIP_SIDE if y > 0 else -HIP_SIDE


def events_on(scene, wow, info):
    shift = np.asarray(info['new_pivots']) - np.asarray(info['pivots'])
    shift[:, 2] += info.get('lift', 0.0)
    scene['events'] = [dict(event, position=(np.asarray(event['position']) + shift[event['bone']]).tolist())
                       for event in wow['events']]


def main(out, hots, wod, tuning=TUNING):
    out, hots, wod = Path(out), Path(hots), Path(wod)
    carry_anims.HOTS_BASE = str(hots / HOTS_MODEL)
    hots_anim.ANIMS = str(hots / HOTS_ANIMS)
    wow_source = scene_from_m2(wod / 'chogall.m2', wod / 'chogall00.skin')
    fit, info = fit_body.fitted_body(m3_scene.load(str(hots / HOTS_MODEL)), wow_source,
                                     fit_body.load_tuning(tuning))
    fit['name'] = 'TwoHeadedOgreMale'
    fit['textures'] = [dict(fit['textures'][0], path=OGRE_TEXTURE)]
    print('off-hand grip moved', off_hand_grip_like_ogre(fit))
    print('main-hand grip moved', off_hand_grip_like_ogre(fit, 'R', 1, MAIN_HAND_GRIP_SHIFT))
    shield_like_weapons(fit)
    smaller_weapons(fit)
    from fixes_n import per_sequence_scales
    print('scale tracks per sequence', per_sequence_scales(fit, WEAPON_BONES))
    wow = scene_from_m2(wod / 'chogall.m2', wod / 'chogall00.skin')
    wow['name'] = 'ChoGall'
    wow['textures'] = [dict(type=0, flags=0, path=CHOGALL_TEXTURES[t['type']]) for t in wow['textures']]
    events_on(fit, wow, info)
    from carry_anims import add_carry_point, add_carry_sequences
    print('carry sequences', add_carry_sequences(fit, info))
    print('carry point', add_carry_point(fit))
    without_armor_spots(fit)
    without_armor_spots(wow)
    if os.environ.get('GRIP_PROBE'):
        for aid, shift in ((2, (0, 0, 0.6)), (21, (0.6, 0, 0))):
            probe = next(a for a in fit['attachments'] if a['id'] == aid)
            probe['position'] = (np.array(probe['position']) + shift).tolist()
            bone = fit['bones'][probe['bone']]
            bone['pivot'] = (np.array(bone['pivot']) + shift).tolist()
    fit['cameras'] = portrait_cameras((0.3, -0.16, 2.55), 2.99)
    print('held grip hangs and faces', add_held_grip(fit))
    ogre = out / 'Creature/TwoHeadedOgre'
    print(write(fit, ogre / 'TwoHeadedOgreMale.m2'))
    held, pointing = held_item_body(fit, 'TwoHeadedOgreMaleHeld')
    print('held items point', pointing, write(held, ogre / 'TwoHeadedOgreMaleHeld.m2'))
    assets.texture(hots / HOTS_DIFFUSE, ogre / 'TwoHeadedOgreMale.blp', 'opaque')
    hips_closer(wow)
    from carry_anims import copy_carry_sequences
    print('carry sequences on the WoW Cho\'Gall', copy_carry_sequences(fit, wow))
    print('carry point', add_carry_point(wow, WOW_CARRY_SHIFT))
    print('skirted edges', skirts(wow))
    print('backing triangles behind the back plates', backing(wow))
    print('sheaths moved out past the back spikes', sheaths_outside(wow))
    print('carried weapons as big as held ones', carried_weapons_like_held(wow))
    for material in wow['materials']:
        material['two_sided'] = True
    wow['cameras'] = portrait_cameras((0.2, -0.15, 2.45), 2.93)
    print('held grip hangs and faces', add_held_grip(wow))
    chogall = out / 'Creature/ChoGall'
    print(write(wow, chogall / 'ChoGall.m2'))
    held, pointing = held_item_body(wow, 'ChoGallHeld')
    print('held items point', pointing, write(held, chogall / 'ChoGallHeld.m2'))
    for name in ('ChoGallTop.blp', 'ChoGallBottom.blp'):
        shutil.copy2(wod / name.lower(), chogall / name)
    for path in sorted(out.rglob('*.*')):
        print(path.relative_to(out), hashlib.md5(path.read_bytes()).hexdigest())


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Build the Two-Players male Two-Headed Ogre from HotS and WoW files.')
    parser.add_argument('out', help='folder the Creature\\ files are written into')
    parser.add_argument('--hots', required=True, help=f'folder with {HOTS_MODEL}, {HOTS_ANIMS} and {HOTS_DIFFUSE}')
    parser.add_argument('--wod', required=True, help="folder with Cho'Gall's chogall.m2, .skin and .anim files")
    parser.add_argument('--tuning', default=TUNING)
    arguments = parser.parse_args()
    main(arguments.out, arguments.hots, arguments.wod, arguments.tuning)
