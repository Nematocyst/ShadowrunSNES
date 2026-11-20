# Shadowrun (SNES) - working notes

## ROM
- Shadowrun (USA), 1,048,576 bytes, headerless .sfc. SHA-1 b04afb21c94dab5c8b982d0c133898dd5ec1d104, CRC32 3f34dff0.
- LoROM, FastROM (map mode $30), cart type $02 (ROM+SRAM+battery), 8 KB SRAM, NTSC, v1.0, checksum $F834 valid. No coprocessor. Reset vector $E34C.
- File $7FB0-$7FBF holds 12 leftover non-header bytes (EB FF .. .. .. .. C0 74 3D 00 03 00 75 0A 0E 00).
- Dialogue and runner names are Huffman-compressed (per Tony Hedstrom's Shadowrun Editor thread). Still to crack.

## RAM map (Jake)
- Stat block $7E3BFB: +0 $3BFB body, +1 $3BFC magic, +2 $3BFD STRENGTH, +3 $3BFE ?, +4 $3BFF charisma, +5 $3C00 max stamina
- $7E3C01 firearms, $3C02 unarmed, $3C03 armed, $3C04 computer, $3C05 LEADERSHIP, $3C06 negotiation, $3C07-$3C0C spells
- $7E3C0D-$3C0F nuyen (24-bit LE), $7E3C11 karma x8 (displayed karma = value >> 3), $7E3C30 armor
- Game Genie "learn skill/stat" codes all patch $8095AE (a startup STA $420D) into LDA #v / STA $7E3Cxx.

## Party / hired runners
- $7E2DE6 = (party size - 1) * 2 (slot index of last member; slot 0 = Jake). Per slot X (0,2,4):
  $7E2DE8,X actor/sprite id, $7E2DF0,X spawn/object record offset, $7E2DF8,X STAY TIMER, $7E1FC4,X object index.
- Hire = native #78 ($80A173), 7 script args; first pushed = base duration, last pushed = actor id.
  Stay timer = base + Leadership * (base >> 3)   (each Leadership level = +12.5%, integer math).
- Tick: $808585-ish. Timers -1 (floor 0) once per map load, on the FIRST "remove combatant" (native #BF) after the map loads,
  i.e. first enemy killed (or leaving combat) on that screen. Flag $7E1FEA reset by $808511 inside the map loader. No tick while $7E1D87 is negative.
  Patch point: file $0596 = DEC A (3A). NOP it (EA) -> runners never leave.
- Departure: runner party script (base file $FAF8E; variant $FB19F) checks native #D5 RUNNER_TIME_LEFT(self) at script start
  (scripts restart on every map load). 0 -> jumps to $FB166 -> spawns script $0194 (leave routine) -> walks off.
  Native #83 ($80A242) removes a slot and compacts the party.
- Hire call sites (file offset of the 58 78; base byte = operand of the first "00 xx" push):
  F7510 actor $A0 Akimi base 50 | F7421 $AC Kitsune 30 | DD427 $0E "Jamaican" 30 | F7312 $05 dwarf 40 | F72CD $0C decker (green) 40 |
  F73DE $0D decker (red/blue) 40 | F746D $9D mage (purple) 40 | F7356 $5B mercenary 20 | F739A $0F blue orc 30 | E7563 $0F blue orc 20 |
  DD49A $63 large red orc 10 | DD99A $59 shaman 10 | 1F487 $0B Jake himself 50 (game start). Sprite descriptions from TCRF; names beyond Akimi/Kitsune unconfirmed.

## Runner gear (armor/weapon restriction)
- The ONLY restriction is Strength. Shared scripts check native #0F (= stat block +2, Strength) of the receiving character against the item's requirement:
  - Armor: script $0320 (file F2D79, code F2D7B), args (self, protection, requirement). Every armor item calls it as push P, dup -> requirement = protection (1..6). Check at file F2D9C: 02 03 8A (push req; lt).
  - Weapons: script $0011 (file E7777, code E7779), args (self, s1, s2, s3, requirement); item scripts at E7AF7..E7BDB push the requirement first (values 1..5). Check at file E779E: 02 04 8A.
  - Fail -> message box (native #C7). Pass -> native #34 EQUIP_ARMOR ($808B16) / #23 EQUIP_WEAPON ($808B9F) for character $1F7C (set by native #01 select-character).
- "Give" (same scripts, menu bit $40) only transfers the item (native #75); the check runs when the item is USED from that character's inventory.
- Script $026B (armor 5) and $014D (weapon 3,8,1) force $1F7C=0 -> Jake only, no check.
- Per-character gear records: 8 bytes at $7E3C2E + 8*index (index = order of table $809683: Jake, purple mage, decker green, dwarf, blue orc A, mercenary, Akimi, Kitsune, decker red/blue, Jamaican, blue orc B, large red orc, shaman):
  +0 armor item type, +2 armor protection, +3 weapon item type, +5..+7 weapon stats. Defaults in ROM at $80972C (same layout). Resets to default when the item leaves the character ($809C67).
- Runner stat blocks are ROM-fixed, 18 bytes, pointers at $80969D (Jake's at RAM $7E3BFB), same layout as Jake's.
  Strength: Akimi 1, Kitsune 1, decker green 3, Jamaican 3, purple mage/decker r-b/blue orc B/red orc/shaman 4, dwarf/blue orc A/merc 5.
- Patch Shadowrun_RunnerGearAnyStrength.ips: both checks "02 0x 8A" -> "00 00 7E" (push 0; and -> always pass) + checksum fix. Boot-tested; not yet tested in-game with a runner.

## Script engine
- Bytecode stack VM, interpreter loop $80F353: opcode byte -> JMP ($F27E,X). Jump operands are offsets from the script's code start (header + 2).
- Script directory: bank bytes $82D970+id, addresses $82DD18+2*id, arg bytes $82E810+id; 936 scripts; 2-byte header then code. Op 52 nnnn = run script nnnn.
- Native calls: op 58 nn -> table $82D604 (219 bank-0 routines), arg counts $82D895, returns-value flags $82D7BA.
  Known: #01 select character, #0F get Strength, #23 equip weapon, #34 equip armor, #75 give item, #78 hire, #7B add karma (x8 units),
  #83 dismiss, #AB add combatant (starts battle music), #BF remove combatant, #C7 message box, #D5 runner time left.
- Tools: srscript.py (script disassembler, optional base for jumps), dis65816.py (65816 disassembler), gg.py (Game Genie decoder).

## Tooling (shadowrun_toolkit.zip)
- snes_retro.py + snes9x libretro core (built from github.com/libretro/snes9x): headless runs, 128 KB WRAM access by SNES address, SRAM get/set, save states, screenshots. Boots to the morgue intro fine.
- snes2asm (github.com/nathancassano/snes2asm) + WLA-DX (github.com/vhelin/wla-dx): full disassembly into 32 bank files; rebuild is byte-identical once the $FFB0-$FFBF fix section is appended to hdr.asm (disassemble.sh does this). Data regions are still decoded as code until a snes2asm YAML config marks them.
- snesrecomp (github.com/RetroPortingToolKit/snesrecomp): static recompiler to a native PC port. Could not run in the cloud sandbox (Rust-only analyzer needs crates.io). Not needed for romhacks.
- Tony Hedstrom's Shadowrun (SNES) ROM Editor (romhacking.net utility 1748) already edits weapons, armor, shops, runner stats and "runners can leave". Worth comparing against.

## Save system & karma spending (for the "permanent runners with karma" idea)
- Save/load = MVN block copy of WRAM $7E2DE0-$7E3CE3 ($0F04 bytes) to/from SRAM bank $70 ($81B139 load / $81B154 save; slot offset from $81B0D6).
  2 slots x $F04 = $1E08 of the 8 KB SRAM -> ~$1F8 bytes spare. Anything outside $2DE0-$3CE3 is lost on save.
- Karma spend routine ~$80EFD0: cost = current level x 8 (karma stored x8), subtract from $7E3C11, then INC [$0E] (24-bit pointer to the stat,
  bank $7E set at $80F026). Stat-address table just before it (~$80EFB0, entries like $3C0C/$3C08/$3C0A). Works on any RAM pointer -> could target runner blocks.
- Runner stat blocks live in ROM (pointers $80969D, bank bytes $8096B7 = $80; Jake's = $7E3BFB with bank $7E). Repointing an entry to RAM is supported by the reader code.
- Karma gain: only native #7B ($80CD82) adds to Jake's $7E3C11; the killer is not recorded.

## Design: persistent runners with own karma (user's chosen design, 2026-10-15)
- Goal: runners never time out; if killed they return to their spawn point (rehireable); each runner earns own karma and can raise own stats;
  a persistent per-runner table (stats, karma, gear) so progress survives dismissal and rehire.
- Gear already persists per runner: 13 fixed gear records at $7E3C2E (inside the saved block), indexed by character, not party slot. (Confirm in-game.)
- Plan: RAM runner table = 12 x (18-byte stat block + 2-byte karma) ~ 240 bytes; point $80969D entries (+ bank bytes $8096B7 -> $7E/$7F) straight at it (no swapping).
  Init from ROM blocks at new game. Patch native #7B (karma gain) to also add to each party runner's karma. Reuse karma-spend routine (~$80EFD0, INC [$0E]) with runner's pointer + karma; open it from runner status screens.
- Save slots: offsets table $81B0E0 = $0000, $0FFE (slot size $FFE); game uses 2 + $F04 = $F06 -> 248 spare bytes per slot at slot+$F06..$FFD. Checksum loop at $81B0E8 covers $F02 bytes.
  RAM after the saved block ($7E3CE4..) IS used -> patch save/load ($81B139/$81B154) to also copy the runner table to slot+$F06.
- Candidate free RAM: never-written ($55 fill) regions in bank $7F after ~1 min of play: $7F9818-$7FC682, $7FE4C2-$7FFFFF, $7FDB1B-$7FE213, $7F6018-$7F69BF, $7F75BC-$7F8017. Needs confirmation with late-game play.
- Open questions: what happens to a runner on death (and whether their spawn returns); karma-spend menu entry point for runners.

## Findings from the user's late-game save (Shadowrn.srm, hotel in Daley, 2026-10-15)
- Party holds Jake + 3 runners: $7E2DE6 max = 6 (slots 0,2,4,6). Save: Jake, Steelflight, Norbert, Akimi.
- CONFIRMED runner identities: Steelflight = sprite $0D (decker red/blue pants), type $15D2, gear/stat index 8, base 40.
  Norbert = sprite $05 ("dwarf"), type $1458, index 3, base 40. Akimi = sprite $A0, type $1B6D, index 6, base 50.
- CONFIRMED stay formula live: Leadership 6 -> Steelflight 70 (had 67), Norbert 70 (69), Akimi 86 (85).
- CONFIRMED departure live: set $7E2DFA (Steelflight timer) = 0, walk to next map -> "It's time for me to leave Jake. I think I have earned my money.", party shrinks.
  His object record ($7E340E, via $13C4,Y with Y = $1FC4,X) byte +1 bit $80 cleared on leaving -> bit $80 = "currently hired".
- Dismiss-self script $0330: natives #27(255) (refill HP, stat block +5) and #CA(255) (refill magic, +1), #7A clears bit $80, then #83 DISMISS.
- WRONG (fixed in v5): $7F9818-$7FA843 IS used by many maps (object data, $40xx words; loc $48 etc.). Map-load sweep (all 512 warps):
  untouched = $7E21DF-$7E239F, $7F6764-$7F69BF, $7FA844-$7FC682, $7FDFBA-$7FE213. v5 table at $7FB600, vars $7FB710-$7FB7E3. Also $7F6150-$7F69BF, $7FDC8A-$7FE213, $7FE4C2-$7FFFFF.
- Debug room (TCRF): PAR 7E3BD3FF + 7E3BD4FF then Open matchbox -> debug room; waitresses give money + karma; doors warp to chapters (Jake's apartment ... Aneki building). Useful test harness.
- Data Crystal RAM map agrees: $7E3BFB body, magic, strength, unknown, charisma, max HP; $3C17-$3C19 sunglasses/dermal armor/wired reflexes; $3CA3-$3CE3 known keywords.
- Emulator harness can load a battery save: e.set_sram(srm[:8192]) before reset, title -> DOWN, START (Start saved game) -> START (Resume game 1).

## RUNNER NAME TABLE (all confirmed, 2026-10-15)
idx = order of $809683 (gear record $7E3C2E+8*idx, stat pointer $80969D+2*idx). Base = stay base. Str = Strength.
| idx | Name | sprite | type | base | Str | hire site | how confirmed |
| 1 | Spatter | $9D purple mage | $0A4F | 40 | 4 | F746D | price table $82FA17 -> type |
| 2 | Jetboy | $0C decker green | $0D2E | 40 | 3 | F72CD | price table $82FA8C + Rebalanced Jetboy price |
| 3 | Norbert | $05 | $1458 | 40 | 5 | F7312 | user's save + price table |
| 4 | Frogtongue | $0F blue orc A | $079A | 30 | 5 | F739A | price table $82FAB3 |
| 5 | Anders | $5B mercenary | $089D | 20 | 5 | F7356 | price table $82FA3E + Rebalanced Anders price |
| 6 | Akimi | $A0 | $1B6D | 50 | 1 | F7510 | save + TCRF + price table |
| 7 | Kitsune | $AC | $0B52 | 30 | 1 | F7421 | TCRF + price table |
| 8 | Steelflight | $0D decker red/blue | $15D2 | 40 | 4 | F73DE | save + price table |
| 9 | Jangadance | $0E "Jamaican" | $0BA6 | 30 | 3 | DD427 | price quote next to hire ($9BD43D) |
| 10 | Hamfist | $0F blue orc B | $078C | 20 | 4 | E7563 | decker flag $8096EB + Computer 3 + transcript "a decker like me" |
| 11 | Orifice | $63 large red orc | $0B3D | 10 | 4 | DD49A | remaining 300-nuyen runner |
| 12 | Dances With Clams | $59 shaman | $098B | 10 | 4 | DD99A | price quote next to hire ($9BD9B8) |
- Hire price script block: bank $82 file 179F0+: push prices, spawn $003F, ..., push.w TYPE, spawn $0162. $8096EB = "can deck" flag table.

## Other hacks by RetchERezzed (user-supplied, 2026-10-15)
- Shadowrun Rebalanced v1.0: 171 writes, all inside 1 MB. Karma: $80EFD5 0A->EA (karma spend cost level*4 instead of *8). Tables at $80DC26.. and $80DD54.., prices ($82F9F0 block, $9BD43D.., $9CF572, $9CDF2D..), spell costs ($83DFF5, $83E061, $83E08C, $83E4C4), nuyen drops $9F9713.., plus text. Checksum $7FDC.
- Expanded Dialogue v1.1 (A/B/C): expands ROM to 2 MB (pad with $00 to reproduce their CRCs). Hooks: $8092FD -> JSL $A09000 (24-bit text pointer loader), $80FE33 -> JML $A08000 (text ids >= $C000 from table $A08100), $80FFD7 = $0B. Writes ~39 KB starting at file $100000 (banks $A0-$A1) + text in file $68000-$69FFF. Uses only DP temporaries, no WRAM.
- Text system (from their hook): $80FE33 takes text id in $02; id < $C000 -> pointer $9D:(id|$8000) (+1 bank if id >= $8000); Huffman decoder at $80FE44.
- NO overlap with any of our patch points (stay $0596, gear checks F2D9C/E779E). Our new code should live at the END of a 2 MB image (e.g. bank $BF, file $1F8000+) so it coexists with Expanded Dialogue; only ~816 bytes of zero-filled space exist inside the original 1 MB ($6EC6A).

## Stage 1 BUILT: Persistent Runners (2026-10-15) - release/Shadowrun_PersistentRunners_Stage1.ips, builder shadowrun_toolkit/build_runners.py
- Patched ROM 2 MB, CRC32 0A1E0CEF. Code 234 bytes at $BF8000 (file $1F8000): SaveHook $BF8000, LoadHook $BF8013, NewGameHook $BF8033, InitTable $BF8044.
- Hooks: $808596 DEC->NOP; $809915 JSL NewGame; $81B141 JSL Save (replaces the WRAM->SRAM MVN); $81B15B JSL Load (replaces SRAM->WRAM MVN).
- Save layout: slot+$0000..$0F03 vanilla (checksum word at slot+0 covers slot+2..+$F03), slot+$F04..+$FF5 runner table (242 bytes). Vanilla leaves those bytes as $AA filler.
- Table $7F9818: 'RT', stats $7F981A + 18*(idx-1), karma $7F98F2 + 2*(idx-1). Old saves (no 'RT') rebuild from ROM on load.
- Death vanilla: HP (object record +2) 0 -> next map load dismisses via script $0330 (heal, clear hired bit). No change needed.
- Tests passed (emulator): new game table init = ROM blocks; user's old save loads + table built; crafted SRAM table restored exactly; party status shows table max stamina (100/150); death dismissal; stacked with Rebalanced + Expanded Dialogue A/B/C in 3 orders -> identical except checksum; stack loads save correctly.
- NOT yet tested live: in-game save (couldn't drive the bed menu from the harness; bed scripts e.g. $033B use menu script $02AA, 'Use' result $0100 -> spawn $00F9 -> native #7F save), timer freeze under actual combat ticks, killed runner reappearing at hangout.
- Object records: current HP at record +2, flags +1 (bit $80 hired). Record address = $13C4,Y for live object Y; persistent records in the saved block (e.g. Norbert $7E33F5).

## Stage 2 groundwork (2026-10-16)
- In-game SAVE now TESTED: test-only ROM (jsr $CE3D at $80DFF6 instead of jsr $EA53, so START opens the rest menu) -> Save game 1 ->
  SRAM slot1 + $F04 holds 'RT' + table identical to RAM. Reload on patched ROM restores it; the ORIGINAL ROM also loads that save fine.
- Rest menu = native #3C ($80CE3D): Exit / Save game ($80CDA6 -> slot menu -> JSL $81B139) / Use karma ($80EE21). Sleep script $01D4
  (attached to bed objects). Native #7F only ends conversations ($1D7F flag), not rest.
- Karma screen $80EE21: header box text $7155 'Karma' + value (display $80EF4C: $7E3C11 >> 3). Menu Exit/Attribute/Skills/Magic ($80EF42 list).
  Uses $969D (index 0 = Jake) for display pointer $F9. Submenus list only stats with value > 0 and below max.
  - Attributes $80F0BD: table $EF7C (addr $3BFB/$3BFC/$3BFD/$3BFF), text $EF84, max $EF8C (20,20,6,6). Raise at $80F14D.
    Body side effect: if addr == $3BFB -> $7E3C00 (max stamina) += 10 and heal Jake object ($0CDE) by 10 (native $CE9B).
  - Skills $80F01E: table $EF94 ($3C01,$3C04,$3C05,$3C06), text $EF9C, max $EFA4.
  - Magic $80F17F: table $EFAC (spells $3C0C,$3C08,$3C0A,...), text $EFB8, max $EFC4.
  - Each: $10 = $7E (bank), $0E = table addr, JSR $80EFD0 raise: cost = value*8 (Rebalanced: *4 via $80EFD5), deduct $7E3C11, INC [$0E].
- Karma gains: only native #7B ($80CD82, adds $00 to $7E3C11). Losses: native at $80CD8E and $808803 (-8 penalty). Keep losses Jake-only.
- Stage 2 plan: hook #7B -> also add to each party runner's karma ($7F98F2+2*(idx-1)); in "Use karma" let the player cycle Jake -> runner(s):
  per character set $F9 = table pointer, $0E = runner block + (addr - $3BFB), $10 = $7F, karma pointer = runner's counter,
  Body side effect -> block +5 += 10 and heal that runner; header shows the character's name instead of 'Karma'.

## Stage 2 BUILT: per-runner karma + "who?" list (2026-10-16) - Shadowrun_PersistentRunners_v2.ips (includes stage 1)
- Patched ROM CRC32 3AB05FCF, code 834 bytes in bank $BF. Labels: kgain $BF80EA, pick $BF8134, setf9, kget, kset, adr_attr/skill/magic, body.
- Hooks: $80CD82 native #7B -> JSL kgain; RTS (adds amount to Jake and to every party runner's counter at $7F98F0+2*idx, capped $FFFF).
  $80CE8D Use karma -> JSL pick (builds list Exit/Jake/party names from $809705 in $7F9920, window x2 y17 w21 via $80F92D, menu $80A654,
  runs $80EE21 per pick, loops; Exit closes window, drops JSL return, JML $80CE3D).
  $80EE27 setf9 (stat pointer for SEL), $80EF6D/$80EFDB kget (PHP/PLP: caller's SEC must survive!), $80F010 kset,
  six table sites -> stat address = runner block + (addr - $3BFB), bank $7F; $80F155 body (runner: block+5 += 10, object HP += 10 capped).
- Bank-$80 RTS routines are called from $BF with an RTL trampoline: PHK; PEA ret-1; PEA $F260; JML target (RTS lands on RTL at $80F261).
- Work vars (not saved): $7F9910 SEL idx, $7F9912 BASE, $7F9916 OBJ, $7F9918 window, $7F991A count, $7F9920 list, $7F9930 map, $7F9940 objects.
- Karma cost rule (vanilla) = current level x8 units (Rebalanced x4). Bug found+fixed in testing: ASL in kget clobbered carry -> runners overcharged by 1 unit.
- Menus: A and B both CONFIRM; pick "Exit" lines to back out. Lists of >=5 entries show a cosmetic scroll arrow.
- Test ROM tricks (not shipped): $80DFF6 jsr $CE3D (START -> rest menu); $80CD87 'A9 40 00 85 00 80 F4' + $80DFF6 jsr $CD87 (START -> +8 karma).
- Tested: pick list, runner karma screen (own karma/stats), Body raise (+1, +10 max, +10 HP, cost), Not enough Karma, Jake path, karma gain to party only,
  save slot 1 + reload (plain and full stack), Rebalanced cost applies to runners (44 units for Body 11).
- Not tested: kill-triggered karma in real combat, runner Skills/Magic menus, killed runner reappearing at hangout.

## Shops (2026-10-16)
- Display-case items run script $028C(self=case, text, price, item, stackable flag). Buy: native #BE pay, #C6 carried count (< 6),
  stackable -> #26 count += 1 (max 6, case stays); equipment -> #33 OR case flag bit 0 = sold, then #74 item owner = Jake ($08B2), spawn $004B.
  Top of script: native #02(self) & 1 -> sold.
- Items are UNIQUE objects: record via $8DB032+type (bank $7E), +2 quantity, +3 owner. No duplicates exist, so restocking equipment would
  re-sell the same object (and take it back from a runner -> $809C67 resets their gear). Stackables already never sell out.
- Options discussed with user: (a) "copy" giving: give armor/weapon to a runner = equip their gear record with its stats while Jake keeps
  the item (needs the $809C67 reset to ignore such copies); (b) real extra copies need new object records in the saved block - no space.

## Stage 3 BUILT: copy equipping (2026-10-16) - Shadowrun_PersistentRunners_v3.ips (includes stages 1-2), CRC32 8239AF2D
- Native #CD (was an unused "has weapon?" routine at $80CFED, never called) repointed to stub $80CD87 = JSL cpgive; RTS. Args 2, no return.
  Script patches: armor $0320 give "58 75"->"58 CD" at file $F2DEB; weapon $0011 at file $E77F1.
- cpgive: $00 = item object, $02 = target TYPE. Vanilla ($809C98 = native #75) unless target != Jake ($08B2) and item owner == Jake.
  Reads caller's thread DP ($026E + [$026C]); script base word at DP+0 ($AD7B armor / $F779 weapon) picks the kind; locals at DP+$13+n
  (armor: protection local1, requirement local3; weapon: s1/s2/s3 locals1-3, requirement local4). Strength = runner block +2.
  Fail -> native #C7 message ($80FE8B; $0A = message index: 20 'Not strong enough.', 2 'Not enough money!') and DP+$03 = script end
  offset ($00F8 armor / $0100 weapon) so the vanilla 'Thanks!' is skipped. Success -> pay ($80CCF0), write gear record
  ($7E3C2E+8*idx: armor type/protection, weapon type/s1-s3) and live armor $7E43D4,obj.
- Prices read at runtime from the shop-case price operands (table type -> SNES address), so Rebalanced prices apply (Colt 300 vs 500).
  Not in a shop: armor by protection [1000,2500,5000,8000,12000,15000,20000,25000,30000,40000], weapons 5000.
- Two different 'Mesh Jacket' objects exist ($0850 shop, $085E). Jake's armor menu = START > Armor; Give uses a map pointer ('Give to:').
- Shop facts: equipment cases pass flag $C0 (nonzero) -> code path adds +1 to item quantity; but Jake's owned equipment shows qty 0 in the save.
  Unresolved; not needed for copy equipping.
- Test ROM tricks: START->warp: stub 'A9 7C 01 85 00 4C 67 CC' (lda #$017C; sta $00; jmp native #56 $80CC67) at $80EE2B + jsr $EE2B at $80DFF6
  (Dark Blade = location $017C). Native #56 = warp(location).
- Tested: Not strong enough (Partial Bodysuit on Steelflight), Mesh Jacket success (-5000, record+live armor, Jake keeps item, 'Thanks!'),
  Colt L36 (-500; -300 on Rebalanced stack), Not enough money!, save/reload keeps copied gear, no overlap with Rebalanced/Dialogue, stage 1-2 regression.

## Cyberware (2026-10-16)
- Cyber screen (START > Cyber, $80E8CA): 'Head computer', 'Datajack' always (Jake built-ins); 'Dermal armor' if $7E3C18; 'Skillsoft' if Leadership $7E3C05 > 0;
  'Wired reflexes' if $7E3C19. ($7E3C17 = sunglasses/portrait flag, $80EAC3.)
- Street doc: each offer runs script $02CC(price lw1, text lw3/lw5, lb7, item type lw8), pays native #BE, then by type:
  $03AA Skillsoft -> $3C05 = 1; $15C4 Dermal armor -> $3C18 = 1; $192F Wired reflexes -> $3C19 = $FF; then native #0D($C0, type) (marks bought). Dermal price $1770 = 6000.
- Effects: Dermal = +2 to Jake's live armor ($7E43D4,obj) in the map-load party spawn ($80A315, only actor $0B). Status armor display also reads it ($80E9D2).
  Wired = Jake's control script $01D9 (17C03) skips an extra 10-frame wait between attacks (20 vs 30 frames, ~1/3 faster).
  Skillsoft = unlocks Leadership (matters only for hiring).
- Runner AI attack delay: each runner's spawner calls spawn $01AD (self, 4, DELAY, X, flags) at FADAA.. (push.b delay: $50,$5A,$2A,$78,$4E,$48,$5A,$64,$78).
  $01AD waits lw2 frames ('16 02 14 81 68 16 06 80 58 9E' at FB0C4) between attacks. Wired for runners = scale that delay.
- Only native #CD was unused; a wired-reflex hook needs another entry point (e.g. adjust the AI thread's lw2 at DP+$15 when it starts, or hook native #9E).
- Save space left: 8 bytes per slot (2 flags x 12 runners fits in 4).

## Stage 4 BUILT: runner cyberware (2026-10-16) - Shadowrun_PersistentRunners_v4.ips (stages 1-4), CRC32 E2568E84, code to $BF89C1
- Street doc = object type $031E (script $00C4) at locations $0BD and $0EE (cyber room). Doc dialog sub F3302 sets var $7E3BE5 = slot and warps to $EE.
  Cyber cases = shelf objects $15C4 Dermal (record $335A), $192F Wired/'Boosted Reflexes' ($335F), $03AA Skillsoft ($3355), script $00F4:
  flags&2 -> dermal offered only if flags bit0 set; else flags&4==0 -> skillsoft, else wired. Owner $1538 (native #C4) = bought, removed from shelf.
  Purchase script $02CC (code $9E:F51B) waits native #9E(1,$A1) for event $20 (select), shows price text + yes/no (native #72), pays native #BE,
  sets Jake flags, native #0D($C0,type), native #C4(self).
- OPCODE FIX: script op $BE is 'bool' (nonzero -> -1), NOT logical not. srscript.py updated. Earlier readings using 'lnot' should be re-checked.
- Hooks: native #BE entry $80CCF0 -> docpay (only when the calling thread runs $9E:F51B and item is $15C4/$192F): who? list (Jake if lacking +
  party runners lacking), pay via JML into $80CCF5, set Jake flag or runner mask, 'Thanks!' (msg 22), then thread PC = +$76 with result 0 and
  JML to an RTS ($80CD86) to leave the native. Item never moved to $1538, so it stays for other runners.
  Native #9E entry $80C3D1 -> wired: threads running runner AI ($9F:AF8E $01AD, $9F:B19F $0328 mages, $9F:B424 $01E9) whose object has the
  wired bit: waits >= 20 frames cut by a third. $80A32C -> derm_spawn (+2 live armor at map load). $80E9CA -> st_armor (status armor +2).
  copy equip live armor includes dermal. Load: restock (owner $1538 -> $FFFF for dermal/wired shelves).
- Save format 2 'R2' = 246 bytes ('RT' format-1 saves upgraded on load). Masks $7F990A dermal / $7F990C wired, bit = runner idx. 4 spare bytes left.
- Test trick: inject select into a case: thread X with DP+0=$F51B, DP+$1B = type -> $7E0C7E+X |= $20 (real select input not found in harness).
  Warp-by-variable test stub at $80EE2B: 'AF 90 99 7F 85 00 4C 67 CC' + START jsr $EE2B; location in $7F9990.
- Runner AI threads: Steelflight/Norbert run $01AD (attack wait lw2 = 90 / 42 frames), Akimi runs $0328 (mage).

## More Enemies With Runners (2026-10-16) - Shadowrun_MoreEnemiesWithRunners.ips (standalone), builder shadowrun_toolkit/build_enemies.py
- Enemy spawning: roll-based enemies (13 scripts: $0174,$039F,$0083,$0076,$005B,$0168,$00D8,$0236,$0321,$037F,$0157,$0195,$0398) call
  script $007E (code $9F:9AE9) once when they start: if random(10) < chance (local 0) and var[42] < 4 -> var[42]++, appear; else native #B8 (gone).
  var 42 ($7E3BE5, game var table $7E3BBB + n via natives #57 get / #12 set) is reset to 0 by area-init objects (e.g. type $0E62, script $0060).
  Chances mostly 2-5 (in 10). Death: karma +1 unit (native #7B 1), REMOVE_COMBATANT. No respawn within a visit for $0174-type enemies.
- Patch: native #3E entry $80C4EF -> 'rand' (from $007E at script offset 6: random(100)/(10+2n)); native #57 entry $80CBD7 -> 'getvar'
  (from $007E offset $0C reading var 42: value - {0,1,2,2}[n]). n = $7E2DE6/2. Code 202 bytes at $BFE000, vars $7F99B0-$7F99B5.
- First version (random(10) result scaled) overshot (+40/67/99% by thread count) because of integer rounding; 1% roll fixed it.
- Measured (var42 after 900 frames, 23 areas x 12 entries): vanilla ~1.25/entry; patched +19% / +33% / +63% for 1/2/3 runners; 0 runners same.
  (Counting live enemy threads after 240 frames shows vanilla 2.29 with Jake alone vs ~1.75 with runners - an artifact of that method.)
- Area ids with roll-based enemies (from a warp scan): 0x24,0x25,0x33,0x92,0x93,0xB2,0xBE,0xBF,0xC6,0x128,0x145,0x19C,0x1B5,0x1B8-0x1BA,0x1C8,0x1D5,...
- No overlap with Persistent Runners v4, Rebalanced, Expanded Dialogue; 4-patch stack identical in 3 orders.

## Smart Targeting patch (build_targeting.py, code $BFE800, RAM $7F99C0-$7F99E3)
- Jake's input = native #CF ($80DFDE, returns $00 = fire). Joypad: $01E6 held, $01EA new presses (edge computed at $809D9D),
  $01E8 previous. Bits: B 8000, Y 4000, SEL 2000, START 1000, U/D/L/R 0800/0400/0200/0100, A 0080, X 0040, L 0020, R 0010.
- Pointer off ($01F4=0): A -> $80E07A JSR $BC50 (gun cross-hair, mode FFFE, offsets $0200/$0202 = $05E4/$0BE8, $1D79=-1);
  X -> $BC69 magic ($1D7B); B/L/R -> $BC37 hand pointer. Pointer on + aiming: A/X held over object with $1474 bit15 -> fire;
  $7E3C33==1 weapons fire while held ($80E12D), others per press. B/L/R close ($80E164).
- Pointer clamp $80BEC8: x 3..239, y 3..206 (pixel = high byte of $01F0/$01F2). Hover test $80BC8E (runs when no D-pad held,
  lags a few frames): box left<x<=right, top<y<=bottom using $7E421C/$42CC/$4274/$4324/$437C,X.
- Enemies = combatant list $1FCC/$1FCE ($1474 bit15 is also set on Jake and runners, so not a hostility flag).
- Hooks: $809DA6 latch L/R; $80E07A snap (JSL+3 NOP); $80E0F8 cycle/lock (JSL+2 NOP); $80E130 D0 13 -> EA EA (all weapons auto).
- Main loop lags on busy frames (joypad not read), so very fast taps can be missed - vanilla behaviour.
- Test trick: counter at $7F9F00 hooked on $80E13F/$80E148 (mkcnt.py) counts fire returns.

## Runner Pack v1 (build_all.py)
- One IPS = Persistent Runners v4 + More Enemies + Smart Targeting, built in that order from the clean ROM.
  Pack CRC32 56C9F435 (2 MB); identical to stacking the three separate IPS in any of the 6 orders (checked).
- Rebalanced v1.0 and Expanded Dialogue A/B/C still apply on top in any order (checked byte-identical both ways).
- Install gotcha: user's ROM had a 512-byte copier header; tick 'remove copier header' in ROM Patcher JS. BPS version of the pack (validates source CRC) shipped too.

## v5 / Runner Pack v2 (2026-10-16): RAM relocation fix
- Bug (user): Orifice showed nothing on karma screen, raising Body corrupted the screen. Cause: runner table at $7F9818 overwritten by
  map data (blocks of idx 11/12, karma words, cyber masks at $7F990A/C). Sweep: warp to each loc, diff region.
- Fix: TABLE $7FB600 (stats $7FB602, karma $7FB6DA, masks $7FB6F2/F4); runner vars $7FB710-$7FB76F; enemies $7FB7B0; targeting $7FB7C0-E3.
  SRAM format unchanged ('R2' at slot+$F04).
- repair (on load + when opening Use karma), per byte: < ROM value or > 30 -> ROM value; max stamina = ROM + 10*(Body gained), cap 255;
  karma >= $2000 units -> 0; mask with bits $E001 -> 0. (Defaults baked in from the clean ROM at build time; Rebalanced doesn't touch them.)
- User's real save (user2.srm, both slots R2): EVERY block hit - strength/offset 3 zeroed, offsets 8-9/14-15 zeroed or $40Cx words,
  Jetboy/Orifice karma $40C9/$4111, WIRED mask $40CB. Slot 2: Orifice body 15 bought with the junk karma (kept by repair: can't tell).
  Hamfist body 11 / skill 6 / karma 34 = real progress, kept.
- Targeting: 'near' tolerance (4 px) for lock/cycle (game nudges pointer y by 1).
- Pack v2 CRC32 3D2E5104. Sweep after fix: only legit karma changes in the table; loc $1FC = invalid (black screen, fills RAM with $A1).

## Fixed (placed) enemies / spawn points (2026-10-16)
- Location table $8D92AF + 9*loc: +0 map data ptr (bit15 -> bank $9A else $99; addr |= $8000), +2 entry byte, +3.. start pos.
  Map data: +4 object count, then 6 bytes/object: w1 = x (11 bits) + z low bits, w2 = y (11 bits) + z high bits, w3 = object TYPE.
- Map object loader $80A343 (called from map load $80A4DB): spawns an object if type flags ($8DB031) | $2DE4 != 0 and record
  owner ($7E:rec+3) == $FFFF; $80A7C2 creates the object (sprite $8DB034, script $8DB036); then $1526 = type, $141C, $13C4 = record.
- Records are 5 bytes in the saved block (+2 = HP). Every placed enemy is its own TYPE with its own record and a tiny script that
  calls a generic AI: $010C, $027B, $02A9, $007A, $00FB, $00A0, $010D, $0335, $035B (then $01C2).
- analyze.py / maplist.py (scratchpad): 166 fixed enemy spawn points in 65 locations (many locations share one layout, e.g.
  $0FD-$100, $168-$17B = $1E1-$1E7 office floors, $0D3/$0D4, $138/$139). Table in fixed_spawns.json.
- Idea for more indoor enemies: clone a placed enemy at map load (new object via $80A7C2, same sprite/script, private 5-byte record
  in free bank-$7E RAM $7E21E0-$7E239F). Risks: unique drops, death bookkeeping on the record, 44-object limit, wall placement.

## Indoor reinforcements (More Enemies v2, Runner Pack v3, CRC32 32EC6BD5)
- First try (clone every guard at map load) FROZE the game at $0A0: script thread pool (48, free list $026A linked via $032E)
  ran out (each guard copy costs ~4-5 threads in combat). Object pool (44, $7E3F04,X < 0 = free) was fine.
- Final design: map-load hook $80A4D8 (JSR A287/A343 -> JSL mapobj) queues up to 8 reinforcements (20% per runner per
  living placed guard: type, $0E44/$0E9C/$0EF4, record bytes 0-2) at $7FB840; main-loop hook $80963D (JSR BE3D/BF0B ->
  JSL director) every 64 frames spawns the next one if free threads >= 30, free objects >= 12 and < 2 reinforcements alive.
  Object via $80A7C2 ($00 sprite, $02/$04/$06 pos>>2, $08 script) + $1526/$141C/$13C4; private record $7E2300+5k.
  Steps 14 units aside using the game's wall tests $8080B2/$808133/$8081B4/$808238 (X = object; carry set = free, else
  A = step height, >= 5 blocked). DP $00-$3F saved to $7FB800 around it.
- Guard types: map objects in GUARD_LOCS whose script is a shared guard script ($018A,$031A,$0167,$0317,$006C,$020D) or first
  spawns a generic AI ($010C,$010D,$027B,$02A9,$007A,$00FB,$00A0,$0335,$035B); sprite used at >= 3 placed spots (bosses out).
  $0A0/$176 excluded. 81 types.
- Kill marks only the copy's private record (natives use the object's $13C4: $809CFD writes owner $1538). Main loop $80962E.
- Tests: all 65 areas with guards revived: min free threads >= 11 (vanilla 12-17), no freezes; all 500 areas liveness identical
  to v2; game nudges pointer onto hovered object ($80BE08).

## Slowdown investigation (2026-10-16)
- Profiler core: snes9x_prof (scratchpad) counts instructions per PC (prof_buf/prof_on exported). Main-loop counter test hook:
  $80962E (JSL $81B05D = wait-for-NMI, loop start) -> count at $7FB900 (mkcount.py). $7E1C92 = NMI frame counter (inc at $80C103).
- Vanilla $0A0: 295 main loops / 600 frames (half speed). Idle 26%. Hot: sprite-vs-scenery masking at $80B200-$B7FF (~40% of
  all instructions, ~54% of work), reading priority maps $7F0C00/$7F69C0 per 8x8 block into $188E/$1A8E.
- snes9x core option snes9x_overclock_cycles: 0a0 295 -> light 328, compatible 365, max 456. Batocera key snes.reduce_slowdown.
- Reinforcements add sprites -> some guard rooms drop to half speed in fights (e.g. $107 turret corridor 501 -> 302).
  v3.1: director skips spawning when NMI frames per 64 main-loop passes > 72 (MAX_LAG). Pack v3.1 CRC32 5971C82A.
- Cycle profile (prof_cyc added to snes9x_prof): sprite system = $80B8AF (main loop, per visible object in $14CE list -> $80B1DB
  with A = frame ptr $7E3F5C,X) = 56% of work in $0A0, 64% in $1E1. Split: B1DB setup 10%, phase A occlusion grid $B356-$B41E
  21% (per 8x8 cell vs BG priority maps $7F0000/$7F0C00 -> $188E flags, $1A8E overlay tile), phase B $B41F-$B725 11% (emits BG
  overlay sprites via $B101, 9 calls per flagged 16x16 cell, most rejected tile 0), sprite emit $B726 8%.
  Outputs only: OAM low $7E3CE4+$84 (4 bytes each), OAM high bits $7E3EE4 (2 bits each), $1474,Y bits, $1C90.
- ~70% of drawn objects have identical position ($0E44/$0E9C/$0EF4) and frame ptr between main-loop passes (camera still)
  -> per-object OAM output cache could cut ~35-40% of total work ($0A0 1.36 -> ~0.85 frames).

## Less Slowdown = sprite cache (build_speed.py, Runner Pack v4 CRC32 28036CBB)
- Hook $80B8DF (PHY/TXY/JSR $B1DB/PLY -> JSL spr). Per object slot (44) record of 124 bytes: age, key (frame ptr,
  (0C00-F4C-EF4) asr 1, (0600+E9C-E44) asr 1, F4C>>2, CE0>>2, CE2>>2, $1314, $141C, VRAM slot, location), n, outbits
  ($1474 bits set by B1DB over (in & F5FB)), $1C90, up to 16 entries x (4 OAM bytes + high bits). Slots 0-21 at $7FA900,
  22-43 at $7FB900; vars $7FC600-$7FC613. Code $BFEC00, tables $BFF400 (1 KB bit table, keep masks, replay dispatch).
- VRAM slot computed inline exactly like $80AA97 (same side effect). Key at half resolution is exact: frame offsets
  $1A/$1D are even. Camera moved this pass (pass id = NMI counter $1C92) -> plain B1DB call, records invalidated.
  Not cached: > 16 entries, OAM (nearly) full after the call ($84 >= $1FC). Re-checked every 16 passes.
- Replay writes high-table bits with a 4-way unrolled loop (pos = (Y>>2)&3), merging with the existing byte.
- VERIFY build (build_speed.patch(rom, verify=True)): on every hit replays, snapshots, restores, recomputes with B1DB and
  compares OAM bytes + high bits + end offset. 507 areas: 771,805 hits, 0 mismatches; full pack too.
- Speed (main-loop passes / 600 frames, standing): 106 laggy areas avg 475 -> 531; 26 reach >= 585. $0A0 295->400,
  $168 304->422, $0FE 392->538 (pack4->pack5). Office floors $1E1 ~296->326 (OAM full of overlay sprites).
  Walking: no systematic change (avg 172 vs 170 of 240; results chaotic when timing differs).

## Arena Leagues (2026-10-17) - build_arena.py, code/data/scripts in bank $BE ($BE8000, ~2.6 KB)
- Arena: entrance $008, ring $02C (fighters placed there, appear when their type flag $80 is set), office/fight
  instances $0AD/$0AE (manager object $1B66, script $01E4, record $3AB7; exit $0DEB).
- Manager script $01E4 polls its own flags (native #02): 1 = won (conv 1, prize), 2 = lost (conv 5), $20, 4 = start fight
  (sets $80 on the opponent type for var 4 = 0..9 -> $1267,$0CE8,$0D43,$0A5D,$0AE2,$0620,$137F,$1283,$01F1,$0A95, warps $02C),
  8 = King fight ($0245). Flag $80 (+$40) = champion: conv 7 (only $80) or the floater 'Buddy, nobody left to fight here!!'
  (native #C7 message 199, both $80 and $40). $40 = set by script $0134 (King prize 3000).
- Fight offer: conv topic -> script $02D0 -> $0118(text E0) yes/no -> manager flag 4. $0118 says E1 'No more fighters' if $80.
- Prize script $0299: native #98(amount) + texts D2 / D4+n (the amount as text) / D3, var 4 += 1; at var4 = 9 sets manager $80.
- Fighter scripts: spawn $0390 (appear if own flag $80, else native #B8), native #9F(HP,self), [waits/C7 speech], ADD_COMBATANT,
  AI spawn (returns lost/won for 6 of them), karma #7B, REMOVE, $035C death, manager flag 1, wait 100, warp $0AE.
  $01F1's AI ($00AB) does the combat list/death itself; $0A95 summons helpers (var 42) and waits for them.
- Natives: table $82D604 (addr, bank $80), arg words $82D895, returns-value $82D7BA. Native args: $00 = last pushed.
  #0D(v,type) flags|=, #4B(m,type) flags&=, #BA(type) get flags, #02/#7A/#94 on self. #56 warp = sets $7E2DE2 + $1D05=$7FFF.
  #98 add nuyen, #7B add karma ($7E3C11), #3C rest menu (only bed script $01D4 uses it), #9F set record HP.
  Records: +0 flags2 (#08/#9C), +1 flags, +2 HP, +3 owner ($1538 gone). Death = HP 0 -> event $0800 on the object's
  innermost thread ($136C chain, $80:86CC).
- Script directory lookups: $80C298 (bank/args/address) and $80F433 (args, spawn op). Per-script 'returns a value' flags at
  $82E468+id (used by op 52 spawn): a caller must DROP only if set (dropping otherwise underflows the stack -> corrupts
  the thread heap; that was the first copy-script bug).
- Text: messages $80D980[idx] -> text id -> $80FE33 (Huffman, tree $9D8000: node word, bit15 = leaf of 1-2 chars, high byte
  first; bitstream MSB-first, 16-bit words; $0A ends). FE44 = decode from [$CF] (24-bit, bank in $D1); it ends PLB/RTS, so a
  caller must PUSH B right before jumping in (PHB / JMP $FE44, or PHK/PEA/PEA/PHB/JML from another bank).
  Natives #99 ($8092BD, new box) / #D6 ($8092DE, append) / #C7 ($80FE8B, floater: $00 x, $02 y, $04 w, $06 h tiles).
- Patch: #98 x(league+1) in $0299 + 10th prize arms countdown; #99/#D6/#C7 custom texts (prize amounts, offer E0, E1,
  floater 199 -> 3-line 'come back in few days'); #3C sleep: champion (var4>=10, mgr $80) and league<2 -> countdown,
  after SLEEPS (1): league++, var4=0, mgr &= ~$80, ten fighter records = 00 00 HP FF FF; #9F: arena original in $02C ->
  league copies (A7C2, private records $7E2340+5k, script 936+fight from our table); #56: $02C -> $0AE warp held while
  any arena type is in the combat list unless manager flag 2. Copy script = HP, wait, [ADD], same AI args, lose path
  (clear 1, set 2) or drop-if-returns, [karma, REMOVE, $035C], wait, warp.
- State: league $7E3BF3, countdown $7E3BF4 (inside the saved block $7E2DE0-$7E3CE3, unused and 0 in all saves).
- Tests: 60 kill-order trials (league 0/1/2 x original-first/copies-first x 10 fights) on pack, arena-only and the full
  stack with Rebalanced + Expanded Dialogue A: warp exactly after the last death, var 4 +1, prize x1/x2/x3, karma per
  fighter. Natural flow checked: floater text, sleep -> pro, offer text, manager warp, copy spawn, lose path.
  L2 boss fight: min 12 free threads, 13 free objects.
- Runner Pack v5 = v4 + Arena Leagues, CRC32 06713BE4 (Shadowrun_RunnerPack_v5.zip).

## Ending bug fix (2026-10-18) - Runner Pack v5.1, CRC32 77A00E68
- The ending is a chain of 'dream' scenes: game var 44 ($7E3BE7) = scene step; Jake's control script $01D9 runs
  script $0026 at map load when var 44 != 0, which picks the scene script by step (3 $00BB ... 12 $0097 roll call,
  13 $01D1 office $0ED). Each scene ends with $008B (var 44 += 1, warp). Ending recap: 58,b5,b4,ef,d9,b3,d6,b1,b0,f0,ed.
  Test: set var 44 = 3 and warp anywhere.
- Bug (More Enemies since v1): rand hook at $80C4EF, path 'random(0)' / roll path returned with A = junk (bytes pulled
  off the stack) instead of the result. Script callers read $00 (fine) but asm callers use A - e.g. the hit damage roll
  at $80:86A1 ('jsr $C4EF / ply / inc A / sbc armor'), also $80895A.., $808BDD, $808CA1, $80F278, $80FF1E. So zero-range
  damage rolls became huge hits. In the recap scene $0B5 (script $026F, Jake fires via $0045) it killed the octopus
  boss (type $07A8, 90 HP) -> off-script, the chain stalls at $0B4 with a dog-spirit conversation / garbage on hardware.
  Fix: LDA $00 before leaving. Also More Enemies is off (vanilla rolls, no reinforcements) while var 44 != 0.
- Note: the game's RNG ($80C530) mixes the NMI counter and the H/V counters, so any timing change re-rolls everything;
  compare behaviour across several start offsets, not single runs.

## Arena fix v5.2 (2026-10-18) - Runner Pack v5.2, CRC32 329573CC
- User bug (elite): killed one enemy, no pay, next fight empty ring, stuck. Cause: original fighter died ($035C -> native
  #C4 sets owner $1538) and then a copy beat Jake (lose path: manager flags 1 cleared, 2 set) -> loss, var 4 unchanged,
  but the original's record stays 'gone' -> the map loader skips him on the rematch; no fighter script runs -> no warp.
- Fix: warp hook, destination $02C: if var 4 < 10 and TYPES[var4]'s record owner == $1538 -> owner $FFFF, HP = table.
  (php/rep #$30 around it; flags byte untouched, the manager sets $80 just before the warp.) Saves already stuck heal
  on the next fight request.
- Decisions: keep SLEEPS = 1. Parked: Glutman random missions, Wastelands club slowdown (Pi 4 side).
- OPEN (parked by user 2026-10-18): elite league, once: killed an enemy, no pay, next fight empty ring, stuck in the
  ring. User was heavily overpowered and is sure it was NOT a loss (so not the knock-out case fixed in v5.2; arena
  knock-out = Jake HP <= 5 in fights 1-6, from AI scripts' 'native 28 / native 08 <= 5' check). Not reproduced in
  60 kill-order trials. Reloading a save and redoing the fight worked. Revisit if it happens again (ask for the save
  right before the fight and which fight number).

## Glutman's Jobs (2026-10-18) - build_jobs.py (inside the arena module), Runner Pack v6, CRC32 E4EDC20E
- Glutman: type $03BF (sprite $37, script $039E, record $2EFA), conversation 72. Story: appears once at The Cage
  (map $067C = locations $008/$01C) when flag $80 set, talks, warps to $141 (car yards), native #C4 -> owner $1538.
- Conversations (native #94(conv,self), table $80947A -> record in bank $8D): +0..2 portrait ptr, +3 flags, then entries
  [topic][len][flags = n keywords | $80 script][n keyword ids][script word if $80][text id word]; topic $FF greeting,
  $FE Talk, $FD default, $F8 end, else keyword. Lookup + display $809123 (A = topic -> $1D); entry scripts run via
  $80C31A (X = id, $00 = self) + $80C19A. Menu choice $80918D (0 Exit / 1 Talk / 2 Ask).
- Locations = map + entry point: $8D92AF + 9*loc: +0 map ptr (bit15 -> bank $9A else $99), +2 facing, +3/+5/+7 entry
  x/y/z. Several location ids share one map (one per door you can arrive through).
- Exits are box zones: [$9D] (24-bit, set at map load) -> 2 lists (count byte, 14-byte entries x1 y1 z1 x2 y2 z2 data):
  pass 0 runs script `data` while Jake is inside, pass 1 loads location `data` ($80A44C). Engine check $808000.
- Map load: $80A4D8 jsr A287 (party at entry) / jsr A343 (map objects) / $80A4DE jsr A3F1 (camera) / jsl $819AE6.
- Natives: #0A(obj) = distance to Jake (doors open at < 31), #D1(obj,0,5) = standing animation (an object with no
  animation, $7E3F5C = 0, is not drawn), #9E(2,0) = wait to be talked to, #72(8,24) yes/no, #3E random, #56 warp.
  Script globals: push.gb/pop.gb ($04/$2E) and .gw ($18/$36) address bank $7E directly.
- Name labels: sprite -> text id table $8CF1C8 (0 = none).
- Patch: map-load hook $80A4DE (clears 'talking' flag; spawns Glutman at $248,$1F4 when his record is gone; on the
  active job's street map Glutman's man (type $0FCE) at the first wall-test-free spot of 4 offline-chosen spots
  24-32 from the job's street entry and far from exit zones; entering the job room (arrival flag + destination match):
  [$9D] -> empty zone list, invisible exit trigger at the room entry, boss copy (3x health) on the guard post farthest
  from the entry + escort, or a data terminal (room's terminal type, sprite $B2) there). Topic hook $809123: while our
  Glutman talks ($7E234D), greeting = our text, Talk = our job script. Job scripts (ids 946-950): glut, talk, door,
  exit, comp. Texts = message indices $0F00+n through the arena text hooks (native #99/#D6/#C7).
- 7 jobs: streets $017 / $022 / $03F / $000 -> office floors $1E1-$1E7 (siblings of $168.. of a late-game tower;
  one exit each). Pay 7,000 + 1,000 x job. State $7E3BF9 (0 free / 1 active / 2 done / 3 paid), job $7E3BFA.
- Gotchas found: RAM powers up as $55 in snes9x (and random on hardware) -> flags must be cleared at map load and
  arrival checked against the destination; save states made with an older build run stale script pointers after
  a rebuild (always regenerate states from u2s1_tw.state); native #0A distance of (40,40) is not > 40.
- Tests: all 7 jobs end to end (offer -> door -> room -> objective -> exit -> street), pay + cooldown text, sleep
  reset, arena suites + ending chain regression, other conversations unaffected, full stack with Rebalanced + ED A.

## Script dump / Script Atlas (2026-10-20) - dump_scripts.py, build_browser.py
- dump_scripts.py ROM OUTDIR data/zones.json: all 936 scripts -> pseudo-code (per-block expression rebuild, in-script
  subroutine signatures) + raw bytecode, with 'Used by' (object types + locations they're placed at, conversation topics,
  floor zones, callers, CREATE_OBJECT script args). 868/936 have a reference; 68 none (engine-started or leftovers,
  e.g. $11D 'Winter CES'93 Las Vegas - Warp!').
- VM corrections: op $C2 = push local byte 0 (DP $13; = self in object scripts, NOT a special self opcode; in $007E
  local 0 is the chance). Op $54 -> $80F8F1 (invalid/halt). Op $56 = end, returns the popped value. Op $4C call
  pushes the return pc on the script call stack ($05); $50 ret. Binary ops: a op b with a pushed first (checked lt/le/gt/sub).
- Native args: the LAST pushed arg is the routine's $00 (often the object), the one before $02, etc.
- Keyword table $8D8000 (64 text ids: 0 Akimi ... 18 Glutman ... 63 Volcano). Conversation topic byte = keyword index.
- Exit-zone pointer [$9D] is computed at map load ($81877F: $9A + offset after decompression); data/zones.json was
  captured by warping to every map in the emulator (van_tw.sfc + u2s1_tw.state).
- Type table: 7-byte entries at $8DB031+t (flags, record, sprite, script), t up to ~$209F (1193 valid types).
- $8CF1C8 (6-byte entries, word +4 = text id) is NOT indexed by the type's sprite word for most objects (Hotel Manager
  matched, others don't). Real hover-name lookup still unknown.
- New native names (read from the routines): 4F/50/51 GET_X/Y/Z, 82 SET_POS, 79 WALK_TO?, A8 CREATE_OBJECT
  ($00 last = ... first pushed = script), 63 RAND_RAW, C5 IS_TAKEN, 33/7A/95 SET/AND/STORE record flags, BA type record
  flags, 84 JAKE, 91 X distance, CE/2C OR/AND object bits $1474.
- Script Atlas artifact: https://claude.ai/artifact/UF9Y2mNAYHT8uMwsR7jSE7 (searchable, cross-linked).

## All natives named (2026-10-20)
- dump_scripts.py NATIVES now covers all 219 (grouped: record, type record, objects, position/anim, movement,
  combat, stats/money, story state, text/menus, cursor/input, timing/sound, cut-scene ring/orbit effects).
- Object hover names FOUND: per-sprite 6-byte entries at $8CEFB0 = [name text id][attr0][attr1]; natives #19/#5C/#40
  read attr0/attr1 ($8CEFB2/$8CEFB4). (The old note "$8CF1C8" was wrong.) Sprite 0 = shared by invisible helpers.
- Record bytes: +0 rec0 (#06/#9C), +1 flags (#02/#33 OR/#7A AND/#95 store), +2 HP (#08 get, #9F set, #2B dec ->
  true at 0), +3 owner (#0C get, #70 clear = back on map, #6F owner=$2DF0 (party slot 0 = Jake), #C4 gone).
  Type versions take a type id: #C2/#66 rec0, #BA/#0D/#4B/#60 flags, #68 HP, #CC/#BB owner, #42 owned-by.
- #28 and #84 both return Jake's object ($0CDE) - #28 was mislabelled GET_HP before.
- Movement: $0D3C/$0D94/$0DEC = velocity (#79 set, #4D zero, #44/#46/#47 get, #73 straight-line toward obj
  returns frames, #62/#D8 lob/arc). Path walking: $40BC active, $4114 mode (0 direct, 1 axis-by-axis?), target
  $416C/$41C4: #80/#1D to map point n ([$F3] 6-byte points), #2F/#B9 to x,y, #25/#B0 follow obj, #21/#AD follow
  Jake, #3B stop, #A7/#43 walk to cursor click. #B5 teleport to point n. $11B4 = facing 0-7 (#6A/#5D, #1B face obj,
  #6C face Jake). $43D4 = base animation (#24/#22/#14/#30). $1054 = one-shot anim (#D0, #6E done = $FFFF).
- Combat: $1FC4 party list (count $2DE6), $1FCE combat list ($1FCC). #07 random party target, #85 nearest party
  target, #4E random visible combatant, #48 prev combatant, #59 combat active, #5F in combat, #69 can hit
  (line of sight $81A25F), #10 ATTACK(p1..p4, target, self), #5A attack with equipped weapon, #7C area damage.
- Keywords: $7E3CA3 = learned keyword list (FF-terminated, sorted): #97 knows, #71 learn, #8F forget.
- $2DE4 = story progress bits (#D4 get, #DA n -> at least 2^n-1). $3C1C = choice list (#6D add, #89 menu).
- Cortex bomb timer: #C8 start ($1DA3=$0DD4 frames/hour, $1DA5=29 hours), #C3 active, #2A sets $1DA5=-1.
- #B4(msg,obj) = examine text ($7E442C, shown via $8092EF when you Examine the object). #13(flags) = action menu
  (Examine/Pickup/...). #AA/#8B spend/add magic points $3C96[char] ("I'm not giving it to THAT!" msg 11 on fail).
- #4C(a,b,sfx,obj) = sound effect (AI scripts: sfx 12 before ATTACK). #11/#D9 set $1FF6/$1FF4 = leave main loop.

## Object hover names - confirmed in code (2026-10-20)
- Hover routine $80BCA8 loops over drawn objects; $80BCCF: X = $7E3F04,X (the object's LIVE sprite, set only by
  object create $80A7C2) * 6 -> lda $8CEFB0,X = name text id. $FFFF = object can't be pointed at (skipped).
  Sprite $0B ("Me", Jake) is only pointable in target-picking modes ($01F4 = $FFFD or $1D7B/$1D89 set).
- $80BD9A: when the cursor settles, if object bits $1474 & 3 == 3 (hired party member) the label is the runner's
  name: type looked up in $809683 (13 types) -> text id from $809705 (Jake, Spatter, Jetboy, Norbert, Frogtongue,
  Anders, Akimi, Kitsune, Steelflight, Jangadance, Hamfist, Orifice, Dances). Otherwise $8CEFB0 + 6*sprite.
- Same table used by $80E5B0 (combat target list) and $80E980 (status screen title, via the type's sprite;
  $716C if none).
- Types with sprite 0 in the type table are spawned by scripts (CREATE_OBJECT picks the sprite), e.g. runners like
  Jetboy. dump_scripts.py now labels those from the creating call ('object created by script $X with sprite $S').
- To rename something in a hack: change its text, or point the sprite's $8CEFB0 entry at a new text id.

## Readable disassembly (2026-10-20) - srdisasm.py
- python3 srdisasm.py shadowrun.sfc OUTDIR [sdump/index.json]; cd OUTDIR; sh build.sh shadowrun.sfc -> byte-identical
  (WLA-DX 10.8, .BASE $80 so labels are $80xxxx; explicit .b/.w/.l on every operand; PEI must be written 'pei ($12)';
  MVN/MVP operands are written src,dst = second byte, first byte).
- Flow analysis from vectors, 219 natives, VM opcode handlers, NAMES list; M/X tracked through REP/SEP/PHP/PLP;
  4 jump tables in bank $81 ($81BB13, $81BBD8, $81BD13, $81D3DC). 21,273 instructions / 48 KB code (bank $80 ~80%,
  $81 ~67%); 59 M/X conflicts (same code entered with different flag sizes).
- Data decoded in place: 936 scripts (one instruction per line), 1,589 Huffman texts (byte-aligned, walked
  sequentially through banks $9D-$9E; tree $9D8000 up to the first text), tables. Message table $80D980 has
  $264 entries (ends at native $87, $80DE48; last = "(C) 1993 DATAEAST."). Staff credits ASCII at $81F27E.
- Not decoded yet: banks $82/$83 first ~22 KB, $84-$9A (graphics, maps, music), parts of $9B/$9C.

## Sprite graphics - decoded (2026-10-20) - srgfx.py
- Sprite graphics are UNCOMPRESSED 4bpp in banks $8E-$95; each 16x16 cell = two 64-byte 16x8 strips DMA'd as the
  frame changes (dest tiles from $AE41/$AE51 tables, VRAM slots allocated per object via $1314/$1580 chain).
- sprite id -> $8CED8A+2*id -> animation table (bank $8C, one word per animation; count = (first ptr - table)/2).
  Animation record: +1 delay (bit7 loop), +2 palette id, +8..+15 per-facing byte offset (from record+8) of the
  frame-word list; 0 = facing not used; a facing's list runs to the next larger offset.
- Frame word: bit15 -> bank $9C else $9B; addr = word|$8000 -> [n][2n gfx words][x org][y org][rows<<4|cols]
  [cells column-major; bit5 empty, bit6 hflip, bit7 vflip]. gfx word: bank $8E+(w&$3F), addr w&$FFC0.
  obj_frame ($7E3F5C) points past the gfx list (at the x-origin byte). Loader $80AC52-$80AD80, draw $80B1DB/$80B726.
- Palette id p -> 16 colours at $8DF1CA + $20*p (colour 0 transparent); CGRAM DMA copies 15 from +2.
- Map/BG tiles are NOT stored as plain tiles: the map loader composes up to 3 overlapping source tiles per 8x8
  cell (hash table at $818E57, buffers $A684/$AE84/$B684) and uploads the composed tiles from WRAM. Map
  'pieces' are referenced through table $8AC36A. Not decoded yet.
- Tools built for this: snes9x_prof core now also logs ROM reads (rd_cnt/rd_pc) and DMAs (dma_log); rdtrace.py.

## Maps and background graphics (2026-10-20) - srlz.py, capmaps.py
- Compression (all map graphics + layouts): LZ at $809E1E (entries $809E01 fixed $80 bytes, $809ED0 size in word0,
  $809EF0 same into bank $7F). Block: word0 size, word1 control-stream offset (+2), literals from byte 4; control
  = 16-bit words MSB first. Literal run (gamma code) first; match = absolute offset of k bits (k = $809FB6[len],
  or $809FB6[len>>8]+8 once len >= 256), length gamma+2; after a match 1 bit: 1 = match, 0 = literals. srlz.py
  ports it; verified: 219 decoded tiles equal tiles in VRAM after a map load.
- Map tile graphics: tile id t (14-bit) -> 128-byte group of four 8x8 tiles at bank $82+((t>>10)&15) :
  word $8DA431 + ((t>>1)&$1FFE) (banks $82-$87). Tile pixels are PLANE-SEQUENTIAL 4bpp (8 bytes per bitplane),
  not SNES format: the engine converts while composing. Cache: ids $7E:DF04, data $7E:DF84 (loader $81A1F9).
- BG is composed at run time: up to 3 overlapping source tiles per 8x8 cell are merged (hash $818E57, triples in
  $A684/$AE84/$B684) and the result uploaded from WRAM. Two BG layers (BG1/BG2) carry the map; BG3 = HUD/text,
  OBJ = sprites. Map buffer $7E4684 (0x6000 bytes = 96x64 cells x 2 layers); maps are at most 768x512 px.
- Map data ($99/$9A via location table): +0 layout index, +1 music track ($FF = keep), +2 word = exit-zone
  pointer +1 (-> $0CF6), +4 object count, 6-byte objects, then exit zones.
- Layout index n -> 3-byte pointer $8BFA53+3n -> compressed layout (decompressed to $7F:DA14 by $81A117):
  word0 -> $0D2E, byte2 = tile/palette set (-> pointers $8DF1B2/$8DF1BE), byte3 = count of height/priority
  shapes (4-5 bytes each, $818DE2), then [count] pieces for one BG layer ($7684) and [count] for the other ($4684):
  piece = word (index*2 into $8AC36A piece table, bits 14/15 = flips) + x, y, z bytes. Piece records in bank $8A,
  piece tile layouts in bank $96 (renderer $81903E/$819115). Not fully decoded yet (needed for a map editor).
- capmaps.py renders maps with the game itself: test-warp ROM with $808000 patched to CLC/RTS (no exit warps),
  snes9x layers 3 and 5 disabled (SNES_VARS env in snes_retro.py), Jake teleported over a grid so the camera
  ($0CE0/$0CE2, pixels = value/4) pans, screenshots stitched (8 px border trimmed). 189 maps, ~1 s each.

## Sprite import tool (2026-10-20) - srsprite.py
- export ROM XX -> sprite_XX_edit.png: palette swatch rows (8px, one row per palette id the sprite uses) + one
  block per animation, rows = facings, frames as stored; magenta = transparent, grey (40,40,48) ignored,
  (64,64,76) = empty cell (no gfx). Layout is deterministic from the ROM, so no side file is needed.
- import ROM PNG [XX] [OUT] -> OUT.sfc + OUT.ips + JSON report. Pixel mapping: keep the original index if the
  colour still equals that index's old/new palette colour (handles duplicate palette colours), magenta -> 0,
  exact palette match, else nearest (counted as snapped). Swatch changes rewrite the palette ($8DF1CA+$20*p).
- Cells are keyed by their (top, bottom) strip words. A strip used by anything other than this cell of this
  sprite is copied (copy-on-write) into the pool $BC:8000-$BD:FFFF ('SRSPR' + 16-bit count, strips from
  $BC:8040; word = addr&$FFC0 | (bank-$8E)), and only the matching word pairs in this sprite's frame records
  are repointed. Identity import leaves the ROM byte-identical for all 274 sprites. 1 MB ROMs are padded to 2 MB.
- Verified in the emulator: Jake's standing frame edited -> new graphics shown in game; IPS applies to the
  Runner Pack v6 ROM. Palette 02 is shared by ~115 sprites; no own-palette option yet (free palette slots unknown).

## Map building blocks - decoded (2026-10-20) - srmap.py
- python3 srmap.py ROM LOC [out.png] renders a location's map; srmap.py ROM piece P [out.png] renders one building block.
  Port of the layout loader $81A117, piece placer $81903E and tile merger $818E57. Checked against the game's own
  layer buffers for all 194 real maps: 384,596 cells, 0 mismatches.
- Chain: location -> map data +0 layout n -> $8BFA53+3n -> compressed layout (srlz): word0 ($0D2E), tile set byte,
  shape count + shapes (walk/height, not drawn), [count] pieces layer A ($7E7684), [count] pieces layer B ($7E4684,
  priority bit $2000). Piece entry 5 bytes: word w (bit15 mirror, bit14/13 = sign of y/x, bits 0-12 piece), z, x, y.
- Piece p -> word $8AC36A+2p -> record in bank $8A: +0 block count, +1 cell offset, +3 mirrored cell offset, +5 depth
  offset, +8 blocks x 5 bytes (word b: bit15 mirror + block number; row; column; depth).
- Block b -> 3-byte pointer $96C45E+3b: +0 cols-1 | (rows-1)<<4, +1 bit7 = depth per column else per tile, bits 0-6
  palette; then column by column [depth] tile word (0 empty; bits 0-13 tile id, bit14 hflip, bit15 vflip).
- Screen position: a = -((d2F + z - $300) & $FFFF) >> 2 (sign from bit 13; /4, not /8 as it first looks);
  b = ((y - x + $280) & $FFFF) >> 3, bytes swapped; col = (pos>>8) - 32, row = (pos & $7F) >> 1.
  Layers are 96 cols x 64 rows, stored COLUMN by column (index col*64+row).
- Floor: drawn first from the grid at $7F:CE14 (read at x + $400); each metatile v = 4 cols x 2 rows, tiles at
  [$11]+16v, palette byte [$14]+v ($11/$14 from $8DF1B2/$8DF1BE[tile set]). Fill routine $818DC0 steps x by $82.
- Cells keep up to 3 tiles sorted by depth (larger = further back); a full cell drops the new tile if it is
  furthest, else pushes out the furthest; palette = nearest tile's. Palette slots are handed out in order of first
  use (floor first) -> list at $0D1A. BG palette p = $8CF622 + $20p.
- Counts: 165 layouts, all used; 548 distinct pieces (max $223), 657 blocks, 13,574 placements. Maps $141/$15A/$0F0
  (black in the engine capture) render fine from the ROM (dark car yards).
- Map Atlas (https://claude.ai/artifact/85EZmaJE5L95NtfZ2eX64J) now shows ROM renders + a Building blocks tab.

## Map editor (2026-10-20) - editor/srcore.js, editor_template.html, build_editor.py
- Map Editor artifact: https://claude.ai/artifact/9j6oAJXnSCHUFKZxNGxQmA (loads the user's ROM locally; exports a .zip with
  Shadowrun_MapEdits.ips + shadowrun_map_edits.json + README; uses the artifact 'downloads' capability, which only allows
  zip/json/txt..., hence the zip). build: python3 editor/build_editor.py data/editor_maps.json preview.png out.html.
- srcore.js = JS port of srlz + srmap (cell-identical to the Python on test layouts), plus compressor, collision, IPS, zip.
- COLLISION comes from the pieces: $8184DE walks both layout piece lists; piece record +7 = box count, boxes after the
  blocks (8 + 5*nblk), 6 bytes each: dx(s8) wx dy(s8) wy dz(s8) wz, in world units (piece x*4, y*4, z*8 = obj_x>>2...).
  Mirrored piece: first pair goes to Y, second to X. Pieces with negative x, y (w bits $6000) or negative z get NO boxes.
  Boxes (12 bytes x1 y1 z1 x2 y2 z2) at $7E:E288+, bucketed by ((x & $3C0)>>6, (y & $3C0)>>6) into $DE88/$E088 chains
  ($EF18/$F778). After the piece boxes: the map data's own list at [$9A] (= right after the objects: count + 12-byte
  walls), then the zone lists (count + 14-byte entries, pass 0 floor scripts, pass 1 exits). Checked against WRAM on
  175/188 maps (the rest were dumped before loading finished; 400 frames after the warp is safe).
- Projection (map pixel) of world point: px = Y - X + 384, py = 768 - (X+Y)/2 - Z.
- Compressor: optimal parse; k(pos) = bit length of pos (that is what table $809FB6 holds). 1% smaller than the
  original. All 165 layouts recompressed + written back: 188 maps identical in the game.
- IN-PLACE ROOM: original streams share a straddling last byte with the next layout (e.g. $7C's stream reads 1 byte
  into $44) -> room = min(stream end, next layout start); last in a bank: stream end - 1. (Overwriting by 1 byte broke 17
  maps in the first test.) Bigger layouts go to a pool in banks $B0-$B3 ('SRMAP' at $B0:8000, data from $B0:8010; the
  pool is rebuilt on every export). 1 MB ROMs are padded to 2 MB with $00 and $7FD7 = $0B (same as Runner Pack).
  Runner Pack v6 leaves layouts and banks $B0-$B3 untouched.
- LIMITS: decompressed layout <= 2048 bytes ($7F:DA14..$7F:E213); <= 255 pieces per layer; wall boxes ~268 max
  ($E288..$EF18), editor caps 260; bucket entries 1072 max, cap 1000. TILES: merged 8x8 tiles share 1023 slots; dedup is
  per layer (hash table reset between layers), a whole-cell flip is the same tile -> count = sum over layers of distinct
  canonical tile stacks (matches the game exactly or game +1..6 from doors etc.; vanilla max 950). Over 1023 the game
  draws wrong tiles (seen when a test mirrored 1/3 of map $001's blocks). Editor cap 1010.
- Tests: edited maps $000 (40 added blocks, pool), $001 (mirrors, raised), $0AD (in place): 0 cell mismatches, 0 box
  mismatches. Added wall piece $02B at (122,117,8) on map $000: walking right Jake stops at x=492 instead of 462 (vanilla
  and Runner Pack v6 alike).
- Not editable yet: floor shapes, objects, exits/zones, map-data walls (shown as overlays).

## Map editor v2 (2026-10-20): floors, exits/walls/triggers, characters
- Modes: Blocks / Floor / Exits & walls / Characters. Edits file format version 2: layouts {n: {layers, floor?}},
  mapdata {loc: {objects, walls, zones, exits}}.
- FLOOR: grid = 24 cols x 32 rows of 32x16 px metatiles (k = col*32 + row; grid offset $400 + col*$80 + row*2).
  Metatile v of tile set t: 8 tile words at $8D:[$8DF1B2+2t] + 16v (4x2 cells), palette byte $8D:[$8DF1BE+2t] + v.
  Metatiles per set = (pal table - tile table)/16: sets 0-5 = 104, 80, 80, 80, 128, 24. Floor grid is drawing-only
  (nothing else reads $7F:CA14). Edited floor = original shapes + short runs (shape w>=0, 4 bytes) for changed cells
  only (value 0 erases); full re-encode if smaller. Original floors need <= 110 runs; nshapes byte caps at 255.
- PALETTES: max 7 BG palette slots per map (3 bits in the tilemap); vanilla max is 7 (layout $29). Editor meter.
- MAP DATA: $8D92AF+9*loc word -> block in bank $99 (bit15 -> $9A): +0 layout, +1 music, +2 word -> camera-limit
  table in the same bank ($0CF6/$0CF8, used by $818A05), +4 object count, objects, walls (12), zones (14), exits (14),
  then waypoints ($F3: count + 6 bytes) and more. Banks $99/$9A are full (1-3 bytes free) and the bank is chosen by
  bit 15 only, so the editor rewrites in place: same counts. Switch off = (0,0,$7FFF,0,0,$7FFF).
- Tests (vanilla test-warp ROM): painted floor patch -> 0 cell mismatches; Hitman moved to x=440 -> spawns at 440;
  exit $016 moved into Jake's path -> walking right warps to $016 (needs $808000 not patched).

## Text editor (2026-10-20) - editor/srtext.js, text_head.part + text_body.part, build_text_editor.py, build_text_index.py
- Text Editor artifact: https://claude.ai/artifact/Gm6yn3sZWCSWypDGaGanhg (loads the ROM locally, exports a zip with
  Shadowrun_TextEdits.ips + shadowrun_text_edits.json + README). build_text_index.py makes data/text_index_meta.json
  (conversation people, message users, unreferenced ids); labels are rebuilt from the ROM at run time.
- Text id = address: id < $C000 -> $9D:(id|$8000), bank $9E if bit 15. Byte-aligned starts, MSB-first bit stream,
  decoder reads 16-bit words via inc $CF (never let a text cross a bank). Tree $9D:8000: 351 leaves, 1-2 chars each,
  $0A ends. Single-char leaves exist for all printable ASCII except # % & + ; < > @ [ \ ] ^ ` { } ~ (not in font).
  Codes $01-$08 = blank spacers 1-8 px (menu alignment); $0E-$11, $1E, $1F, $7F = symbols. '|' = emphasise the
  next word (bold until a space; becomes $1A, width 0).
- Decoder: $80FE33 (id -> [$CF]) then $80FE44 (Huffman -> $7E21A0, then renderer $80FB03). Expanded Dialogue's hook
  ($80FE33 -> JML $A08000, ids >= $C000 -> 3-byte table $A0:8100) also ends with JML $80FE44.
- Our hook: $80FE44 = JML $B48000; code compares the 24-bit [$CF] with a table at $B4:8100 (word end offset = 6*count,
  then [old ptr][new ptr]) and swaps; then pea $7E7E / plb / JML $80FE48. Moved texts at $B5:8000-$B7:FFFF. In-place
  room = up to the next known text start (2 texts lie inside others -> always moved).
- Font: $95:F2D0 8 bytes per char, rows RIGHT-aligned (bit w-1 = leftmost pixel); widths $81:ABC8 (most chars 6 px).
  Bold = row | row<<1, +1 px.
- Conversation box: text area 142 px wide (measured: wraps match the game at 140-143), 11 lines of 8 px (a 241-char
  test line filled 10). Wrap rule: next word goes to a new line if its width >= remaining width.
- Length cap 250 decoded chars: buffer $7E21A0; the Runner Pack keeps records from $7E2300. Vanilla max is 218.
- Tests (emulator, START-stub calling native #C7 floater / #94 conversation): longer text (moved, via hook) and
  shorter (in place) decode and display on vanilla, Runner Pack v6 and Expanded Dialogue A (an ED text moved too).
  Text and map patches touch different banks (text $9D/$9E, $B4-$B7, $80FE44; maps $8B/$8A.., $B0-$B3, $99/$9A),
  so they stack in either order on the same base.

## Map editor v3 (2026-10-20): adding/deleting exits, walls, triggers, characters (map-data relocation hook)
- Map data block, full layout: +0 layout, +1 music, +2 word -> camera-limit table in the same bank (8-byte entries,
  $FFFF ends; usually right after the block), +4 object count, objects (6), walls (count + 12), floor zones (+14),
  exits (+14), walking points $F3 (count + 6), line-of-sight blockers $FC (count + 12: x1 y1 z1 x2 y2 z2 words,
  $81A25F). Parses cleanly for every real map.
- Only reader of the map pointer for loading: load_location $80A44C -> sub_80A3DA (bank = $99 + bit 15 into $88,
  $0CF8, $9F, $9C, $F5, $FE). Natives #7E CURRENT_MAP / #17 MAP_OF_LOCATION return the vanilla word as an identity,
  so the vanilla table at $8D92AF is never changed.
- HOOK: $80A3DA = JML $B88610: phx/pha; X = loc*3 ($7E2DE2); if $B8:8000+X (3 bytes) has a bank byte -> $86 = addr,
  bank from the table; else vanilla bank; store the 6 bank bytes; pla/plx; JML $80A3F0 (the RTS). 'SRMAPDATA' at
  $B8:8600; blocks from $B8:8800 to $BB:FFFF; rebuilt on every export; every location sharing the vanilla pointer gets
  the override. Same counts -> still rewritten in place (no hook).
- Tests: all 188 maps moved to the pool -> fixed boxes identical (13,276), map loads fine (differences at 400 frames are
  the game's own timing randomness: vanilla shifted by one frame differs on 79 maps). Map $000 with an added exit
  (warps to $016), added wall (Jake stops at y=483 instead of 447), added Water Fountain ($012D, no record) and a
  Busy Man ($1BDD) -> all work, vanilla and Runner Pack v6.
- Records: load_map_objects spawns an object if type flags | progress != 0 and (record == 0 or record owner == $FFFF).
  514 placed types have no record (free to copy). Copies of a record type share it; an extra Hitman copy did not
  spawn. Vanilla never places one type twice. Editor caps characters at 32 (vanilla max 27; object pool is 44).

## Own sprite palettes (2026-10-21) - srpal.py, srsprite.py --own, editor/srspr.js + sprite_*.part
- Sprite Colours artifact: https://claude.ai/artifact/H2q8dDst47YgyVQYpiySwf (recolour a sprite's palette as its own
  or for everyone sharing it; exports Shadowrun_SpriteColours.ips). srsprite.py import ... --own does the same from PNG.
- Palette pipeline: anim record +2 = palette id -> $1264,obj. $80AA97 (per draw pass) gives each id one of 8 OBJ
  palettes: $1802+2*id = slot*2 (reset to $FFFF by $81A7FC, ids 0-69: the table ends at $188C, the sprite mask grid
  $188E follows), $17F2 = list of id*2 per slot, $17F0 = next slot*2 (no overflow check). NMI code at $81A8D5 (it was
  shown as data in the disassembly) DMAs 15 colours from $8D:F1CC+32*id to CGRAM $81+16*slot. All 70 ids are used;
  data after id 69 ($8D:F98A..) is other data (e.g. $8DFB8A cursor tiles). Vanilla uses at most 7 slots in ordinary
  scenes (sweep of 188 maps).
- Patch: bank $AF ('SRPAL' 1, count $AF8006, original id per extra $AF8010+n, colours $AF9000+32n, ids 70-109),
  RAM $7F:C630-$7F:C67F (extra slot table). $80AA97 -> JML $AF815E (JSL core $AF8100; JML $80AAB2). Core: ids 70+ use
  the RAM table; with 7 slots taken they fall back to their original id; a 9th slot for anything shares slot 7
  instead of overflowing. $81A8D1 (last reset store + RTL) -> JML $AF8180 (also clears the RAM table).
  $81A8E1..$81A90A (NMI loop body) -> JSL $AF8200 + NOPs (ids 70+ from bank $AF).
  Runner Pack sprite cache inlines $80AA97 (B9 64 12 0A AA BD 02 18 ... 8E F0 17, 30 bytes, at file $1FEC13 in v6):
  replaced with LDA $1264,Y / JSL core. So apply the palette patch AFTER the Runner Pack.
- 12 animation records are shared, only inside identical sprite groups (same animation table): a group changes together.
- Tests: Jake own palette ($02 -> $46): Jake recoloured, other palette-$02 sprites unchanged (both palettes loaded);
  vanilla and Runner Pack v6; all 188 maps swept on the pack: max 8 slots (4 Wastelands-type maps), no corruption.
  JS tool output byte-identical to srsprite.py --own.

## Script editor (2026-10-25) - editor/srvm.js, script_head/body.part, build_script_editor.py, data/natives.json, data/script_meta.json
- Script Editor artifact: https://claude.ai/artifact/ETfxUhsTGMztfR5JUTLwan (decompile any of the 936 scripts to
  SRScript, edit, compile live with line-numbered errors, export Shadowrun_Scripts.ips + sources).
- SRScript = the decompiler's own output, made exactly compilable: one statement per line; `self`, `L.wN`, `L.bN`,
  `L.sbN`, `var[n]`, `gb/gsb/gw[$xxxx]`, named globals (karma, body..., `.w` for words); literals: decimal (minimal
  opcode), `$XX` = push.b, `$XXXX` = push.w, `+N` = push.sb, `0` = push0; operators = unsigned opcodes; signed
  variants as functions (lt_sl/lt_sr, eq_sl, mul_ss, ...; _sl = left operand signed); inc/dec/neg/bool; natives by
  name (arg count checked from $82D895); script_XXX(args) (checked against the directory); sub_XXXX(args) for
  in-script subroutines with a known signature, `gosub` otherwise; `push X`, `pop()`, `push dup(X)`, `drop [X]`
  keep the original stack juggling; `if [not] X goto L`, `goto`, labels; plus `if X { } else { }` and
  `while X { }` for new code. Header line: script $id args N returns yes|no locals N stack N.
- VM facts: header bytes = locals size (exact max local used) + stack size; frame = h0 + h1 + $17 ($80C298).
  $B0 = same handler as $AA (==), $B8 as $B2 (!=); $C2 = push.lb 0 (zero-extended); variants 8C/8E etc. are
  mixed-sign compares. Returns flag $82E468 = 2 or 0; arg bytes $82E810 = 2*args.
- Round trip: compile(decompile(s)) gives the same instruction stream for all 936 scripts (vanilla and Runner Pack
  v6), 833 opcode-exact, the rest only $B0->$AA / $B8->$B2 (same handler) and dropped dead bytes.
- IMPORTANT: keep each script's header sizes. Enlarging the stack size of 17 scripts (my depth estimate is higher
  than theirs) changed thread memory layout and 13 maps diverged; with the original sizes, all 936 recompiled and
  moved to $AC-$AE gave 188 maps pixel-identical for 400 frames (screen + object positions every 50 frames).
  build() keeps the original stack size unless the new code's estimated depth exceeds the old code's.
- Writer: in place when the new script fits before the next script (no script overlaps another), else pool
  $AC:A200-$AE:FFFF; registry 'SRSCR' 1 at $AC:8000, count $AC:8006, 9-byte entries from $AC:8010 (id, original
  address, original room, length) so later edits can go back in place; directory repointed.
- Tests: $060 + ADD_NUYEN(1234) -> +1234 nuyen on entering map $000 (also via the page's exported IPS);
  while/if-else test -> +307 exactly.
- Runner Pack recognises 28 scripts by address (editor warns): $02CC doc, $01AD/$0328/$01E9 runner AI, $007E More
  Enemies, $0299/$0118/$01E4 arena, $0320/$0011 copy equipping, shop-price scripts $B4 $B9 $BD $C0 $C9 $CE $CF $D0
  $14C $301 $307 $30C $30F $313 $316 $340 $348 $34E. New script ids (>= 936) are not supported yet: the Runner Pack
  already hooks the directory for its own ids 936+.

## Own save slots for copied characters (2026-10-25) - srcore.js installCopies/cpCode, editor build_type_class.js
- Problem: a placed type with a record (◆) shares that 5-byte record ($8DB032+type) with every copy -> extra copies may not
  spawn and killing one removes all. Records are bank $7E at $2E00-$3BBA (703 x 5, initial image LZ at $8BFC42 ->
  $7E2E00 by the new-game routine $80986C). No free saved-block bytes: vars 52-61 are touched by asm, the keyword
  list fills $3CA3-$3CE3; SRAM only has 4 spare bytes per slot (slot+$FFA..$FFD, after the Runner Pack's R2 table).
- Design (bank $AB, 'SRCOPY' 1): live private records = pool of 19 at $7E22A0 (5 bytes each; text buffer $7E21A0 ends
  at $229A with the 250 cap; ED max is 218); gone flags (words) $7FC5A0, pool ids $7FC5D0, NEXT $7FC5F6, temps
  $7FC592-$7FC5FE. Table $AB9000 (length in bytes at $AB8008): 7-byte entries [vanilla map pointer word ($8D92AF+9*loc)]
  [Y after the object = 11+6*index][copy id 0-23][rec0][flags][HP] (from the new-game image).
  Hooks (original bytes copied into the code and kept at $AB8010 for re-export; works on vanilla and Runner Pack):
  $80A343 (JSL; map load start: pool -> gone flags where owner != $FFFF, pool cleared, PW from $7E2DE2),
  $80A38E (lda $8DB032,X / sta $23 -> JSL: table hit -> next pool record, owner $FFFF or $1538 if gone),
  $81B141 save (after the copy: gone flags of ids 0-23 -> 3 bytes + check b0^b1^b2^$5A at slot+$FFA),
  $81B15B load (check ok -> flags, else all alive; pool cleared), $809878 new game (all alive).
- Editor: added ◆ copies get own=true (checkbox); items (script reaches #6F/#C5, 73 types) and runners (12 runner types
  + hire conversations) are excluded; selfref (script pushes its own type id, 17) warned. Ids stay stable across
  re-exports (read back from the ROM table). Limits 19 per map, 24 per game. Meters show both.
- Tests (van_tw2 = vanilla + test warp/save/load stub at $AA8000: START with $7F9992 = 1 save slot 0 / 2 load):
  map $168 + own copy of Massive Orc $0961: both spawn; copy killed (HP 0, game marks $1538) -> gone on re-entry,
  original stays; save -> tail 01 00 00 5B; fresh RAM + load -> copy stays gone; old save (tail AAAAAAAA) -> copy alive;
  original gone ($1538) -> copy still spawns; new game from title clears flags. Same on Runner Pack v6 (R2 table intact).
  Copy of a dead original (map $002 Orc) spawns. Re-export from a patched ROM keeps ids and original hook bytes.
  Rebalanced / Expanded Dialogue touch none of the hook sites or bank $AB.
- Regression: cp2 (copy on map $002 only) vs the same edit without own slot: object sets 40 frames after load on 188
  maps differ only in random street spawns (8 maps); plain map-data relocation vs vanilla shows the same kind of
  differences (7 maps) -> timing/RNG, not the hooks. Map Editor artifact republished (v4) with the feature.

## Map editor v4 (2026-10-25): floor tile set, walking points, sight blockers
- Tile set byte (layout +2) is only read at $81A158 to set $11/$14 (metatile tiles / palettes for the floor), so
  switching is a byte change; cells whose number the new set lacks (count = sets 0-5: 104/80/80/80/128/24 incl. 0)
  are erased. Tested: map $001 -> set 4, map $000 -> set 5: engine layer buffers = editor render (0 mismatches;
  cmp_js.js = JS port of mapcmp.py). Editor: Floor mode "Tile set" select (shared layouts warned), undo-able,
  projects store layouts[n].tset when changed.
- Walking points: [$F3] = count + (x, y, z words); natives #B5 PLACE_AT_POINT (index*6+1) / #80 WALK_TO_POINT;
  scripts name them by index -> editor adds at the end, deletes only the last. Sight blockers: [$FC] = count +
  x1 y1 z1 x2 y2 z2 words, checked by $81A25F, called from the attack code $808A66-$808CFF (line between two
  objects). srcore mapInfo now decodes both as signed words; sameCounts/writeMapData include them (in place when
  counts match). Test: map $000 +2 points +1 blocker (moved block) and script $060 = PLACE_AT_POINT(1, Jake):
  Jake lands on (452,506,64); [$F3]/[$FC] point into the relocated block; map $168 in place pointers ok.

## Text windows (2026-10-25) - build_msg_windows.js (adds meta.msg_win), text_body.part previews
- Window open $80F92D: $00 x, $02 y, $04 w, $06 h (tiles, clamped to the screen), $08 style; text width stored as
  (w-2)*8 at $7E2120,X. Floater native #C7($80FE8B): args in push order (time, message, style, h, w, y, x); window
  size is set per call by the script. Measured (START stub calling $80FE8B with DP args from $7F99A0): text wraps
  at exactly (w-2)*8 px with the "word width >= room left" rule (w=16 -> 112, w=24 -> 176), h-2 lines.
- #99 TEXT_BOX / #D6 TEXT_APPEND print a message into window $14 = the open conversation window (used by topic
  scripts) -> conversation box. #B4(conv, obj) examine = a CONVERSATION number ($7E442C -> $8092EF), not a message.
- #6D ADD_CHOICE adds a message to the list $7E3C1C; #89 CHOOSE_FROM_LIST ($80E199) opens 16x7 at 14,5 with "Exit"
  ($70C8) first; entries are one line starting after the cursor: 103 px fits, 104 px breaks the whole menu.
- Messages with known windows from scripts: 343 (274 floaters, 63 text box, 7 menu entries: 79-81, 83-86). Engine
  menus/status texts remain unmeasured (preview says so).

## Pixel painting (2026-10-25) - srspr.js (cellPixels, frame(word, ov), stripUsers, applyPixels), sprite_body.part
- Sprite Colours page now paints pixels: cells = 16x16 graphics from two strips (word -> $8E+(w&$3F) bank, 64 bytes
  = two 4bpp tiles); frame record at $9B/$9C: n, 2n strip words, header (ox, oy, cols|rows<<4), cell bytes ($20 empty,
  $40 hflip, $80 vflip). Edits are per graphics cell (all frames/mirrors that show it). Export = srsprite.py logic:
  strips used only by this group's cell rewritten in place, otherwise copied to the pool $BC:8000 ('SRSPR' + count,
  strips from $BC:8040) and this group's frame records repointed; frame records shared with other sprites are
  reported (Jake's are shared with sprite $95).
- Tests: node apply of bars over all of Jake's cells (118 strips in place, 140 copied): Jake shows the bars in the
  game (emulator screenshot); only sprite $95's 2 frames change elsewhere. Page export (drag stroke) decodes to the
  painted row. Project JSON v2 adds pixels {sprite: {"top,bot": 256 hex nibbles}}.

## Music per map (2026-10-26)
- Map data +1 = song. Map load $80A484: $FF keeps the current song; else if != $1CFA fade ($81EF55) and after the
  load $80A500 plays it via $81EF08 (sta $1CFA; $81F21B sends the song to the SPC; 0 = stop). Combat start ($80854B)
  saves $1CFA in $1FE6 and plays song 6 (battle), restored at $80861F.
- Songs 1-12 are real (audio recorded from the emulator: snes_retro now records when _state['audio'] is a
  bytearray); 13+ are silence/noise. Map usage: 1 streets, 2 clubs, 3 ghouls/spirits, 4 indoors/hotel, 5 club
  (bouncer), 6 battle (also map $02C), 7 morgue/doc/arena/monorail, 12 corporate towers; 8-11 unused by maps
  (8 played at $81C38F); map $1FA has 64 (plays nothing), 131 maps have $FF.
- Map Editor: "Music" select in the toolbar; writeMapData now writes the byte in place. Test: map $000 -> song 3
  via the page export (14-byte IPS): $1CFA = 3 after warping in.

## Pixel painting extras (2026-10-26) - sprite_body.part
- Tools: pencil, flood fill (4-connected, same index, only inside cells with graphics), colour picker (also right-
  click / Alt-click); Copy frame / Paste / Paste mirrored (left-right, empty cells skipped, top-left aligned when
  sizes differ); Save frame as PNG (sprite_XX_animN_FACE_fK.png, colour 0 transparent) / Load PNG into frame (must
  match the frame size; alpha < 128 or magenta = colour 0; other colours snap to the nearest palette colour,
  counted). Every action is one undo step. Tested in Chromium: fill, pick, copy + mirrored paste, PNG out -> in
  unchanged = no edit, off-palette line snapped (16 px), wrong size refused, export still decodes in the ROM.

## Camera limits (2026-10-26)
- Map data +2 word -> table in the same bank (right after the block; never shared). Only the FIRST entry counts
  ($818A05; $0CF6 = word - 1, Y = 1): 4 words minX', maxX', minY', maxY' where X' = x + 12, Y' = y + 12 of the
  followed object ($0CDE, Jake): caller $818C2E passes $0E = $400 + 4(y - x), $11 = $910 - $0F4C ($0F4C = 2(x+y),
  checked in RAM); the routine works in ((0x940-$11)*2 -/+ ($0E-$400))/8 = x+12 / y+12. First word $FFFF = no
  limits. 115 maps have one entry, 71 none, maps $1F7/$1FA have no table at all (word < $8000).
- Effect: the camera focus is Jake's x, y clamped to [x1..x2] x [y1..y2]; camera = $0CE0/$0CE2 (BG1 H scroll =
  $0CE0/4 at $8189E1). Tests: map $001 box 640-660 x 410-430 (in place, 21-byte IPS from the page) -> camera stops
  following once Jake leaves it; limits removed (block moved) -> camera follows; map $000 given new limits (moved,
  table appended) -> camera frozen at the area while Jake walks outside it.
- srcore: mapInfo.camBox = [x1, y1, x2, y2] or null; serializeMapData writes camBytes(camBox) (sorted min/max);
  writeMapData rewrites the 8 bytes in place; sameCounts requires the same presence. Editor: Exits & walls mode,
  "Camera area" (dashed yellow at floor height), Add camera limits / Delete, X/Y inputs, drag, arrow keys.

## Game menu windows (2026-10-26) - editor/mk_text_logger.py, menu_fuzz.py, build_eng_windows.py (meta.eng_win)
- Messages are only shown through 4 routines (floater $80FE8B, text box $8092BD/$8092DE, choice list $80E199); the
  engine prints its own texts by id: lda #id / sta $02 / jsr $FE33 into the current window ($00), cursor set by
  $80FA76 ($02 column, $04 row; cursor = base + row*(w-2) + col at $7E20C0,X).
- Measurement: test ROM with $80FE33 -> JML $AA9000 logger (text id, window w $7E2020,X, h $7E2040,X, cursor offset)
  into $7FA900; random button presses from 10 states (field, bed, doc, arena, Dark Blade, title boot) plus menu-only
  runs with START patched to the rest menu, 4 conversations and yes/no (40,000 / 20,000 frames each). 123 texts got
  windows; 85 are shown in a new "Menus" group (status screen, party status, inventory list, action menus, spells,
  rest menu, save slots, conversation Talk/Ask, yes/no, Exit...), ~20 of them were missing from the text list
  before (Money, Karma, Exit, Talk, Pickup, spell lines...). Not reached: karma spending screen, shops' list
  screens, matrix.
- Preview: width (w-2)*8, first line indented by column*8, h-2-row lines. Check: rest menu "Use karma" (12x5, col 1,
  line 3, 80 px) -> "Use all the karma" wraps exactly as predicted and pushes "karma" over "Exit" in the game.

## More than 24 own save slots: 16 KB save file (2026-10-26) - srcore.js cpCode/installCopies
- Gone flags are now one BYTE per copy id at $7FB000-$7FB0FF (was 24 words at $7FC5A0). Table id byte allows 0-255 (CP_MAX_BIG = 256).
- Ids 0-23 are still packed into the 4 spare bytes at slot+$FFA (3 bytes + check = b0^b1^b2^$5A), so 8 KB saves work as before.
- CP_BIG byte at $AB:800A = 1 when any id >= 24; export then sets ROM header $FFD8 = 4 (16 KB SRAM). Header is never lowered.
- BIG save: SRAM $2000 (slot offset $0000) / $2200 (slot $0FFE; was $2100 at first = overlapped slot 1's 260-byte block, fixed same day): 'CPv1' + 256 flag bytes (MVN $70,$7F). Load: unpack tail into ids 0-23 (all others zeroed), then if BIG and 'CPv1' present MVN the 256 bytes back. No signature (old 8 KB save padded by the emulator) -> copies past 23 start alive.
- New game zeroes all 256 flags. TMPID is now the id itself (not 2*id).
- Verified (snes9x core): cold boot with header 4 OK; slot 1 and slot 2 save/load of id 200; id 5 still uses only the tail; padded save without block -> copy alive; Runner Pack v6 SRAM identical to unpatched except the tail bytes (R2 table intact).
- BizHawk pads/truncates .SaveRAM to the core size (MainForm); RetroArch loads a smaller .srm into the start of SRAM.

## Brand-new scripts (2026-10-26) - editor/srvm.js (readNewDir, newHookCode, applyScripts), script_body.part
- New script ids $400-$5FF (Runner Pack keeps 936-950 = $3A8-$3B6; 951-1023 left free). Must be numbered without gaps.
- Header 'SRNEW' 1 at $AC:A200, entry count word $AC:A206, original bytes of the 3 hooked reads at $AC:A210 (25),
  $AC:A230 (7), $AC:A238 (7); hook code $AC:A240; directory $AC:A400, 7 bytes per id: address 3, arg bytes, returns
  flag (0/2), length word. Script bodies (moved + new) in the pool from $AC:B400 (was $AC:A200; re-export reads the
  old place through the directory, so older patches convert fine).
- Hooks (X = id, 16-bit): $80C298 (25 bytes: bank/args/address, out $71/$73/$0264, X = 2*id), $80F433 (op $52 arg
  bytes, flags from AND #$FF), $80F473 (op $52 returns flag; vanilla AND the Runner Pack read $82E468,X directly, which
  for ids >= 936 falls into the arg-bytes table). Ids outside $400..$400+count run the stored original bytes; an
  original JSL (Runner Pack's $80C298 / $80F433 hooks) is chained as a JML. Deleting the last new script restores
  the original bytes.
- VM: newDir (from ROM), pending (args/returns of scripts being written), gone (deleted in the editor); known(id).
  Compiler: script_XXX with XXX >= $400 that does not exist is an error. New script stack size = 2*depth+4.
- Verified (snes9x): $060 -> new $400 -> new $401 (2 args, returns value, if on its result) +1234 nuyen on vanilla
  and Runner Pack v6; editor export / reload ('added by an earlier patch') / edit / delete+re-add / re-export;
  deleting all restores the hooked bytes exactly (vanilla and pack). Screens differ from the unhooked ROM only by a
  random street spawn at $016, same as a control ROM with a plain JSL detour (extra cycles shift the RNG).

## Map editor: scripts on characters and floor triggers (2026-10-26) - srcore.js installObjScripts/osCode, editor_template.html
- Floor triggers: script number is now a hex text box; accepts 0-$3A7 or the ROM's new scripts ($400.. from 'SRNEW'
  count at $AC:A206; srcore newScriptCount/scriptExists). Zone scripts run via $80C31A (X = id) every frame while
  Jake is inside (a test script adding 1234 nuyen ran 217 times in 400 frames) -> new trigger scripts need a var guard.
- Per-character script: object field .script (hex box in the Characters panel, empty = type's script $8DB036+type).
  Bank $A9: 'SROBJ' 1, byte count (5*n) word $A9:8008, original 6 bytes at $A9:8010, code $A9:8020, table $A9:8100 =
  5-byte entries [24-bit ROM address of the object's 6-byte entry in its map data block, script word]. Hook $80A3A8
  (lda $8DB036,X / sta $08 -> JSL): object address = $86 + Y - 6, bank $88. Table rebuilt every export after all map
  data moves (edited maps from md.objects, others carried over by old->new block address); none left -> original
  bytes back. Bank $A9 confirmed empty in vanilla, Runner Pack v6 and Expanded Dialogue A ($A0-$A2 used by ED).
- Verified (snes9x): Massive Orc on $168 -> new script $400 (+1234 nuyen, once) on vanilla and Runner Pack with the
  map data moved and an unchanged copy beside it; re-export of another map keeps it; clearing restores $80A3A8;
  editor UI: bad numbers refused with a reason, export, README line; floor trigger with $400 via the UI.

## Separate item copies = new item types (2026-10-26) - srcore.js installItems + cpCode(orig, nItems), editor_template.html
- Inventory list ($80E555..): walks EVERY type from $208A down by 7 (type table $8DB031+t), keeps those whose record
  owner == the character ($1F76) and whose sprite category ($8CEFB4 & 3) matches; one row per TYPE -> a copy needs its
  own type. Pickup (native #6F) writes owner through the live object's record pointer $13C4.
- Type table moved to $A3:8000 (+t; 7-byte entries, vanilla types 0..$2098 = $209F bytes copied). All 'BF 31..36 B0 8D'
  (lda $8DB031..36,X) in banks $80/$AB/$BE/$BF repointed: 39 vanilla + 9 Runner Pack + the copies code's saved bytes.
  New item types $209F + 7k = original's entry with record $7E21E0 + 5k (max 36: $21E0-$2293, never written in 15
  maps + menus + save/load on vanilla/Runner Pack). 'SRTYP' 1 at $A3:FFE0, count $A3:FFE6, original types $A3:F000+2k.
  Inventory loop start $80E564 = last new type. Records saved by the copies module: count $AB:800B, starting records
  $AB:8800 (init bytes of the original's record + owner $FFFF), SRAM $2400 (slot 1) / $2500 (slot 2) after 'IT';
  load without 'IT' (older save) -> starting records; new game -> starting records. Header $FFD8 = 4.
- BUG FIXED same day: the >24 own-slot block for slot 2 was at SRAM $2100, overlapping slot 1's 260-byte block -> now $2200.
- Editor: item copies get 'Separate item' (o.newItem; after export o.type = new type, o.itemOf = original). Not for
  the game's own placement or SELFREF items. Max 36.
- Verified (snes9x): Dog Collar ($1546) copy on location 1: spawns as $209F after loading an older save (original
  already owned stays away), owner poke -> save writes 'IT' record, load restores it, owned copy not placed again;
  inventory shows two "Dog Collar" rows (types $209F and $1546); editor UI export with 2 copies -> $209F/$20A6 both spawn.
  Not yet tested: picking up with the in-game cursor, using/dropping/giving a copy, shops.
