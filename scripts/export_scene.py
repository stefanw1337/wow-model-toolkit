"""Sample Blender/FBX/OBJ assets into the toolkit's neutral scene format.

Run using Blender in background mode. Original input files are never saved.
"""
import bpy
import json
import math
import sys
import numpy as np
import copy
from pathlib import Path
from mathutils import Matrix, Vector, Quaternion


def require(ok, message):
    if not ok:
        raise ValueError(message)


def main(config_path, destination):
    cfg = json.loads(Path(config_path).read_text(encoding='utf-8-sig'))
    source = Path(cfg['source'])
    if not source.is_absolute():
        source = Path(config_path).resolve().parent / source
    if source.suffix.lower() == '.blend':
        bpy.ops.wm.open_mainfile(filepath=str(source))
    else:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        if source.suffix.lower() == '.fbx':
            bpy.ops.import_scene.fbx(filepath=str(source), anim_offset=cfg.get('fbx_frame_offset', 0))
        elif source.suffix.lower() == '.obj':
            bpy.ops.wm.obj_import(filepath=str(source), forward_axis=cfg.get('obj_forward_axis', 'NEGATIVE_Z'), up_axis=cfg.get('obj_up_axis', 'Y'))
        else:
            raise ValueError('Supported inputs: .blend, .fbx, .obj')
    scene = bpy.context.scene
    fps = float(cfg.get('fps', scene.render.fps / scene.render.fps_base))
    require(0 < fps <= 240, 'FPS must be between 0 and 240')
    animated = cfg.get('mode', 'animated') == 'animated'
    meshes = [o for o in scene.objects if o.type == 'MESH' and (not cfg.get('meshes') or o.name in cfg['meshes'])]
    require(meshes, 'No selected meshes')
    if cfg.get('meshes'):
        require(set(cfg['meshes']) == {o.name for o in meshes}, 'Some requested mesh names were not found')
    arms = [o for o in scene.objects if o.type == 'ARMATURE' and (not cfg.get('armature') or o.name == cfg['armature'])]
    require(not animated or len(arms) == 1, 'Animated export requires one selected armature')
    arm = arms[0] if animated else None
    bones = list(arm.data.bones) if arm else []
    require(len(bones) <= 256, 'M2 vertex bone indices support at most 256 bones in this exporter')
    names = {b.name: i for i, b in enumerate(bones)}
    for b in bones:
        require(not b.parent or names[b.parent.name] < names[b.name], 'Bones must be in parent-before-child order')
    if arm:
        require(arm.animation_data and arm.animation_data.action, 'Armature has no active action')
        if cfg.get('action'):
            arm.animation_data.action = bpy.data.actions[cfg['action']]
    scene.frame_set(int(cfg.get('reference_frame', 43 if animated else 0)))
    bpy.context.view_layer.update()
    # Scene coordinates are Z-up; rotate only around Z to match WoW's +X forward.
    scale = float(cfg.get('scale', 1.0))
    require(math.isfinite(scale) and scale > 0, 'Scale must be positive and finite')
    conversion = Matrix.Rotation(math.radians(cfg.get('rotation_z_degrees', 90)), 4, 'Z') @ Matrix.Scale(scale, 4)
    conversion.translation = Vector(cfg.get('offset', [0, 0, 0]))
    arm_bind = arm.matrix_world.copy() if arm else Matrix.Identity(4)
    bind = [conversion @ arm_bind @ b.matrix_local for b in bones]
    pivots = [m.translation.copy() for m in bind]
    vertices, triangles, source_vertices = [], [], []
    worst_discarded = 0.0
    for obj in meshes:
        for modifier in obj.modifiers:
            require(modifier.type == 'ARMATURE', 'Apply non-armature modifiers before export: ' + modifier.type)
            if animated:
                require(modifier.object == arm and not modifier.use_deform_preserve_volume, 'Use linear skinning on the selected armature')
        mesh = obj.data
        require(not mesh.shape_keys, 'Bake shape-key animation before export; skeletal tracks only')
        require(mesh.uv_layers.active, 'Mesh requires a UV map: ' + obj.name)
        mesh.calc_loop_triangles()
        matrix = conversion @ obj.matrix_world
        require(matrix.determinant() > 0, 'Apply mirrored transforms before export')
        normals = matrix.to_3x3().inverted().transposed()
        uv = mesh.uv_layers.active.data
        groups = {g.index: names.get(g.name) for g in obj.vertex_groups}
        cache = {}
        for tri in mesh.loop_triangles:
            ids = []
            for loop_id in tri.loops:
                li = mesh.loops[loop_id]
                v = mesh.vertices[li.vertex_index]
                pos = matrix @ v.co
                normal = (normals @ mesh.corner_normals[loop_id].vector).normalized()
                tex = uv[loop_id].uv
                influences = sorted([(groups[g.group], g.weight) for g in v.groups if groups.get(g.group) is not None and g.weight > 0], key=lambda x: -x[1]) if animated else [(0, 1.0)]
                require(influences, 'Unweighted vertex in ' + obj.name)
                total = sum(w for _, w in influences)
                discarded = sum(w for _, w in influences[4:]) / total
                worst_discarded = max(worst_discarded, discarded)
                require(discarded <= cfg.get('max_discarded_weight', 0.02), 'More than four significant bone weights on a vertex')
                influences = influences[:4]
                total = sum(w for _, w in influences)
                weights = [int(round(w / total * 255)) for _, w in influences]
                weights[0] += 255 - sum(weights)
                bone_ids = [i for i, _ in influences]
                weights += [0] * (4-len(weights)); bone_ids += [0] * (4-len(bone_ids))
                data = dict(position=list(pos), normal=list(normal), uv=[tex.x, 1-tex.y], weights=weights, bones=bone_ids)
                key = (li.vertex_index, tuple(round(x, 7) for x in data['normal']), tuple(data['uv']))
                if key not in cache:
                    cache[key] = len(vertices)
                    vertices.append(data)
                    source_vertices.append((obj, li.vertex_index))
                ids.append(cache[key])
            triangles.append(ids)
    require(len(vertices) <= 65535 and len(triangles)*3 <= 65535, 'Single-section limit exceeded; split the source asset')
    result = dict(format='wow-model-toolkit-scene-v1', source=str(source), fps=fps, vertices=vertices, triangles=triangles, bones=[], sequences=[], collision=None)
    result['bones'] = [dict(name=b.name, parent=names[b.parent.name] if b.parent else -1, pivot=list(pivots[i])) for i,b in enumerate(bones)] if arm else [dict(name='Root', parent=-1, pivot=[0,0,0])]
    clips = cfg.get('animations', []) if animated else [dict(name='Stand', id=0, ranges=[[0,1]], loop=True)]
    require(clips, 'Animated export requires configured clips')
    require(len({c['id'] for c in clips}) == len(clips), 'Duplicate animation IDs are not supported')
    cache_frames = {}
    max_matrix_error, max_vertex_error = 0.0, 0.0
    depsgraph = bpy.context.evaluated_depsgraph_get()
    def sample(frame):
        nonlocal max_matrix_error, max_vertex_error
        if frame in cache_frames:
            return cache_frames[frame]
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        skin = [conversion @ arm.matrix_world @ arm.pose.bones[b.name].matrix @ bind[i].inverted() for i,b in enumerate(bones)] if arm else [Matrix.Identity(4)]
        tracks=[]
        for i,bone in enumerate(result['bones']):
            local = skin[bone['parent']].inverted() @ skin[i] if bone['parent'] >= 0 else skin[i]
            loc, rotation, scaling = local.decompose()
            reconstructed = Matrix.LocRotScale(loc, rotation, scaling)
            error = max(abs(local[r][c]-reconstructed[r][c]) for r in range(4) for c in range(4))
            max_matrix_error=max(max_matrix_error,error)
            require(error < cfg.get('max_matrix_error',0.002), 'Bone animation contains unsupported shear: frame=%s bone=%s error=%g scale=%s' % (frame,bone['name'],error,list(scaling)))
            pivot = Vector(bone['pivot'])
            translation = loc-pivot+local.to_3x3() @ pivot
            tracks.append(dict(translation=list(translation), rotation=[rotation.x,rotation.y,rotation.z,rotation.w], scale=list(scaling)))
        evaluated={o.name:o.evaluated_get(depsgraph) for o in meshes}
        points=[]
        for v,(obj,index) in zip(vertices,source_vertices):
            original=Vector(v['position'])
            transformed=sum(((skin[bid] @ original)*(weight/255) for bid,weight in zip(v['bones'],v['weights']) if weight), Vector((0,0,0)))
            points.append(list(transformed))
            if animated:
                e=evaluated[obj.name]
                expected=conversion @ e.matrix_world @ e.data.vertices[index].co
                max_vertex_error=max(max_vertex_error,(expected-transformed).length)
        data=dict(tracks=tracks,minimum=[min(p[i] for p in points) for i in range(3)],maximum=[max(p[i] for p in points) for i in range(3)],radius=max(Vector(p).length for p in points))
        cache_frames[frame]=data
        return data
    for clip in clips:
        frames=[]
        exclusive=cfg.get('frame_end_exclusive',False)
        for start,end in clip['ranges']:
            require(isinstance(start,int) and isinstance(end,int) and end>start, 'Frame ranges must be increasing integer pairs')
            # Shared boundaries are included once. Disjoint spans are concatenated.
            part=list(range(start,end if exclusive else end+1))
            frames.extend(part[1:] if not exclusive and frames and frames[-1]==start else part)
        if exclusive:frames.append(frames[-1])
        speed=float(clip.get('playback_rate',1))
        require(speed>0, 'Playback rate must be positive')
        samples=[sample((frames[0] if clip.get('hold',False) else f)+cfg.get('source_frame_offset',0)) for f in frames]
        if 'ground_clamp_z' in clip:
            # Some source death clips intentionally sink into a different scene or effect.
            # A profile can keep the complete exported body above the WoW ground plane.
            samples=copy.deepcopy(samples)
            for sampled in samples:
                dz=max(0,float(clip['ground_clamp_z'])-sampled['minimum'][2])
                for bi,bone in enumerate(result['bones']):
                    if bone['parent']<0:sampled['tracks'][bi]['translation'][2]+=dz
                sampled['minimum'][2]+=dz;sampled['maximum'][2]+=dz;sampled['radius']+=dz
        timestamps=[round(i*1000/fps/speed) for i in range(len(frames))]
        require(len(set(timestamps))==len(timestamps), 'Sample rate exceeds millisecond resolution')
        sequence=dict(name=clip['name'],id=clip['id'],loop=clip.get('loop',False),duration=timestamps[-1],timestamps=timestamps,source_frames=frames,movespeed=clip.get('movespeed',0),tracks=[[] for _ in result['bones']], minimum=[min(s['minimum'][i] for s in samples) for i in range(3)],maximum=[max(s['maximum'][i] for s in samples) for i in range(3)],radius=max(s['radius'] for s in samples))
        for s in samples:
            for bi,track in enumerate(s['tracks']):sequence['tracks'][bi].append(track)
        # Optional short blend makes sampled locomotion loops meet at their endpoints.
        blend_frames=int(clip.get('loop_blend_frames',0))
        require(not blend_frames or clip.get('loop',False),'Loop blending requires a loop clip')
        if blend_frames:
            require(1<=blend_frames<len(frames),'Invalid loop blend length')
            for tracks in sequence['tracks']:
                target=tracks[0]
                for k in range(len(tracks)-blend_frames,len(tracks)):
                    factor=(k-(len(tracks)-blend_frames)+1)/blend_frames
                    old=tracks[k];a=Quaternion((old['rotation'][3],*old['rotation'][:3]));b=Quaternion((target['rotation'][3],*target['rotation'][:3]));q=a.slerp(b,factor)
                    tracks[k]=dict(translation=[a*(1-factor)+b*factor for a,b in zip(old['translation'],target['translation'])],scale=[a*(1-factor)+b*factor for a,b in zip(old['scale'],target['scale'])],rotation=[q.x,q.y,q.z,q.w])
            for k in range(len(frames)-blend_frames,len(frames)):
                matrices=[]
                for bi,bone in enumerate(result['bones']):
                    t=sequence['tracks'][bi][k];q=Quaternion((t['rotation'][3],*t['rotation'][:3]));p=Vector(bone['pivot'])
                    m=Matrix.LocRotScale(Vector((0,0,0)),q,Vector(t['scale']));m.translation=Vector(t['translation'])+p-m.to_3x3() @ p
                    if bone['parent']>=0:m=matrices[bone['parent']] @ m
                    matrices.append(m)
                for v in vertices:
                    point=sum(((matrices[bid] @ Vector(v['position']))*(w/255) for bid,w in zip(v['bones'],v['weights']) if w),Vector((0,0,0)))
                    sequence['minimum']=[min(a,b) for a,b in zip(sequence['minimum'],point)]
                    sequence['maximum']=[max(a,b) for a,b in zip(sequence['maximum'],point)]
                    sequence['radius']=max(sequence['radius'],point.length)
        sequence['minimum']=[x-0.005 for x in sequence['minimum']]
        sequence['maximum']=[x+0.005 for x in sequence['maximum']]
        sequence['radius']+=0.005
        result['sequences'].append(sequence)
        print('Sampled',clip['name'],len(frames),'frames',flush=True)
    require(max_vertex_error <= cfg.get('max_skinning_error',0.02), 'Skinning differs from Blender: '+str(max_vertex_error))
    result['validation']=dict(sampled_frames=len(cache_frames),max_matrix_error=max_matrix_error,max_vertex_error=max_vertex_error,max_discarded_weight=worst_discarded)
    collision=cfg.get('collision',{'mode':'none'})
    if collision['mode']=='mesh':
        require(not animated, 'NPC exports do not use collision meshes')
        obj=bpy.data.objects[collision['object']]
        require(obj.type=='MESH', 'Collision object must be a mesh')
        obj.data.calc_loop_triangles()
        result['collision']=dict(vertices=[list(conversion @ obj.matrix_world @ v.co) for v in obj.data.vertices],triangles=[list(t.vertices) for t in obj.data.loop_triangles])
    else:
        require(collision['mode']=='none','Collision mode must be none or mesh')
    Path(destination).write_text(json.dumps(result,separators=(',',':')))
    print('EXPORT_REPORT='+json.dumps(result['validation']))


if __name__=='__main__':
    args=sys.argv[sys.argv.index('--')+1:]
    main(*args)
