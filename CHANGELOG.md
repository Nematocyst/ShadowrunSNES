# Changelog

## Toolkit v1.0 — 2026-10-26

First release bundling everything.

### Map Editor
- Blocks: move, raise, mirror, duplicate, delete, add from ~550 blocks; front/back layers; tile, palette, wall and
  layout meters.
- Floor: paint/erase; switch a map's floor tile set.
- Exits, walls, floor triggers, walking points, sight blockers and camera limits: add, move, switch off, delete.
- Characters: move, add, copy, delete; music per map.
- Own save slots for copied characters: up to 19 per map, 256 in the game (more than 24 use a 16 KB save file).
- Separate item copies: copies of items get item types of their own (up to 36), listed separately in the inventory.
- Per-character scripts and hex script numbers on floor triggers, including new scripts from the Script Editor.
- Fixed: with more than 24 own-save-slot copies, save slot 2's extra flags overlapped slot 1's (now at SRAM `$2200`).

### Script Editor
- Decompile all 936 scripts to SRScript, edit with live compile errors, write back (in place or moved).
- Brand-new scripts `$400`–`$5FF`, callable from scripts, characters and floor triggers; works on Runner Pack ROMs.

### Text Editor
- All 1,589 texts plus 85 menu texts, live preview in the game's font and the right window (conversation box,
  floater, choice list, menus); longer texts moved automatically.

### Sprite Colours
- Own palettes per character or shared changes; pixel painting with pencil, fill, picker, copy/paste (mirrored) and
  PNG frame export/import.

### Runner Pack v6 (2026-10-18)
- Persistent Runners v5, More Enemies With Runners v2, Smart Targeting, Less Slowdown, Arena Leagues, Glutman's Jobs.
  Details in `patches/RunnerPack_v6/README.txt`.
