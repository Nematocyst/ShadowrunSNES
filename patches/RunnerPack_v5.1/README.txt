Shadowrun (SNES) - Runner Pack v5.1
===================================
One patch containing all five of our hacks:
  1. Persistent Runners v5
  2. More Enemies With Runners v2
  3. Smart Targeting
  4. Less Slowdown
  5. Arena Leagues (new)

Needs: Shadowrun (USA).sfc, unmodified - CRC32 3F34DFF0, 1 MB (1,048,576 bytes).
Result: a 2 MB ROM - CRC32 77A00E68 (if you apply only this patch).

HOW TO APPLY
------------
1. Open https://www.marcrobledo.com/RomPatcher.js/ in your browser.
2. "ROM file": choose your clean Shadowrun (USA).sfc.
3. "Patch file": choose Shadowrun_RunnerPack_v5.1.ips.
   IMPORTANT: if your ROM has a copier header (1,049,088 bytes, often .smc),
   ROM Patcher shows a checkbox to remove the copier header - TICK IT.
   Otherwise the patch lands 512 bytes off and the ROM won't start.
   (Shadowrun_RunnerPack_v5.1.bps is the same patch and warns you about this.)
4. Click "Apply patch" and save the new .sfc.
5. Optional - other people's hacks: apply Shadowrun Rebalanced v1.0 and/or ONE
   Expanded Dialogue option (A, B or C) to that saved file the same way.
   Any order works; they don't touch the same bytes.
6. Open the result in your emulator (BizHawk, Batocera, ...).

Saves: your existing .srm save works. Keep the .srm next to the ROM with the
same file name (e.g. "Shadowrun Pack.sfc" + "Shadowrun Pack.srm").
Saves from earlier Runner Packs or the older separate patches load fine - no need
to start over.

WHAT'S NEW IN v5.1
------------------
- FIX: the ending could break (garbled screen / stuck recap). Cause: a bug
  in More Enemies' random-number hook. When the game asked for a random
  number "from 0", the hook returned junk instead of 0. Most code ignored
  it, but the hit-damage roll uses it, so some hits that should do almost
  nothing did huge damage. In the ending recap Jake's shots killed a boss
  that's meant to survive, the recap went off script and the ending broke.
  The same junk could also cause rare one-shot kills (either side) in
  normal fights. Now it returns 0 like the original.
- More Enemies now stays off during story cut-scenes (the intro, flashback
  and ending sequences) so no extra enemies show up there.
- Tested: the full ending sequence plays through to the final city shot.

WHAT'S NEW IN v5
----------------
- Arena Leagues: the arena (The Cage) is now renewable.
  * Win all 10 fights as usual. Talk to the arena owner: he tells you to
    come back in a few days.
  * Sleep once in any bed. The PRO LEAGUE starts: the same 10 fights, but
    every fighter comes with a copy of himself (2 at once) and every prize
    is doubled (600 ... 16,000 nuyen).
  * Win those 10, sleep again: ELITE LEAGUE - 3 fighters at once, prizes
    tripled (900 ... 24,000 nuyen). After the elite league the arena is done.
  * A fight is won when ALL fighters are down. Each copy fights with the
    original's own moves and gives the same karma.
  * If you already finished the arena in your save, just sleep once and
    the pro league starts - no new game needed.
  * The Pro and Elite fights earn 74,000 and 111,000 nuyen in total.
  The league is stored in your save file. The "King" side fight is
  unchanged.

WHAT'S NEW IN v4
----------------
- Less Slowdown: crowded rooms run noticeably faster. The game redraws
  every character's sprites from scratch each update, including working
  out which parts are hidden behind walls and furniture - more than half of
  its work in busy rooms. Characters that haven't moved or changed pose
  now reuse last update's sprites instead. Measured on 106 rooms that lag
  in the original game: average speed went from 79% to 89%; 26 of them now
  run at full speed; the worst ones improve a lot (e.g. one office/fight
  room 49% -> 65%, a corridor 56% -> 91%) but the busiest still slow down.
  While the screen is scrolling there's no gain (everything moves).
  Tested to give exactly the same sprites the game would draw.

WHAT'S NEW IN v3.1
------------------
- Reinforcements now also wait while the game is already slowing down, so
  rooms that lag in the original game don't get pushed further.

WHAT'S NEW IN v3
----------------
- Indoor guards: in the building "dungeons" (office tower floors, corridor
  complexes, caves, sewers...) each guard present when you walk in has a
  20% / 40% / 60% chance (1 / 2 / 3 runners) to call one reinforcement.
  Reinforcements arrive one at a time at that guard's post, a little to the
  side, with the same look, weapon and health. They only come in while the
  game has room for them (at most 2 alive at once), so a big fight never
  overloads the game. They never touch your save: leave and come back and
  the area rolls again.
- Bosses and special one-off enemies are never copied, and the scripted
  ambush with the "Playtime for Otto" line is left as it was.

WHAT'S NEW IN v2
----------------
- FIX: runner stats/karma could get scrambled (e.g. Orifice showing nothing
  on the karma screen, garbage when raising Body). The runner table sat in
  memory that some game areas also use; it now lives in memory the game
  never touches. Saves are compatible both ways.
- Loading a save repairs runner data that was already scrambled. Stats can
  only go up from a runner's starting values, so any stat below its starting
  value (or impossibly high) goes back to the starting value, max stamina is
  recalculated from Body, impossible karma (1000+) is reset to 0, and junk
  runner-cyberware flags are cleared. Real progress (e.g. raised Body or
  skills) is kept.
- Smart Targeting: L/R cycling is more reliable when the game nudges the
  cross-hair by a pixel.

WHAT'S IN IT
------------
Persistent Runners v5
- Hired runners never leave on their own. If one dies they go back to where
  you hired them and can be rehired.
- Each runner has their own karma and stats (raised from the karma screen -
  a "who?" list picks the runner) and keeps the gear you gave them, even
  after being dismissed and rehired later.
- Paid "copy equipment" for runners.
- Street docs sell Dermal armor and Wired reflexes for runners (full price
  per runner). Skillsofts stay Jake-only.

More Enemies With Runners
- Random street enemies appear about 20% / 40% / 60% more often with
  1 / 2 / 3 runners in the party (more fights = more nuyen and karma).
- Indoor guards can call reinforcements (see v3 above).
  Story and boss fights are unchanged.

Less Slowdown
- Reuses unchanged characters' sprites (see v4 above).

Arena Leagues
- Pro and Elite arena leagues after the 10 regular fights (see v5 above).

Smart Targeting
- A puts the cross-hair straight on the nearest on-screen enemy.
- L / R jump to the next enemy left / right.
- Hold A to keep firing; the cross-hair follows the target and moves on to
  the next nearest enemy when it drops. D-pad breaks the lock; B cancels.
