# The source (`source/`)

Python 3.10+ and Node 18+. Most tools take the ROM path as their first argument. A few research scripts still have
the author's paths as defaults (`/home/claude/shadowrun.sfc`): pass your own ROM path or edit the constant at the top.

## Rebuilding the editors

Run from `source/`:

```
python3 editor/build_editor.py         data/editor_maps.json     data/previews/map_preview.png    map_editor.html
python3 editor/build_script_editor.py  data/natives.json         data/script_meta.json            script_editor.html
python3 editor/build_text_editor.py    data/text_index_meta.json data/previews/text_preview.png   text_editor.html
python3 editor/build_sprite_editor.py  data/srpal_code.json      data/previews/sprite_preview.png sprite_colours.html
```

The built page is a fragment meant for hosting inside an artifact; the copies in `editors/` were wrapped in a full
HTML document (`<!doctype html>`, charset, viewport) so they open straight from disk.

| Editor source | Contents |
|---|---|
| `editor/srcore.js` | map core: layout (de)compression, map drawing, collision boxes, map data, own save slots, item types, per-character scripts, IPS |
| `editor/editor_template.html` | Map Editor page |
| `editor/srvm.js` | script VM: decoder, decompiler (SRScript), compiler, ROM writer, new-script directory and hooks |
| `editor/script_head.part`, `script_body.part` | Script Editor page |
| `editor/srtext.js` | text core: Huffman decode/encode with the game's tree, font preview, text inventory, writer |
| `editor/text_head.part`, `text_body.part` | Text Editor page |
| `editor/srspr.js` | sprites: animations/frames, palettes, pixel cells, strip pool |
| `editor/sprite_head.part`, `sprite_body.part` | Sprite Colours page |

Data tables (`data/`): `editor_maps.json` (map names and object labels), `natives.json` (names of the 219 script
commands), `script_meta.json` (script names, users, Runner Pack markers), `text_index_meta.json` (text groups,
people, window sizes), `type_class.json` (items, runners, self-referencing types), `srpal_code.json` (palette hook
code), `zones.json` (floor triggers per map), `text_index.json` (text ids by group; no text).

Metadata builders: `build_text_index.py`, `editor/build_type_class.js`, `editor/build_msg_windows.js`,
`editor/build_eng_windows.py` (+ `editor/mk_text_logger.py`, `editor/menu_fuzz.py` to measure menu windows in the
emulator).

## Patch builders (the Runner Pack)

| Script | Builds |
|---|---|
| `build_all.py` | the combined Runner Pack (calls the ones below in order) |
| `build_runners.py`, `build_runners_v4.py` | Persistent Runners (hired runners stay, karma, gear, cyberware) |
| `build_enemies.py` | More Enemies With Runners |
| `build_targeting.py` | Smart Targeting |
| `build_speed.py` | Less Slowdown (sprite cache) |
| `build_arena.py`, `build_jobs.py` | Arena Leagues and Glutman's Jobs |

## Research tools

| Script | What it does |
|---|---|
| `snes_retro.py` | headless emulator harness (stable_retro-style API) driving the snes9x libretro core through ctypes; `SR_ROM=rom.sfc python3 script.py`. The core is not included: see `BUILD_CORE.md`. |
| `srdisasm.py` | readable, rebuildable disassembly of the whole ROM |
| `dis65816.py` | small 65816 disassembler for any LoROM address |
| `disassemble.sh` | snes2asm + WLA-DX round trip (tools not included; see `README.md`) |
| `srscript.py`, `srasm.py` | script bytecode disassembler / assembler |
| `dump_scripts.py`, `build_browser.py`, `browser_template.html` | all 936 scripts as pseudo-code with cross-references -> the Script Atlas page |
| `srlz.py` | graphics/layout decompressor (port of `$809E1E`) |
| `srmap.py`, `capmaps.py` | map renderer from the ROM; whole-map captures from the emulator |
| `srgfx.py`, `srsprite.py`, `srpal.py` | sprite decoding, PNG export/import, own palettes |
| `ips.py` | apply / list IPS patches |
| `gg.py` | Game Genie decoder |

## Where to read more

`docs/TECHNICAL_NOTES.md` is the complete research log: RAM and ROM maps, the script VM, every native command,
formats (maps, layouts, texts, sprites, palettes), save system, and how each patch and editor feature was built and
tested.
