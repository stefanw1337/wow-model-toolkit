import json

import numpy as np

import adjust
import fixes_n
import physics
import retarget

SCALE = 0.75
ABDUCTION = 15
HIP_PLATES_BACK = 0.12
CLOTH_REGION = 4
BODY_FIELDS = ('name', 'flags', 'global_sequences', 'vertices', 'bones', 'sequences', 'textures', 'materials',
               'groups', 'attachments', 'bounds')


def tuple_keys(channels):
    for channel in channels.values():
        channel['keys'] = [(list(times), [tuple(v) if isinstance(v, list) else v for v in values])
                           for times, values in channel['keys']]
    return channels


def fitted_body(hots, wow, tuning):
    extra, chains = physics.planned(len(wow['bones']))
    scene, info = retarget.retarget(wow, hots, SCALE, extra_map=extra, abduct=ABDUCTION)
    adjust.hip_plates_inward(scene, hots, amount=0.0, back=HIP_PLATES_BACK)
    physics.add_chains(scene, info, hots, chains)
    for bone, channels in tuning['hair_channels'].items():
        scene['bones'][int(bone)]['channels'] = tuple_keys(channels)
    cloth = [v for v in scene['vertices'] if v['region'] == CLOTH_REGION]
    if len(cloth) != len(tuning['cloth_weights']):
        raise SystemExit(f"the loincloth has {len(cloth)} vertices, the tuning {len(tuning['cloth_weights'])}")
    for vertex, weights in zip(cloth, tuning['cloth_weights']):
        vertex['bones'], vertex['weights'] = list(weights['bones']), list(weights['weights'])
    info['lift'] = fixes_n.flat_feet(scene)
    for bone, values in tuning['weapon_bones'].items():
        scene['bones'][int(bone)]['pivot'] = list(values['pivot'])
        scene['bones'][int(bone)]['channels'] = tuple_keys(values['channels'])
    scene['attachments'] = [dict(a, position=list(a['position'])) for a in tuning['attachments']]
    for index, blend in tuning['blend_times'].items():
        scene['sequences'][int(index)]['blend_time'] = blend
    return {field: scene[field] for field in BODY_FIELDS}, info


def load_tuning(path):
    with open(path, encoding='utf-8') as file:
        return json.load(file)
