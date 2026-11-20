"""Build "Shadowrun: More Enemies With Runners" (standalone, stacks with Persistent Runners / Rebalanced / Expanded Dialogue).

  python3 build_enemies.py IN_ROM OUT_PREFIX      (IN_ROM: clean 1 MB ROM, or any 2 MB patched ROM)

How the game spawns street enemies: each placed enemy runs script $007E when you enter a map:
    if random(10) < chance  and  var[42] < 4:  var[42]++ ; appear     (var 42 = enemies active this visit, reset per map)
This patch, depending on the number of hired runners in the party (0-3):
  * the roll counts as  chance x 1.0 / 1.2 / 1.4 / 1.6   (random(10) is replaced by random(100) / (10+2n), i.e.
                                                         'r < chance' becomes 'r100 < 10*chance*(1+0.2n)' at 1% steps)
  * the cap of 4 becomes 4 / 5 / 6 / 6                   (var[42] is read as var[42] - extra in that check only)
Only the roll-based enemies are affected (street gangs, ghouls, etc.); story and boss fights are unchanged.
Nothing changes while a story cut-scene runs (game var 44 nonzero, e.g. the ending recap).
Code lives at $BFE000 (file $1FE000); the ROM is expanded to 2 MB if needed.
"""
import sys, zlib
from build_runners import Asm, lorom, make_ips, RTL80

CODE = 0xBFE000
ROLL_CODE = (0x9F, 0x9AE9)     # code start of script $007E
PC_RANDOM = 0x0006             # script offset right after 'native 3E' (random) in $007E
PC_CAP = 0x000C                # script offset right after the first 'native 57' (read var 42)
CAP_EXTRA = [0, 1, 2, 2]       # 4 -> 4/5/6/6 (nearest to +20/40/60%)
TMPV, TMPN, TMPR = 0x7FB7B0, 0x7FB7B2, 0x7FB7B4
# --- indoor guards (placed enemies): reinforcements ---
PCT, NPEND, PIDX, CT, CO, CR, FRM, TMPQ = 0x7FB7B6, 0x7FB7B8, 0x7FB7BA, 0x7FB7BC, 0x7FB7BE, 0x7FB7A0, 0x7FB7A2, 0x7FB7A4
BXV, BYV, LASTN = 0x7FB7A6, 0x7FB7A8, 0x7FB7AA
MAX_LAG = 72                           # frames per 64 main-loop passes: above this the game is already slowing down
DPSAVE = 0x7FB800                      # 64-byte copy of direct page $00-$3F around our object creation
PEND, PSZ, MAXP = 0x7FB840, 12, 8      # pending reinforcements: type, x, y, z, record bytes 0-2 (12 bytes each)
SPREAD = 14                            # a reinforcement stands this far from its guard's spot (first free side)
POOL = 0x2300                          # private 5-byte records for reinforcements, unsaved bank-$7E RAM ($7E2300-$7E2327)
MIN_THREADS = 30                       # only bring one in while this many script threads are free (pool of 48)
MIN_OBJECTS = 12                       # ... and this many object slots (pool of 44)
MAX_LIVE = 2                           # ... and fewer than this many reinforcements are still alive
EVERY = 0x3F                           # check every 64 main-loop frames
# areas whose enemies are all placed (no dice roll); found by loading every area (see notes).
# Left out: $0A0/$176 (scripted ambush, already the busiest scene for script threads).
GUARD_LOCS = [0x007, 0x05F, 0x060, 0x082, 0x08F, 0x09B, 0x0B0, 0x0B3, 0x0B4, 0x0C8, 0x0C9, 0x0CA, 0x0CD, 0x0CE,
              0x0D3, 0x0D4, 0x0D6, 0x0D9, 0x0E3, 0x0E4, 0x0E5, 0x0E6, 0x0FD, 0x0FE, 0x0FF, 0x100, 0x105, 0x106, 0x107,
              0x108, 0x109, 0x10A, 0x10B, 0x10C, 0x10D, 0x11B, 0x11C, 0x11D, 0x11E, 0x138, 0x139, 0x13A, 0x13B, 0x13C,
              0x13D, 0x13E, 0x15E, 0x168, 0x169, 0x16A, 0x16F, 0x170, 0x175, 0x17B, 0x1CB, 0x1DB, 0x1E1, 0x1E2,
              0x1E3, 0x1E4, 0x1E5, 0x1E6, 0x1E7]
MIN_SPRITE_USES = 3                    # a guard look used at fewer placed spots is a boss / special: never copied
AI_SCRIPTS = {0x010C, 0x010D, 0x027B, 0x02A9, 0x007A, 0x00FB, 0x00A0, 0x0335, 0x035B}   # generic guard AIs (called)
GUARD_SCRIPTS = {0x018A, 0x031A, 0x0167, 0x0317, 0x006C, 0x020D}   # guard scripts shared by many guards (own AI)
import os
CLEAN = open(os.environ.get('SR_CLEAN', os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'shadowrun.sfc')), 'rb').read()
RTS80 = 0x80C50F               # the RTS at the end of native #3E


def guard_tables(rom):
    """Placed enemies = map objects whose script first spawns one of the generic guard AIs."""
    lr = lambda x: ((x & 0x7F0000) >> 1) | (x & 0x7FFF)
    RB = lambda x: rom[lr(x)]; RW = lambda x: int.from_bytes(rom[lr(x):lr(x) + 2], 'little')
    def first_spawn(sid):
        if sid >= 936: return None
        o = lr((RB(0x82D970 + sid) << 16) | RW(0x82DD18 + 2 * sid)) + 2
        for k in range(40):
            if rom[o + k] == 0x52: return int.from_bytes(rom[o + k + 1:o + k + 3], 'little')
    spots = {}
    for loc in GUARD_LOCS:
        p = RW(0x8D92AF + 9 * loc); base = ((0x99 + (p >> 15)) << 16) | (p | 0x8000)
        for k in range(RB(base + 4)):
            t = RW(base + 5 + 6 * k + 4)
            sc = RW(0x8DB036 + t)
            if sc in GUARD_SCRIPTS or first_spawn(sc) in AI_SCRIPTS: spots[(loc, k)] = t
    uses = {}
    for t in spots.values(): uses[RW(0x8DB034 + t)] = uses.get(RW(0x8DB034 + t), 0) + 1
    return sorted({t for t in spots.values() if uses[RW(0x8DB034 + t)] >= MIN_SPRITE_USES})


def build_code():
    global GUARD_TYPES
    GUARD_TYPES = guard_tables(CLEAN)
    a = Asm(CODE)
    # helper: Z flag set if the current script thread runs $007E at script offset in A. Clobbers X.
    a.label('is_roll')
    a.sta_l(TMPR)
    a.lda_l(0x7E026C); a.b(0xAA); a.lda_lx(0x7E026E); a.b(0xAA)
    a.lda_lx(0x7E0002); a.b(0x29); a.w(0xFF); a.imm(0xC9, ROLL_CODE[0]); a.rel(0xD0, 'ir_out')
    a.lda_lx(0x7E0000); a.imm(0xC9, ROLL_CODE[1]); a.rel(0xD0, 'ir_out')
    a.lda_lx(0x7E0003); a.cmp_l(TMPR)
    a.label('ir_out'); a.b(0x60)
    # helper: A = number of hired runners in the party (0..3)
    #         (0 during the story cut-scenes: game var 44 is the cut-scene step, e.g. the ending recap; extra
    #         guards there break the scripted scenes)
    a.label('runners')
    a.lda_l(0x7E3BBB + 44); a.rel(0xF0, 'rn_play'); a.imm(0xA9, 0); a.b(0x60)
    a.label('rn_play')
    a.lda_l(0x7E2DE6); a.rel(0x10, 'rn_ok'); a.imm(0xA9, 0)
    a.label('rn_ok'); a.b(0x4A); a.imm(0xC9, 4); a.rel(0x90, 'rn_r'); a.imm(0xA9, 3)
    a.label('rn_r'); a.b(0x60)

    # --- native #3E random(n): JSL from $80C4EF (replaces LDA $00 / BEQ) ---
    a.label('rand')
    a.b(0xA5, 0x00); a.rel(0xF0, 'rd_leave')                                   # random(0): return 0
    a.lda_l(0x7E3BBB + 44); a.rel(0xD0, 'rd_van')                             # cut-scene: untouched
    a.imm(0xA9, PC_RANDOM); a.jsr('is_roll'); a.rel(0xF0, 'rd_mine')
    a.label('rd_van')
    a.b(0xA5, 0x00); a.b(0x6B)                                                 # vanilla: continue at $80C4F3
    a.label('rd_mine')                                                          # 1%-resolution roll:
    a.imm(0xA9, 100); a.b(0x85, 0x00); a.call80(0x80C4F3)                       # r100 = random(100)
    a.jsr('runners'); a.b(0x0A); a.b(0x18); a.imm(0x69, 10); a.sta_l(TMPN)      # divisor 10 + 2n
    a.b(0xA5, 0x00); a.imm(0xA2, 0)
    a.label('rd_div'); a.b(0x38); a.b(0xEF); a.l(TMPN); a.rel(0x90, 'rd_dd'); a.b(0xE8); a.bra('rd_div')
    a.label('rd_dd'); a.b(0x86, 0x00)                                          # r' = r100 / (10+2n)
    a.label('rd_leave')
    a.b(0xE2, 0x20, 0x68, 0x68, 0x68, 0xC2, 0x20)                              # drop our JSL return
    a.b(0xA5, 0x00)                                                            # A = result, like the original
    a.b(0x5C); a.l(RTS80)                                                      # leave (callers such as the damage
                                                                               # roll at $80:86A1 use A, not $00)

    # --- native #57 get var: JSL from $80CBD7 (replaces LDX $00 / LDA $7E3BBB,X); returns A ---
    a.label('getvar')
    a.b(0xA6, 0x00); a.lda_lx(0x7E3BBB); a.sta_l(TMPV)
    a.b(0xE0); a.w(42); a.rel(0xD0, 'gv_ret')
    a.imm(0xA9, PC_CAP); a.jsr('is_roll'); a.rel(0xD0, 'gv_ret')
    a.jsr('runners'); a.b(0x0A, 0xAA); a.lda_lx(0); a.fix.append(('long', len(a.code) - 3, 'extra'))
    a.sta_l(TMPN); a.lda_l(TMPV); a.b(0x38); a.b(0xEF); a.l(TMPN); a.rel(0xB0, 'gv_r2'); a.imm(0xA9, 0)
    a.label('gv_r2'); a.b(0xA6, 0x00); a.b(0x6B)
    a.label('gv_ret'); a.b(0xA6, 0x00); a.lda_l(TMPV); a.b(0x6B)
    a.label('extra')
    for v in CAP_EXTRA: a.w(v)

    # --- placed guards. Map load (JSL from $80A4D8, replaces JSR $A287 / JSR $A343): for each placed guard that
    #     appeared, roll 20% per runner; a hit queues one reinforcement of that guard (spot, look, script, health).
    a.label('mapobj')
    a.call80(0x80A287); a.call80(0x80A343)
    a.b(0x08, 0xC2, 0x30)                                                      # php; rep #$30
    a.imm(0xA9, 0); a.sta_l(NPEND); a.sta_l(PIDX)
    a.lda_l(0x7E2DE2); a.sta_l(CT); a.imm(0xA2, 0)                             # location in the list?
    a.label('mo_loc'); a.lda_lx(0); a.fix.append(('long', len(a.code) - 3, 'locs'))
    a.imm(0xC9, 0xFFFF); a.rel(0xF0, 'mo_x1'); a.cmp_l(CT); a.rel(0xF0, 'mo_go'); a.b(0xE8, 0xE8); a.bra('mo_loc')
    a.label('mo_x1'); a.brl('mo_exit')
    a.label('mo_go')
    a.jsr('runners'); a.rel(0xF0, 'mo_x1')                                     # no runners: vanilla
    a.b(0x0A, 0x0A); a.sta_l(TMPN); a.b(0x0A, 0x0A, 0x18); a.adc_l(TMPN); a.sta_l(PCT)   # 20% per runner
    a.b(0x8B); a.imm(0xA2, 0); a.imm(0xA0, DPSAVE & 0xFFFF); a.imm(0xA9, 63); a.b(0x54, 0x7F, 0x7E); a.b(0xAB)
    a.imm(0xA0, 0)
    a.label('mo_loop')
    a.b(0xB9); a.w(0x3F04); a.rel(0x30, 'mo_n1')                               # free slot
    a.b(0xB9); a.w(0x1526); a.sta_l(CT); a.imm(0xA2, 0)                        # guard type?
    a.label('mo_ty'); a.lda_lx(0); a.fix.append(('long', len(a.code) - 3, 'types'))
    a.imm(0xC9, 0xFFFF); a.rel(0xF0, 'mo_n1'); a.cmp_l(CT); a.rel(0xF0, 'mo_t'); a.b(0xE8, 0xE8); a.bra('mo_ty')
    a.label('mo_n1'); a.brl('mo_next')
    a.label('mo_t')
    a.b(0xBE); a.w(0x13C4); a.rel(0xF0, 'mo_n1')                               # LDX $13C4,Y: record
    a.lda_lx(0x7E0003); a.imm(0xC9, 0xFFFF); a.rel(0xD0, 'mo_n1')              # alive
    a.lda_lx(0x7E0002); a.imm(0x29, 0xFF); a.rel(0xF0, 'mo_n1')                # with health
    a.b(0x8A); a.sta_l(CO)
    a.b(0x5A); a.imm(0xA9, 100); a.b(0x85, 0x00); a.call80(0x80C4F3); a.b(0x7A)   # roll
    a.b(0xA5, 0x00); a.cmp_l(PCT); a.rel(0xB0, 'mo_n1')
    a.lda_l(NPEND); a.imm(0xC9, MAXP); a.rel(0xB0, 'mo_x2')
    # entry address X = NPEND * 12
    a.lda_l(NPEND); a.b(0x0A, 0x0A); a.sta_l(TMPN); a.b(0x0A, 0x18); a.adc_l(TMPN); a.b(0xAA)
    a.lda_l(CT); a.sta_lx(PEND + 0)
    a.b(0xB9); a.w(0x0E44); a.sta_lx(PEND + 2)
    a.b(0xB9); a.w(0x0E9C); a.sta_lx(PEND + 4)
    a.b(0xB9); a.w(0x0EF4); a.sta_lx(PEND + 6)
    a.b(0xDA); a.lda_l(CO); a.b(0xAA); a.lda_lx(0x7E0000); a.sta_l(TMPN); a.lda_lx(0x7E0001); a.b(0xFA)
    a.sta_lx(PEND + 9); a.lda_l(TMPN); a.sta_lx(PEND + 8)                      # record bytes 0-2
    a.lda_l(NPEND); a.b(0x1A); a.sta_l(NPEND)
    a.label('mo_next'); a.b(0xC8, 0xC8); a.b(0xC0); a.w(0x58); a.rel(0xB0, 'mo_x2'); a.brl('mo_loop')
    a.label('mo_x2')
    a.b(0x8B); a.imm(0xA2, DPSAVE & 0xFFFF); a.imm(0xA0, 0); a.imm(0xA9, 63); a.b(0x54, 0x7E, 0x7F); a.b(0xAB)
    a.label('mo_exit'); a.b(0x28, 0x6B)                                        # plp; rtl

    # --- main loop (JSL from $80963D, replaces JSR $BE3D / JSR $BF0B): bring in the next queued reinforcement when
    #     the game has room for it (free threads / objects, few reinforcements alive, not already slowed down),
    #     checking every 64 main-loop passes.
    a.label('director')
    a.call80(0x80BE3D); a.call80(0x80BF0B)
    a.b(0x08, 0xC2, 0x30)
    a.lda_l(PIDX); a.cmp_l(NPEND); a.rel(0x90, 'dr_1'); a.brl('dr_out')
    a.label('dr_1')
    a.lda_l(FRM); a.b(0x1A); a.sta_l(FRM); a.imm(0x29, EVERY); a.rel(0xF0, 'dr_2'); a.brl('dr_out')
    a.label('dr_2')
    a.lda_l(0x7E1C92); a.b(0x38); a.b(0xEF); a.l(LASTN); a.sta_l(TMPN)        # frames since the last check ($1C92 = NMI count)
    a.lda_l(0x7E1C92); a.sta_l(LASTN)
    a.lda_l(TMPN); a.imm(0xC9, MAX_LAG + 1); a.rel(0x90, 'dr_2b'); a.brl('dr_out')   # game already slowed down: wait
    a.label('dr_2b')
    a.b(0xAE); a.w(0x026A); a.imm(0xA0, 0)                                     # free threads: walk the free list
    a.label('dr_th'); a.b(0x8A); a.rel(0x30, 'dr_th2'); a.b(0xC8); a.b(0xBD); a.w(0x032E); a.b(0xAA)
    a.b(0xC0); a.w(60); a.rel(0x90, 'dr_th')
    a.label('dr_th2'); a.b(0xC0); a.w(MIN_THREADS); a.rel(0xB0, 'dr_3'); a.brl('dr_out')
    a.label('dr_3')
    a.imm(0xA2, 0x56); a.imm(0xA0, 0)                                          # free objects + live reinforcements
    a.imm(0xA9, 0); a.sta_l(TMPQ)
    a.label('dr_ob'); a.lda_lx(0x7E3F04); a.rel(0x10, 'dr_used'); a.b(0xC8); a.bra('dr_obn')
    a.label('dr_used'); a.b(0xBD); a.w(0x13C4); a.b(0xC9); a.w(POOL); a.rel(0x90, 'dr_obn')
    a.b(0xC9); a.w(POOL + 5 * MAXP); a.rel(0xB0, 'dr_obn')
    a.b(0xDA); a.b(0xAA); a.lda_lx(0x7E0003); a.b(0xFA); a.imm(0xC9, 0xFFFF); a.rel(0xD0, 'dr_obn')
    a.lda_l(TMPQ); a.b(0x1A); a.sta_l(TMPQ)
    a.label('dr_obn'); a.b(0xCA, 0xCA); a.rel(0x10, 'dr_ob')
    a.b(0xC0); a.w(MIN_OBJECTS); a.rel(0xB0, 'dr_4'); a.brl('dr_out')
    a.label('dr_4'); a.lda_l(TMPQ); a.imm(0xC9, MAX_LIVE); a.rel(0x90, 'dr_5'); a.brl('dr_out')
    a.label('dr_5')
    a.b(0x8B); a.imm(0xA2, 0); a.imm(0xA0, DPSAVE & 0xFFFF); a.imm(0xA9, 63); a.b(0x54, 0x7F, 0x7E); a.b(0xAB)
    a.lda_l(PIDX); a.b(0x0A, 0x0A); a.sta_l(TMPN); a.b(0x0A, 0x18); a.adc_l(TMPN); a.b(0xAA); a.b(0x8A); a.sta_l(CO)   # entry
    a.lda_l(PIDX); a.b(0x0A, 0x0A, 0x18); a.adc_l(PIDX); a.b(0x18); a.imm(0x69, POOL); a.sta_l(CR)    # record = POOL + 5k
    # write private record: bytes 0-2 from the entry, owner $FFFF
    a.lda_l(CO); a.b(0xAA); a.lda_lx(PEND + 8); a.sta_l(TMPN); a.lda_lx(PEND + 9); a.sta_l(TMPQ)
    a.lda_l(CR); a.b(0xAA); a.lda_l(TMPN); a.sta_lx(0x7E0000); a.lda_l(TMPQ); a.sta_lx(0x7E0001)
    a.imm(0xA9, 0xFFFF); a.sta_lx(0x7E0003)
    # create the object at the guard's spot
    a.lda_l(CO); a.b(0xAA)
    a.lda_lx(PEND + 0); a.sta_l(CT)
    a.lda_lx(PEND + 2); a.sta_l(BXV); a.b(0x4A, 0x4A, 0x85, 0x02)
    a.lda_lx(PEND + 4); a.sta_l(BYV); a.b(0x4A, 0x4A, 0x85, 0x04)
    a.lda_lx(PEND + 6); a.b(0x4A, 0x4A, 0x85, 0x06)
    a.lda_l(CT); a.b(0xAA); a.lda_lx(0x8DB034); a.b(0x85, 0x00); a.lda_lx(0x8DB036); a.b(0x85, 0x08)
    a.call80(0x80A7C2)
    a.b(0xA6, 0x00)                                                            # X = new object
    a.lda_l(CT); a.b(0x9D); a.w(0x1526)
    a.b(0xDA); a.b(0xAA); a.lda_lx(0x8DB031); a.b(0xFA); a.imm(0x29, 0xC0); a.b(0xEB, 0x0A); a.imm(0x69, 0)
    a.b(0x9D); a.w(0x141C)
    a.lda_l(CR); a.b(0x9D); a.w(0x13C4)
    # step aside from the spot (the guard may still stand there): first side the game's wall test allows
    for k, (dx, dy, test) in enumerate(((SPREAD, 0, 0x8080B2), (-SPREAD, 0, 0x808133), (0, SPREAD, 0x8081B4), (0, -SPREAD, 0x808238))):
        a.lda_l(BXV); a.b(0x18); a.imm(0x69, (dx * 4) & 0xFFFF); a.b(0x9D); a.w(0x0E44)
        a.lda_l(BYV); a.b(0x18); a.imm(0x69, (dy * 4) & 0xFFFF); a.b(0x9D); a.w(0x0E9C)
        a.b(0xDA); a.call80(test); a.b(0xFA)
        a.rel(0xB0, 'dr_k%d' % k); a.imm(0xC9, 5); a.rel(0xB0, 'dr_s%d' % k)
        a.label('dr_k%d' % k); a.brl('dr_ok')
        a.label('dr_s%d' % k)
    a.lda_l(BXV); a.b(0x9D); a.w(0x0E44); a.lda_l(BYV); a.b(0x9D); a.w(0x0E9C)  # boxed in: stay on the spot
    a.label('dr_ok')
    a.b(0xBD); a.w(0x0E44); a.b(0x18); a.b(0x7D); a.w(0x0E9C); a.b(0x4A); a.b(0x9D); a.w(0x0F4C)   # depth
    a.lda_l(PIDX); a.b(0x1A); a.sta_l(PIDX)
    a.b(0x8B); a.imm(0xA2, DPSAVE & 0xFFFF); a.imm(0xA0, 0); a.imm(0xA9, 63); a.b(0x54, 0x7E, 0x7F); a.b(0xAB)
    a.label('dr_out'); a.b(0x28, 0x6B)
    a.label('locs')
    for l in GUARD_LOCS: a.w(l)
    a.w(0xFFFF)
    a.label('types')
    for t in GUARD_TYPES: a.w(t)
    a.w(0xFFFF)
    return a.done(), a.labels


def patch(rom):
    rom = bytearray(rom)
    if len(rom) < 0x200000: rom += b'\x00' * (0x200000 - len(rom))
    code, L = build_code()
    o = lorom(CODE); assert all(b == 0 for b in rom[o:o + len(code)]), 'code area not free'
    rom[o:o + len(code)] = code
    def put(addr, old, new):
        f = lorom(addr); assert rom[f:f + len(old)] == old, (hex(addr), rom[f:f + len(old)].hex()); rom[f:f + len(new)] = new
    jsl = lambda t: bytes([0x22, t & 0xFF, (t >> 8) & 0xFF, t >> 16])
    assert rom[lorom(RTL80)] == 0x6B and rom[lorom(RTS80)] == 0x60
    put(0x80C4EF, bytes.fromhex('A500F01C'), jsl(L['rand']))
    put(0x80CBD7, bytes.fromhex('A600BFBB3B7E'), jsl(L['getvar']) + b'\xEA\xEA')
    put(0x80A4D8, bytes.fromhex('2087A22043A3'), jsl(L['mapobj']) + b'\xEA\xEA')
    put(0x80963D, bytes.fromhex('203DBE200BBF'), jsl(L['director']) + b'\xEA\xEA')
    rom[0x7FD7] = 0x0B
    rom[0x7FDC:0x7FE0] = b'\xFF\xFF\x00\x00'; s = sum(rom) & 0xFFFF
    rom[0x7FDC:0x7FDE] = (s ^ 0xFFFF).to_bytes(2, 'little'); rom[0x7FDE:0x7FE0] = s.to_bytes(2, 'little')
    return bytes(rom)


if __name__ == '__main__':
    src = open(sys.argv[1], 'rb').read(); out = sys.argv[2]
    new = patch(src)
    open(out + '.sfc', 'wb').write(new); open(out + '.ips', 'wb').write(make_ips(src, new))
    print('code', len(build_code()[0]), 'bytes; ROM CRC32 %08X' % zlib.crc32(new))
