"""Build "Shadowrun: Arena Leagues + Glutman's Jobs" (standalone; stacks with the Runner Pack parts, Rebalanced and
Expanded Dialogue). Glutman's jobs live in build_jobs.py and share this module's hooks; see that file.

  python3 build_arena.py IN_ROM OUT_PREFIX      (IN_ROM: clean 1 MB ROM, or any 2 MB patched ROM)

Vanilla arena (The Cage): the manager (object $1B66, script $01E4) offers ten fights; game var 4 counts the fights
won and script $0299 pays 300..8,000 nuyen. After fight 10 the manager only says "No more fighters left".

This patch adds two more rounds of the same ten fights:
  * After the 10th amateur fight the manager says to come back in a few days (when you talk to him). Sleep SLEEPS
    time(s) in any bed and the PRO LEAGUE starts: every fighter brings 1 extra copy of himself, prizes x2.
  * Finish that, sleep again: ELITE LEAGUE, 2 extra copies, prizes x3. After the elite league the arena is done.
  * A fight is won when the fighter and all copies are down (the copies use the fighter's own AI and give karma).

How (all hooks are on bank-$80 natives, nothing in the script banks is changed):
  native #98 (pay)      : from script $0299 the amount is multiplied by league+1; the 10th prize arms the countdown
  native #99/#D6 (text) : new texts for the prize amounts, the manager's 'no more fighters' (+ arms the countdown)
                          and the fight offer; encoded with the game's own Huffman tree, stored in bank $BE
  native #3C (rest menu): only bed sleeping uses it; counts sleeps and starts the next league (resets var 4,
                          clears the manager's 'champion' flag, revives the ten fighters' records)
  native #9F (set HP)   : when an arena fighter appears in the ring ($02C), spawns the copies next to him
  native #56 (warp)     : the warp back to the office ($0AE) waits until no arena fighter is left in the combat list
  script directory      : ids >= 936 come from our own table (the copies' scripts), at $80C298 and $80F433
State: league $7E3BF3, countdown $7E3BF4 (inside the saved block, never used by the game; zero in old saves).
Jobs add hooks at $809123 (conversation topic) and $80A4DE (map load), and texts/scripts after the arena's.
"""
import sys, zlib, os
from build_runners import Asm, lorom, make_ips
import build_jobs as J

CODE = 0xBE8000
SLEEPS = 1                                 # sleeps after the manager's 'come back in a few days' before a new league
SPREAD = 16                                # a copy stands this far from the fighter (first free side)
LEAGUE, WAITC = 0x7E3BF3, 0x7E3BF4
DPS = 0x7F6780                             # 64-byte copy of direct page $00-$3F around our object creation
TMP, KIDX, CNT, CK, BX, BY, BZ, CREC, CTY, C7F, C7P = (0x7F6800 + 2 * i for i in range(11))
POOL = 0x2340                              # private 5-byte records for the copies ($7E2340..), unsaved
MGR, MGR_REC = 0x1B66, 0x3AB7
VAR4 = 0x7E3BBB + 4
LOC_RING, LOC_OFFICE = 0x02C, 0x0AE
NSCRIPTS = 936
TYPES = [0x1267, 0x0CE8, 0x0D43, 0x0A5D, 0x0AE2, 0x0620, 0x137F, 0x1283, 0x01F1, 0x0A95]   # fights 1..10 (var 4 = 0..9)
PRIZES = [300, 700, 1000, 2000, 3000, 4000, 5000, 6000, 7000, 8000]
CLEAN = open(os.environ.get('SR_CLEAN', os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'shadowrun.sfc')), 'rb').read()
RTS_WARP = 0x80CC73                         # the RTS of native #56
RTL80 = 0x80F261


def RB(a): return CLEAN[lorom(a)]
def RW(a): return CLEAN[lorom(a)] | CLEAN[lorom(a) + 1] << 8
def snes(off): return 0x800000 | ((off >> 15) << 16) | 0x8000 | (off & 0x7FFF)
def script_file(sid): return lorom((RB(0x82D970 + sid) << 16) | RW(0x82DD18 + 2 * sid))


# ---------------- text: the game's Huffman code (tree at $9D8000, decoder $80FE44) ----------------
def _leaves():
    out = {}
    def walk(x, path):
        for b in (0, 1):
            w = RW(0x9D8000 + x + 2 * b)
            if w & 0x8000:
                w &= 0x7F7F; s = bytes([w >> 8]) + (bytes([w & 0xFF]) if w & 0xFF else b'')
                out.setdefault(s, path + [b])
            else: walk(w, path + [b])
    walk(0, []); return out
LEAVES = _leaves()


def encode(s):
    s = s.encode('latin1') + b'\n'; INF = 1 << 30
    best = [INF] * (len(s) + 1); prv = [None] * (len(s) + 1); best[0] = 0
    for i in range(len(s)):
        if best[i] == INF: continue
        for k in (1, 2):
            t = s[i:i + k]
            if len(t) == k and t in LEAVES and best[i] + len(LEAVES[t]) < best[i + k]:
                best[i + k] = best[i] + len(LEAVES[t]); prv[i + k] = (i, t)
    assert best[-1] < INF, 'character not in the game font/tree: %r' % s
    toks = []; i = len(s)
    while i: j, t = prv[i]; toks.append(t); i = j
    bits = [b for t in reversed(toks) for b in LEAVES[t]]; bits += [0] * (-len(bits) % 16)
    return bytes(int(''.join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8))


def decode(blob):
    """check helper: decode like $80FE44 from bytes"""
    pos = 0; out = []
    def bit():
        nonlocal pos
        b = (blob[pos >> 3] >> (7 - (pos & 7))) & 1; pos += 1; return b
    while True:
        x = 0
        while True:
            if bit(): x += 2
            w = RW(0x9D8000 + x)
            if w & 0x8000: break
            x = w
        w &= 0x7F7F
        for c in (w >> 8, w & 0xFF):
            if c == 0x0A: return ''.join(out)
            if c: out.append(chr(c))


def money(v): return '{:,}'.format(v)
TEXT_COMEBACK = ["No more fighters left. You is one tough dude! Come back in few days. Then pro league start: "
                 "fighters come in pairs, you get double nuyen!",
                 "No more fighters left. You is real pro! Come back in few days. Then elite league start: "
                 "three fighters at once, triple nuyen!"]
TEXT_FLOAT = ["No more fighters, chummer. Come back in few days: pro league! Double fighters, double nuyen!",
              "No more fighters, chummer. Come back in few days: elite league! Triple fighters, triple nuyen!"]
TEXT_OFFER = ["Pro league now! Fighters come two at once. You get double nuyen. You fight for crowds, yes? What say?",
              "Elite league! Three fighters at once, triple nuyen. Crowds go crazy! What say?"]


# ---------------- the copies' scripts ----------------
def fighter(t):
    """pieces of the fighter's own script: HP, AI call, lose path?, karma"""
    sid = RW(0x8DB036 + t); o = script_file(sid); code = o + 2; b = CLEAN[code:code + 400]
    i9f = b.find(b'\xc2\x58\x9f'); assert b[i9f - 2] == 0; hp = b[i9f - 1]
    iab = b.find(b'\xc2\x58\xab', i9f)
    s = iab + 3 if 0 <= iab < 60 else None
    if s is None:                                       # no ADD_COMBATANT ($01F1): AI call follows the HP / waits
        s = i9f + 3
        while b[s] == 0x00 and b[s + 2] == 0x00 and b[s + 4:s + 7] == b'\x58\x9e\xbc': s += 7
    j = s
    while b[j] != 0x52: j += {0x00: 2, 0x14: 3, 0x0A: 2, 0xC2: 1, 0xC0: 1, 0x80: 1, 0x58: 2}[b[j]]
    ai = b[s:j + 3]
    lose = b[j + 3] == 0x44
    k = b.find(b'\x58\x7b', j); karma = b[k - 1] if 0 <= k < j + 40 and b[k - 2] == 0 else None
    return dict(sid=sid, hdr=CLEAN[o:o + 2], hp=hp, ai=ai, lose=lose, karma=karma)


def copy_script(t):
    f = fighter(t)
    sid = f['sid']; o = script_file(sid) + 2; orig = CLEAN[o:o + 400]
    own = 0 <= orig.find(b'\xc2\x58\xab') < 60         # the fighter handles combat list / death itself? ($01F1 does not)
    s = bytearray(f['hdr'])
    c = bytearray()                                     # code; jump operands are offsets from the code start
    c += b'\x2c\x00'                                    # pop.lb 0 (self)
    c += bytes([0x00, f['hp'], 0xC2, 0x58, 0x9F])       # set HP (record of the copy)
    c += b'\x00\x1e\x00\x01\x58\x9e\xbc'                # wait 30 frames
    if own: c += b'\xc2\x58\xab'                        # ADD_COMBATANT
    c += f['ai']                                        # the fighter's own AI, same arguments
    fix = []
    if f['lose']:
        c += b'\x44\x00\x00'; fix.append((len(c) - 2, 'died'))      # jz died
        c += b'\x0a\xfe\x14' + MGR.to_bytes(2, 'little') + b'\x58\x4b'   # manager flags &= ~1 (no win)
        c += b'\x00\x02\x14' + MGR.to_bytes(2, 'little') + b'\x58\x0d'   # manager flags |= 2 (lost)
        c += b'\x48\x00\x00'; fix.append((len(c) - 2, 'warp'))
    elif RB(0x82E468 + int.from_bytes(f['ai'][-2:], 'little')):   # AI script returns a value ($82E468 flags)
        c += b'\xbc'                                    # drop it
    lab = {'died': len(c)}
    if own:
        if f['karma'] is not None: c += bytes([0x00, f['karma'], 0x58, 0x7B])
        c += b'\xc2\x58\xbf'                            # REMOVE_COMBATANT
        c += b'\xc2\x52\x5c\x03\xbc'                    # death (script $035C)
    c += b'\x00\x64\x00\x01\x58\x9e\xbc'                # wait 100
    lab['warp'] = len(c)
    c += bytes([0x00, LOC_OFFICE, 0x58, 0x56])          # warp to the office (held while fighters are left)
    c += b'\x56'
    for at, l in fix: c[at:at + 2] = lab[l].to_bytes(2, 'little')
    return bytes(s + c)


def build_code():
    a = Asm(CODE)
    nl = len(TYPES)

    # ---- helper: Z set if the running script thread's code start is bank $9F : A ----
    a.label('inctx')
    a.sta_l(TMP)
    a.lda_l(0x7E026C); a.b(0xAA); a.lda_lx(0x7E026E); a.b(0xAA)
    a.lda_lx(0x7E0002); a.imm(0x29, 0xFF); a.imm(0xC9, 0x9F); a.rel(0xD0, 'ic_out')
    a.lda_lx(0x7E0000); a.cmp_l(TMP)
    a.label('ic_out'); a.b(0x60)
    # ---- helper: A = index of type A in TYPES, carry clear if found ----
    a.label('typeidx')
    a.sta_l(TMP); a.imm(0xA2, 0)
    a.label('ti_lp'); a.lda_lx(0); a.fix.append(('long', len(a.code) - 3, 'types'))
    a.cmp_l(TMP); a.rel(0xF0, 'ti_hit'); a.b(0xE8, 0xE8); a.b(0xE0); a.w(2 * nl); a.rel(0x90, 'ti_lp')
    a.b(0x38, 0x60)
    a.label('ti_hit'); a.b(0x8A, 0x4A, 0x18, 0x60)

    # ---- native #98 pay (JSL from $80CCAB, replaces CLC / LDA $7E3C0D): prizes x (league+1) in script $0299 ----
    a.label('pay')
    a.imm(0xA9, snes(script_file(0x299) + 2) & 0xFFFF); a.jsr('inctx'); a.rel(0xD0, 'py_out')
    a.lda_l(VAR4); a.imm(0xC9, 9); a.rel(0xD0, 'py_n10')                      # 10th prize: start the countdown
    a.b(0xE2, 0x20); a.lda_l(LEAGUE); a.b(0xC9, 2); a.rel(0xB0, 'py_n9')
    a.lda_l(WAITC); a.rel(0xD0, 'py_n9'); a.b(0xA9, 1); a.sta_l(WAITC)
    a.label('py_n9'); a.b(0xC2, 0x20)
    a.label('py_n10')
    a.lda_l(LEAGUE); a.imm(0x29, 0xFF); a.rel(0xF0, 'py_out'); a.b(0xAA)
    a.b(0xA5, 0x00); a.sta_l(TMP)
    a.label('py_mul'); a.b(0x18); a.b(0xA5, 0x00); a.adc_l(TMP); a.b(0x85, 0x00); a.b(0xCA); a.rel(0xD0, 'py_mul')
    a.label('py_out'); a.b(0x18); a.lda_l(0x7E3C0D); a.b(0x6B)

    # ---- text natives #99 / #D6 (A = message index). Out: $02 = text id, $00 = $14; carry set = our text,
    #      pointer already in $CF/$D1 (caller then does PHB / JMP $FE44) ----
    a.label('text')
    a.sta_l(CNT)
    a.imm(0xC9, 0x0F00); a.rel(0x90, 'tx_std')                               # our texts: message $0F00 + n
    a.b(0xA5, 0x14, 0x85, 0x00); a.lda_l(CNT); a.b(0x38); a.imm(0xE9, 0x0F00); a.brl('tx_ptr')
    a.label('tx_std'); a.lda_l(CNT)
    a.b(0x0A, 0xAA); a.lda_lx(0x80D980); a.b(0x85, 0x02); a.b(0xA5, 0x14, 0x85, 0x00)
    a.lda_l(CNT); a.imm(0xC9, 0xD4); a.rel(0x90, 'tx_n1'); a.imm(0xC9, 0xD4 + 10); a.rel(0xB0, 'tx_n1')
    # prize amount (script $0299, league 1/2)
    a.lda_l(LEAGUE); a.imm(0x29, 0xFF); a.rel(0xF0, 'tx_no')
    a.imm(0xA9, snes(script_file(0x299) + 2) & 0xFFFF); a.jsr('inctx'); a.rel(0xD0, 'tx_no')
    a.lda_l(LEAGUE); a.imm(0x29, 0xFF); a.b(0x3A); a.sta_l(TMP); a.b(0x0A, 0x0A, 0x18); a.adc_l(TMP)   # (L-1)*5
    a.b(0x0A); a.b(0x18); a.adc_l(CNT); a.b(0x38); a.imm(0xE9, 0xD4)       # (L-1)*10 + idx-D4
    a.brl('tx_ptr')
    a.label('tx_no'); a.b(0x18, 0x6B)
    a.label('tx_n1')
    a.lda_l(CNT); a.imm(0xC9, 0xE1); a.rel(0xF0, 'tx_e1'); a.imm(0xC9, 0xE0); a.rel(0xD0, 'tx_no')
    # fight offer (script $0118, league 1/2): texts 22/23
    a.lda_l(LEAGUE); a.imm(0x29, 0xFF); a.rel(0xF0, 'tx_no')
    a.imm(0xA9, snes(script_file(0x118) + 2) & 0xFFFF); a.jsr('inctx'); a.rel(0xD0, 'tx_no')
    a.lda_l(LEAGUE); a.imm(0x29, 0xFF); a.b(0x18); a.imm(0x69, 21); a.bra('tx_ptr')
    a.label('tx_e1')
    # 'no more fighters' (script $0118): league 0/1 -> 'come back in a few days' (texts 20/21), arms the countdown
    a.lda_l(LEAGUE); a.imm(0x29, 0xFF); a.imm(0xC9, 2); a.rel(0xB0, 'tx_no')
    a.imm(0xA9, snes(script_file(0x118) + 2) & 0xFFFF); a.jsr('inctx'); a.rel(0xD0, 'tx_no')
    a.b(0xE2, 0x20); a.lda_l(WAITC); a.rel(0xD0, 'tx_arm'); a.b(0xA9, 1); a.sta_l(WAITC)
    a.label('tx_arm'); a.b(0xC2, 0x20)
    a.lda_l(LEAGUE); a.imm(0x29, 0xFF); a.b(0x18); a.imm(0x69, 20)
    a.label('tx_ptr')                                                          # A = our text number
    a.b(0x0A, 0xAA); a.lda_lx(0); a.fix.append(('long', len(a.code) - 3, 'tptr'))
    a.b(0x85, 0xCF); a.b(0xE2, 0x20); a.b(0xA9, CODE >> 16); a.b(0x85, 0xD1); a.b(0xC2, 0x20)
    a.b(0x38, 0x6B)

    # ---- native #3C rest menu (JSL from $80CE3D, replaces LDA #$000A / STA $00): sleeping counts down ----
    a.label('sleep')
    a.jsr('jobsleep')
    a.b(0xE2, 0x20)
    a.lda_l(LEAGUE); a.b(0xC9, 2); a.rel(0xB0, 'sl_out8')                   # elite done: nothing more
    a.lda_l(VAR4); a.b(0xC9, 10); a.rel(0x90, 'sl_out8')                      # all ten fights won
    a.lda_l(0x7E0000 + MGR_REC + 1); a.rel(0x10, 'sl_out8')                   # and champion (flag $80)
    a.lda_l(WAITC); a.rel(0xD0, 'sl_armed'); a.b(0x1A)                         # not armed yet (old save): arm now
    a.label('sl_armed')
    a.b(0x1A); a.sta_l(WAITC); a.b(0xC9, SLEEPS + 1); a.rel(0xB0, 'sl_go')
    a.label('sl_out8'); a.b(0xC2, 0x20); a.brl('sl_out')
    a.label('sl_go')                                                           # next league
    a.b(0xA9, 0); a.sta_l(WAITC)
    a.lda_l(LEAGUE); a.b(0x1A); a.sta_l(LEAGUE)
    a.lda_l(0x7E0000 + MGR_REC + 1); a.b(0x29, 0x7F); a.sta_l(0x7E0000 + MGR_REC + 1)   # not champion any more
    a.b(0xC2, 0x20)
    a.imm(0xA9, 0); a.sta_l(VAR4)                                              # fights won = 0
    a.imm(0xA0, 0)
    a.label('sl_rv')                                                           # revive the ten fighters' records
    a.b(0xBB); a.lda_lx(0); a.fix.append(('long', len(a.code) - 3, 'types'))   # tyx; lda types,X
    a.b(0xAA); a.lda_lx(0x8DB032); a.b(0xAA)
    a.imm(0xA9, 0); a.sta_lx(0x7E0000)                                         # flags 0 / 0
    a.b(0xDA); a.b(0xBB); a.lda_lx(0); a.fix.append(('long', len(a.code) - 3, 'hps')); a.b(0xFA)
    a.b(0xE2, 0x20); a.sta_lx(0x7E0002); a.b(0xC2, 0x20)                      # health
    a.imm(0xA9, 0xFFFF); a.sta_lx(0x7E0003)                                    # owner: none (back in the ring)
    a.b(0xC8, 0xC8); a.b(0xC0); a.w(2 * nl); a.rel(0x90, 'sl_rv')
    a.label('sl_out'); a.imm(0xA9, 0x000A); a.b(0x85, 0x00); a.b(0x6B)

    # ---- native #9F set HP (JSL from $80CAB0, replaces LDY $00 / LDX $13C4,Y): an arena fighter appearing in
    #      the ring in league 1/2 gets 1/2 copies ----
    a.label('sethp')
    a.b(0x08, 0xC2, 0x30)
    a.lda_l(LEAGUE); a.imm(0x29, 0xFF); a.rel(0xF0, 'hp_x1')
    a.lda_l(0x7E2DE2); a.imm(0xC9, LOC_RING); a.rel(0xD0, 'hp_x1')
    a.b(0xA4, 0x00); a.b(0xB9); a.w(0x1526); a.jsr('typeidx'); a.rel(0xB0, 'hp_x1')
    a.sta_l(KIDX)
    a.b(0xB9); a.w(0x1526); a.sta_l(CTY); a.b(0xAA); a.lda_lx(0x8DB032)        # the original (ROM record) only
    a.b(0xD9); a.w(0x13C4); a.rel(0xF0, 'hp_go')
    a.label('hp_x1'); a.brl('hp_out')
    a.label('hp_go')
    a.b(0xB9); a.w(0x0E44); a.sta_l(BX); a.b(0xB9); a.w(0x0E9C); a.sta_l(BY); a.b(0xB9); a.w(0x0EF4); a.sta_l(BZ)
    a.b(0x8B); a.imm(0xA2, 0); a.imm(0xA0, DPS & 0xFFFF); a.imm(0xA9, 63); a.b(0x54, DPS >> 16, 0x7E); a.b(0xAB)
    a.imm(0xA9, 0); a.sta_l(CK)
    a.label('hp_cl')
    # private record POOL + 5k: 00 00 HP FF FF
    a.lda_l(CK); a.b(0x0A, 0x0A, 0x18); a.adc_l(CK); a.b(0x18); a.imm(0x69, POOL); a.sta_l(CREC); a.b(0xAA)
    a.imm(0xA9, 0); a.sta_lx(0x7E0000); a.imm(0xA9, 0xFFFF); a.sta_lx(0x7E0003)
    a.b(0xDA); a.lda_l(KIDX); a.b(0x0A, 0xAA); a.lda_lx(0); a.fix.append(('long', len(a.code) - 3, 'hps')); a.b(0xFA)
    a.b(0xE2, 0x20); a.sta_lx(0x7E0002); a.b(0xC2, 0x20)
    # create the object on the fighter's spot, script = our copy script (936 + fight)
    a.lda_l(BX); a.b(0x4A, 0x4A, 0x85, 0x02); a.lda_l(BY); a.b(0x4A, 0x4A, 0x85, 0x04); a.lda_l(BZ); a.b(0x4A, 0x4A, 0x85, 0x06)
    a.lda_l(CTY); a.b(0xAA); a.lda_lx(0x8DB034); a.b(0x85, 0x00)
    a.lda_l(KIDX); a.b(0x18); a.imm(0x69, NSCRIPTS); a.b(0x85, 0x08)
    a.call80(0x80A7C2)
    a.b(0x8A); a.rel(0x10, 'hp_ok1'); a.brl('hp_done')                        # no free object slot
    a.label('hp_ok1')
    a.b(0xA6, 0x00)
    a.lda_l(CTY); a.b(0x9D); a.w(0x1526)
    a.b(0xDA); a.b(0xAA); a.lda_lx(0x8DB031); a.b(0xFA); a.imm(0x29, 0xC0); a.b(0xEB, 0x0A); a.imm(0x69, 0)
    a.b(0x9D); a.w(0x141C)
    a.lda_l(CREC); a.b(0x9D); a.w(0x13C4)
    # step aside: first side the wall test allows (copy 2 starts on the opposite side)
    dirs = ((SPREAD, 0, 0x8080B2), (-SPREAD, 0, 0x808133), (0, SPREAD, 0x8081B4), (0, -SPREAD, 0x808238))
    for c in range(2):
        a.label('hp_c%d' % c)
        if c == 0:
            a.lda_l(CK); a.rel(0xF0, 'hp_c0b'); a.brl('hp_c1')
            a.label('hp_c0b')
        order = (0, 2, 1, 3) if c == 0 else (1, 3, 0, 2)
        for k in order:
            dx, dy, test = dirs[k]; t = 'hp_%d_%d' % (c, k)
            a.lda_l(BX); a.b(0x18); a.imm(0x69, (dx * 4) & 0xFFFF); a.b(0x9D); a.w(0x0E44)
            a.lda_l(BY); a.b(0x18); a.imm(0x69, (dy * 4) & 0xFFFF); a.b(0x9D); a.w(0x0E9C)
            a.b(0xDA); a.call80(test); a.b(0xFA)
            a.rel(0xB0, t + 'k'); a.imm(0xC9, 5); a.rel(0xB0, t + 's')
            a.label(t + 'k'); a.brl('hp_pl')
            a.label(t + 's')
        a.lda_l(BX); a.b(0x9D); a.w(0x0E44); a.lda_l(BY); a.b(0x9D); a.w(0x0E9C)
        a.brl('hp_pl')
    a.label('hp_pl')
    a.b(0xBD); a.w(0x0E44); a.b(0x18); a.b(0x7D); a.w(0x0E9C); a.b(0x4A); a.b(0x9D); a.w(0x0F4C)   # depth
    a.lda_l(CK); a.b(0x1A); a.sta_l(CK)
    a.lda_l(LEAGUE); a.imm(0x29, 0xFF); a.cmp_l(CK); a.rel(0xF0, 'hp_done'); a.rel(0x90, 'hp_done'); a.brl('hp_cl')
    a.label('hp_done')
    a.b(0x8B); a.imm(0xA2, DPS & 0xFFFF); a.imm(0xA0, 0); a.imm(0xA9, 63); a.b(0x54, 0x7E, DPS >> 16); a.b(0xAB)
    a.label('hp_out'); a.b(0x28)
    a.b(0xA4, 0x00); a.b(0xBE); a.w(0x13C4); a.b(0x6B)

    # ---- native #56 warp (JSL from $80CC67, replaces LDA $00 / STA $7E2DE2): ring -> office waits for the
    #      last arena fighter (unless the manager's 'lost' flag is set) ----
    a.label('warp')
    # going into the ring: the fighter for this fight (var 4) must be in it. A fight lost after the original
    # fighter went down (his copies won) leaves his record 'gone' -> the rematch would have nobody to fight.
    a.b(0x08, 0xC2, 0x30)                                                      # php / rep #$30
    a.b(0xA5, 0x00); a.imm(0xC9, LOC_RING); a.rel(0xD0, 'wp_nr')
    a.lda_l(VAR4); a.imm(0xC9, len(TYPES)); a.rel(0xB0, 'wp_nr')
    a.b(0x0A, 0xAA); a.b(0xDA); a.lda_lx(0); a.fix.append(('long', len(a.code) - 3, 'types'))
    a.b(0xAA); a.lda_lx(0x8DB032); a.b(0xAA)
    a.lda_lx(0x7E0003); a.imm(0xC9, 0x1538); a.rel(0xD0, 'wp_alive')
    a.imm(0xA9, 0xFFFF); a.sta_lx(0x7E0003)                                    # back in the ring
    a.b(0x7A); a.b(0xDA); a.b(0xBB); a.lda_lx(0); a.fix.append(('long', len(a.code) - 3, 'hps')); a.b(0xFA)   # ply/phx/tyx
    a.b(0xE2, 0x20); a.sta_lx(0x7E0002); a.b(0xC2, 0x20); a.b(0x5A)            # full health
    a.label('wp_alive'); a.b(0xFA)
    a.label('wp_nr'); a.b(0x28)                                                # plp
    a.b(0xA5, 0x00); a.imm(0xC9, LOC_OFFICE); a.rel(0xD0, 'wp_go')
    a.lda_l(0x7E2DE2); a.imm(0xC9, LOC_RING); a.rel(0xD0, 'wp_go')
    a.lda_l(0x7E0000 + MGR_REC + 1); a.imm(0x29, 2); a.rel(0xD0, 'wp_go')
    a.b(0xAE); a.w(0x1FCC); a.rel(0x30, 'wp_go')
    a.label('wp_lp')
    a.b(0xDA); a.b(0xBD); a.w(0x1FCE); a.b(0xA8); a.b(0xB9); a.w(0x1526); a.jsr('typeidx'); a.b(0xFA)
    a.rel(0x90, 'wp_hold')
    a.b(0xCA, 0xCA); a.rel(0x10, 'wp_lp')
    a.label('wp_go'); a.b(0xA5, 0x00); a.sta_l(0x7E2DE2); a.b(0x6B)
    a.label('wp_hold')                                                         # leave native #56 untouched
    a.b(0xE2, 0x20, 0x68, 0x68, 0x68, 0xC2, 0x20); a.b(0x5C); a.l(RTS_WARP)

    # ---- native #C7 floating message. Entry (JSL from $80FE8B, replaces LDA $08 / CMP #$0400): the champion's
    #      'nobody left to fight' (message 199, manager script $01E4) becomes 'come back in a few days' (3 lines,
    #      arms the countdown) in league 0/1 ----
    a.label('c7in')
    a.imm(0xA9, 0); a.sta_l(C7F)
    a.b(0xA5, 0x0A); a.imm(0xC9, 0x0F00); a.rel(0x90, 'c7_std')             # our texts: message $0F00 + n
    a.b(0x38); a.imm(0xE9, 0x0F00); a.b(0x0A, 0xAA)
    a.lda_lx(0); a.fix.append(('long', len(a.code) - 3, 'tptr')); a.sta_l(C7P)
    a.imm(0xA9, 1); a.sta_l(C7F); a.brl('c7_out')
    a.label('c7_std')
    a.b(0xA5, 0x0A); a.imm(0xC9, 199); a.rel(0xD0, 'c7_out')
    a.lda_l(LEAGUE); a.imm(0x29, 0xFF); a.imm(0xC9, 2); a.rel(0xB0, 'c7_out')
    a.imm(0xA9, snes(script_file(0x1E4) + 2) & 0xFFFF); a.jsr('inctx'); a.rel(0xD0, 'c7_out')
    a.b(0xE2, 0x20); a.lda_l(WAITC); a.rel(0xD0, 'c7_arm'); a.b(0xA9, 1); a.sta_l(WAITC)
    a.label('c7_arm'); a.b(0xC2, 0x20)
    a.lda_l(LEAGUE); a.imm(0x29, 0xFF); a.b(0x18); a.imm(0x69, 24); a.b(0x0A, 0xAA)
    a.lda_lx(0); a.fix.append(('long', len(a.code) - 3, 'tptr')); a.sta_l(C7P)
    a.imm(0xA9, 1); a.sta_l(C7F)
    a.b(0xA5, 0x06); a.b(0x18); a.imm(0x69, 2); a.b(0x85, 0x06)               # two more text lines
    a.label('c7_out'); a.b(0xA5, 0x08); a.imm(0xC9, 0x0400); a.b(0x6B)
    # text (JSL from $80FE9E, replaces LDA $0A ... JSR $FE33, 12 bytes)
    a.label('c7txt')
    a.lda_l(C7F); a.rel(0xD0, 'c7_my')
    a.b(0xA5, 0x0A); a.b(0x0A, 0xAA); a.lda_lx(0x80D980); a.b(0x85, 0x02)
    a.call80(0x80FE33); a.b(0x6B)
    a.label('c7_my')
    a.imm(0xA9, 0); a.sta_l(C7F)
    a.lda_l(C7P); a.b(0x85, 0xCF); a.b(0xE2, 0x20); a.b(0xA9, CODE >> 16); a.b(0x85, 0xD1); a.b(0xC2, 0x20)
    ret = a.pc() + 1 + 3 + 3 + 1 + 4                                         # PHK/PEA/PEA/PHB/JML: $FE44 wants
    a.b(0x4B); a.b(0xF4); a.w(ret - 1); a.b(0xF4); a.w(RTL80 - 1); a.b(0x8B); a.b(0x5C); a.l(0x80FE44)   # B on top
    assert a.pc() == ret
    a.b(0x6B)

    # ---- script directory, ids >= 936 from our table ----
    # $80C298 (replaces LDA $82D970,X ... STA $71, 25 bytes): out $73 bank, $0264 arg bytes, $71 address, X = id*2
    a.label('sdir')
    a.b(0xE0); a.w(NSCRIPTS); a.rel(0xB0, 'sd_new')
    a.lda_lx(0x82D970); a.b(0x85, 0x73); a.lda_lx(0x82E810); a.imm(0x29, 0xFF); a.b(0x8D); a.w(0x0264)
    a.b(0x8A, 0x0A, 0xAA); a.lda_lx(0x82DD18); a.b(0x85, 0x71); a.b(0x6B)
    a.label('sd_new')
    a.b(0x8A); a.b(0x38); a.imm(0xE9, NSCRIPTS); a.b(0x0A, 0xAA)
    a.lda_lx(0); a.fix.append(('long', len(a.code) - 3, 'sptr')); a.b(0x85, 0x71)
    a.imm(0xA9, CODE >> 16); a.b(0x85, 0x73); a.imm(0xA9, 2); a.b(0x8D); a.w(0x0264)
    a.b(0x8A); a.b(0x18); a.imm(0x69, 2 * NSCRIPTS); a.b(0xAA); a.b(0x6B)
    # $80F433 (replaces LDA $82E810,X / AND #$00FF): A = arg bytes, flags from AND
    a.label('sargs')
    a.b(0xE0); a.w(NSCRIPTS); a.rel(0xB0, 'sa_new')
    a.lda_lx(0x82E810); a.imm(0x29, 0xFF); a.b(0x6B)
    a.label('sa_new'); a.imm(0xA9, 2); a.imm(0x29, 0xFF); a.b(0x6B)

    # ---- Glutman's jobs ----
    arena_texts = [encode(money(p * m)) for m in (2, 3) for p in PRIZES] + [encode(s) for s in TEXT_COMEBACK + TEXT_OFFER + TEXT_FLOAT]
    jtexts, jix = J.texts()
    tindex = {k: len(arena_texts) + v for k, v in jix.items()}
    T = {k: 0x0F00 + v for k, v in tindex.items()}
    sid = {k: NSCRIPTS + len(TYPES) + i for i, k in enumerate(J.ORDER)}
    jscripts = J.scripts(T, None)
    J.emit(a, sid, tindex, RW, RB, RTL80, CODE)

    # ---- data ----
    a.label('types')
    for t in TYPES: a.w(t)
    a.label('hps')
    for t in TYPES: a.w(fighter(t)['hp'])
    texts = arena_texts + [encode(s) for s in jtexts]
    scripts = [copy_script(t) for t in TYPES] + [jscripts[k] for k in J.ORDER]
    a.label('tptr'); tp = len(a.code); a.b(*([0] * (2 * len(texts))))
    a.label('sptr'); sp = len(a.code); a.b(*([0] * (2 * len(scripts))))
    for i, blob in enumerate(texts):
        a.code[tp + 2 * i:tp + 2 * i + 2] = list((a.pc() & 0xFFFF).to_bytes(2, 'little')); a.b(*blob)
    for i, blob in enumerate(scripts):
        a.code[sp + 2 * i:sp + 2 * i + 2] = list((a.pc() & 0xFFFF).to_bytes(2, 'little')); a.b(*blob)
    code = a.done()
    assert a.pc() < (CODE | 0xFFFF), 'bank overflow'
    return code, a.labels


def patch(rom):
    rom = bytearray(rom)
    if len(rom) < 0x200000: rom += b'\x00' * (0x200000 - len(rom))
    code, L = build_code()
    o = lorom(CODE); assert all(b == 0 for b in rom[o:o + len(code)]), 'code area not free'
    rom[o:o + len(code)] = code
    def put(addr, old, new):
        f = lorom(addr); assert rom[f:f + len(old)] == old, (hex(addr), rom[f:f + len(old)].hex()); rom[f:f + len(new)] = new
    jsl = lambda t: bytes([0x22, t & 0xFF, (t >> 8) & 0xFF, t >> 16])
    put(0x80CCAB, bytes.fromhex('18AF0D3C7E'), jsl(L['pay']) + b'\xEA')
    put(0x80CE3D, bytes.fromhex('A90A008500'), jsl(L['sleep']) + b'\xEA')
    put(0x80CAB0, bytes.fromhex('A400BEC413'), jsl(L['sethp']) + b'\xEA')
    put(0x80CC67, bytes.fromhex('A5008FE22D7E'), jsl(L['warp']) + b'\xEA\xEA')
    put(0x80C298, bytes.fromhex('BF70D9828573BF10E88229FF008D64028A0AAABF18DD828571'), jsl(L['sdir']) + b'\xEA' * 21)
    put(0x80F433, bytes.fromhex('BF10E88229FF00'), jsl(L['sargs']) + b'\xEA' * 3)
    # text natives: #99 tail ($8092CE, 16 bytes) and #D6 ($8092DE, 17 bytes)
    put(0x8092CE, bytes.fromhex('680AAABD80D98502A5148500 2033FE60'.replace(' ', '')),
        b'\x68' + jsl(L['text']) + b'\xB0\x04\x20\x33\xFE\x60\x8B\x4C\x44\xFE\xEA')   # custom: PHB / JMP $FE44 (its PLB / RTS end the native)
    put(0x8092DE, bytes.fromhex('A5000AAABD80D985 02A51485002033FE60'.replace(' ', '')),
        b'\xA5\x00' + jsl(L['text']) + b'\xB0\x04\x20\x33\xFE\x60\x8B\x4C\x44\xFE\xEA')   # custom: PHB / JMP $FE44 (its PLB / RTS end the native)
    put(0x809123, bytes.fromhex('851DA5148500'), jsl(L['topic']) + b'\xEA\xEA')
    put(0x80A4DE, bytes.fromhex('20F1A322E69A81'), jsl(L['mapload']) + b'\xEA' * 3)
    put(0x80FE8B, bytes.fromhex('A508C90004'), jsl(L['c7in']) + b'\xEA')
    put(0x80FE9E, bytes.fromhex('A50A0AAABD80D985022033FE'), jsl(L['c7txt']) + b'\xEA' * 8)
    rom[0x7FD7] = 0x0B
    rom[0x7FDC:0x7FE0] = b'\xFF\xFF\x00\x00'; s = sum(rom) & 0xFFFF
    rom[0x7FDC:0x7FDE] = (s ^ 0xFFFF).to_bytes(2, 'little'); rom[0x7FDE:0x7FE0] = s.to_bytes(2, 'little')
    return bytes(rom)


if __name__ == '__main__':
    src = open(sys.argv[1], 'rb').read(); out = sys.argv[2]
    new = patch(src)
    open(out + '.sfc', 'wb').write(new); open(out + '.ips', 'wb').write(make_ips(src, new))
    print('code+data', len(build_code()[0]), 'bytes; ROM CRC32 %08X' % zlib.crc32(new))
