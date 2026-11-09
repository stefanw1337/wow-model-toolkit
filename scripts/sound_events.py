"""Append validated Wrath $SND events to a generated model with no existing events."""
import struct as S
from pathlib import Path
from m2_writer import Buffer


def require(ok, message):
    if not ok:
        raise ValueError(message)


def append_events(path,events):
    path=Path(path);data=path.read_bytes()
    require(data[:8]==S.pack('<4sI',b'MD20',264),'Expected Wrath model')
    require(S.unpack_from('<I',data,256)[0]==0,'Refusing to replace existing M2 events')
    ns,seq_offset=S.unpack_from('<II',data,28)
    sequences=[S.unpack_from('<HHI',data,seq_offset+64*i) for i in range(ns)]
    buffer=Buffer(0);buffer.data=bytearray(data)
    event_offset=buffer.add(bytes(36*len(events)));buffer.put(256,'II',len(events),event_offset)
    for ei,event in enumerate(events):
        require(event['sound_id']>0,'Expected a SoundEntries ID')
        pairs=[]
        for id,variation,duration in sequences:
            times=event['times'].get(str(id),event['times'].get(id,[]))
            require(all(0<=t<=duration for t in times) and list(times)==sorted(set(times)),'Invalid sound timestamps')
            pairs.append((len(times),buffer.add(S.pack('<'+'I'*len(times),*times)) if times else 0))
        timestamps=buffer.add(b''.join(S.pack('<II',*p) for p in pairs))
        buffer.put(event_offset+36*ei,'4sII3fHhII',b'$SND',event['sound_id'],0,0,0,0,0,-1,ns,timestamps)
    path.write_bytes(buffer.data)
    return len(events)


def validate_events(data,sequences):
    count,offset=S.unpack_from('<II',data,256)
    require(not count or offset>=304 and offset+count*36<=len(data),'Invalid M2 event array')
    result=[]
    for i in range(count):
        ident,sound,bone,x,y,z,interpolation,global_seq,n,table=S.unpack_from('<4sII3fHhII',data,offset+36*i)
        require(ident==b'$SND' and sound>0 and bone==0 and interpolation==0 and global_seq==-1,'Unsupported generated sound event')
        require(n==len(sequences) and table+n*8<=len(data),'Invalid event timelines')
        active=[]
        for si,sequence in enumerate(sequences):
            k,at=S.unpack_from('<II',data,table+si*8)
            require(not k or at>=304 and at+k*4<=len(data),'Invalid event timestamps')
            times=list(S.unpack_from('<'+'I'*k,data,at)) if k else []
            require(times==sorted(set(times)) and all(t<=sequence['duration'] for t in times),'Event outside sequence')
            if times:active.append(sequence['id'])
        result.append(dict(sound_id=sound,animation_ids=active))
    return result
