"""Convert D3 UI v471 layouts and named TEX atlas sprites into a Wrath addon.

Usage: python convert_d3_ui.py BASE --out OUTPUT [--windows Paragon SkillPane]
Rebuild with --overrides edits.json to adjust controls without editing generated Lua.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from d3_ui import read_ui, atlas_entries
from d3_assets import texture as decode_texture
from assets import texture as encode_blp


def lua(value):
    if value is None:
        return 'nil'
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return '"' + ''.join('\\%03d' % b if b < 32 or b >= 127 else '\\' + chr(b) if b in (34, 92) else chr(b) for b in value.encode('utf-8')) + '"'
    if isinstance(value, list):
        return '{' + ','.join(lua(v) for v in value) + '}'
    return '{' + ','.join('[' + lua(str(k)) + ']=' + lua(v) for k, v in value.items()) + '}'


def slug(value):
    return re.sub('[^A-Za-z0-9_]', '_', value)[:80] + '_' + hashlib.sha256(value.encode()).hexdigest()[:8]


def convert(base, output, windows, overrides=None, icons=True, all_atlases=False):
    base = Path(base).resolve()
    out = Path(output).resolve()
    if out.exists():
        raise ValueError('Use a fresh output directory')
    edits = json.loads(Path(overrides).read_text('utf-8')) if overrides else {}
    out.mkdir(parents=True)
    addon = out / 'D3UI'
    images = addon / 'Textures'
    images.mkdir(parents=True)
    (out / 'intermediate').mkdir()
    previews = out / 'previews'
    previews.mkdir()
    index = {}
    atlas_errors = []
    paths = sorted((base / 'Textures').glob('*.tex' if all_atlases else '2D*.tex'))
    for number, path in enumerate(paths):
        if number % 100 == 0:
            print('Indexing atlas headers', number, '/', len(paths), flush=True)
        try:
            for entry in atlas_entries(path):
                index.setdefault(entry['name'], []).append(entry)
        except (ValueError, UnicodeError) as error:
            atlas_errors.append(dict(file=path.name, error=str(error)))
    print('Indexed', len(index), 'named sprites', flush=True)
    reports = []
    models = {}
    views = {}
    required = set()
    loaded = {}

    def load(name):
        if not re.fullmatch('[A-Za-z0-9_-]+', name):
            raise ValueError('Unsafe UI name')
        if name not in loaded:
            loaded[name] = read_ui(base / 'UI' / (name + '.ui'))
        return loaded[name]

    def inherited(source, chain=()):
        ref = source['strings'].get('157', '')
        result = dict(strings={}, integers={}, floats={})
        if ref:
            if ref in chain or len(chain) > 16:
                raise ValueError('Cyclic style reference')
            group, _, name = ref.partition(':')
            try:
                candidates = [s for s in load(group)['styles'] if s['name'] == name]
            except FileNotFoundError:
                candidates = []
            if len(candidates) == 1:
                result = inherited(candidates[0], chain + (ref,))
            else:
                reports.append(dict(kind='unresolved_style', reference=ref))
        for kind in ('strings', 'integers', 'floats'):
            result[kind].update(source[kind])
        return result

    for name in windows:
        ui = load(name)
        controls = []
        for item in sorted(ui['controls'], key=lambda c: (c['path'].count('.'), c['index'])):
            props = inherited(item['style'])
            ints, strings = props['integers'], props['strings']
            get = lambda key, default: ints.get(str(key), props['floats'].get(str(key), default))
            textures = {}
            for key, state in [('16', 'normal'), ('17', 'highlight'), ('18', 'pushed'), ('19', 'disabled')]:
                if strings.get(key, '').startswith('UI:'):
                    textures[state] = strings[key][3:]
                    required.add(strings[key][3:])
            callbacks = {k: v for k, v in strings.items() if v.startswith('UI') and ':' not in v}
            control = dict(path=item['path'], name=item['name'], parent=item['parent'],
                           type=item['control_type'], x=get(7, 0), y=get(8, 0),
                           width=get(9, 1), height=get(10, 1),
                           text=strings.get('65', ''), font_size=get(59, 20),
                           textures=textures, callbacks=callbacks,
                           unsupported_properties=props,
                           template=strings.get('1') == '1')
            patch = edits.get(name, {}).get(item['path'], {})
            allowed = {'x', 'y', 'width', 'height', 'text', 'font_size', 'textures', 'hidden'}
            if set(patch) - allowed:
                raise ValueError('Unknown override keys: ' + str(set(patch) - allowed))
            control.update(patch)
            for value in control['textures'].values():
                required.add(value)
            if not all(isinstance(control[k], (int, float)) and abs(control[k]) < 100000 for k in ('x', 'y', 'width', 'height', 'font_size')):
                raise ValueError('Invalid control geometry')
            if control['type'] not in (2, 3, 4, 22):
                reports.append(dict(kind='generic_control', window=name, path=item['path'], type=control['type']))
            controls.append(control)
        models[name] = controls
        candidates = {}
        for c in controls:
            if c['width'] >= 500 and c['height'] >= 500:
                key = (c['parent'], c['x'], c['y'], c['width'], c['height'])
                candidates.setdefault(key, []).append(c['path'])
        alternatives = [v for v in candidates.values() if len(v) > 1]
        views[name] = max(alternatives, key=len, default=[])
    for name, ui in loaded.items():
        (out / 'intermediate' / (name + '.json')).write_text(json.dumps(ui, indent=2), encoding='utf-8')

    icon_names = set()
    if icons:
        for name, entries in index.items():
            if any(re.search(r'(Skills_|ParagonSkills)', Path(e['source']).stem, re.I) for e in entries):
                icon_names.add(name)
        required.update(icon_names)
    assets = {}
    grouped = {}
    for name in sorted(required):
        entries = index.get(name, [])
        if len(entries) != 1:
            reports.append(dict(kind='missing_sprite' if not entries else 'ambiguous_sprite', name=name))
            continue
        grouped.setdefault(entries[0]['source'], []).append(entries[0])
    for source, entries in grouped.items():
        atlas = decode_texture(source)
        for entry in entries:
            name = entry['name']
            crop = atlas.crop(entry['pixels'])
            w, h = crop.size
            pw, ph = 1 << (w - 1).bit_length(), 1 << (h - 1).bit_length()
            padded = Image.new('RGBA', (pw, ph))
            padded.paste(crop, (0, 0))
            filename = slug(name)
            png = previews / (filename + '.png')
            padded.save(png)
            encode_blp(png, images / (filename + '.blp'), 'alpha')
            assets[name] = dict(file='Interface\\AddOns\\D3UI\\Textures\\' + filename + '.blp',
                                uv=[0, w / pw, 0, h / ph], width=w, height=h,
                                png=png.name, source=source, source_rectangle=entry['pixels'])
        print('Converted', Path(source).name, len(entries), 'sprites', flush=True)

    data = dict(windows=models, views=views, assets=assets, icons=sorted(icon_names & assets.keys()))
    (addon / 'Data.lua').write_text('D3UIData = ' + lua(data) + '\n', encoding='utf-8')
    runtime = Path(__file__).with_name('d3_ui_runtime.lua').read_text('utf-8')
    (addon / 'D3UI.lua').write_text(runtime, encoding='utf-8')
    (addon / 'D3UI.toc').write_text('## Interface: 30300\n## Title: D3 UI Workshop\n## Notes: Converted D3 layouts and icons; gameplay handlers are not implemented.\n## Version: 0.1.0\nData.lua\nD3UI.lua\n', encoding='utf-8')
    for name, controls in models.items():
        panels = views[name] or [None]
        for panel in panels:
            visible = [c for c in controls if not any((c['path'] == p or c['path'].startswith(p + '.')) and p != panel for p in views[name])]
            render_preview(name + ('-' + panel.rsplit('.', 1)[-1] if panel else ''), visible, assets, previews)
    (out / 'layout.json').write_text(json.dumps(data, indent=2), encoding='utf-8')
    (out / 'overrides.example.json').write_text(json.dumps({windows[0]: {models[windows[0]][0]['path']: {'hidden': False}}}, indent=2))
    report = dict(ui_version=471, texture_version=47, windows={k: len(v) for k, v in models.items()},
                  converted_sprites=len(assets), class_icons=len(data['icons']),
                  atlas_index_errors=atlas_errors, unresolved=reports, in_game_verified=False,
                  limitations=['No D3 gameplay callbacks, animations, dynamic lists or server features are ported.',
                               'Untranslated text shows localization keys; templates show one editable instance.',
                               'Layout and property interpretation require native-client visual verification.'])
    (out / 'conversion-report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    (out / 'README.txt').write_text('Copy D3UI into WoW/Interface/AddOns. In game: /d3ui Paragon, /d3ui SkillPane, /d3ui Traits, /d3ui SkillBar.\n/d3ui SkillPane ActiveSkillSelect selects an alternative panel; /d3ui SkillPane list lists panels.\n/d3icons [search text] opens the paged icon browser. Escape or Close dismisses windows.\nThis is a UI conversion workshop, not a functioning Paragon or D3 skills system.\nSee conversion-report.json for unsupported data. Edit overrides JSON and rebuild into a new output directory.\nRegister callbacks using D3UI.RegisterHandler(name, function) from a separate addon depending on D3UI.\n', encoding='utf-8')
    return report


def render_preview(name, controls, assets, directory):
    canvas = Image.new('RGBA', (1600, 1200), (19, 20, 24, 255))
    positions = {}
    draw = ImageDraw.Draw(canvas)
    for c in controls:
        px, py = positions.get(c['parent'], (0, 0))
        x, y = round(px + c['x']), round(py + c['y'])
        positions[c['path']] = (x, y)
        if c.get('hidden'):
            continue
        w, h = max(1, round(c['width'])), max(1, round(c['height']))
        if w > 8192 or h > 8192:
            continue
        asset = assets.get(c['textures'].get('normal'))
        if asset:
            image = Image.open(directory / asset['png']).crop((0, 0, asset['width'], asset['height'])).resize((w, h), Image.Resampling.LANCZOS)
            canvas.alpha_composite(image, (x, y))
        if c['type'] in (3, 4, 22) and c['text']:
            font = ImageFont.load_default(size=max(8, min(60, c['font_size'])))
            draw.text((x + 2, y + 2), c['text'].partition(':')[2] or c['text'], font=font, fill=(224, 204, 165))
    canvas.convert('RGB').save(directory / (name + '-layout.jpg'), quality=90)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('base'); p.add_argument('--out', required=True)
    p.add_argument('--windows', nargs='+', default=['Paragon', 'SkillPane', 'SkillBar', 'Traits'])
    p.add_argument('--overrides'); p.add_argument('--no-icons', action='store_true')
    p.add_argument('--all-atlases', action='store_true', help='Scan all TEX files instead of the 2D UI texture family')
    args = p.parse_args()
    result = convert(args.base, args.out, args.windows, args.overrides, not args.no_icons, args.all_atlases)
    print(json.dumps({k: v for k, v in result.items() if k not in ('unresolved', 'atlas_index_errors')}, indent=2))
