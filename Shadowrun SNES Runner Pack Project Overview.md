# Shadowrun SNES Runner Pack: Project Overview

Oct 18, 2026 · @Fabio

## Summary

The Runner Pack is one patch for Shadowrun (SNES, USA) that bundles five gameplay hacks. The current release is **Runner Pack v5.2**, file `Shadowrun_RunnerPack_v5.2.zip`, which turns the clean 1 MB ROM into a 2 MB ROM with CRC32 `329573CC`. Every hack was built by reverse-engineering the original game code, and each one also builds as its own patch.

| Hack | What it does in one line |
| --- | --- |
| Persistent Runners v5 | Hired runners never leave on their own; each keeps his own karma, stats and gear. |
| More Enemies With Runners v2 | More street enemies and indoor reinforcements the more runners you have. |
| Smart Targeting | A snaps the cross-hair to the nearest enemy, L/R cycle targets, hold A to keep firing. |
| Less Slowdown | Reuses unchanged character sprites, so crowded rooms lag much less. |
| Arena Leagues | After the 10 arena fights: a Pro league (2 fighters at once, prizes x2) and an Elite league (3 at once, prizes x3). |

The pack stacks with two hacks by other people: Shadowrun Rebalanced v1.0 and Expanded Dialogue v1.1 (any one of options A, B or C). Old saves load without starting over.

## How to install

Apply the patch to an untouched Shadowrun (USA).sfc: 1,048,576 bytes, CRC32 `3F34DFF0`.

1. Open ROM Patcher JS (marcrobledo.com/RomPatcher.js) in a browser.
2. Pick the clean ROM as "ROM file" and `Shadowrun_RunnerPack_v5.2.ips` as "Patch file".
3. If the ROM has a 512-byte copier header (1,049,088 bytes, often `.smc`), tick the box that removes it. Without that the patch lands 512 bytes off and the game will not boot. The `.bps` version of the patch checks the source ROM and warns about this.
4. Apply and save the new `.sfc`.
5. Optional: apply Rebalanced v1.0 and/or one Expanded Dialogue option on top, in any order. None of them touch the same bytes.
6. Play in BizHawk, Batocera or any SNES emulator.

Saves: keep the `.srm` next to the ROM under the same name. Saves from the original game, from earlier Runner Packs and from the older separate patches all load. The pack's extra data lives in spare bytes of the normal save, so a pack save also still loads in the original game.

## Persistent Runners v5

In the original game a hired shadowrunner leaves after a timer runs out and loses whatever you gave him. This hack makes runners real party members you can develop.

- **They stay.** A hired runner never leaves on his own. If one dies, he goes back to where you hired him and can be hired again.
- **Own karma and stats.** Each of the 12 runners (Spatter, Jetboy, Norbert, Frogtongue, Anders, Akimi, Kitsune, Steelflight, Jangadance, Hamfist, Orifice, Dances With Clams) earns his own karma. The karma screen gets a "who?" list to pick the runner whose Body, Strength or skills you raise. Raising Body also raises max stamina by 10.
- **Gear sticks.** Weapons and armor you give a runner stay with him, even after you dismiss and rehire him later.
- **Copy equipment (paid).** You can copy gear onto a runner for a fee, so you don't need to buy everything twice.
- **Cyberware for runners.** The street doc sells Dermal armor and Wired reflexes for runners too, at full price per runner. Skillsofts stay Jake-only.
- **Strength per runner.** Giving or copying gear checks the runner's own Strength (raised with his own karma). Too weak and the game says "Not strong enough."
- **Self-repair on load.** If a save holds corrupted runner data (from the v1 memory bug), loading repairs it. Any stat below the runner's starting value or above 30 goes back to the starting value. Max stamina is recalculated from Body, and impossible karma or cyberware flags are cleared. Real progress is kept.

The runner table (246 bytes: stats, karma, cyberware) is saved in spare bytes at the end of each save slot. Only 4 spare bytes remain there.

## More Enemies With Runners v2

A bigger party draws more trouble, which means more nuyen and karma to pay for the runners. Everything scales with the number of hired runners in the party (0 to 3); with no runners the game plays as the original.

**Street enemies.** Random enemies (gangs, ghouls and so on) roll a dice check each time you enter a map. With runners the check counts as 1.2x / 1.4x / 1.6x the normal chance, and the cap of 4 active enemies per visit becomes 5 / 6 / 6.

**Indoor reinforcements.** In 63 building "dungeon" areas (office tower floors, corridor complexes, caves, sewers) every guard present when you walk in has a 20% / 40% / 60% chance to call one reinforcement. Reinforcements arrive one at a time at that guard's post, a step to the side, with the same look, weapon and health. A director only lets one in when the game has room for it:

- at least 30 free script threads (of 48) and 12 free object slots
- fewer than 2 reinforcements alive at once
- the game isn't already slowing down (checked every 64 updates)

Bosses and one-off special enemies are never copied. The scripted "Playtime for Otto" ambush is left alone. Reinforcements never touch your save: leave and come back and the area rolls again.

**Cut-scenes.** Since v5.1 the hack switches itself off during story cut-scenes (the intro, the flashbacks and the ending recap), so no extra enemies wander into them.

## Smart Targeting

Aiming in the original means steering the cross-hair by hand onto each enemy. This hack makes combat quick on a controller.

| Button | Effect |
| --- | --- |
| A | Puts the cross-hair straight on the nearest on-screen enemy and fires. |
| L / R | Jumps to the next enemy to the left / right. |
| Hold A | Keeps firing with every weapon. The cross-hair stays locked on the target and moves on to the next nearest enemy when it drops. |
| D-pad | Breaks the lock so you can aim by hand. |
| B | Cancels. |

The snap allows a few pixels of slack, because the game itself nudges the cross-hair onto whatever it hovers. That made L/R cycling unreliable until v2 of the pack.

## Less Slowdown

Crowded rooms run noticeably faster. A profiler showed why the game lags: it rebuilds every character's sprites from scratch on each update, including working out which parts hide behind walls and furniture. In busy rooms that is more than half of all its work.

The hack keeps a cache of each character's finished sprite pieces. A character whose pose, screen position, depth, palette and graphics slot haven't changed reuses last update's pieces instead of rebuilding them. While the screen scrolls, everything moves, so there is no gain then.

- Measured on the 106 rooms that lag in the original: average speed went from 79% to 89% of full speed, and 26 of them now run at full speed.
- The worst rooms improve a lot but still slow down (one office fight room 49% to 65%, a corridor 56% to 91%).
- Checked across 507 areas: 771,805 cache reuses, 0 differences from the sprites the game would have drawn.

The Wastelands club, which you reported as slow on the Raspberry Pi 4, runs at 95–100% in all three emulator cores tested here. That points to the Pi side (lighting and transparency effects in the emulator) rather than the game.

## Arena Leagues

The arena (The Cage) becomes a renewable source of money for the late game. In the original, after its 10 fights the owner only says "No more fighters left."

1. Win all 10 fights as usual. Talk to the arena owner. He says: *"No more fighters, chummer. Come back in few days: pro league! Double fighters, double nuyen!"*
2. Sleep once in any bed. The **Pro league** starts: the same 10 fights, but every fighter brings a copy of himself, and every prize is doubled.
3. Win those 10, talk to him, sleep again. The **Elite league** starts: 3 fighters at once, prizes tripled. After the elite league the arena is done.

| League | Fighters per fight | Prizes | Total for 10 fights |
| --- | --- | --- | --- |
| Amateur (original) | 1 | 300 to 8,000 nuyen | 37,000 nuyen |
| Pro | 2 | 600 to 16,000 nuyen | 74,000 nuyen |
| Elite | 3 | 900 to 24,000 nuyen | 111,000 nuyen |

- A fight is won only when every fighter is down. The copies fight with the original fighter's own moves and each gives full karma, so karma doubles or triples too.
- Fights 1 to 6 stop when Jake drops to 5 hitpoints or less (an arena loss, no prize, rematch allowed). Fights 7 to 10 are to the death, and losing them is game over. Both are the original game's rules.
- The owner's fight offer and the prize text show the league and the new amounts. The new lines were written in the game's own compressed text format.
- A save that already finished the arena only needs one sleep to start the Pro league.
- The league is stored in the save file. The "King" side fight is unchanged.

## Version history

Each release replaced the one before; the newest is at the top.

| Release | Date | What changed |
| --- | --- | --- |
| Runner Pack v5.2 (CRC32 `329573CC`) | Oct 18, 2026 | Arena fix: if the main fighter went down but his copies then won the fight, the rematch started with an empty ring and you were stuck. He is now put back in the ring whenever his fight starts. |
| Runner Pack v5.1 (CRC32 `77A00E68`) | Oct 18, 2026 | Ending fix. More Enemies' dice-roll hook returned junk instead of 0 for zero-range rolls, so some hits did huge damage. In the ending recap a boss meant to survive died, the recap stalled and the screen garbled. Also More Enemies is now off during cut-scenes. |
| Runner Pack v5 (CRC32 `06713BE4`) | Oct 17, 2026 | Added Arena Leagues. |
| Runner Pack v4 (CRC32 `28036CBB`) | Oct 16, 2026 | Added Less Slowdown. |
| Runner Pack v3.1 | Oct 16, 2026 | Reinforcements also wait while the game is already slowing down. |
| Runner Pack v3 | Oct 16, 2026 | Indoor guard reinforcements. The first try (cloning every guard at map load) froze one ambush scene by running out of script threads; replaced by the queued director. |
| Runner Pack v2 | Oct 16, 2026 | Fixed runner stats turning to garbage (Orifice's empty karma screen): the runner table had been placed in memory some maps also use, and was moved to memory the game never touches. Saves are repaired on load. L/R cycling made reliable. |
| Runner Pack v1 | Oct 16, 2026 | First single patch combining the separate hacks. Install note and BPS added after you found the copier-header checkbox issue. |
| Separate patches | Before Oct 16, 2026 | Persistent Runners (stages 1 to 4), More Enemies With Runners, Smart Targeting and Runner Gear Any Strength, each as its own patch. |

## How it was built

Everything was worked out from the ROM itself; there was no source code. Each hack is a Python script that writes new 65816 machine code into empty space at the end of an expanded 2 MB ROM. It then redirects a few bytes of the original code to that new code.

**Reverse engineering.**

- Most game logic runs as bytecode in a small script language inside the game: 936 scripts with stack operations and calls into about 219 built-in routines ("natives"). A disassembler for that language (`srscript.py`) made the game readable: hiring, arena fights, dialogue, cut-scenes.
- A 65816 disassembler (`dis65816.py`) covered the machine code under it: the script interpreter, object system, sprite drawing, text decompression.
- The dialogue decoder was rebuilt in Python, and an encoder was added for new lines.

**Testing in an emulator.** A Python harness drives the snes9x emulator core directly. It loads save states, presses buttons, reads memory and takes screenshots.

- Test ROMs add a warp on START so any of the game's 512 areas can be loaded on demand.
- Your own uploaded save was used as the late-game test state.
- A profiler build of snes9x counts the CPU time per instruction; that is how the slowdown cause was found.
- A memory sweep over all 512 area loads found RAM the game never uses, where the hacks keep their data.
- Behaviour is compared against the unpatched ROM, and random-dependent scenes from several start points. The game's dice rolls depend on exact CPU timing, so any change re-rolls everything.

**Compatibility.** Every build checks that the bytes it changes match the original, so the parts never overlap each other or Rebalanced / Expanded Dialogue. Stacked patches were tested in several orders.

The build scripts and the full technical notes are in the project: `build_runners.py`, `build_enemies.py`, `build_targeting.py`, `build_speed.py`, `build_arena.py`, `build_all.py` and `shadowrun_notes.md`.

## Technical reference

The five parts use separate code areas and separate hook points, so the combined patch equals applying them one by one in any order. Addresses are SNES (LoROM, FastROM). New code lives in banks `$BE–$BF`, below `$BFFE00` where Expanded Dialogue ends.

**Code areas and hooks**

| Part | New code | Hooks into the original code |
| --- | --- | --- |
| Persistent Runners | `$BF8000` | save `$81B141`, load `$81B15B`, new game `$809915`, runner stat pointers `$80969D` / `$8096B7`, karma gain `$80CD82`, karma screen `$80CE8D` / `$80EE27` / `$80EF6D` / `$80EFDB` / `$80F010`, Body `$80F155`, gear give (native #CD) and scripts `$9EADEB` / `$9CF7F1`, street doc `$80A32C` / `$80E9CA` / `$80CCF0`, Wired reflexes `$80C3D1` |
| More Enemies | `$BFE000` | dice roll `$80C4EF`, variable read `$80CBD7`, map object load `$80A4D8`, main loop `$80963D` |
| Smart Targeting | `$BFE800` | latch `$809DA6`, snap `$80E07A`, cycle and lock `$80E0F8`, auto-fire `$80E130` |
| Less Slowdown | `$BFEC00`, tables `$BFF400` | sprite build loop `$80B8DF` |
| Arena Leagues | `$BE8000` (code, texts, 10 copy scripts) | pay `$80CCAB`, rest menu `$80CE3D`, set HP `$80CAB0`, warp `$80CC67`, script directory `$80C298` / `$80F433`, text `$8092CE` / `$8092DE`, floating text `$80FE8B` / `$80FE9E` |

**RAM used** (all found unused by the game in a sweep of every area)

| Address | Owner | Contents |
| --- | --- | --- |
| `$7FB600–$7FB6F5` | Persistent Runners | runner table, saved to SRAM at slot + `$F04` |
| `$7FB710–$7FB76E` | Persistent Runners | work variables |
| `$7FB7A0–$7FB8A0` | More Enemies | roll and director variables, direct-page backup, reinforcement queue |
| `$7E2300–$7E2327` | More Enemies | private records for reinforcements |
| `$7FB7C0–$7FB7E3` | Smart Targeting | target lock variables |
| `$7FA900`, `$7FB900`, `$7FC600` | Less Slowdown | sprite cache (44 slots) and variables |
| `$7E2340–$7E2349`, `$7F6780–$7F6815` | Arena Leagues | copies' records, work variables |
| `$7E3BF3`, `$7E3BF4` | Arena Leagues | league and sleep countdown, inside the normal save |

**Key game internals**

- Script VM: interpreter `$80F342`, scheduler `$80C1B3`, 48 threads. Script directory: bank `$82D970`, address `$82DD18`, argument bytes `$82E810`, "returns a value" flags `$82E468`.
- Natives: address table `$82D604`, argument counts `$82D895`, return flags `$82D7BA`. Game variables at `$7E3BBB` + n.
- Objects: 44 slots. Type table `$8DB031` + type (flags, record, sprite, script). Records are 5 bytes: flags2, flags, HP, owner (`$1538` = gone).
- Text: message table `$80D980`, Huffman tree `$9D8000`, decoder `$80FE33` / `$80FE44`.
- RNG `$80C530` mixes the frame counter with the video beam position, so it depends on exact CPU timing.
- Cut-scenes are a chain driven by game variable 44 (the ending recap is steps 3 to 13).

## Open issues and parked ideas

Nothing is known to be broken in v5.2 except one unexplained arena glitch.

| Item | Status | Notes |
| --- | --- | --- |
| Elite league glitch | Open, parked | Seen once: an enemy was killed, there was no pay, and the next fight had no enemies, leaving Jake stuck in the ring. Not a loss. Reloading and redoing the fight worked. Not reproduced in 60 test fights. If it happens again, keep a save from just before the fight and note the fight number. |
| Glutman random missions | Parked idea | Glutman hands out random jobs: go through a locked door on Tenth Street or Downtown into one or two rooms built from existing maps, kill a boss-type enemy or hack a computer, report back to get paid, come back a day or two later. The arena work already built most of the pieces (new scripts, new dialogue, spawning enemies, counting sleeps, payouts). |
| Wastelands club slowdown | Parked | Runs at full speed in the emulator; the slowdown on the Raspberry Pi 4 is probably on the Pi side. |
| Days between leagues | Decided | One sleep starts the next league. |
