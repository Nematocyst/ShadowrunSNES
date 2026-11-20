# Compatibility, ROM space and known limits

## Patch order

1. Clean Shadowrun (USA), CRC32 `3F34DFF0`.
2. Gameplay patches: **Runner Pack v6**, and if you want them *Shadowrun Rebalanced v1.0* and one *Expanded Dialogue*
   option. These change bytes the editors read, so they go first.
3. Editor patches, each exported from the ROM produced by the step before (see the README's "Using more than one
   editor"). To put new scripts on characters or floor triggers, apply the Script Editor patch before opening the
   Map Editor.

A 1 MB ROM is expanded to 2 MB (filled with zeros, header byte `$7FD7` = `$0B`) by whichever tool needs space first,
exactly like the Runner Pack does.

## ROM space used

| Banks | Used by |
|---|---|
| `$80`–`$9F` | the game (each tool hooks a few places, listed in its export README) |
| `$A0`–`$A2` | Expanded Dialogue (third-party) |
| `$A3` | Map Editor: object type table, moved here when separate item copies exist |
| `$A9` | Map Editor: per-character scripts |
| `$AB` | Map Editor: own save slots and separate item records (code + tables) |
| `$AC`–`$AE` | Script Editor: moved and new scripts, new-script directory (`$AC:A200`) |
| `$AF` | Sprite Colours: extra palettes |
| `$B0`–`$B3` | Map Editor: layouts that grew |
| `$B4`–`$B7` | Text Editor: text hook and moved texts |
| `$B8`–`$BB` | Map Editor: moved map data (+ loader hook at `$80A3DA`) |
| `$BC` | Sprite Colours: repainted sprite graphics |
| `$BE`, `$BF` | Runner Pack (Arena Leagues + Glutman's Jobs; Persistent Runners and friends) |

Every editor rebuilds only its own banks on export, so the editors never overwrite each other.

### Hooks shared between tools
- Script directory reads `$80C298`, `$80F433`, `$80F473`: Script Editor (new scripts). The Runner Pack's hooks on the
  first two are kept and chained.
- Save/load/new game `$81B141`, `$81B15B`, `$809878`, map load `$80A343`, map objects `$80A38E`: Map Editor (own save
  slots, item records). The Runner Pack's save hook is kept and chained.
- `$80A3A8`: Map Editor (per-character scripts). `$80E564`: inventory list start (separate items).

## RAM used (bank $7E / $7F)

| Address | Used by |
|---|---|
| `$7E21E0`–`$7E2293` | separate item records (5 bytes each, 36 max) |
| `$7E22A0`–`$7E231C` | own-save-slot copies on the current map (19 records) |
| `$7E2340`– | Runner Pack arena copies |
| `$7FB000`–`$7FB0FF` | own-save-slot "gone" flags (one byte per copy) |
| `$7FC592`–`$7FC5FF` | own-save-slot working area |
| `$7FC630`–`$7FC67F` | extra sprite palettes |

All were checked as never written by the game across many maps, menus, combat and save/load.

## Save files

- 8 KB normally. Map Editor patches with more than 24 own-save-slot copies, or with any separate item, set the ROM
  header to **16 KB** (`$FFD8` = 4):
  - SRAM `$2000` (slot 1) / `$2200` (slot 2): `CPv1` + 256 copy flags;
  - SRAM `$2400` (slot 1) / `$2500` (slot 2): `IT` + item records.
- Saves made before such a patch load fine: copies past 24 start alive, item copies start on the map.
- BizHawk pads or truncates `.SaveRAM` to the size the core expects; RetroArch/Batocera loads a smaller `.srm` into the
  start of SRAM. Keep a backup anyway.
- Ids 0-23 of own-save-slot copies stay in the 4 spare bytes at the end of each normal save slot, so patches with up
  to 24 copies keep the 8 KB file.

## Known limits

**Map Editor**
- Separate item copies: picking one up with the in-game cursor, and using, dropping and giving a copy, were not
  tested in an emulator yet (inventory listing, spawning and save/load were). A copy is not the item the story looks
  for (e.g. a key item copy won't open the door its original opens).
- Floor triggers run their script on every frame while Jake stands inside.
- Characters: at most 32 per map (vanilla max 27; the game's object pool is 44).
- Characters whose script checks its own type number may still behave like the original (the editor notes these).
- Version note: Map Editor builds made before this release placed the extra copy flags for save slot 2 at SRAM
  `$2100`, which overlapped slot 1's. Re-export any patch that has more than 24 own-save-slot copies.

**Script Editor**
- New scripts: `$400`–`$5FF`, numbered without gaps. Ids `$3A8`–`$3B6` belong to the Runner Pack.
- Keep each script's header sizes unless you need more: changing a script's stack size changes the game's thread
  memory layout (the editor does this only when the new code needs it).

**Text Editor**
- 250 characters per text. Not measured: the karma-spending screen, shop list screens and the Matrix.

**Sprite Colours**
- Up to 40 extra palettes (ids 70-109). Some animation records are shared inside identical sprite groups, so a group
  changes together; frame records shared with other sprites are reported on export (Jake's are shared with sprite
  `$95`).

**General**
- A different emulator timing or the extra CPU cycles of a hook can change *random* street encounters compared to the
  unpatched game. This is the game's own randomness, not a bug.
