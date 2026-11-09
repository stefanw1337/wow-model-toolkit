"""Build the diffuse texture atlas described by a D3 import profile."""
import json
import sys
from pathlib import Path
from PIL import Image
from d3_assets import texture, require


def build(profile_path,output):
    profile=json.loads(Path(profile_path).read_text())
    entries=profile['meshes'];base=Path(profile['data_root'])/'Textures'
    images={entry['texture']:texture(base/entry['texture']) for entry in entries}
    if len(images)==1 and all('atlas_rect' not in e for e in entries):
        image=next(iter(images.values()))
    else:
        # Profiles use normalized atlas rectangles. Preserve the largest source resolution.
        width=max(round(images[e['texture']].width/e['atlas_rect'][2]) for e in entries)
        height=max(round(images[e['texture']].height/e['atlas_rect'][3]) for e in entries)
        image=Image.new('RGBA',(width,height),(0,0,0,255))
        for entry in entries:
            x,y,w,h=entry['atlas_rect'];source=images[entry['texture']]
            source=source.resize((round(w*width),round(h*height)),Image.Resampling.LANCZOS)
            image.paste(source,(round(x*width),round(y*height)))
    output=Path(output);require(not output.exists(),'Refusing to overwrite atlas')
    image.save(output)
    print('Created',output,image.size)


if __name__=='__main__':build(*sys.argv[1:])
