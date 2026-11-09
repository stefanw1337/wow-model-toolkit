"""Regression tests for file safety, alpha preservation and skeletal serialization."""
import json
import struct
import sys
import tempfile
import unittest
import io
import zlib
from types import SimpleNamespace
from pathlib import Path
import numpy as np
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from assets import member,texture,DBC,install_name,client_archives
from m2_writer import write,encode_quaternion,decode_quaternion
from validate import validate,read,pose
from sound_events import append_events, validate_events
from mpq_read import read_file
from mpq_music import pack_music
import mpyq


class ToolkitTests(unittest.TestCase):
    def test_transparent_scene_layers_keep_distinct_sort_centers(self):
        key=dict(translation=[0,0,0],rotation=[0,0,0,1],scale=[1,1,1])
        vertices=[dict(position=[x,y,z],normal=[0,-1,0],uv=[0,0],weights=[255,0,0,0],bones=[0,0,0,0])
                  for y in (0,-1) for x,z in ((0,0),(1,0),(0,1))]
        scene=dict(vertices=vertices,triangles=[[0,1,2],[3,4,5]],triangle_groups=[0,1],
            bones=[dict(parent=-1,pivot=[0,0,0])],collision=None,
            sequences=[dict(id=0,name='Stand',duration=1000,movespeed=0,loop=True,timestamps=[0],tracks=[[key]],
                minimum=[0,-1,0],maximum=[1,0,1],radius=2)])
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'layers.m2';write(scene,p,'Textures/layers.blp',dict(blend='alpha',two_sided=True,unlit=True,unfogged=True,no_depth_write=True))
            validate(p,scene);data=p.read_bytes();_,at=struct.unpack_from('<II',data,112)
            self.assertEqual(struct.unpack_from('<HH',data,at),(23,2))
            skin=p.with_name('layers00.skin').read_bytes();count,at=struct.unpack_from('<II',skin,28)
            self.assertEqual(count,2)
            centers=[struct.unpack_from('<I8H7f',skin,at+48*i)[13] for i in range(2)]
            self.assertEqual(centers,[0,-1])
    def test_death_transition_keeps_corpse_endpoint(self):
        import copy
        from animation_adaptation import apply_transitions
        key=dict(translation=[0,0,0],rotation=[0,0,0,1],scale=[1,1,1])
        corpse=copy.deepcopy(key);corpse['rotation']=[2**-0.5,0,0,2**-0.5]
        sequences=[dict(id=i,name=str(i),duration=1000,movespeed=0,loop=i!=1,
            timestamps=[0],tracks=[[copy.deepcopy(k)]],minimum=[-2,-2,-2],maximum=[2,2,2],radius=4)
            for i,k in [(0,key),(1,key),(6,corpse)]]
        scene=dict(fps=30,bones=[dict(parent=-1,pivot=[0,0,0])],collision=None,
            triangles=[[0,1,2]],vertices=[dict(position=p,normal=[0,0,1],uv=[0,0],
                bones=[0,0,0,0],weights=[255,0,0,0]) for p in [[0,0,0],[1,0,0],[0,0,1]]],sequences=sequences)
        before=copy.deepcopy(scene)
        apply_transitions(scene,[dict(id=1,to_id=6,duration_ms=1800,ground_z=0)])
        self.assertEqual(scene['sequences'][0],before['sequences'][0])
        self.assertEqual(scene['sequences'][2],before['sequences'][2])
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'transition.m2';write(scene,path,'Textures/test.blp');model=read(path)
            self.assertTrue(np.allclose(pose(model,1,1800),pose(model,2,0),atol=1e-8))
            for t in scene['sequences'][1]['timestamps'][1:-1]:
                self.assertAlmostEqual(float(pose(model,1,t)[:,2].min()),0,places=4)
    def test_client_patch_filename_rules(self):
        self.assertEqual(install_name('patch-M.MPQ',data_root=True),'patch-M.MPQ')
        self.assertEqual(install_name('patch-enGB-Z.MPQ'),'patch-enGB-Z.MPQ')
        for name in ('patch-D3music.MPQ','patch-MM.MPQ','patch-enGB-ZZ.MPQ'):
            with self.assertRaises(ValueError):install_name(name,data_root=True)
        with tempfile.TemporaryDirectory() as folder:
            data=Path(folder)/'Data';locale=data/'enGB';locale.mkdir(parents=True)
            for p in (data/'patch-M.MPQ',data/'patch-D3music.MPQ',locale/'patch-enGB-Z.MPQ',locale/'patch-enGB-ZZ.MPQ'):
                p.touch()
            self.assertEqual({p.name for p in client_archives(folder,'enGB')},{'patch-M.MPQ','patch-enGB-Z.MPQ'})
    def test_music_names_share_payload_not_block_records(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'song.mp3'
            source.write_bytes(bytes(range(256))*8)
            names={f'Sound/Music/Area{i}/Track.mp3':source for i in range(48)}
            output=root/'music.MPQ';report=pack_music(names,output)
            self.assertEqual(report['archive_members_verified'],48)
            self.assertEqual(report['unique_audio_blocks'],1)
            with output.open('rb') as stream:
                archive=mpyq.MPQArchive(stream)
                blocks=[]
                for name in names:
                    name=name.replace('/','\\')
                    self.assertEqual(read_file(archive,name),source.read_bytes())
                    blocks.append(archive.get_hash_table_entry(name).block_table_index)
                self.assertEqual(len(set(blocks)),48)
                self.assertEqual(len({archive.block_table[i].offset for i in blocks}),1)
    def test_mixed_mpq_sectors(self):
        raw=bytes(range(256))*2
        tail=b'A'*512
        compressed=b'\x02'+zlib.compress(tail)
        payload=struct.pack('<3I',12,524,524+len(compressed))+raw+compressed
        archive=SimpleNamespace(file=io.BytesIO(payload),header=dict(offset=0,sector_size_shift=0),
            block_table=[SimpleNamespace(flags=0x80000200,offset=0,archived_size=len(payload),size=1024)],
            get_hash_table_entry=lambda name: SimpleNamespace(block_table_index=0))
        self.assertEqual(read_file(archive,'audio.wav'),raw+tail)
    def test_multiple_bone_palettes(self):
        # Independent moving triangles force more than 64 genuinely weighted bones.
        bones=[dict(parent=-1,pivot=[0,0,0]) for _ in range(99)]
        vertices=[];triangles=[];tracks=[]
        for i in range(99):
            start=len(vertices)
            vertices.extend(dict(position=p,normal=[0,0,1],uv=[0,0],weights=[255,0,0,0],bones=[i,0,0,0]) for p in ([0,0,0],[1,0,0],[0,1,0]))
            triangles.append([start,start+1,start+2])
            tracks.append([dict(translation=[i/100,0,0],rotation=[0,0,0,1],scale=[1,1,1])]*2)
        scene=dict(vertices=vertices,triangles=triangles,bones=bones,collision=None,sequences=[dict(id=0,name='Stand',duration=1000,movespeed=0,loop=True,timestamps=[0,1000],tracks=tracks,minimum=[0,0,0],maximum=[2,1,0],radius=3)])
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'many.m2';write(scene,path,'Textures/test.blp');validate(path,scene)
            decoded=read(path)
            self.assertEqual(len(decoded['bones']),99)
            self.assertTrue(np.allclose(pose(decoded,0,0)[-3:],[ [.98,0,0],[1.98,0,0],[.98,1,0] ],atol=.0002))
            skin=path.with_name('many00.skin');data=bytearray(skin.read_bytes())
            nsec=struct.unpack_from('<I',data,28)[0];self.assertGreater(nsec,1)
            offset=struct.unpack_from('<I',data,24)[0];data[offset]=255;skin.write_bytes(data)
            with self.assertRaises(ValueError):read(path)
    def test_unsafe_archive_paths(self):
        for path in ('../x','/x','C:/x','a/../x','a//x','x\nfoo'):
            with self.assertRaises(ValueError):member(path)
        self.assertEqual(member('Creature\\Custom\\test.m2'),'Creature/Custom/test.m2')
    def test_signed_quaternion_encoding(self):
        self.assertEqual(encode_quaternion([0,0,0,1]),[-32768,-32768,-32768,-1])
        for q in ([0.5,-0.5,0.5,-0.5],[0,0,0,1],[0,-1,0,0]):
            self.assertTrue(np.allclose(decode_quaternion(encode_quaternion(q)),q,atol=1/32767))
    def test_alpha_texture(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);im=Image.new('RGBA',(8,8),(100,150,200,255))
            for y in range(8):
                for x in range(4):im.putpixel((x,y),(100,150,200,0))
            im.save(p/'source.png');texture(p/'source.png',p/'test.blp','cutout')
            decoded=Image.open(p/'test.blp').convert('RGBA')
            self.assertEqual(decoded.getchannel('A').getextrema(),(0,255))
    def test_hierarchical_motion_and_corruption(self):
        # A translated parent and rotated child must move a triangle around its pivot.
        vertices=[dict(position=p,normal=[0,0,1],uv=[0,0],weights=[255,0,0,0],bones=[1,0,0,0]) for p in ([1,0,0],[2,0,0],[1,1,0])]
        identity=dict(translation=[0,0,0],rotation=[0,0,0,1],scale=[1,1,1])
        parent=dict(translation=[2,0,0],rotation=[0,0,0,1],scale=[1,1,1])
        child=dict(translation=[0,0,0],rotation=[0,0,2**-0.5,2**-0.5],scale=[1,1,1])
        scene=dict(vertices=vertices,triangles=[[0,1,2]],bones=[dict(parent=-1,pivot=[0,0,0]),dict(parent=0,pivot=[1,0,0])],sequences=[dict(id=0,name='Stand',duration=1000,movespeed=0,loop=True,timestamps=[0,1000],tracks=[[identity,parent],[identity,child]],minimum=[-4,-4,-4],maximum=[4,4,4],radius=7)],collision=None)
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'test.m2';write(scene,path,'Textures/test.blp')
            validate(path,scene)
            actual=pose(read(path),0,1000)
            self.assertTrue(np.allclose(actual,[[3,0,0],[3,1,0],[2,0,0]],atol=0.0002))
            self.assertEqual(validate(path)['collision_triangles'],0)
            append_events(path,[dict(sound_id=20000,times={0:[20,500]})])
            decoded=read(path)
            self.assertEqual(validate_events(path.read_bytes(),decoded['sequences']),[dict(sound_id=20000,animation_ids=[0])])
            with self.assertRaises(ValueError):append_events(path,[])
            valid=path.read_bytes();bad=bytearray(valid)
            event=struct.unpack_from('<I',bad,260)[0]
            timeline=struct.unpack_from('<I',bad,event+32)[0]
            timestamp=struct.unpack_from('<I',bad,timeline+4)[0]
            struct.pack_into('<I',bad,timestamp,1001);path.write_bytes(bad)
            with self.assertRaises(ValueError):read(path)
            path.write_bytes(valid)
            data=bytearray(path.read_bytes());struct.pack_into('<I',data,64,len(data)+100);path.write_bytes(data)
            with self.assertRaises(ValueError):read(path)


if __name__=='__main__':unittest.main()
