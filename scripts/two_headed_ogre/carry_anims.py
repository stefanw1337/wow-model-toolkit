"""Retarget the HotS Cho'Gall horse-carrying animations onto the WoW Cho'Gall skeleton of the fit."""
import numpy as np

from hots_anim import Anims
from m3_scene import load
from retarget import CHAINS, SIDES, align, bone_map, to_wow

HOTS_BASE = None
GRAB, GRAB_CLOSED, GRAB_THROWN = 226, 227, 228
MOUNT_CAST_MS = 1500
CARRY_SEQUENCES = ((GRAB_CLOSED, 'Stand Ridenone', 0, 0, 0.0),
                   (GRAB_THROWN, 'Walk A Ridenone', 5, 0, 7.4),
                   (GRAB, 'Channel Mount', 0, MOUNT_CAST_MS, 0.0))
SKIPPED = ('Twist', 'Lat_', 'Breast', 'Belly_', 'HipPlate', 'Buttock', 'ShoulderPlate', 'Skirt')
SAMPLE_MS = 33
FOLLOW_INSTEAD = {106: 3, 107: 3}
CARRY_POINT = 48
CARRY_HAND = 57
CARRY_FOREARM = 43
PALM_REACH = 0.12
BELLY_DROP = 0.55
CARRY_HEAD = 28
TOWARD_HEAD = 0.45
ABOVE_HEAD = 0.05
TO_WOW = np.array([[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])


def orthonormal(m):
    u, _, vt = np.linalg.svd(m)
    r = u @ vt
    return r if np.linalg.det(r) > 0 else u @ np.diag([1, 1, -1]) @ vt


def quaternion(r):
    t = np.trace(r)
    if t > 0:
        s = np.sqrt(t + 1.0) * 2
        q = [(r[2, 1] - r[1, 2]) / s, (r[0, 2] - r[2, 0]) / s, (r[1, 0] - r[0, 1]) / s, 0.25 * s]
    elif r[0, 0] > r[1, 1] and r[0, 0] > r[2, 2]:
        s = np.sqrt(1.0 + r[0, 0] - r[1, 1] - r[2, 2]) * 2
        q = [0.25 * s, (r[0, 1] + r[1, 0]) / s, (r[0, 2] + r[2, 0]) / s, (r[2, 1] - r[1, 2]) / s]
    elif r[1, 1] > r[2, 2]:
        s = np.sqrt(1.0 + r[1, 1] - r[0, 0] - r[2, 2]) * 2
        q = [(r[0, 1] + r[1, 0]) / s, 0.25 * s, (r[1, 2] + r[2, 1]) / s, (r[0, 2] - r[2, 0]) / s]
    else:
        s = np.sqrt(1.0 + r[2, 2] - r[0, 0] - r[1, 1]) * 2
        q = [(r[0, 2] + r[2, 0]) / s, (r[1, 2] + r[2, 1]) / s, 0.25 * s, (r[1, 0] - r[0, 1]) / s]
    q = np.array(q)
    return q / np.linalg.norm(q)


def encode_quaternion(q):
    return [int(round(v * 32767 - 32768)) if v >= 0 else int(round(v * 32767 + 32767)) for v in q]


def rest_alignment(base, info):
    names = [b['name'] for b in base['bones']]
    parents = [b['parent'] for b in base['bones']]
    joints = np.asarray(info['joints'])
    posed = np.asarray(info['posed'])
    chain_child = {}
    for side, s in SIDES.items():
        for a, b, _, _ in CHAINS:
            chain_child[names.index(a.format(s=side))] = names.index(b.format(s=side))
    rotation = []
    for i in range(len(names)):
        parent_rot = rotation[parents[i]] if parents[i] >= 0 else np.eye(3)
        if i in chain_child:
            c = chain_child[i]
            rotation.append(align(parent_rot @ (joints[c] - joints[i]), posed[c] - posed[i]) @ parent_rot)
        else:
            rotation.append(parent_rot)
    return names, rotation


def primary_sources():
    chosen = {}
    for name, wow_bone in bone_map().items():
        if any(skip in name for skip in SKIPPED) or wow_bone in chosen:
            continue
        chosen[wow_bone] = name
    return chosen


def sampled_pose(scene, anims, sequence, t, keys, alignment, scale, rest_root):
    base_names, align_rot = alignment
    deltas = anims.deltas(sequence, t, keys)
    by_name = {n: i for i, n in enumerate(anims.names)}
    sources = primary_sources()
    world = []
    local = []
    for w, bone in enumerate(scene['bones']):
        parent = world[bone['parent']] if bone['parent'] >= 0 else np.eye(3)
        name = sources.get(w)
        if name in by_name and name in base_names:
            d = TO_WOW @ orthonormal(deltas[by_name[name]][:3, :3]) @ TO_WOW.T
            target = d @ align_rot[base_names.index(name)].T
            local.append(parent.T @ target)
            world.append(target)
        else:
            local.append(None)
            world.append(parent)
    root = deltas[by_name['Bone_Root']]
    moved = (root @ np.append(rest_root, 1.0))[:3]
    shift = to_wow(moved - rest_root) * scale
    for bone, follows in FOLLOW_INSTEAD.items():
        parent = world[scene['bones'][bone]['parent']]
        local[bone] = parent.T @ world[follows]
    return local, shift


def copy_event_times(scene, like, duration):
    like_duration = max(1, scene['sequences'][like]['duration'])
    for event in scene.get('events', []):
        times = event['times']
        moments = [] if event.get('global_seq', -1) >= 0 or like >= len(times) else \
            [int(round(t * duration / like_duration)) for t in times[like]]
        event['times'] = list(times) + [moments]


def duplicate_keys(channel, source, duration, source_duration):
    times, values = channel['keys'][source]
    factor = duration / max(1, source_duration)
    return [int(round(t * factor)) for t in times], list(values)


def add_carry_sequences(scene, info, chosen=CARRY_SEQUENCES):
    anims = Anims()
    base = load(HOTS_BASE)
    alignment = rest_alignment(base, info)
    raw = np.array([to_wow(np.linalg.inv(m)[:3, 3]) for m in base['inverse_bind']])
    joints = np.asarray(info['joints'])
    scale = float(np.linalg.norm(joints[5] - joints[0]) / np.linalg.norm(raw[5] - raw[0]))
    root_index = anims.names.index('Bone_Root')
    rest_root = np.linalg.inv(anims.inverse_bind[root_index])[:3, 3]
    sources = primary_sources()
    added = []
    for sequence_id, hots_name, like_id, stretched, movespeed in chosen:
        like = next(i for i, s in enumerate(scene['sequences']) if s['id'] == like_id and s['variation'] == 0)
        native = anims.duration(hots_name)
        duration = stretched or native
        keys = anims.keys(hots_name)
        times = list(range(0, duration, SAMPLE_MS)) + [duration]
        poses = [sampled_pose(scene, anims, hots_name, t * native / duration, keys, alignment, scale, rest_root)
                 for t in times]
        for w, bone in enumerate(scene['bones']):
            channels = bone['channels']
            for field, channel in list(channels.items()):
                if channel.get('global', -1) >= 0:
                    continue
                channel['keys'].append(duplicate_keys(channel, like, duration, scene['sequences'][like]['duration']))
            overridden = poses[0][0][w] is not None
            if overridden:
                values = [encode_quaternion(quaternion(local[w])) for local, _ in poses]
                rotation = channels.setdefault('rotation', dict(interp=1, **{'global': -1},
                                                                keys=[([], [])] * len(scene['sequences'])))
                if len(rotation['keys']) == len(scene['sequences']):
                    rotation['keys'].append(None)
                rotation['keys'][-1] = (times, values)
            if w == 1:
                translation = channels.setdefault('translation', dict(interp=1, **{'global': -1},
                                                                      keys=[([], [])] * len(scene['sequences'])))
                if len(translation['keys']) == len(scene['sequences']):
                    translation['keys'].append(None)
                translation['keys'][-1] = (times, [list(map(float, shift)) for _, shift in poses])
        record = dict(scene['sequences'][like], id=sequence_id, variation=0, duration=duration,
                      frequency=32767, variation_next=-1, movespeed=movespeed)
        scene['sequences'].append(record)
        copy_event_times(scene, like, duration)
        added.append((sequence_id, hots_name, duration, len(sources)))
    return added


def extend_other_tracks(scene, like, duration):
    count = len(scene['sequences'])
    like_duration = scene['sequences'][like]['duration']

    def visit(node):
        if isinstance(node, dict):
            keys = node.get('keys')
            if isinstance(keys, list) and len(keys) == count and node.get('global', node.get('global_seq', -1)) < 0:
                keys.append(duplicate_keys(node, like, duration, like_duration))
                return
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    for name, value in scene.items():
        if name not in ('bones', 'sequences'):
            visit(value)


def copy_carry_sequences(source, target):
    shared = min(len(source['bones']), len(target['bones']))
    copied = []
    for index, record in enumerate(source['sequences']):
        if record['id'] not in (GRAB, GRAB_CLOSED, GRAB_THROWN):
            continue
        like = next(i for i, s in enumerate(target['sequences']) if s['id'] == (5 if record['id'] == GRAB_THROWN else 0)
                    and s['variation'] == 0)
        duration = record['duration']
        for w, bone in enumerate(target['bones']):
            channels = bone['channels']
            for field, channel in list(channels.items()):
                if channel.get('global', -1) >= 0:
                    continue
                channel['keys'].append(duplicate_keys(channel, like, duration, target['sequences'][like]['duration']))
            if w >= shared:
                continue
            for field in ('rotation', 'translation'):
                track = source['bones'][w]['channels'].get(field)
                if not track or track.get('global', -1) >= 0 or not track['keys'][index][0]:
                    continue
                if field == 'translation' and w != 1:
                    continue
                own = channels.setdefault(field, dict(interp=1, **{'global': -1},
                                                      keys=[([], [])] * len(target['sequences'])))
                if len(own['keys']) == len(target['sequences']):
                    own['keys'].append(None)
                own['keys'][-1] = (list(track['keys'][index][0]), list(track['keys'][index][1]))
        extend_other_tracks(target, like, duration)
        target['sequences'].append(dict(target['sequences'][like], id=record['id'], variation=0, duration=duration,
                                        frequency=32767, variation_next=-1, movespeed=record['movespeed']))
        copy_event_times(target, like, duration)
        copied.append(record['id'])
    return copied


def add_carry_point(scene, shift=(0.0, 0.0, 0.0)):
    from pose import bone_matrices
    carried = [i for i, seq in enumerate(scene['sequences']) if seq['id'] in (GRAB_CLOSED, GRAB_THROWN, GRAB)]
    stand_carry = next(i for i in carried if scene['sequences'][i]['id'] == GRAB_CLOSED)
    hand = scene['bones'][CARRY_HAND]
    rest = bone_matrices(scene, stand_carry, 0)
    wrist = (rest[CARRY_HAND] @ np.append(hand['pivot'], 1))[:3]
    elbow = (rest[CARRY_FOREARM] @ np.append(scene['bones'][CARRY_FOREARM]['pivot'], 1))[:3]
    palm = wrist + PALM_REACH * (wrist - elbow) / np.linalg.norm(wrist - elbow)
    head = (rest[CARRY_HEAD] @ np.append(scene['bones'][CARRY_HEAD]['pivot'], 1))[:3]
    palm[:2] += TOWARD_HEAD * (head[:2] - palm[:2])
    palm[2] = max(palm[2], head[2]) + ABOVE_HEAD
    pivot = (np.linalg.inv(rest[CARRY_HAND]) @ np.append(palm, 1))[:3]
    bone = dict(key=-1, flags=hand['flags'], parent=CARRY_HAND, pivot=pivot.tolist(), channels={})
    keys = [([], []) for _ in scene['sequences']]
    for index in carried:
        duration = scene['sequences'][index]['duration']
        times = list(range(0, duration, SAMPLE_MS)) + [duration]
        values = []
        for t in times:
            hand_world = orthonormal(bone_matrices(scene, index, t)[CARRY_HAND][:3, :3])
            values.append(encode_quaternion(quaternion(hand_world.T)))
        keys[index] = (times, values)
    bone['channels']['rotation'] = {'interp': 1, 'global': -1, 'keys': keys}
    scene['bones'].append(bone)
    scene['attachments'] = [a for a in scene['attachments'] if a['id'] != CARRY_POINT]
    scene['attachments'].append(dict(id=CARRY_POINT, bone=len(scene['bones']) - 1,
                                     position=(pivot + (0.0, 0.0, -BELLY_DROP) + np.asarray(shift)).tolist()))
    return np.round(palm, 2).tolist()
