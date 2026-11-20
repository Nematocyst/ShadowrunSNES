# Shadowrun (SNES) Toolkit v1.0

Four browser editors for Shadowrun (USA, SNES), the Runner Pack v6 gameplay patch, and the full source and research
notes behind them. Released 2026-10-26.

Nothing here contains the game (no ROM, no extracted art or text). Every tool reads **your own ROM** in your browser and writes an **IPS patch** for it.

```
README.md               this file: start here
CHANGELOG.md            what each tool can do, version by version
CREDITS.md              sources and thanks
editors/                the four editors, one self-contained .html page each
  map_editor.html
  script_editor.html
  text_editor.html
  sprite_colours.html
patches/
  RunnerPack_v6/        the current gameplay patch (.ips and .bps) with its own README
  RunnerPack_v5.1/      the previous release, kept for reference
docs/
  RUNNER-PACK-OVERVIEW.md  what each Runner Pack hack does, in player terms
  EDITORS.md            how to use each editor, feature by feature
  COMPATIBILITY.md      patch order, ROM space used by each tool, save files, known limits
  TOOLKIT.md            the Python/JavaScript source: what each script does and how to rebuild the editors
  TECHNICAL_NOTES.md    the complete reverse-engineering notes (RAM/ROM maps, engine, script VM, formats)
source/                 all the code (Python tools, editor sources, data tables)
releases/               the original release zips
```

## What you need

- **Shadowrun (USA)**, unmodified: 1 MB (1,048,576 bytes), CRC32 `3F34DFF0`. A copy with a 512-byte copier header
  (1,049,088 bytes, often `.smc`) also works in the editors: they strip the header themselves.
- A desktop browser (Chrome, Edge, Firefox or Safari). The editors work offline. Nothing is uploaded anywhere.
- An IPS patcher, for example [ROM Patcher JS](https://www.marcrobledo.com/RomPatcher.js/), Floating IPS or Lunar IPS.
- An emulator. These patches have been tested with snes9x-based emulators; the user plays them in BizHawk and Batocera
  (RetroArch).

## Quick start

1. **Optional: gameplay patch first.** Apply `patches/RunnerPack_v6/Shadowrun_RunnerPack_v6.ips` to your clean ROM
   (see its README). Third-party patches such as *Shadowrun Rebalanced* or *Expanded Dialogue* go on at this step as well.
2. **Open an editor.** Double-click a file in `editors/`. Click *Open ROM…* (or drop the ROM on the page) and choose the
   ROM from step 1, or your clean ROM.
3. **Edit.** Your work is kept in the browser automatically. *Save edits* writes a small `.json` file you can load
   again later, on the same ROM or on a different one.
4. **Export patch.** You get a `.zip` with the `.ips` patch, your edits file and a README that says exactly which ROM
   the patch is for and what CRC32 the result should have.
5. **Apply the .ips to the same ROM you opened** in step 2, and play.

### Using more than one editor

Each patch is made for the exact ROM you opened. To combine editors, chain them:

```
clean ROM -> (Runner Pack, other patches) -> ROM A
ROM A -> Text Editor  -> export, apply -> ROM B
ROM B -> Script Editor -> export, apply -> ROM C
ROM C -> Map Editor    -> export, apply -> ROM D   (play this one)
```

Any order works between the editors. One exception: to use **new scripts** in the Map Editor (on a character or a
floor trigger), the Script Editor patch must already be applied to the ROM you open in the Map Editor.

If you later change something earlier in the chain (a new Runner Pack, more text edits), load each editor's
`.json` edits file on the new ROM and export again. Old patches do not apply on top of a different ROM.

## The editors in one paragraph each

**Map Editor** — rearrange any of the game's maps: move, add, flip and delete building blocks, repaint floors, change
a map's floor tile set, music and camera limits, edit exits, walls, floor triggers, walking points and sight blockers,
and place characters. Copies of characters can keep their own state in your saves, copies of items can be separate
items, and any placed character or floor trigger can run a different script.

**Script Editor** — every event in the game is one of 936 small scripts. The editor decompiles each one to readable
code, recompiles as you type, and writes it back. It can also add **brand-new scripts** (numbered from `$400`) that
other scripts, characters and floor triggers can run.

**Text Editor** — rewrite any of the 1,589 texts (conversations, messages, keywords, names, menus) with a live
preview in the game's font, in the right window size for where the text appears. Longer texts are moved to free space.

**Sprite Colours** — give a character its own palette so you can recolour it alone, or change a shared palette for
everyone; repaint its pixel art frame by frame, or export and import frames as PNG.

Full instructions: [docs/EDITORS.md](docs/EDITORS.md).

## Save files

- Most patches keep the normal 8 KB save, and your existing saves keep working.
- Two Map Editor features make the save file **16 KB**: more than 24 copies with their own save slot, and any
  separate item copy. BizHawk and RetroArch/Batocera enlarge an old 8 KB save by themselves and it still loads.
  **Back up your `.srm` / `.SaveRAM` before trying such a patch.**
- Keep the save next to the ROM with the same file name.

## Status and testing

Everything listed in the CHANGELOG was verified in a snes9x emulator (automated play-throughs, save/load,
pixel and RAM comparisons) and the editor pages with automated browser tests. Each feature notes what was
**not** tested in [docs/COMPATIBILITY.md](docs/COMPATIBILITY.md#known-limits). Report problems with the README of the
patch that caused them: it lists every hook and address it touched.

## Credits

Reverse engineering, tools and patches: Nematocyst, with Claude. See [CREDITS.md](CREDITS.md). Licensed under the MIT license ([LICENSE](LICENSE)).
Shadowrun © its respective rights holders; this toolkit contains no game data beyond what is needed to name things
(map names, script names, type categories) and three small preview pictures.
