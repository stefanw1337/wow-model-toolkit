"""Build static or animated models, targeted DBC overlays, and additive MPQ files."""
import argparse
import json
import subprocess
import sys
from pathlib import Path
import assets
import m2_writer
from validate import validate

ROOT=Path(__file__).resolve().parent.parent


def build(config,output,blender,scene_cache=None):
    config=Path(config).resolve();output=Path(output).resolve()
    assets.require(not output.exists(),'Use a fresh output directory')
    cfg=json.loads(config.read_text(encoding='utf-8-sig'))
    output.mkdir(parents=True);stage=output/'archive';stage.mkdir()
    (output/'build-config.json').write_text(json.dumps(cfg,indent=2))
    scene_path=output/'scene.json'
    if scene_cache:
        scene_path.write_bytes(Path(scene_cache).read_bytes())
    else:
        command=[str(blender),'-b','-t','2','--python-exit-code','1','--python',str(ROOT/'scripts/export_scene.py'),'--',str(config),str(scene_path)]
        result=subprocess.run(command,capture_output=True,text=True,timeout=600)
        (output/'export.log').write_text(result.stdout+'\n'+result.stderr)
        assets.require(result.returncode==0,'Blender export failed; see '+str(output/'export.log'))
    scene=json.loads(scene_path.read_text())
    if cfg.get('animation_transitions'):
        from animation_adaptation import apply_transitions
        apply_transitions(scene,cfg['animation_transitions'])
        scene_path.write_text(json.dumps(scene,separators=(',',':')))
    model_path=assets.member(cfg['model_path']);texture_path=assets.member(cfg['texture_path'])
    assets.require(model_path.lower().endswith('.m2') and texture_path.lower().endswith('.blp'),'Expected M2 and BLP output paths')
    source=Path(cfg['texture']);source=source if source.is_absolute() else config.parent/source
    tex=assets.texture(source,stage/texture_path,cfg.get('material',{}).get('blend','opaque'))
    model=m2_writer.write(scene,stage/model_path,texture_path,cfg.get('material'))
    report=dict(model=model,texture=tex,source_validation=scene['validation'],validation=validate(stage/model_path,scene))
    if cfg.get('display_ids'):
        report['display_overlay']=assets.display_overlay(cfg['client'],cfg.get('locale','enGB'),cfg['display_ids'],model_path,model,stage)
    name=assets.member(cfg.get('patch_name','patch-Z.MPQ'));assets.require('/' not in name and name.lower().endswith('.mpq'),'Expected MPQ filename')
    report['package']=assets.pack(stage,output/name,ROOT/'tools/MPQEditor.exe')
    (output/'validation.json').write_text(json.dumps(report,indent=2))
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    a=sub.add_parser('build');a.add_argument('config');a.add_argument('--out',required=True);a.add_argument('--blender',required=True)
    a=sub.add_parser('validate');a.add_argument('model')
    a=sub.add_parser('pack');a.add_argument('stage');a.add_argument('output')
    a=p.parse_args()
    if a.command=='build':result=build(a.config,a.out,a.blender)
    elif a.command=='validate':result=validate(a.model)
    else:result=assets.pack(a.stage,a.output,ROOT/'tools/MPQEditor.exe')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    try:main()
    except Exception as e:print('ERROR:',e,file=sys.stderr);sys.exit(1)
