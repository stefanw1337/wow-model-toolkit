"""Build a layered animated D3 login scene for the Wrath model renderer.

Uses separately rendered original D3 landscape, cloud and foreground layers,
plus original D3 mist textures. Motion is recreated with looping M2 bones.
This is a scene adaptation, not a direct port of D3 particle/material programs.
"""
import argparse
import json
import math
import struct
from pathlib import Path
import numpy as np
from PIL import Image,ImageChops
from assets import texture,require
from m2_writer import Buffer,write,track
from validate import read,pose,validate


def append_camera(path,fov,distance):
    b=Buffer(0);b.data=bytearray(path.read_bytes());o=b.add(bytes(100));b.put(272,'II',1,o)
    b.put(o,'i3f',-1,fov,1000,0.1)
    # Diagnostic variant: match the original login camera's explicit tracks,
    # flyby type and spline-key payload layout. Runtime success is not established.
    for offset in (16,48):track(b,o+offset,[[0]],[[(0.0,)*9]],'9f')
    track(b,o+80,[[0]],[[(0.0,)*3]],'3f')
    b.put(o+36,'3f',0,-distance,0);b.put(o+68,'3f',0,0,0)
    b.array(280,'h',[(0,),(-1,)]);path.write_bytes(b.data)


def build(layers,output):
    layers=Path(layers).resolve();out=Path(output).resolve()
    require(not out.exists(),'Use a fresh output directory');stage=out/'archive';stage.mkdir(parents=True)
    images={n:Image.open(layers/('login-'+n+'.png')).convert('RGBA') for n in ('landscape','clouds','foreground')}
    mist=Image.open(layers/'Battlenet_Main_Mistplane_Color.png').convert('RGBA').resize((1920,1080),Image.Resampling.LANCZOS)
    mask=Image.open(layers/'Battlenet_Main_Mistplane_Alpha.png').convert('RGBA').getchannel('A').resize(mist.size,Image.Resampling.LANCZOS)
    alpha=ImageChops.multiply(mist.getchannel('A'),mask)
    # A soft lower-screen envelope avoids exposing rectangular sprite edges.
    yy,xx=np.mgrid[0:1080,0:1920];edge=np.sin(np.pi*np.clip(xx/1919,0,1))**2
    vertical=np.exp(-((yy/1079-0.72)/0.23)**2)*np.sin(np.pi*yy/1079)**2
    a=np.asarray(alpha,dtype=float)*edge*vertical*0.28
    mist.putalpha(Image.fromarray(a.astype('uint8')));images['mist']=mist
    atlas=Image.new('RGBA',(2048,2048));rects={}
    order=['landscape','clouds','foreground','mist']
    for i,name in enumerate(order):
        im=images[name].resize((1008,567),Image.Resampling.LANCZOS)
        x=(i%2)*1024+8;y=(i//2)*1024+8;atlas.paste(im,(x,y))
        rects[name]=[x/2048,y/2048,1008/2048,567/2048]
    atlas.save(out/'atlas.png')
    texpath='Interface/Glues/Models/D3Login/D3LoginAnimated.blp'
    texture(out/'atlas.png',stage/texpath,'alpha')
    texture_paths=[]
    for name in order:
        image=images[name].resize((2048,1152),Image.Resampling.LANCZOS)
        canvas=Image.new('RGBA',(2048,2048),(0,0,0,255) if name=='landscape' else (0,0,0,0));canvas.paste(image,(0,0))
        source=out/(name+'.png');canvas.save(source)
        member='Interface/Glues/Models/D3Login/D3Login_'+name+'.blp'
        texture(source,stage/member,'opaque' if name=='landscape' else 'alpha');texture_paths.append(member)
    fov=math.pi/4;distance=10;aspect=16/9
    h=distance*math.tan(fov/2)/math.sqrt(1+aspect*aspect)*1.02;w=h*aspect
    duration=30000;times=list(range(0,duration+1,250));vertices=[];triangles=[];groups=[];bones=[];tracks=[]
    for i,name in enumerate(order):
        depth=-i*0.04;perspective=(distance+depth)/distance
        # Overscan moving clouds and mist so their outer edges stay outside the viewport.
        overscan=1.10 if name in ('clouds','mist') else 1
        xextent=w*perspective*overscan;zextent=h*perspective*overscan
        positions=[[-xextent,depth,-zextent],[xextent,depth,-zextent],[xextent,depth,zextent],[-xextent,depth,zextent]]
        uvs=[[0,1152/2048],[1,1152/2048],[1,0],[0,0]]
        start=len(vertices)
        vertices.extend(dict(position=p,normal=[0,-1,0],uv=uv,weights=[255,0,0,0],bones=[i,0,0,0]) for p,uv in zip(positions,uvs))
        triangles.extend([[start,start+1,start+2],[start,start+2,start+3]]);groups.extend([i,i])
        bones.append(dict(name=name,parent=-1 if i==0 else 0,pivot=[0,0,0]));keys=[]
        for t in times:
            phase=2*math.pi*t/duration
            motion=[0,0,0]
            if name=='clouds':motion=[0.20*math.sin(phase),0,0.035*math.sin(phase*2)]
            if name=='mist':motion=[-0.32*math.sin(phase),0,0.07*math.sin(phase*2)]
            if t==duration:motion=[0,0,0]
            keys.append(dict(translation=motion,rotation=[0,0,0,1],scale=[1,1,1]))
        tracks.append(keys)
    scene=dict(format='wow-model-toolkit-scene-v1',fps=4,vertices=vertices,triangles=triangles,triangle_groups=groups,bones=bones,collision=None,
        sequences=[dict(id=0,name='Stand',duration=duration,movespeed=0,loop=True,timestamps=times,tracks=tracks,
            minimum=[-w*1.2,-0.2,-h*1.2],maximum=[w*1.2,0.1,h*1.2],radius=math.hypot(w*1.2,h*1.2))])
    (out/'scene.json').write_text(json.dumps(scene,separators=(',',':')))
    models=[]
    for name in ('UI_MainMenu_Northrend','UI_MainMenu'):
        path=stage/'Interface/Glues/Models'/name/(name+'.m2')
        write(scene,path,texpath,dict(blend='opaque',two_sided=True,unlit=True))
        # Keep an opaque base pass, as in the client-confirmed static model.
        # Transparent atmosphere/foreground layers use a separate standard alpha pass.
        b=Buffer(0);b.data=bytearray(path.read_bytes());b.array(112,'HH',[(5,0),(5,2)])
        entries=[]
        for texture_name in texture_paths:
            text=texture_name.replace('/','\\').encode()+b'\0';entries.append((0,0,len(text),b.add(text)))
        b.array(80,'4I',entries);b.array(128,'H',[(i,) for i in range(4)]);path.write_bytes(b.data)
        skin_path=path.with_name(path.stem+'00.skin');skin=bytearray(skin_path.read_bytes())
        count,offset=struct.unpack_from('<II',skin,36)
        require(count==4,'Expected four layer batches')
        for i in range(count):
            struct.pack_into('<H',skin,offset+i*24+10,0 if i==0 else 1)
            struct.pack_into('<H',skin,offset+i*24+16,i)
        skin_path.write_bytes(skin)
        append_camera(path,fov,distance);models.append(validate(path,scene))
        model=read(path);first=pose(model,0,0);mid=pose(model,0,7500);last=pose(model,0,duration)
        require(np.max(np.abs(first-last))<1e-8,'Loop endpoint mismatch')
        require(np.max(np.abs(first[4:8]-mid[4:8]))>0.19,'Cloud layer is not animated')
        require(np.max(np.abs(first[12:16]-mid[12:16]))>0.31,'Mist layer is not animated')
        require(np.max(np.abs(first[:4]-mid[:4]))<1e-8 and np.max(np.abs(first[8:12]-mid[8:12]))<1e-8,'Foreground or landscape drifted')
    report=dict(animated=True,loop_seconds=30,layers=order,animated_layers=['clouds','mist'],
        motion='Recreated M2 bone tracks; original D3 artwork rendered into separate layers',
        native_d3_particle_programs=False,loop_seam_verified=True,stationary_foreground_verified=True,
        camera=dict(fov=fov,distance=distance),texture_size=2048,separate_layer_textures=True,opaque_base_pass=True,
        models=models,in_game_verified=False)
    (out/'validation.json').write_text(json.dumps(report,indent=2));return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('layers');p.add_argument('--out',required=True);a=p.parse_args()
    print(json.dumps(build(a.layers,a.out),indent=2))
