# D3 UI conversion workshop

Convert extracted Diablo III `.ui` v471 files and `.tex` v47 atlas sprites to an
editable intermediate JSON layout and a World of Warcraft 3.3.5a addon. Inputs
are read-only. Output directories must be new. No game executables are modified.

```powershell
python scripts/convert_d3_ui.py "C:/path/to/Diablo III/Data/data/Work/Base" --out builds/ui-001
```

The default windows are Paragon, SkillPane, SkillBar and Traits. Select others:

```powershell
python scripts/convert_d3_ui.py "C:/path/to/Diablo III/Data/data/Work/Base" --windows Paragon --no-icons --out builds/paragon-001
python scripts/convert_d3_ui.py "C:/path/to/Diablo III/Data/data/Work/Base" --overrides edits.json --out builds/ui-002
```

The standard scan reads only headers and named sprite tables from `2D*.tex`,
not every model texture. Use `--all-atlases` if a required sprite belongs to
another family. Identical sprite names in multiple atlases are reported as
ambiguous instead of silently choosing an unrelated image.

## Outputs

- `D3UI/`: installable addon, Lua layouts/runtime and power-of-two BLP2 sprites.
- `intermediate/`: parsed controls, full parent paths, styles and raw properties.
- `layout.json`: resolved styles, geometry, texture mappings and callback names.
- `previews/`: cropped PNGs and static layout previews; these are not WoW screenshots.
- `conversion-report.json`: unsupported controls and unresolved graphics/styles.
- `overrides.example.json`: starting point for per-control adjustments.

Install the `D3UI` directory under the client's `Interface/AddOns/`. It is a
development addon separate from the M/Z MPQs. Enable it on character selection.

Commands inside the game:

```text
/d3ui Paragon
/d3ui SkillPane
/d3ui SkillPane list
/d3ui SkillPane ActiveSkillSelect
/d3ui SkillPane PassiveSkillSelect
/d3ui SkillPane ParagonPointSelect
/d3ui Traits
/d3ui SkillBar
/d3icons
/d3icons Barbarian
```

The icon browser is paged and searchable. Hover for the source sprite name;
click to print it in chat. Escape or the top-right WoW close button closes a view.
Alternative large panels are detected by shared parent and rectangle, then exposed
as explicit workshop views. This does not infer D3's runtime navigation logic.

## Fast edits and gameplay integration

Overrides are keyed by window and exact control path. Supported fields are
`x`, `y`, `width`, `height`, `text`, `font_size`, `textures` and `hidden`.
For example:

```json
{
  "Paragon": {
    "Paragon_main.LayoutRoot.Title": {"text": "Paragon"}
  }
}
```

Generated controls preserve D3 callback names. A separate addon can register a
function using `D3UI.RegisterHandler("UIParagon_OnClick_CloseButton", callback)`.
Unknown clicks only print their callback name. Never evaluate extracted strings
as Lua. Gameplay integration must validate actual player state on the server.

## Supported conversion and remaining work

The first export contains 297 controls across four windows, 1,212 sprites,
including 1,158 class/skill icons. All referenced external styles resolved.
One legacy sprite reference, `SkillsPane_Paragon_SkillIntelligence`, is missing
from the scanned atlases. It is reported and left empty.

Converted: hierarchy, position/size properties, basic frames/buttons/labels,
inherited styles, normal/hover/pressed/disabled sprites and named atlas crops.
Unknown property IDs are retained in JSON. Text localization keys remain visible
unless replaced with override text; StringList localization is not yet imported.

Not converted: D3 scripts, animation tracks, stack/list population, radio-group
semantics, dynamic skill/rune bindings and Paragon progression. A template is an
editable single instance, not a populated list. Unsupported widgets become generic
frames and appear in the report. This is a reusable visual conversion tool and
workshop, not a functional D3 skill system or pixel-perfect UI port.

Binary corruption/version tests and a Lua 5.1 widget-harness test pass. The harness
does not establish native WoW rendering or visual correctness; verify in the client.

## Format evidence

The UI v471 control table uses 1,856-byte records and the style table uses 656-byte
records. Strings are inline, including 512-byte control/parent/style names.
Style string values use 264-byte records; integer/float values use 16-byte records.
Property IDs 7/8/9/10 map to x/y/width/height in the inspected assets. TEX v47 named
sprites use 80-byte records (64-byte name plus four normalized coordinates).

WhiteoutLib's UIControlData/UIStyle definitions helped identify the structure:
https://github.com/FernandoS27/WhiteoutLib/blob/master/src/whiteout/sno/d3/sno_defs.cpp
The current runtime descriptors differ from the extracted disk layout. Do not
replace the version-gated reader with unchecked runtime offsets.
