"""Turn a WoW M2 (v264/v272, with .anim files) into a scene for m2_model_writer."""
from m2_read import M2, Skin

FIELDS = (('translation', '3f'), ('rotation', '4h'), ('scale', '3f'))


def scene_from_m2(m2_path, skin_path):
    m = M2(m2_path)
    skin = Skin(skin_path)
    bones = []
    for bone in m.bones():
        channels = {}
        for field, fmt in FIELDS:
            header = bone['tracks'][field]
            interp, global_seq, nt, _, _, _ = m.u('HhIIII', header)
            if nt == 0:
                continue
            if global_seq >= 0:
                _, times, values = m.track(header, fmt, 0)
                channels[field] = dict(interp=interp, global_seq=global_seq, keys=[(times, values)])
            else:
                keys = [m.track(header, fmt, i)[1:] for i in range(len(m.sequences))]
                channels[field] = dict(interp=interp, keys=keys)
            channels[field]['global'] = global_seq
        bones.append(dict(key=bone['key'], flags=bone['flags'], parent=bone['parent'], pivot=bone['pivot'],
                          channels=channels))
    vertices = m.vertices()
    for v in vertices:
        total = sum(v['weights'])
        if total != 255 and total:
            biggest = max(range(4), key=lambda k: v['weights'][k])
            v['weights'][biggest] += 255 - total
    combos = m.lookup(128)
    groups = []
    for batch in skin.batches:
        sub = skin.submeshes[batch['section']]
        tri = skin.triangles[sub['index_start']:sub['index_start'] + sub['index_count']]
        triangles = [tuple(skin.indices[t] for t in tri[k:k + 3]) for k in range(0, len(tri), 3)]
        groups.append(dict(triangles=triangles, texture=combos[batch['texture_combo']], material=batch['material'],
                           shader=batch['shader'], batch_flags=batch['flags'], geoset=sub['id'],
                           color=batch['color']))
    blend_names = {0: 'opaque', 1: 'cutout', 2: 'alpha', 3: 'additive'}
    materials = [dict(blend=blend_names.get(bl, 'opaque'), two_sided=bool(fl & 4), unlit=bool(fl & 1),
                      unfogged=bool(fl & 2), no_depth_write=bool(fl & 16)) for fl, bl in m.materials()]
    textures = [dict(type=t['type'], flags=t['flags'], path=t['name']) for t in m.textures()]
    sequences = []
    for s in m.sequences:
        sequences.append(dict(id=s['id'], variation=s['variation'], duration=s['duration'], movespeed=s['movespeed'],
                              flags=s['flags'], minimum=s['minimum'], maximum=s['maximum'], radius=s['radius'],
                              frequency=m.u('h', m.array(28)[1] + s['index'] * 64 + 16)[0],
                              replay_min=m.u('I', m.array(28)[1] + s['index'] * 64 + 20)[0],
                              replay_max=m.u('I', m.array(28)[1] + s['index'] * 64 + 24)[0],
                              blend_time=m.u('I', m.array(28)[1] + s['index'] * 64 + 28)[0] & 0xFFFF,
                              variation_next=m.u('h', m.array(28)[1] + s['index'] * 64 + 60)[0]))
    gcount, goffset = m.array(20)
    box = m.u('7f', 160)
    return dict(name=m.data[m.u('I', 12)[0]:m.u('I', 12)[0] + m.u('I', 8)[0]].rstrip(b'\0').decode(),
                flags=0, global_sequences=list(m.u(f'{gcount}I', goffset)) if gcount else [],
                vertices=vertices, bones=bones, sequences=sequences, textures=textures, materials=materials,
                groups=groups, attachments=m.attachments(), colors=m.colors(), events=m.events(),
                bounds=dict(minimum=list(box[:3]), maximum=list(box[3:6]), radius=box[6]))
