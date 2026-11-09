"""Build a static login M2 and logo using an extracted/rendered D3 background.

Replaces assets only: no GlueXML edits and no executable patching.
Camera layout reference: WoWee src/pipeline/m2_loader.cpp (WotLK M2CameraDisk).
"""
import argparse
import json
import math
from pathlib import Path
from PIL import Image
from assets import texture
from m2_writer import Buffer,write
from validate import validate

def build(background,logo,output):
    out=Path(output).resolve()
    if out.exists():raise ValueError('Use a fresh output directory')
    stage=out/'archive';stage.mkdir(parents=True)
    image=Image.open(background).convert('RGBA').resize((2048,1152),Image.Resampling.LANCZOS)
    canvas=Image.new('RGBA',(2048,2048),(0,0,0,255));canvas.paste(image,(0,0));canvas.save(out/'background.png')
    texpath='Interface/Glues/Models/D3Login/D3Login.blp'
    texture(out/'background.png',stage/texpath,'opaque')
    fov=math.pi/4;d=10;aspect=16/9
    h=d*math.tan(fov/2)/math.sqrt(1+aspect*aspect)*1.02;w=h*aspect
    positions=[[-w,0,-h],[w,0,-h],[w,0,h],[-w,0,h]]
    scene=dict(fps=30,bones=[dict(name='Root',parent=-1,pivot=[0,0,0])],collision=None,
        vertices=[dict(position=p,normal=[0,-1,0],uv=uv,weights=[255,0,0,0],bones=[0,0,0,0])
                  for p,uv in zip(positions,[(0,1152/2048),(1,1152/2048),(1,0),(0,0)])],triangles=[[0,1,2],[0,2,3]],
        sequences=[dict(id=0,name='Stand',duration=1000,movespeed=0,loop=True,timestamps=[0],
            tracks=[[dict(translation=[0,0,0],rotation=[0,0,0,1],scale=[1,1,1])]],
            minimum=[-w,0,-h],maximum=[w,0,h],radius=math.hypot(w,h))])
    models=[]
    for name in ('UI_MainMenu_Northrend','UI_MainMenu'):
        p=stage/'Interface/Glues/Models'/name/(name+'.m2')
        write(scene,p,texpath,dict(blend='opaque',two_sided=True,unlit=True))
        b=Buffer(0);b.data=bytearray(p.read_bytes());o=b.add(bytes(100));b.put(272,'II',1,o)
        b.put(o,'I3f',0,fov,1000,0.1)
        for offset in (16,48,80):b.put(o+offset,'Hh4I',0,-1,0,0,0,0)
        b.put(o+36,'3f',0,-d,0);b.put(o+68,'3f',0,0,0)
        b.array(280,'h',[(0,),(-1,)])
        p.write_bytes(b.data);models.append(validate(p))
    logo_image=Image.open(logo).convert('RGBA');bounds=logo_image.getchannel('A').point(lambda a:255 if a>16 else 0).getbbox()
    if not bounds:raise ValueError('Logo has no visible pixels')
    logo_image=logo_image.crop(bounds);logo_image.thumbnail((480,224),Image.Resampling.LANCZOS)
    logo_canvas=Image.new('RGBA',(512,256));logo_canvas.alpha_composite(logo_image,((512-logo_image.width)//2,(256-logo_image.height)//2));logo_canvas.save(out/'logo.png')
    texture(out/'logo.png',stage/'Interface/Glues/Common/Glues-WoW-WotLKLogo.blp','alpha')
    report=dict(background=str(Path(background).resolve()),static_background=True,original_d3_scene=True,
        native_d3_effects_reproduced=False,gluexml_modified=False,executable_modified=False,
        camera=dict(fov=fov,position=[0,-d,0],target=[0,0,0],layout_bytes=100),models=models,in_game_verified=False)
    (out/'validation.json').write_text(json.dumps(report,indent=2));return report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('background');p.add_argument('logo');p.add_argument('--out',required=True);a=p.parse_args()
    print(json.dumps(build(a.background,a.logo,a.out),indent=2))
