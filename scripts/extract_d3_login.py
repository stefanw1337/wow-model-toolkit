"""Decode original Diablo III login scene textures to PNG without altering sources."""
import argparse
from pathlib import Path
from d3_assets import texture

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('data_root');p.add_argument('output');a=p.parse_args()
    out=Path(a.output);out.mkdir(parents=True,exist_ok=True)
    for name in ['Battlenet_MainScreenBackground','Battlenet_MainScreenBackground_Alpha',
                 'Battlenet_MainScreenBackground_Clouds','Battlenet_MainScreen_CharacterPlatform',
                 '2DUI_Bnet_LoadingScreen_Logo_enUS','Battlenet_Main_Mistplane_Color',
                 'Battlenet_Main_Mistplane_Alpha']:
        texture(Path(a.data_root)/'Textures'/(name+'.tex')).save(out/(name+'.png'))
