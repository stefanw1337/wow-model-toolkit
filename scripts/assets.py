"""Texture, DBC overlay and additive MPQ packaging utilities."""
import hashlib
import io
import json
import math
import re
import struct as S
import subprocess
from pathlib import Path, PurePosixPath
import mpyq
from mpq_read import read_file as read_mpq_file
from PIL import Image


def require(ok,message):
    if not ok: raise ValueError(message)


def member(path):
    path=str(path).replace('\\','/')
    require(path and not PurePosixPath(path).is_absolute() and all(x not in ('','.','..') for x in path.split('/')) and not any(c in path for c in ':"\r\n'),'Unsafe archive path')
    return path


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def install_name(name,locale='enGB',data_root=False):
    prefix='patch-' if data_root else 'patch-'+re.escape(locale)+'-'
    require(re.fullmatch(prefix+r'[A-Za-z0-9]\.MPQ',name,re.I) is not None,
            'WoW requires a single-character patch suffix; set install_name (for example patch-M.MPQ or patch-enGB-Z.MPQ)')
    return name


def texture(source,output,blend):
    with Image.open(source) as original:image=original.convert('RGBA')
    w,h=image.size
    require(w>0 and h>0 and not w&(w-1) and not h&(h-1),'Texture dimensions must be powers of two')
    require(max(w,h)<=4096,'Texture exceeds 4096 pixels')
    if blend=='opaque':image.putalpha(255)
    # Encode BC1 for opaque surfaces and BC3 for alpha surfaces, including small mips.
    offsets=[0]*16;sizes=[0]*16;payload=[];offset=1172;i=0
    while True:
        padded=image
        if min(image.size)<4:
            padded=Image.new('RGBA',(max(4,image.width),max(4,image.height)))
            for y in range(padded.height):
                for x in range(padded.width):padded.putpixel((x,y),image.getpixel((min(x,image.width-1),min(y,image.height-1))))
        stream=io.BytesIO();padded.save(stream,format='DDS',pixel_format='DXT1' if blend=='opaque' else 'DXT5')
        raw=stream.getvalue()[128:];offsets[i]=offset;sizes[i]=len(raw);payload.append(raw);offset+=len(raw);i+=1
        if image.size==(1,1):break
        image=image.resize((max(1,image.width//2),max(1,image.height//2)),Image.Resampling.LANCZOS)
    header=S.pack('<4sI4BII16I16I',b'BLP2',1,2,0 if blend=='opaque' else 8,0 if blend=='opaque' else 7,1,w,h,*offsets,*sizes)
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True);require(not output.exists(),'Texture output already exists')
    output.write_bytes(header+bytes(1024)+b''.join(payload))
    with Image.open(output) as decoded:
        decoded.load();require(decoded.size==(w,h),'BLP decode failed')
    return dict(width=w,height=h,mips=i,encoding='BC1' if blend=='opaque' else 'BC3',alpha_depth=0 if blend=='opaque' else 8)


class DBC:
    def __init__(self,data):
        require(data[:4]==b'WDBC','Expected WDBC')
        n,self.fields,self.stride,size=S.unpack_from('<4I',data,4)
        require(self.stride==4*self.fields and len(data)==20+n*self.stride+size,'Invalid DBC size')
        self.rows=[bytearray(data[20+i*self.stride:20+(i+1)*self.stride]) for i in range(n)]
        self.strings=bytearray(data[20+n*self.stride:])
    def value(self,row,field):return S.unpack_from('<I',row,4*field)[0]
    def set(self,row,field,value):S.pack_into('<I',row,4*field,value)
    def find(self,id):
        matches=[r for r in self.rows if self.value(r,0)==id]
        require(len(matches)==1,'Missing or duplicate DBC ID '+str(id));return matches[0]
    def string(self,row,field):
        start=self.value(row,field)
        require(start<len(self.strings),'Invalid DBC string offset')
        end=self.strings.find(0,start)
        require(end>=start,'Unterminated DBC string')
        return self.strings[start:end].decode()
    def add_string(self,text):
        offset=len(self.strings);self.strings.extend(text.encode()+b'\0');return offset
    def encode(self):return S.pack('<4s4I',b'WDBC',len(self.rows),self.fields,self.stride,len(self.strings))+b''.join(self.rows)+self.strings


def client_archives(client,locale):
    data=Path(client)/'Data';loc=data/locale
    ordered=[]
    for name in ('common.MPQ','common-2.MPQ','expansion.MPQ','lichking.MPQ'):
        if (data/name).exists():ordered.append(data/name)
    for name in ('locale-'+locale+'.MPQ','expansion-locale-'+locale+'.MPQ','lichking-locale-'+locale+'.MPQ'):
        if (loc/name).exists():ordered.append(loc/name)
    # Match the loader patterns found in this client's Wow.exe: patch-?.MPQ
    # and patch-%s-?.MPQ. Long descriptive filenames are build artifacts only.
    patches=[p for p in data.glob('patch*.MPQ') if re.fullmatch(r'patch(?:-[A-Za-z0-9])?\.MPQ',p.name,re.I)]
    patches += [p for p in loc.glob('patch*.MPQ') if re.fullmatch(r'patch-'+re.escape(locale)+r'(?:-[A-Za-z0-9])?\.MPQ',p.name,re.I)]
    def key(p):
        suffix=re.sub(r'^patch(?:-'+re.escape(locale)+r')?', '',p.stem,flags=re.I).lstrip('-')
        return (0,0,str(p)) if not suffix else (1,int(suffix),str(p)) if suffix.isdigit() else (2,suffix.upper(),str(p))
    return ordered+sorted(patches,key=key)


def read_client_files(client,locale,names):
    found={}
    for p in client_archives(client,locale):
        with p.open('rb') as f:
            archive=mpyq.MPQArchive(f)
            for name in names:
                data=read_mpq_file(archive,name.replace('/','\\'))
                if data:found[name]=(data,str(p))
    require(set(found)==set(names),'Missing client files: '+str(set(names)-set(found)))
    return found


def display_overlay(client,locale,ids,model_path,model_report,stage):
    return display_overlays(client,locale,[dict(display_ids=ids,model_path=model_path,model=model_report)],stage)


def display_overlays(client,locale,replacements,stage):
    names=['DBFilesClient/CreatureDisplayInfo.dbc','DBFilesClient/CreatureModelData.dbc']
    files=read_client_files(client,locale,names)
    displays=DBC(files[names[0]][0]);models=DBC(files[names[1]][0])
    require(displays.fields==16 and models.fields==28,'Expected Wrath DBC layouts')
    # Clone a creature model record, not a player-character customization record.
    donor=next((r for r in models.rows if 'zombie' in models.string(r,2).lower()),None)
    require(donor is not None,'No creature donor record found')
    ids=[id for replacement in replacements for id in replacement['display_ids']]
    require(len(set(ids))==len(ids),'Duplicate replacement display ID')
    changes=[];new_ids=[]
    for replacement in replacements:
        model_path=replacement['model_path'];model_report=replacement['model']
        display_scale=float(replacement.get('display_scale',1.0))
        require(math.isfinite(display_scale) and 0<display_scale<=100,'Invalid creature display scale')
        new_id=max(models.value(r,0) for r in models.rows)+1;new_ids.append(new_id)
        row=bytearray(donor);models.set(row,0,new_id);models.set(row,1,0)
        models.set(row,2,models.add_string(model_path.replace('/','\\').rsplit('.',1)[0]+'.mdx'))
        models.set(row,3,0);S.pack_into('<f',row,4*4,1.0)
        models.set(row,13,0)
        for field,value in [(14,0.45),(15,1.5),(16,2.0)]:S.pack_into('<f',row,field*4,value)
        S.pack_into('<6f',row,17*4,*model_report['minimum'],*model_report['maximum'])
        models.rows.append(row)
        for id in replacement['display_ids']:
            r=displays.find(id);old_model=displays.value(r,1)
            changes.append(dict(display_id=id,old_model_id=old_model,old_model_path=models.string(models.find(old_model),2),new_model_id=new_id))
            displays.set(r,1,new_id);displays.set(r,3,0)
            for field in (6,7,8):displays.set(r,field,0)
            S.pack_into('<f',r,16,display_scale)
    stage=Path(stage)
    for name,dbc in zip(names,(displays,models)):
        dest=stage/member(name);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(dbc.encode())
    # Verify every unrequested display row and every original model row remains byte-identical.
    original_display=DBC(files[names[0]][0]);original_model=DBC(files[names[1]][0])
    require(all(a==b for a,b in zip(original_display.rows,displays.rows) if original_display.value(a,0) not in ids),'Unexpected display edits')
    require(models.rows[:len(original_model.rows)]==original_model.rows,'Unexpected model edits')
    return dict(changes=changes,base_archives={n:files[n][1] for n in names},base_sha256={n:hashlib.sha256(files[n][0]).hexdigest() for n in names},new_model_ids=new_ids,new_model_id=new_ids[0],scope='Every creature using these display IDs, regardless of location. No server database changes.')


def pack(stage,output,exe):
    stage=Path(stage).resolve();output=Path(output).resolve();exe=Path(exe).resolve()
    require(not output.exists(),'MPQ output already exists')
    require(output.parent!=stage and stage not in output.parents,'MPQ must be outside staging')
    files=sorted(p for p in stage.rglob('*') if p.is_file())
    require(files,'No staged files')
    output.parent.mkdir(parents=True,exist_ok=True)
    entries=[member(p.relative_to(stage)) for p in files]
    require(len(set(x.lower() for x in entries))==len(entries),'Case-insensitive archive path conflict')
    for p in [str(stage),str(output),str(exe)]:require(not any(c in p for c in '"\r\n'),'Unsupported filesystem path')
    script=output.with_suffix('.build.txt')
    require(not script.exists(),'MPQ build script already exists')
    capacity=max(32,2**math.ceil(math.log2(len(files)*2)))
    # Store audio unchanged: editor compression preferences can apply unsupported
    # or lossy WAV codecs, and MP3 is already compressed.
    lines=[f'new "{output}" {capacity}']
    for p,entry in zip(files,entries):
        flags='' if p.suffix.lower() in ('.wav','.mp3') else ' /c'
        lines.append(f'add "{output}" "{p}" "{entry.replace(chr(47),chr(92))}"{flags}')
    lines += [f'close "{output}"','exit']
    script.write_text('\n'.join(lines)+'\n')
    result=subprocess.run([str(exe),'/console',str(script)],capture_output=True,timeout=120,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    require(result.returncode==0,'MPQEditor failed: '+result.stderr.decode(errors='replace'))
    with output.open('rb') as f:
        archive=mpyq.MPQArchive(f)
        listed={n.decode().replace('\\','/').lower() for n in archive.files if not n.startswith(b'(')}
        require(listed=={e.lower() for e in entries},'MPQ member set mismatch')
        for p,e in zip(files,entries):require(read_mpq_file(archive,e.replace('/','\\'))==p.read_bytes(),'MPQ round-trip failed: '+e)
    return dict(mpq=str(output),sha256=digest(output),files=[dict(path=e,bytes=p.stat().st_size,sha256=digest(p)) for p,e in zip(files,entries)],archive_members_verified=len(entries))
