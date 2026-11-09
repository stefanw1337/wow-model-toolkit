"""Create explicit grounded pose transitions for cinematic source animations."""
import copy
import math
import numpy as np
from validate import rotation


def apply_transitions(scene, settings):
    original = copy.deepcopy(scene['sequences'])
    vertices = scene['vertices']
    points = np.array([v['position'] + [1] for v in vertices])
    ids = np.array([v['bones'] for v in vertices])
    weights = np.array([v['weights'] for v in vertices]) / 255
    def find(anim):
        return next(s for s in original if s['id'] == anim)
    for setting in settings:
        target = next(s for s in scene['sequences'] if s['id'] == setting['id'])
        first = find(setting.get('from_id', setting['id']))
        last = find(setting['to_id'])
        duration = int(setting['duration_ms'])
        if duration <= 0 or duration > 30000:
            raise ValueError('Transition duration must be in (0, 30000] milliseconds')
        count = max(2, round(duration * scene['fps'] / 1000) + 1)
        target['duration'] = duration
        target['timestamps'] = [round(i * duration / (count - 1)) for i in range(count)]
        target['source_frames'] = []
        target['tracks'] = [[] for _ in scene['bones']]
        lower=[];upper=[];radii=[]
        for i in range(count):
            t = i / (count - 1)
            t = t*t*(3-2*t)
            keys=[];matrices=[]
            for bi,bone in enumerate(scene['bones']):
                a=first['tracks'][bi][0];b=last['tracks'][bi][0]
                q=np.array(a['rotation']);r=np.array(b['rotation'])
                if np.dot(q,r)<0:r=-r
                dot=float(np.clip(np.dot(q,r),-1,1))
                if dot<0.9995:
                    angle=math.acos(dot)
                    q=(q*math.sin((1-t)*angle)+r*math.sin(t*angle))/math.sin(angle)
                else:q=q*(1-t)+r*t
                q/=np.linalg.norm(q)
                key={k:((1-t)*np.array(a[k])+t*np.array(b[k])).tolist() for k in ('translation','scale')}
                key['rotation']=q.tolist()
                if i==0:key=copy.deepcopy(a)
                if i==count-1:key=copy.deepcopy(b)
                keys.append(key)
                m=np.eye(4);m[:3,:3]=rotation(np.array(key['rotation']))@np.diag(key['scale'])
                pivot=np.array(bone['pivot']);m[:3,3]=np.array(key['translation'])+pivot-m[:3,:3]@pivot
                if bone['parent']>=0:m=matrices[bone['parent']]@m
                matrices.append(m)
            posed=np.zeros((len(points),3))
            for j in range(4):
                posed+=np.einsum('nij,nj->ni',np.array(matrices)[ids[:,j]],points)[:,:3]*weights[:,j,None]
            # Keep intermediate frames in contact with the ground, preserving exact endpoints.
            if 0<i<count-1 and 'ground_z' in setting:
                dz=float(setting['ground_z'])-float(posed[:,2].min())
                for bi,bone in enumerate(scene['bones']):
                    if bone['parent']<0:keys[bi]['translation'][2]+=dz
                posed[:,2]+=dz
            for bi,key in enumerate(keys):target['tracks'][bi].append(key)
            lower.append(posed.min(0));upper.append(posed.max(0));radii.append(np.linalg.norm(posed,axis=1).max())
        target['minimum']=np.min(lower,axis=0).tolist();target['maximum']=np.max(upper,axis=0).tolist()
        target['radius']=float(max(radii))
        target['adaptation']=dict(setting)
    return scene
