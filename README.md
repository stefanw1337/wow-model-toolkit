# WoW Model Toolkit — first animated release

Convert static OBJ props or rigged FBX/Blender models into World of Warcraft 3.3.5a
M2 version 264, SKIN, BLP2 textures and an additive MPQ. Source assets are read-only.
The exporter writes a new M2 directly; it does not graft a new mesh onto an unrelated rig.

## Related tool: MultiConverter

[MultiConverter](https://github.com/stefanw1337/MultiConverter) (C#/.NET, fork of Adspartan's
converter) downgrades models from newer WoW versions to 3.3.5a in place. Use it when a newer
model should be used as it is; use this toolkit when a model comes from another game or needs
editing in Blender.

| | MultiConverter | WoW Model Toolkit |
| --- | --- | --- |
| Input | Newer WoW M2 (BfA and later; SKIN files in the same folder) and WMO | OBJ, FBX, Blender scenes, Diablo III models |
| Output | The same files rewritten for 3.3.5a | New M2 v264, SKIN, BLP2, MPQ and DBC rows |
| Blender | Not used | Used for rigged and animated models (static OBJ can skip it) |
| Editing the model | No: converts the format only | Yes: mesh, rig, animations, scale and textures |
| Packaging and install | No | MPQ building, validation and install |

To edit a newer WoW model, downgrade it with MultiConverter first. Importing a 3.3.5a M2 into
Blender is not part of this toolkit yet.

## D3 UI workshop

`scripts/convert_d3_ui.py` now converts D3 UI v471 layouts and TEX v47 named sprites
into a Wrath addon, intermediate JSON and visual previews. Paragon, SkillPane,
SkillBar and Traits are included in the first export, with a searchable icon browser.
See `UI-WORKFLOW.md` for commands, supported properties and gameplay limitations.
The animated login experiments remain unsuccessful in the native client; the
previously visible static login assets have been restored for a control test.

## Client filenames

The tested Wow.exe searches for patch-?.MPQ and patch-enGB-?.MPQ: use one suffix character.
Installed music is Data/patch-M.MPQ; combined creatures are Data/enGB/patch-enGB-Z.MPQ.
Long descriptive names and ZZ are not loaded. No separate ZZ or tavern addon is needed.
The installer now rejects incompatible names and the archive reader ignores them.

## Current local test release

`northshire-combined/patch-enGB-Z.MPQ` combines the previous Z and ZZ addons,
the Defias zombies, Garrick Padfoot as Butcher, Northshire wolf displays as Diablo,
and 63 PCM sound samples. It is self-contained. Do not also install the old Z/ZZ files.
`patch-M.MPQ` is independent and belongs in Data, not Data/enGB. It now includes
Classic/TBC/Wrath world, dungeon and raid music, plus the user's Tavern Jingle for inns.
The large MPQ is installed in the client; music/ contains its mapping and reports.
See `D3-WORKFLOW.md` for the complete workflow. Built MPQs and their reports stay local.
These new creature and sound changes still need in-game verification.

## Requirements

- Windows, Python 3.14 and the packages in `requirements.txt`.
- Blender 5.2 (tested with 5.2.2 LTS). Existing Blender files or FBX files can be used.
- MPQEditor by Ladislav Zezula, downloaded from https://www.zezula.net/en/mpq/download.html
  and placed at `tools/MPQEditor.exe`. It is not included in this repository.

Install Python dependencies with `python -m pip install -r requirements.txt`.

## Build

From this toolkit directory:

```powershell
python scripts/pipeline.py build examples/static-prop.json --out builds/static-001 --blender "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe"
python scripts/pipeline.py build examples/zombie-northshire.json --out builds/zombie-001 --blender "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe"
```

Output directories must be new. Every build contains the source configuration, neutral
scene data, export log, unpacked archive files, MPQ and `validation.json`.
`scripts/pipeline.py` remains the command entry point from OBJ-to-M2; this version uses
the new single-model configuration shown in the examples. Legacy configuration files
must be migrated. Existing toolkit installations are not modified.

## Static models

For a plain OBJ with no Blender installed, use the Blender-free path in
[`static-obj/`](static-obj/README.md), carried over from the former obj-to-m2-toolkit.
Inside this main pipeline, use `mode: "static"` with an OBJ or an unrigged Blender/FBX mesh. Supply UV coordinates
and a base-color texture. The OBJ importer triangulates faces. Axis, scale and origin
offset are explicit configuration values. Collision is optional:

- `{"mode": "none"}` is the default.
- `{"mode": "mesh", "object": "Collision"}` uses a named Blender mesh already in the scene.
  Select visible meshes explicitly with `meshes` so the collision object is not rendered.

## Animated models

Use `mode: "animated"`, select the armature and visible meshes, then configure animation
IDs and source-frame ranges. OBJ cannot carry skin weights or skeletal animation.
The exporter samples evaluated Blender poses, converts them to M2 pivot-relative tracks,
quantizes up to four weights per vertex, and checks the result against Blender deformation.
The generated M2 embeds all animation data; no external `.anim` files are needed.
NPC examples export no collision triangles. Selection and culling bounds are still present.

Animation configuration supports:

- `fps`, `source_frame_offset`, and `frame_end_exclusive` at model level.
- Multiple ordered `ranges` per animation, including noncontiguous source intervals.
- `playback_rate` and `movespeed` as separate properties.
- `hold: true` for a static pose such as a corpse.
- `loop_blend_frames` for a short blend back to the first pose.
- An explicit `action` name when the armature has more than one available action.

`loop` expresses the intended playback behavior and enables optional endpoint blending.
WoW also selects and repeats sequences according to AnimationData and gameplay state;
an M2 flag alone does not force an emote to play or persist.

The Northshire example keeps the supplied frame labels, interprets range ends as exclusive,
and applies `source_frame_offset: 1` to the existing Blender scene. Inspection found that
Blender frame 364 is still the corpse and frame 365 begins Walk. This adjustment belongs
to this asset configuration, not the generic exporter. FBX import separately supports
`fbx_frame_offset` (default zero).

Run temporarily reuses Walk at 1.5x speed. Attack1H and Ready1H reuse the corresponding
unarmed poses because the original Defias can request armed animation IDs. No visible
weapon attachments are exported in this release. Eating and spawn clips are included,
but installing an MPQ does not add server-side events to trigger them.

## Materials

Specify one diffuse image per output model. Supported `material.blend` values are
`opaque`, `cutout`, `alpha`, and `additive`; optional `two_sided` and `unlit` flags are
available. Textures retain their original power-of-two dimensions, up to 4096 pixels,
and receive a complete mip chain. Opaque textures use BC1; alpha textures use BC3.
PBR specular/glow maps are not automatically converted into WoW material effects.

## Targeted creature replacement

The example targets Defias Thug display IDs **5035 and 5036**. It adds one custom
CreatureModelData row and changes only those two CreatureDisplayInfo rows. The original
human model files and other display rows remain untouched. Both variants use the same
male zombie source asset. The scope is every NPC using those display IDs, even outside
Northshire; it is not a geographic filter.

The two full DBC tables in the add-on archive are based on the selected client's current
tables. Existing MPQs are only read. A different custom patch modifying the same tables
may require rebuilding this overlay. No server database changes are made.

## Install and remove

Close WoW first. To add a validated build:

```powershell
python scripts/install_patch.py builds/zombie-001 --client "C:/path/to/WoW-3.3.5a"
```

The installer verifies the archive checksum and the DBC source versions, then creates
`Data/enGB/patch-enGB-Z.MPQ`. It refuses to overwrite any existing file. To undo this
test, close WoW and remove only that newly added MPQ. Do not replace original archives.

Start the client normally and inspect both Defias variants in Northshire. Check standing,
walking/chasing, attacking, hit reaction, death, corpse, facing and scale. File validation
and Blender previews are not proof of in-game rendering; the initial delivery is a
client-test build until that runtime check is completed.

## Verification and current limits

```powershell
python tests/test_toolkit.py
python scripts/pipeline.py validate builds/zombie-001/archive/Creature/Custom/D3Zombie/D3Zombie.m2
```

Build validation checks binary ranges, animation lookups and timestamps, bone weights,
hierarchy, skin palettes, sampled pose reconstruction and byte-exact MPQ extraction.
The standalone validator checks the toolkit's supported subset, not arbitrary M2 files.

Current export limits: one texture/material and one SKIN profile per model, at most
256 bones with multiple sections (64 palette bones per section), 65,535 SKIN vertex references
and 21,845 triangles, linear skeletal skinning,
no shape-key animation, particles, ribbons, cameras, or attachment export. Non-armature
modifiers must be applied in a working copy before export. Significant shear or discarded
weights fail validation. Small source transform approximation is reported explicitly.

Format references: [wowdev](https://wowdev.wiki/M2),
[pywowlib](https://github.com/wowdev/pywowlib), and
[AzerothCore animation definitions](https://github.com/azerothcore/azerothcore-wotlk/blob/master/src/server/shared/SharedDefines.h).
# Latest test package

The combined `patch-enGB-Z.MPQ` now also contains a static original-D3 login background and
red D3 logo, plus Diablo's adapted death transition. The previous Dead pose is preserved.
The separate `patch-M.MPQ` uses **And the Heavens Shall Tremble** for login, without the
additional MainTitle parts. Northshire/shared Forest music starts with classic Tristram,
followed by D3 Tristram 02 and 03. Shire now plays at Darkmoon Faire.
The user confirmed the static login framing in WoW. Four layered animation experiments
subsequently rendered black; the static assets were restored. Animated login is unresolved.
See D3-WORKFLOW.md for reusable tools.

