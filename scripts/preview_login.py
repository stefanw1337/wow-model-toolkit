"""Render the exported animated login M2 at selected times in Blender."""
import sys,json,math,struct
from pathlib import Path
import bpy
from mathutils import Vector
sys.path.insert(0,str(Path(__file__).resolve().parent))
from validate import read,pose

model_path,atlas_path,out=map(Path,sys.argv[sys.argv.index('--')+1:]);out=out.resolve();out.mkdir(parents=True,exist_ok=True)
model=read(model_path);data=model_path.read_bytes();n,o=struct.unpack_from('<II',data,272);assert n==1
_,fov,far,near=struct.unpack_from('<I3f',data,o);position=Vector(struct.unpack_from('<3f',data,o+36));target=Vector(struct.unpack_from('<3f',data,o+68))
bpy.ops.wm.read_factory_settings(use_empty=True);scene=bpy.context.scene
scene.render.engine='CYCLES';scene.cycles.samples=4;scene.cycles.transparent_max_bounces=16
scene.render.resolution_x=960;scene.render.resolution_y=540;scene.render.resolution_percentage=100
scene.view_settings.view_transform='Standard';scene.world=bpy.data.worlds.new('Dark');scene.world.use_nodes=True
scene.world.node_tree.nodes['Background'].inputs[0].default_value=(0,0,0,1)
bpy.ops.object.camera_add(location=position);cam=bpy.context.object;scene.camera=cam
cam.rotation_euler=(target-position).to_track_quat('-Z','Y').to_euler();cam.data.sensor_fit='HORIZONTAL'
cam.data.angle=2*math.atan(math.tan(fov/2)*(16/9)/math.sqrt(1+(16/9)**2))
material=bpy.data.materials.new('M2 unlit alpha');material.use_nodes=True;nodes=material.node_tree.nodes;nodes.clear()
image=nodes.new('ShaderNodeTexImage');image.image=bpy.data.images.load(str(atlas_path.resolve()));image.extension='CLIP'
emit=nodes.new('ShaderNodeEmission');clear=nodes.new('ShaderNodeBsdfTransparent');mix=nodes.new('ShaderNodeMixShader');output=nodes.new('ShaderNodeOutputMaterial')
links=material.node_tree.links;links.new(image.outputs['Color'],emit.inputs[0]);links.new(image.outputs['Alpha'],mix.inputs[0]);links.new(clear.outputs[0],mix.inputs[1]);links.new(emit.outputs[0],mix.inputs[2]);links.new(mix.outputs[0],output.inputs['Surface'])
for time in (0,7500,22500,30000):
    points=pose(model,0,time);mesh=bpy.data.meshes.new('Decoded model');mesh.from_pydata(points.tolist(),[],model['triangles'].tolist());mesh.update()
    uv=mesh.uv_layers.new(name='UVMap')
    for loop in mesh.loops:
        u,v=model['vertices'][loop.vertex_index,14:16];uv.data[loop.index].uv=(u,1-v)
    obj=bpy.data.objects.new('Login',mesh);scene.collection.objects.link(obj);mesh.materials.append(material)
    scene.render.filepath=str(out/f'frame-{time:05}.png');bpy.ops.render.render(write_still=True)
    bpy.data.objects.remove(obj,do_unlink=True);bpy.data.meshes.remove(mesh)
