"""Overlay prepared assets onto a complete custom addon and verify every member."""
import argparse,json,shutil
from pathlib import Path
import mpyq
from assets import digest,member,pack,require
from mpq_read import read_file

def build(source,overlays,output,editor):
    source=Path(source).resolve();out=Path(output).resolve()
    require(not out.exists(),'Use a fresh output directory');stage=out/'archive';stage.mkdir(parents=True)
    original={}
    with source.open('rb') as stream:
        a=mpyq.MPQArchive(stream)
        for raw in a.files:
            if raw.startswith(b'('):continue
            name=member(raw.decode());data=read_file(a,raw);original[name]=data
            p=stage/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
    require(any(n.startswith('Creature/Custom/') for n in original),'Expected our custom model addon')
    updated=set()
    for overlay in overlays:
        root=Path(overlay).resolve()
        for p in root.rglob('*'):
            if p.is_file():
                name=member(p.relative_to(root));target=stage/name;target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(p,target);updated.add(name)
    for name,data in original.items():
        if name not in updated:require((stage/name).read_bytes()==data,'Unrelated asset changed')
    report=dict(source=str(source),previous_sha256=digest(source),
        changed_members=sorted(n for n in updated if n in original and (stage/n).read_bytes()!=original[n]),
        added_members=sorted(updated-original.keys()),in_game_verified=False)
    report['package']=pack(stage,out/source.name,editor)
    (out/'validation.json').write_text(json.dumps(report,indent=2));return report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source');p.add_argument('--overlay',action='append',required=True)
    p.add_argument('--out',required=True);p.add_argument('--editor',required=True);a=p.parse_args()
    print(json.dumps(build(a.source,a.overlay,a.out,a.editor),indent=2))
