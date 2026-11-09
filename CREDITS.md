# Credits and project lineage

This toolkit extends the project's earlier static OBJ-to-M2 workflow with a Python M2/SKIN
writer, Blender/FBX animation sampling, validation and packaging, developed with Codex assistance.
It is not a claim that all underlying tools, formats or source assets were authored by the user.

- **Garthog:** original OBJtoM2 converter used by the earlier static workflow. Its original
  acknowledgements thank **relaxok, schlumpf, gamh, mjollna, zim, pxr.dk and modcraft**.
  Upstream mirror: https://github.com/bollafa/OBJtoM2 ; user fork:
  https://github.com/stefanw1337/OBJtoM2 . The mirror owner is not the original author.
  The current Python export path does not execute or bundle OBJtoM2.exe.
- **Ladislav Zezula:** MPQEditor — https://www.zezula.net/en/mpq/download.html .
- **Blender contributors:** Blender, FBX/OBJ import, scene evaluation and rendering —
  https://www.blender.org/ .
- **wowdev contributors:** M2 documentation and pywowlib reference structures —
  https://wowdev.wiki/M2 and https://github.com/wowdev/pywowlib .
- **AzerothCore contributors:** animation definitions and documentation —
  https://github.com/azerothcore/azerothcore-wotlk .
- **Python, NumPy, Pillow and mpyq contributors:** runtime and supporting libraries.

- **Taylor Mouse:** the user's Diablo III model and animation MaxScripts (April 2014)
  informed the APP/ANI layout and transform interpretation. They are not bundled here.
- **Fernando Sahmkow / WhiteoutLib:** TEX layout and block-plane references;
  the inspected source carries Copyright (c) 2026 Fernando Sahmkow, BSD-3-Clause.
  The UIControlData/UIStyle definitions also informed the UI v471 disk-layout
  investigation: https://github.com/FernandoS27/WhiteoutLib . The UI reader is
  independently implemented and version-gated against the extracted files.
- **Ladislav Zezula and CascLib contributors:** local CASC archive access;
  https://github.com/ladislav-zezula/CascLib .
- **vgmstream contributors:** decoding FSB5/FMOD FADPCM into PCM WAV;
  https://github.com/vgmstream/vgmstream (tested r2117).
- **FFmpeg contributors:** encoding genuine MP3 audio. The tested external binary was supplied
  by imageio-ffmpeg 0.6.0. Decoder/encoder binaries are not bundled in the toolkit release.

Blizzard's game assets are not original toolkit artwork. Preserve attribution and applicable notices
independently of tool modifications. See THIRD_PARTY_NOTICES.md; credits do not assign a blanket license.
