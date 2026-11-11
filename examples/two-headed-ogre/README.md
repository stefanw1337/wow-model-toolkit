# Two-Headed Ogre (male) from your own Heroes of the Storm and WoW files

Builds the male Two-Headed Ogre of CoA's Two-Players mode: the Heroes of the Storm Cho'Gall body on the WoW
Cho'Gall skeleton, with his animations, carry poses, weapon grips and hair swing, plus the WoW Cho'Gall model it
is built on. No game files are stored here; everything comes from installs you own.

```
python scripts/two_headed_ogre/setup_m3addon.py
python scripts/two_headed_ogre/build.py <out> --hots <hots folder> --wod <chogall folder>
```

- `--hots`: `storm_hero_chogall_base.m3`, `storm_hero_chogall_requiredanims.m3a` and
  `storm_hero_chogall_base_diff.dds` from Heroes of the Storm (CascExtractor: filter `storm_hero_chogall_`).
- `--wod`: `chogall.m2`, `chogall00.skin` and his `.anim`, `chogalltop.blp`, `chogallbottom.blp` from WoW
  (`creature/chogall/`).
- `tuning.json`: the hand-made parts (loincloth weights, baked hair swing, weapon and attachment points, blend
  times). It contains no mesh or texture data.

Output: `Creature\TwoHeadedOgre\TwoHeadedOgreMale(.m2, Held.m2, .blp)` and `Creature\ChoGall\...`, identical to the
2026-11-11 in-game build when fed the same files. Needs numpy and Pillow; m3addon (SC2Mapster, GPL-2) is downloaded
by the setup script and never committed.
