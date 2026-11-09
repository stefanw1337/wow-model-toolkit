# Diablo III conversion and local test release

Read CREDITS.md before extending this workflow. Source files are read-only.
The tools and documentation are English. This local release targets WoW 3.3.5a (M2 version 264).

## Native model import

OBJ is suitable for static geometry. Animated conversion must retain skeletons, skin weights and
animation channels. The native path uses extracted APP, ANI and TEX files without an intermediate
OBJ and without 3ds Max Batch licensing. The older FBX/Blender pipeline remains available.

From the toolkit directory, choose a new output directory for each run:

```powershell
& "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b -t 2 --python-exit-code 1 --python scripts/import_d3.py -- examples/butcher-d3.json builds/butcher-source
python scripts/prepare_d3_texture.py examples/butcher-d3.json builds/butcher-source/diffuse.png
python scripts/pipeline.py build builds/butcher-source/model.json --out builds/butcher --blender "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe"
```

Use examples/diablo-d3.json for Diablo. Profiles contain mesh selection, texture atlas rectangles,
animation IDs, scale and optional per-clip root rotation. Edit data_root to match your extracted Base
directory. Supported native versions: APP 260, ANI 118, TEX 47. Unknown versions fail explicitly.
All sampled native bone transforms are compared against the imported Blender armature.

Butcher uses 54 bones and 3,834 vertices. Diablo uses 99 bones and 7,544 vertices. The writer now
partitions SKIN sections into palettes of at most 64 bones without discarding the rest of the rig.
Both creature profiles disable collision. Diablo's cinematic corpse remains a visual limitation:
its tail supports the torso above ground in the preview. The current root tilt is an adaptation,
not proof of a finished natural corpse pose. Check the corpse in game before considering it final.

## Sound extraction and conversion

The optional local CASC reader requires a separately built ANSI x64 CascLib.dll. It never opens an
online archive. Use --pattern to select exact banks and --extract to write a new directory:

```powershell
python scripts/casc_extract.py --dll "C:/path/to/tools/CascLib.dll" --storage "C:/path/to/Diablo III" --pattern "^Base/SoundBank/Butcher(\.sbk|/)" --output builds/butcher-audio --extract
python scripts/decode_d3_audio.py builds/butcher-audio builds/butcher-wav --decoder "C:/path/to/tools/vgmstream-cli.exe"
```

SBK v41 gives sample names; numbered FSB/OGG files contain audio. Renaming these files does not convert
them. vgmstream decodes the FSB5/FMOD FADPCM data into ordinary PCM16 WAV. Music uses a separately
supplied FFmpeg executable with libmp3lame to encode genuine 44.1 kHz, 192 kbit/s MP3 files.
These external audio tools and CascLib.dll are not bundled in the curated toolkit ZIP.

## Combined creature patch

scripts/build_creature_bundle.py merges explicitly named addon MPQs in order, copies new model
builds, appends targeted model/display rows, and adds SoundEntries and per-sequence $SND events.
The current examples/northshire-bundle.json records this machine's source locations. Update paths
before reuse. Its original merge inputs Z and ZZ are now in the client's AddonPatchBackups folder;
the example documents the initial consolidation, not an idempotent upgrade of an installed bundle.
Do not repeatedly rebuild against the installed bundle and append duplicate model/sound rows.

The delivered northshire-combined/patch-enGB-Z.MPQ is self-contained:

| Display IDs | Replacement |
| --- | --- |
| 5035, 5036 | Defias Thug male/female become the existing male zombie |
| 2073 | Garrick Padfoot becomes Butcher |
| 31048, 31049 | Northshire wolf displays become Diablo |

All NPCs sharing these display IDs are affected, including outside Northshire. No server database
was edited. Existing unrelated display and model rows and existing SoundEntries rows were preserved.

Attack, wound and death events are included for all three creatures (63 audio files total).
Zombie emergence and Butcher intro dialogue require Birth/Spawn playback. Diablo's boss intro
dialogue is packaged with a SoundEntries ID but has no automatic encounter trigger. These are
client replacements, not complete server-side Diablo boss encounters. Random eating and automatic
emergence remain unresolved; merely adding animation IDs does not make the client select them.

## Combined world and tavern music patch

```powershell
python scripts/build_world_music.py examples/world-music.json --out builds/world-music --encoder "C:/path/to/tools/ffmpeg.exe"
```

The explicit example contains all 1,166 archive path assignments. Review or change each theme's
track pool to customize it. It references this machine's decoded WAV libraries and the prepared
Tavern Jingle MP3; update source paths for another setup. --audio-cache can reuse the audio folder
of an earlier build, with complete decode verification. Source files remain untouched.

The output contains patch-M.MPQ, MUSIC-MAPPING.md, build-config.json and validation.json.
Classic, TBC and Wrath regular zone/dungeon/raid music references are covered. Undead Dance,
the Darkmoon ETC performance and TempMono remain unchanged. Nine referenced paths that were
missing from the original client are supplied. No DBC tables or new playback triggers are added.
Areas sharing music files use the same replacement; silent areas without playback assignments
are not given new triggers. The mapping includes all ZoneMusic entries and direct AreaTable links.

The ten capital cities use Tristram. Login uses MainTitle segments 01-06. All 39 regular tavern
paths use Tavern Jingle, supplied by the user and attributed in its metadata to stefanw1337.
The original Downloads MP3 is unchanged; the client copy is stereo 44.1 kHz, 192 kbit/s with
attached artwork removed. Do not install a separate tavern patch: the user requested one music MPQ.

The archive stores 63 unique audio payloads behind 1,166 named block-table entries, about 268 MB.
mpq_music.py writes a classic MPQ and checks every name/payload mapping. Each path has its own
block-table record for native enumeration; identical records may point to the same file bytes.
The large MPQ is installed separately in the client's Data directory, not repeated in the toolkit ZIP.

To update an existing installation, use scripts/update_music_patch.py with the exact previous
archive SHA-256. It checks that WoW is closed, backs up the existing addon outside Data, and swaps
in the verified build. Its scope is restricted to patch-M.MPQ. Original game MPQs are untouched.

## Installation and verification

Close WoW before installation. scripts/install_patch.py checks checksums and DBC base versions.
It refuses to overwrite a destination. A consolidation moves only explicitly listed, checksum-matched
old addon patches into a dated backup outside Data and verifies the final effective DBC tables.
Original game MPQs are never edited. The music patch is independent and can be removed on its own.

Current installed paths:

- C:/path/to/WoW-3.3.5a/Data/enGB/patch-enGB-Z.MPQ
- C:/path/to/WoW-3.3.5a/Data/patch-M.MPQ
- Old Z/ZZ backup: C:/path/to/WoW-3.3.5a/AddonPatchBackups/20261003-172345

Run python -m unittest discover -s tests -v. Seven tests cover skinning, 99-bone section partitioning,
event timestamp bounds, alpha textures, path safety and mixed compressed/raw MPQ sectors.
The combined creature patch passed 75 byte-exact file checks. The expanded music patch passed
1,166 path/payload checks; independent MPQEditor extraction verified 101 files covering all 63 unique
tracks and all 39 tavern paths. Audio files
passed decoding checks. Native and exported model poses were compared, and decoded M2 previews
were rendered. These checks do not prove in-game model rendering, sound events or music playback.

Restart WoW and test login, city music, Northshire wolves, Garrick, Defias combat and death. The
user previously verified the zombie model; the new additions still require that runtime check.
# Original D3 login and cinematic death adaptation

The animated login workflow is EXPERIMENTAL: builds 001-004 render black in WoW.
Do not ship their MPQs as working releases. The static backdrop is the current fallback.
For research, first run `extract_d3_login.py DATA_ROOT LAYERS` with Python,
then Blender `--background --python scripts/render_d3_login.py -- DATA_ROOT LAYERS --layers`.
The renderer writes landscape, cloud and foreground PNGs separately and packs textures into
the saved Blender file. Run `build_animated_login.py LAYERS --out BUILD` with Python to create
two Wrath login models, their SKIN files and separate layer textures. `preview_login.py`
only supports the earlier single-atlas layout and must not be used to validate the current
multi-texture variant. Offline validation has not explained the native rendering failure.

Animated effects are recreated as 30-second bone tracks. They are not D3 particle programs.
The moving clouds are behind the stationary tree/ground; translucent mist moves independently.
The writer's optional `triangle_groups` retains separate layer sections and sort centers.
Optional `unfogged` and `no_depth_write` material flags support transparent scene compositing.
Keep the existing creature export defaults unchanged when adding interface-specific features.

Music assignments may specify `track_name` to select an exact track from their theme.
This preserves an established mapping when a different path moves out of a rotating theme.
An ordered `sources` list concatenates music in that order; Northshire's shared Forest files
use classic Tristram, then D3 Tristram 02 and 03. Client music scheduling still applies.

`extract_d3_login.py DATA_ROOT OUTPUT` decodes the original BattleNet scene textures.
Run `render_d3_login.py` inside Blender with the same arguments to render the static scene.
`build_login_backdrop.py BACKGROUND.png LOGO.png --out OUTPUT` creates replacement login
M2/SKIN/BLP assets with an embedded camera. It does not modify GlueXML or executable files.
The current backdrop approximates original shaders and omits animated scene effects.
Use `merge_addon_assets.py` to overlay its archive directory onto the complete model addon.
`update_model_patch.py BUILD --client CLIENT` verifies the previous checksum, backs up the
installed custom Z addon outside Data, and replaces it only while WoW is closed.

`animation_transitions` is an optional model/profile setting. Example:

```json
[{"id": 1, "from_id": 1, "to_id": 6, "duration_ms": 1800, "ground_z": -0.03}]
```

It replaces the selected sequence with an eased skeletal transition from the first pose of
`from_id` to the first pose of `to_id`. Endpoints remain exact; intermediate frames contact
the configured ground plane. This is a custom adaptation of a cinematic source, not its
original motion. Other sequences remain unchanged. The pipeline applies it after Blender
extraction, so the editable source Blender scene still contains the original clips.

