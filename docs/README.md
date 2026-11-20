# Documentation

| Page | Read it to |
| --- | --- |
| [RUNNER-PACK-OVERVIEW.md](RUNNER-PACK-OVERVIEW.md) | see what each Runner Pack hack does, in player terms |
| [EDITORS.md](EDITORS.md) | learn the four browser editors feature by feature |
| [COMPATIBILITY.md](COMPATIBILITY.md) | check patch order, ROM space, save files and known limits |
| [TOOLKIT.md](TOOLKIT.md) | find what each script in `source/` does and rebuild the editors |
| [TECHNICAL_NOTES.md](TECHNICAL_NOTES.md) | read the full reverse-engineering log (below is an index by topic) |

`TECHNICAL_NOTES.md` is a chronological log, newest findings last. Early sections can be superseded by later ones (the runner patch went through four stages before v5). When two sections disagree, the later date wins.

## Index of TECHNICAL_NOTES.md

### The game and its engine

- [ROM](TECHNICAL_NOTES.md#rom)
- [RAM map (Jake)](TECHNICAL_NOTES.md#ram-map-jake)
- [Party / hired runners](TECHNICAL_NOTES.md#party--hired-runners)
- [Runner gear (armor/weapon restriction)](TECHNICAL_NOTES.md#runner-gear-armorweapon-restriction)
- [Script engine](TECHNICAL_NOTES.md#script-engine)
- [Tooling (shadowrun_toolkit.zip)](TECHNICAL_NOTES.md#tooling-shadowrun_toolkitzip)
- [Save system & karma spending (for the "permanent runners with karma" idea)](TECHNICAL_NOTES.md#save-system--karma-spending-for-the-permanent-runners-with-karma-idea)
- [RUNNER NAME TABLE (all confirmed, 2026-10-15)](TECHNICAL_NOTES.md#runner-name-table-all-confirmed-2026-10-15)
- [Shops (2026-10-16)](TECHNICAL_NOTES.md#shops-2026-10-16)
- [Cyberware (2026-10-16)](TECHNICAL_NOTES.md#cyberware-2026-10-16)

### Runner Pack: how each hack was built

- [Design: persistent runners with own karma (user's chosen design, 2026-10-15)](TECHNICAL_NOTES.md#design-persistent-runners-with-own-karma-users-chosen-design-2026-10-15)
- [Stage 1 BUILT: Persistent Runners (2026-10-15) - release/Shadowrun_PersistentRunners_Stage1.ips, builder shadowrun_toolkit/build_runners.py](TECHNICAL_NOTES.md#stage-1-built-persistent-runners-2026-10-15---releaseshadowrun_persistentrunners_stage1ips-builder-shadowrun_toolkitbuild_runnerspy)
- [Stage 2 groundwork (2026-10-16)](TECHNICAL_NOTES.md#stage-2-groundwork-2026-10-16)
- [Stage 2 BUILT: per-runner karma + "who?" list (2026-10-16) - Shadowrun_PersistentRunners_v2.ips (includes stage 1)](TECHNICAL_NOTES.md#stage-2-built-per-runner-karma--who-list-2026-10-16---shadowrun_persistentrunners_v2ips-includes-stage-1)
- [Stage 3 BUILT: copy equipping (2026-10-16) - Shadowrun_PersistentRunners_v3.ips (includes stages 1-2), CRC32 8239AF2D](TECHNICAL_NOTES.md#stage-3-built-copy-equipping-2026-10-16---shadowrun_persistentrunners_v3ips-includes-stages-1-2-crc32-8239af2d)
- [Stage 4 BUILT: runner cyberware (2026-10-16) - Shadowrun_PersistentRunners_v4.ips (stages 1-4), CRC32 E2568E84, code to $BF89C1](TECHNICAL_NOTES.md#stage-4-built-runner-cyberware-2026-10-16---shadowrun_persistentrunners_v4ips-stages-1-4-crc32-e2568e84-code-to-bf89c1)
- [More Enemies With Runners (2026-10-16) - Shadowrun_MoreEnemiesWithRunners.ips (standalone), builder shadowrun_toolkit/build_enemies.py](TECHNICAL_NOTES.md#more-enemies-with-runners-2026-10-16---shadowrun_moreenemieswithrunnersips-standalone-builder-shadowrun_toolkitbuild_enemiespy)
- [Smart Targeting patch (build_targeting.py, code $BFE800, RAM $7F99C0-$7F99E3)](TECHNICAL_NOTES.md#smart-targeting-patch-build_targetingpy-code-bfe800-ram-7f99c0-7f99e3)
- [Runner Pack v1 (build_all.py)](TECHNICAL_NOTES.md#runner-pack-v1-build_allpy)
- [v5 / Runner Pack v2 (2026-10-16): RAM relocation fix](TECHNICAL_NOTES.md#v5--runner-pack-v2-2026-10-16-ram-relocation-fix)
- [Fixed (placed) enemies / spawn points (2026-10-16)](TECHNICAL_NOTES.md#fixed-placed-enemies--spawn-points-2026-10-16)
- [Indoor reinforcements (More Enemies v2, Runner Pack v3, CRC32 32EC6BD5)](TECHNICAL_NOTES.md#indoor-reinforcements-more-enemies-v2-runner-pack-v3-crc32-32ec6bd5)
- [Slowdown investigation (2026-10-16)](TECHNICAL_NOTES.md#slowdown-investigation-2026-10-16)
- [Less Slowdown = sprite cache (build_speed.py, Runner Pack v4 CRC32 28036CBB)](TECHNICAL_NOTES.md#less-slowdown--sprite-cache-build_speedpy-runner-pack-v4-crc32-28036cbb)
- [Arena Leagues (2026-10-17) - build_arena.py, code/data/scripts in bank $BE ($BE8000, ~2.6 KB)](TECHNICAL_NOTES.md#arena-leagues-2026-10-17---build_arenapy-codedatascripts-in-bank-be-be8000-26-kb)
- [Ending bug fix (2026-10-18) - Runner Pack v5.1, CRC32 77A00E68](TECHNICAL_NOTES.md#ending-bug-fix-2026-10-18---runner-pack-v51-crc32-77a00e68)
- [Arena fix v5.2 (2026-10-18) - Runner Pack v5.2, CRC32 329573CC](TECHNICAL_NOTES.md#arena-fix-v52-2026-10-18---runner-pack-v52-crc32-329573cc)
- [Glutman's Jobs (2026-10-18) - build_jobs.py (inside the arena module), Runner Pack v6, CRC32 E4EDC20E](TECHNICAL_NOTES.md#glutmans-jobs-2026-10-18---build_jobspy-inside-the-arena-module-runner-pack-v6-crc32-e4edc20e)

### Formats and decoders

- [Script dump / Script Atlas (2026-10-20) - dump_scripts.py, build_browser.py](TECHNICAL_NOTES.md#script-dump--script-atlas-2026-10-20---dump_scriptspy-build_browserpy)
- [All natives named (2026-10-20)](TECHNICAL_NOTES.md#all-natives-named-2026-10-20)
- [Object hover names - confirmed in code (2026-10-20)](TECHNICAL_NOTES.md#object-hover-names---confirmed-in-code-2026-10-20)
- [Readable disassembly (2026-10-20) - srdisasm.py](TECHNICAL_NOTES.md#readable-disassembly-2026-10-20---srdisasmpy)
- [Sprite graphics - decoded (2026-10-20) - srgfx.py](TECHNICAL_NOTES.md#sprite-graphics---decoded-2026-10-20---srgfxpy)
- [Maps and background graphics (2026-10-20) - srlz.py, capmaps.py](TECHNICAL_NOTES.md#maps-and-background-graphics-2026-10-20---srlzpy-capmapspy)
- [Sprite import tool (2026-10-20) - srsprite.py](TECHNICAL_NOTES.md#sprite-import-tool-2026-10-20---srspritepy)
- [Map building blocks - decoded (2026-10-20) - srmap.py](TECHNICAL_NOTES.md#map-building-blocks---decoded-2026-10-20---srmappy)

### Editors: how each feature was built

- [Map editor (2026-10-20) - editor/srcore.js, editor_template.html, build_editor.py](TECHNICAL_NOTES.md#map-editor-2026-10-20---editorsrcorejs-editor_templatehtml-build_editorpy)
- [Map editor v2 (2026-10-20): floors, exits/walls/triggers, characters](TECHNICAL_NOTES.md#map-editor-v2-2026-10-20-floors-exitswallstriggers-characters)
- [Text editor (2026-10-20) - editor/srtext.js, text_head.part + text_body.part, build_text_editor.py, build_text_index.py](TECHNICAL_NOTES.md#text-editor-2026-10-20---editorsrtextjs-text_headpart--text_bodypart-build_text_editorpy-build_text_indexpy)
- [Map editor v3 (2026-10-20): adding/deleting exits, walls, triggers, characters (map-data relocation hook)](TECHNICAL_NOTES.md#map-editor-v3-2026-10-20-addingdeleting-exits-walls-triggers-characters-map-data-relocation-hook)
- [Own sprite palettes (2026-10-21) - srpal.py, srsprite.py --own, editor/srspr.js + sprite_*.part](TECHNICAL_NOTES.md#own-sprite-palettes-2026-10-21---srpalpy-srspritepy---own-editorsrsprjs--sprite_part)
- [Script editor (2026-10-25) - editor/srvm.js, script_head/body.part, build_script_editor.py, data/natives.json, data/script_meta.json](TECHNICAL_NOTES.md#script-editor-2026-10-25---editorsrvmjs-script_headbodypart-build_script_editorpy-datanativesjson-datascript_metajson)
- [Own save slots for copied characters (2026-10-25) - srcore.js installCopies/cpCode, editor build_type_class.js](TECHNICAL_NOTES.md#own-save-slots-for-copied-characters-2026-10-25---srcorejs-installcopiescpcode-editor-build_type_classjs)
- [Map editor v4 (2026-10-25): floor tile set, walking points, sight blockers](TECHNICAL_NOTES.md#map-editor-v4-2026-10-25-floor-tile-set-walking-points-sight-blockers)
- [Text windows (2026-10-25) - build_msg_windows.js (adds meta.msg_win), text_body.part previews](TECHNICAL_NOTES.md#text-windows-2026-10-25---build_msg_windowsjs-adds-metamsg_win-text_bodypart-previews)
- [Pixel painting (2026-10-25) - srspr.js (cellPixels, frame(word, ov), stripUsers, applyPixels), sprite_body.part](TECHNICAL_NOTES.md#pixel-painting-2026-10-25---srsprjs-cellpixels-frameword-ov-stripusers-applypixels-sprite_bodypart)
- [Music per map (2026-10-26)](TECHNICAL_NOTES.md#music-per-map-2026-10-26)
- [Pixel painting extras (2026-10-26) - sprite_body.part](TECHNICAL_NOTES.md#pixel-painting-extras-2026-10-26---sprite_bodypart)
- [Camera limits (2026-10-26)](TECHNICAL_NOTES.md#camera-limits-2026-10-26)
- [Game menu windows (2026-10-26) - editor/mk_text_logger.py, menu_fuzz.py, build_eng_windows.py (meta.eng_win)](TECHNICAL_NOTES.md#game-menu-windows-2026-10-26---editormk_text_loggerpy-menu_fuzzpy-build_eng_windowspy-metaeng_win)
- [More than 24 own save slots: 16 KB save file (2026-10-26) - srcore.js cpCode/installCopies](TECHNICAL_NOTES.md#more-than-24-own-save-slots-16-kb-save-file-2026-10-26---srcorejs-cpcodeinstallcopies)
- [Brand-new scripts (2026-10-26) - editor/srvm.js (readNewDir, newHookCode, applyScripts), script_body.part](TECHNICAL_NOTES.md#brand-new-scripts-2026-10-26---editorsrvmjs-readnewdir-newhookcode-applyscripts-script_bodypart)
- [Map editor: scripts on characters and floor triggers (2026-10-26) - srcore.js installObjScripts/osCode, editor_template.html](TECHNICAL_NOTES.md#map-editor-scripts-on-characters-and-floor-triggers-2026-10-26---srcorejs-installobjscriptsoscode-editor_templatehtml)
- [Separate item copies = new item types (2026-10-26) - srcore.js installItems + cpCode(orig, nItems), editor_template.html](TECHNICAL_NOTES.md#separate-item-copies--new-item-types-2026-10-26---srcorejs-installitems--cpcodeorig-nitems-editor_templatehtml)

### Notes from play and other people's work

- [Findings from the user's late-game save (Shadowrn.srm, hotel in Daley, 2026-10-15)](TECHNICAL_NOTES.md#findings-from-the-users-late-game-save-shadowrnsrm-hotel-in-daley-2026-10-15)
- [Other hacks by RetchERezzed (user-supplied, 2026-10-15)](TECHNICAL_NOTES.md#other-hacks-by-retcherezzed-user-supplied-2026-10-15)
