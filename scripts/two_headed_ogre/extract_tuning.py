import json, pickle, sys
import numpy as np

WEAPON_BONES = (106, 107, 115, 116, 117, 118, 119, 133, 134, 135, 136, 137)
HAIR_BONES = range(142, 152)
CLOTH_REGION = 4


def plain(value):
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    if isinstance(value, np.generic):
        return value.item()
    return value


def main(fit_path, out_path):
    fit, info = pickle.load(open(fit_path, 'rb'))
    cloth = [dict(bones=v['bones'], weights=v['weights']) for v in fit['vertices'] if v['region'] == CLOTH_REGION]
    tuning = dict(
        cloth_weights=cloth,
        hair_channels={i: fit['bones'][i]['channels'] for i in HAIR_BONES},
        weapon_bones={i: dict(pivot=fit['bones'][i]['pivot'], channels=fit['bones'][i]['channels'])
                      for i in WEAPON_BONES},
        attachments=fit['attachments'],
        blend_times={i: s['blend_time'] for i, s in enumerate(fit['sequences'])},
    )
    json.dump(plain(tuning), open(out_path, 'w'), separators=(',', ':'))


if __name__ == '__main__':
    main(*sys.argv[1:])
