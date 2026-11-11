"""Read a Heroes of the Storm / StarCraft II .m3 mesh with skin weights, using m3addon's structures."""
import sys
from pathlib import Path
import numpy as np

M3ADDON = str(Path(__file__).resolve().parents[2] / 'tools' / 'm3addon')


def load(path):
    if M3ADDON not in sys.path:
        sys.path.insert(0, M3ADDON)
    import m3
    model = m3.loadModel(path, checkExpectedValue=False)
    description = m3.structures['VertexFormat' + hex(model.vFlags)].getVersion(0)
    raw = description.createInstances(buffer=model.vertices, count=len(model.vertices) // description.size)
    bones = [dict(name=b.name, parent=b.parent) for b in model.bones]
    inverse = [np.array([[getattr(getattr(m.matrix, col), row) for col in 'xyzw'] for row in 'xyzw'])
               for m in model.absoluteInverseBoneRestPositions]
    regions = []
    division = model.divisions[0]
    for obj in division.objects:
        region = division.regions[obj.regionIndex]
        lookup = model.boneLookup[region.firstBoneLookupIndex:region.firstBoneLookupIndex + region.numberOfBoneLookupIndices]
        mult, offset = getattr(region, 'uvwMult', 16.0), getattr(region, 'uvwOffset', 0.0)
        first = region.firstVertexIndex
        verts = []
        for v in raw[first:first + region.numberOfVertices]:
            weights = [v.boneWeight0, v.boneWeight1, v.boneWeight2, v.boneWeight3]
            idx = [lookup[i] if w else 0 for i, w in zip(
                [v.boneLookupIndex0, v.boneLookupIndex1, v.boneLookupIndex2, v.boneLookupIndex3], weights)]
            uv = (v.uv0.x * (mult / 16.0) / 2048.0 + offset, v.uv0.y * (mult / 16.0) / 2048.0 + offset)
            verts.append(dict(position=[v.position.x, v.position.y, v.position.z],
                              normal=[v.normal.x, v.normal.y, v.normal.z], uv=list(uv), weights=weights, bones=idx))
        faces = division.faces[region.firstFaceVertexIndexIndex:
                               region.firstFaceVertexIndexIndex + region.numberOfFaceVertexIndices]
        triangles = [tuple(faces[k:k + 3]) for k in range(0, len(faces), 3)]
        regions.append(dict(index=obj.regionIndex, material=obj.materialReferenceIndex, vertices=verts,
                            triangles=triangles, bone_names=[model.bones[i].name for i in lookup]))
    attachments = [dict(name=a.name, bone=getattr(a, 'bone', getattr(a, 'boneIndex', -1))) for a in model.attachmentPoints]
    return dict(bones=bones, inverse_bind=inverse, regions=regions, attachments=attachments)
