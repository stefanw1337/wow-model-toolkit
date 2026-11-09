"""Render the original D3 BattleNet scene as a static WoW login backdrop.

Run with Blender --background --python render_d3_login.py -- DATA_ROOT OUTPUT.
Uses original mesh positions and UVs; shader effects are approximated with alpha.
"""
import sys
from pathlib import Path
import bpy
from mathutils import Vector
sys.path.insert(0,str(Path(__file__).resolve().parent))
from d3_assets import appearance

args=sys.argv[sys.argv.index('--')+1:]
base,out=map(Path,args[:2]);layered='--layers' in args[2:]
out=out.resolve();out.mkdir(parents=True,exist_ok=True)
model=appearance(base/'Appearance/BattleNet_MainScreen.app')
bpy.ops.wm.read_factory_settings(use_empty=True)
scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.samples=16
scene.render.resolution_x=1920;scene.render.resolution_y=1080;scene.render.resolution_percentage=100
scene.view_settings.view_transform='Standard'
scene.world=bpy.data.worlds.new('Night');scene.world.use_nodes=True
scene.world.node_tree.nodes['Background'].inputs[0].default_value=(0.003,0.006,0.01,1)
scene.world.node_tree.nodes['Background'].inputs[1].default_value=1
for subset in model['meshes']:
    name=subset['name']
    if name.startswith('GRASS') or any(x in name for x in ('mistplane','BannerFog','Valley')):continue
    if 'CharacterPlatform' in name:tex='Battlenet_MainScreen_CharacterPlatform'
    elif 'Clouds' in name:tex='Battlenet_MainScreenBackground_Clouds'
    elif 'Valley' in name:tex='Battlenet_MainScreenBackground'
    else:tex=name.removesuffix('_mstr')
    target=out/(tex+'.png')
    if not target.exists():raise FileNotFoundError('Run extract_d3_login.py first: '+str(target))
    mesh=bpy.data.meshes.new(name);mesh.from_pydata([v['position'] for v in subset['vertices']],[],subset['triangles']);mesh.update()
    uv=mesh.uv_layers.new(name='UVMap')
    for loop in mesh.loops:
        u,v=subset['vertices'][loop.vertex_index]['uv'];uv.data[loop.index].uv=(u,1-v)
    obj=bpy.data.objects.new(name,mesh);scene.collection.objects.link(obj)
    mat=bpy.data.materials.new(name);mat.use_nodes=True;nodes=mat.node_tree.nodes;nodes.clear()
    image=nodes.new('ShaderNodeTexImage');image.image=bpy.data.images.load(str(target));image.extension='CLIP'
    emission=nodes.new('ShaderNodeEmission');transparent=nodes.new('ShaderNodeBsdfTransparent');mix=nodes.new('ShaderNodeMixShader');output=nodes.new('ShaderNodeOutputMaterial')
    links=mat.node_tree.links;links.new(image.outputs['Color'],emission.inputs[0]);links.new(image.outputs['Alpha'],mix.inputs[0]);links.new(transparent.outputs[0],mix.inputs[1]);links.new(emission.outputs[0],mix.inputs[2]);links.new(mix.outputs[0],output.inputs['Surface']);mesh.materials.append(mat)
bpy.ops.object.camera_add(location=(60,162,14));camera=bpy.context.object;scene.camera=camera
camera.rotation_euler=(Vector((66,70,7))-camera.location).to_track_quat('-Z','Y').to_euler();camera.data.lens=45
scene.render.filepath=str(out/'login-background.png');bpy.ops.render.render(write_still=True)
if layered:
    meshes=[o for o in scene.objects if o.type=='MESH']
    for layer in ('landscape','clouds','foreground'):
        scene.render.film_transparent=layer!='landscape'
        for obj in meshes:
            role='clouds' if 'Clouds' in obj.name else 'foreground' if ('Alpha' in obj.name or 'CharacterPlatform' in obj.name) else 'landscape'
            obj.hide_render=role!=layer
        scene.render.filepath=str(out/('login-'+layer+'.png'));bpy.ops.render.render(write_still=True)
    for obj in meshes:obj.hide_render=False
    scene.render.film_transparent=False
bpy.ops.file.pack_all()
bpy.ops.wm.save_as_mainfile(filepath=str(out/'login-background.blend'))
