"""Create a rigged Blender scene and export configuration from a D3 model profile.

Run with Blender --background --python import_d3.py -- profile.json output_directory.
Native animation channels are sampled at integer source frames. No Max license is needed.
"""
import sys
import json
import bisect
import math
from pathlib import Path
import bpy
from mathutils import Matrix, Quaternion, Vector
sys.path.insert(0, str(Path(__file__).resolve().parent))
from d3_assets import appearance, animation, require


def trs(values):
    x,y,z,w,px,py,pz,s=values
    return Matrix.LocRotScale(Vector((px,py,pz)),Quaternion((w,x,y,z)).normalized(),Vector((s,s,s)))


def interpolate(keys, frame, default, quaternion=False):
    if not keys:
        return default
    index=max(0,bisect.bisect_right([k[0] for k in keys],frame)-1)
    a=keys[index]
    b=keys[min(index+1,len(keys)-1)]
    factor=0 if a[0]==b[0] else max(0,min(1,(frame-a[0])/(b[0]-a[0])))
    if quaternion:
        qa=Quaternion((a[4],*a[1:4])).normalized()
        qb=Quaternion((b[4],*b[1:4])).normalized()
        return qa.slerp(qb,factor)
    if len(a)==2:
        return a[1]*(1-factor)+b[1]*factor
    return Vector(a[1:]).lerp(Vector(b[1:]),factor)


def main(profile_path,out):
    profile=json.loads(Path(profile_path).read_text())
    base=Path(profile['data_root']);out=Path(out).resolve()
    require(not out.exists(),'Use a new import directory')
    out.mkdir(parents=True)
    model=appearance(base/'Appearance'/profile['appearance'])
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene=bpy.context.scene;scene.render.fps=30
    armdata=bpy.data.armatures.new('D3 Skeleton')
    arm=bpy.data.objects.new('Armature',armdata);scene.collection.objects.link(arm)
    bpy.context.view_layer.objects.active=arm;arm.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    binds=[]
    for bone in model['bones']:
        bind=trs(bone['transforms'][0]);binds.append(bind)
        eb=armdata.edit_bones.new(bone['name']);eb.head=bind.translation
        eb.tail=bind.translation+bind.to_3x3()@Vector((0,0.3,0))
        eb.matrix=bind
        if bone['parent']>=0:eb.parent=armdata.edit_bones[model['bones'][bone['parent']]['name']]
    bpy.ops.object.mode_set(mode='OBJECT')
    # The third transform is the local bind pose; validate it against the world bind.
    for i,bone in enumerate(model['bones']):
        expected=trs(bone['transforms'][2])
        if bone['parent']>=0:expected=binds[bone['parent']]@expected
        require(max(abs(expected[r][c]-binds[i][r][c]) for r in range(4) for c in range(4))<0.001,'APP bind hierarchy mismatch')
    selected={entry['mesh']:entry for entry in profile['meshes']}
    require(len(selected)==len(profile['meshes']),'Duplicate selected mesh')
    found=set()
    for subset in model['meshes']:
        if subset['name'] not in selected:continue
        found.add(subset['name']);entry=selected[subset['name']]
        mesh=bpy.data.meshes.new(subset['name'])
        mesh.from_pydata([v['position'] for v in subset['vertices']],[],subset['triangles']);mesh.update()
        obj=bpy.data.objects.new(subset['name'],mesh);scene.collection.objects.link(obj)
        uv=mesh.uv_layers.new(name='UVMap')
        rect=entry.get('atlas_rect',[0,0,1,1])
        for loop in mesh.loops:
            u,v=subset['vertices'][loop.vertex_index]['uv']
            require(-0.01<=u<=1.01 and -0.01<=v<=1.01,'Atlas conversion requires normalized UVs')
            uv.data[loop.index].uv=(rect[0]+u*rect[2],1-(rect[1]+v*rect[3]))
        for polygon in mesh.polygons:polygon.use_smooth=True
        for bone in model['bones']:obj.vertex_groups.new(name=bone['name'])
        for vi,vertex in enumerate(subset['vertices']):
            for bid,weight in vertex['weights']:obj.vertex_groups[bid].add([vi],weight,'REPLACE')
        mod=obj.modifiers.new('D3 skin','ARMATURE');mod.object=arm
    require(found==set(selected),'Missing selected mesh')
    for pb in arm.pose.bones:pb.rotation_mode='QUATERNION'
    ranges={};cursor=1;report=[]
    for filename in dict.fromkeys(c['file'] for c in profile['animations']):
        ani=animation(base/'Anim'/filename)
        rotation_settings=[c.get('root_rotation_y_degrees',0) for c in profile['animations'] if c['file']==filename]
        require(all(v==rotation_settings[0] for v in rotation_settings),'Conflicting source-clip rotations')
        rotation_setting=rotation_settings[0]
        require(set(ani['tracks']).issubset({b['name'] for b in model['bones']}),'Animation contains unknown bones')
        print('IMPORT',filename,ani['frames'],flush=True)
        for frame in range(ani['frames']):
            scene.frame_set(cursor+frame)
            worlds=[]
            for i,bone in enumerate(model['bones']):
                default=bone['transforms'][2];channels=ani['tracks'].get(bone['name'],{})
                loc=interpolate(channels.get('translation',[]),frame,Vector(default[4:7]))
                rot=interpolate(channels.get('rotation',[]),frame,Quaternion((default[3],*default[:3])),True)
                scale=interpolate(channels.get('scale',[]),frame,default[7])
                local=Matrix.LocRotScale(loc,rot,Vector((scale,)*3))
                if bone['parent']<0 and rotation_setting:
                    angle=(rotation_setting[0]+(rotation_setting[1]-rotation_setting[0])*frame/max(1,ani['frames']-1)) if isinstance(rotation_setting,list) else rotation_setting
                    local=Matrix.Rotation(math.radians(angle),4,'Y')@local
                world=worlds[bone['parent']]@local if bone['parent']>=0 else local
                worlds.append(world)
                # matrix_basis is relative to the edit-bone rest transform and parent pose.
                rest=armdata.bones[bone['name']].matrix_local
                relative_rest=(armdata.bones[model['bones'][bone['parent']]['name']].matrix_local.inverted()@rest) if bone['parent']>=0 else rest
                pb=arm.pose.bones[bone['name']];pb.matrix_basis=relative_rest.inverted()@local
                pb.keyframe_insert('location',frame=cursor+frame)
                pb.keyframe_insert('rotation_quaternion',frame=cursor+frame)
                pb.keyframe_insert('scale',frame=cursor+frame)
            bpy.context.view_layer.update()
            error=max(abs(arm.pose.bones[b['name']].matrix[r][c]-worlds[i][r][c]) for i,b in enumerate(model['bones']) for r in range(4) for c in range(4))
            require(error<0.003,'Blender/native animation matrix mismatch: '+str(error))
        ranges[filename]=[cursor,cursor+ani['frames']-1]
        report.append(dict(file=filename,frames=ani['frames'],range=ranges[filename]))
        cursor+=ani['frames']+2
    scene.frame_start=1;scene.frame_end=cursor-3;scene.frame_set(1)
    destination=out/(profile['name']+'.blend')
    bpy.ops.wm.save_as_mainfile(filepath=str(destination))
    cfg=dict(mode='animated',source=str(destination),meshes=list(selected),armature='Armature',fps=30,
             reference_frame=1,source_frame_offset=0,frame_end_exclusive=False,
             rotation_z_degrees=profile.get('rotation_z_degrees',0),scale=profile['scale'],collision={'mode':'none'},
             texture=str(out/'diffuse.png'),model_path=profile['model_path'],texture_path=profile['texture_path'],
             material=profile.get('material',{'blend':'opaque'}),patch_name=profile['patch_name'],animations=[])
    if profile.get('animation_transitions'):
        cfg['animation_transitions']=profile['animation_transitions']
    for clip in profile['animations']:
        c={k:v for k,v in clip.items() if k not in ('file','root_rotation_y_degrees')};start,end=ranges[clip['file']]
        c['ranges']=[[start,max(start+1,end)]]
        cfg['animations'].append(c)
    (out/'model.json').write_text(json.dumps(cfg,indent=2))
    (out/'import-report.json').write_text(json.dumps(dict(source=profile,bones=len(model['bones']),clips=report),indent=2))


if __name__=='__main__':
    main(*sys.argv[sys.argv.index('--')+1:])
