# Using the editors

All four editors work the same way:

- **Open ROM…** (or drop the file on the page). Shadowrun (USA) only; 1 MB vanilla or 2 MB patched ROMs both work.
  The ROM never leaves your computer.
- Your edits are kept in the browser while you work and picked up again when you reopen the same ROM.
- **Save edits** writes a `.json` file. **Load edits…** reads it back, on the same ROM or another one (the editor warns
  when the ROM is different; check the result before exporting).
- **Export patch** downloads a `.zip`: the `.ips` patch, your edits file and a `README.txt` naming the ROM it is for,
  the CRC32 of the result and every address the patch touched.
- Numbers shown with `$` are hexadecimal, the same numbering the game's code uses.

---

## Map Editor (`map_editor.html`)

Pick a map in the toolbar, then a mode.

### Blocks
Maps are built from about 550 building blocks (walls, desks, doors, cars, stairs). Click a block to select it; drag to
move, **Shift**+drag to raise or lower; **Mirror**, **Duplicate**, **Delete**, move it between the **front and back
layers**, or add any block from the catalogue. Each block brings its
own walls, so where Jake can walk changes with it.

Meters at the side show the limits the game can draw: tiles (max ~1,010), palettes (7), wall boxes (~260) and the
layout size. Stay inside them: over the tile limit the game draws wrong graphics.

### Floor
Paint the floor with the map's tile set, erase cells, or switch the map's **tile set** (cells the new set doesn't have
are erased). Several maps share one layout: the editor warns when a change affects other maps too.

### Exits & walls
Every invisible box on the map, drawn over the picture:

- **Exits**: walking into the box takes Jake to another location. Pick where it leads.
- **Walls**: invisible walls that belong to the map (often the street edge).
- **Floor triggers**: run a script while Jake stands inside. The script number is typed in hex (e.g. `$1E4`).
  New scripts from the Script Editor (`$400` and up) work once the ROM you opened contains them.
  A trigger runs its script **again on every frame** while Jake is inside: a new script that must happen once should
  check and set a story variable.
- **Walking points**: numbered spots scripts send characters to. Points can only be deleted from the end, because
  scripts count them by number.
- **Sight blockers**: boxes that block line of sight in combat.
- **Camera area**: the camera follows Jake only while he is inside this rectangle. Add, move, resize or delete it.

Add, move (drag or type coordinates), switch off or delete any box. A map whose boxes or characters were added or
deleted is moved to free space when you export; a map with the same counts is rewritten in place.

### Characters
Every placed character and object. Drag to move, **Shift**+drag to raise. Add anything from the catalogue (it
appears in the middle of the view), delete, or copy.

- **Runs script** (hex): give this one character a different script from the rest of its type, for example a new
  script from the Script Editor. Leave empty for the type's own script (shown greyed out).
- **Own save slot** (types marked ◆ keep a save record: health, alive or gone): a copy with its own save slot lives
  and dies on its own. Up to 19 per map and 256 in the game. Past 24 the save file grows to 16 KB.
  Not available for items and hireable runners.
- **Separate item** (items only): the copy gets an item type of its own, so it is a second item: you can pick up both,
  and the inventory lists both under the same name. Up to 36 in the game; the save file becomes 16 KB.
  The game's own placement of an item, and items whose script checks its own number, stay as they are.
- Copies of ◆ types without their own slot share the original's record: the editor warns that extra copies may not
  appear, and that killing or taking one removes the others.

### Toolbar extras
- **Music**: the song a map plays (or "keep the current song").
- **Undo / Redo**, zoom (1×, 2×, 3×), overlays for block walls and exits, and **Revert map** to drop all changes to
  the map you are on.

---

## Script Editor (`script_editor.html`)

Everything that happens in the game (doors, conversations, fights, shops) is one of 936 scripts. Find a script by
name, by who uses it, by number, or (tick the box) by text inside the code. The list marks edited scripts with ●.

- The code reads like this:
  ```
  script $060 args 1 returns no locals 1 stack 4
      self = arg1
      ADD_NUYEN(1234)        ; a new line: +1,234 nuyen
      SET_VAR(0, 42)
      REMOVE_SELF(self)
      end
  ```
  `self` is the object running the script; `L.w1`, `L.b5` its local slots; `var[42]` the story variables;
  `gb[$xxxx]` / `gw[$xxxx]` any byte or word of RAM bank $7E. `if … { } else { }`, `while … { }`, `goto` and labels
  work. The *Commands* panel lists every command the game has, with how many values it takes.
- It recompiles as you type and points at the line with the problem. Export stays off until every edited script
  compiles.
- Scripts that grow are moved to free space automatically. **Revert to original** undoes one script.
- Some scripts are recognised by the Runner Pack by their address; the editor warns before you edit one of those.

### Brand-new scripts
**+ New script** adds a script numbered from `$400` (up to `$5FF`). Write its code, then run it:

- from any script: `script_400(self)` (pass as many values as its `args`),
- from a placed character or a floor trigger in the Map Editor (after this patch is applied to the ROM you open there).

New scripts can call each other before they exist in the ROM. Calling a new script that doesn't exist is an error.
Only the highest-numbered new script can be deleted (the numbers must stay without gaps); deleting one that others
still call switches Export off until you fix the callers. Open a patched ROM later and the new scripts are listed as
"added by an earlier patch": edit, delete or add more and export again.

---

## Text Editor (`text_editor.html`)

All 1,589 texts: conversations (by person and topic), messages, keywords, names, and 85 game menu texts.
Search by words, person or keyword; filter by group.

- The preview uses the game's font and the window the text appears in (conversation box, floating message, choice
  list, or the game's menus), so you see where lines wrap and whether the text fits.
- `|` before a word shows it emphasised, like the game does.
- Longer texts are moved to free space automatically; shorter ones are written in place. Limit: 250 characters.
- Works on vanilla, Runner Pack and Expanded Dialogue ROMs.

---

## Sprite Colours (`sprite_colours.html`)

Pick a character; the preview animates it.

- **Colours**: click a swatch and choose a colour. Most characters share palettes (Jake's is used by 117 sprites):
  choose **its own palette** to recolour only this character, or change the shared palette for everyone.
- **Paint pixels**: pencil, flood fill and colour picker (also right-click or Alt-click) on any frame; **Copy frame /
  Paste / Paste mirrored**; **Save frame as PNG / Load PNG into frame** (same size; colours snap to the palette);
  undo and reset. A pixel edit changes every frame that shows the same graphics.
- Apply this patch **after** the Runner Pack (the Runner Pack's sprite cache must already be in the ROM).
