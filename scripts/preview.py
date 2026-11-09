"""Render poses decoded from the exported M2, using Blender background mode."""
import bpy
import json
import sys
from pathlib import Path
from mathutils import Vector
sys.path.insert(0,str(Path(__file__).resolve().parent))
from validate import read,pose

args=sys.argv[sys.argv.index('--')+1:]
model_path,texture_path,output=args
out=Path(output).resolve();out.mkdir(parents=True,exist_ok=True)
model=read(model_path)
bpy.ops.wm.read_factory_settings(use_empty=True)
scene=bpy.context.scene
scene.render.engine='CYCLES';scene.cycles.samples=24
scene.render.resolution_x=480;scene.render.resolution_y=480;scene.render.resolution_percentage=100
scene.world=bpy.data.worlds.new('Studio');scene.world.use_nodes=True
scene.world.node_tree.nodes['Background'].inputs[0].default_value=(0.16,0.18,0.22,1)
scene.world.node_tree.nodes['Background'].inputs[1].default_value=0.5
material=bpy.data.materials.new('Exported diffuse');material.use_nodes=True
nodes=material.node_tree.nodes;shader=nodes.get('Principled BSDF');shader.inputs['Roughness'].default_value=0.85
image=nodes.new('ShaderNodeTexImage');image.image=bpy.data.images.load(str(Path(texture_path).resolve()))
material.node_tree.links.new(image.outputs['Color'],shader.inputs['Base Color'])
bpy.ops.object.camera_add(location=(5,-6,3.3));camera=bpy.context.object;scene.camera=camera
camera.rotation_euler=(Vector((0,0,1))-camera.location).to_track_quat('-Z','Y').to_euler();camera.data.type='ORTHO';camera.data.ortho_scale=3.8
for location,power,size in [((4,-4,6),850,5),((-3,-2,4),600,4),((1,4,4),900,3)]:
    bpy.ops.object.light_add(type='AREA',location=location);o=bpy.context.object;o.data.energy=power;o.data.shape='DISK';o.data.size=size;o.rotation_euler=(Vector((0,0,1))-o.location).to_track_quat('-Z','Y').to_euler()
bpy.ops.mesh.primitive_plane_add(size=200,location=(0,0,-0.025));plane=bpy.context.object
ground=bpy.data.materials.new('Ground');ground.diffuse_color=(0.065,0.075,0.095,1);plane.data.materials.append(ground)
outputs=[]
for anim,fraction in [(0,0.3),(4,0.3),(16,0.45),(1,0.8),(6,0),(14,0.5)]:
    si=next((i for i,s in enumerate(model['sequences']) if s['id']==anim),None)
    if si is None:continue
    vertices=pose(model,si,model['sequences'][si]['duration']*fraction)
    lower=Vector(vertices.min(0));upper=Vector(vertices.max(0));target=(lower+upper)*0.5
    extent=max(upper-lower)
    camera.location=target+Vector((5,-6,3.3))*max(1,extent/3)
    camera.rotation_euler=(target-camera.location).to_track_quat('-Z','Y').to_euler()
    camera.data.ortho_scale=max(2.0,extent*1.3)
    mesh=bpy.data.meshes.new('Decoded M2');mesh.from_pydata(vertices.tolist(),[],model['triangles'].tolist());mesh.update()
    uv=mesh.uv_layers.new(name='UVMap')
    for loop in mesh.loops:
        u,v=model['vertices'][loop.vertex_index,14:16];uv.data[loop.index].uv=(u,1-v)
    for p in mesh.polygons:p.use_smooth=True
    obj=bpy.data.objects.new('Exported pose',mesh);scene.collection.objects.link(obj);mesh.materials.append(material)
    scene.render.filepath=str(out/f'pose-{anim}.png');bpy.ops.render.render(write_still=True)
    outputs.append(dict(id=anim,minimum=vertices.min(0).tolist(),maximum=vertices.max(0).tolist()))
    bpy.data.objects.remove(obj,do_unlink=True);bpy.data.meshes.remove(mesh)
(out/'poses.json').write_text(json.dumps(outputs,indent=2))
