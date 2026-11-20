"""Build "Shadowrun: Smart Targeting" (standalone; stacks with Persistent Runners / More Enemies / Rebalanced / Expanded Dialogue).

  python3 build_targeting.py IN_ROM OUT_PREFIX      (IN_ROM: clean 1 MB ROM, or any 2 MB patched ROM)

Jake's controls are read by native #CF ($80DFDE). With the pointer off, A opens the gun cross-hair ($80E07A -> $80BC50,
pointer placed on Jake). With the pointer on in combat mode ($1D79 / $1D7B set), A or X held over an object whose
$1474 bit 15 is set fires: once per new press, or every time the script asks while held if the weapon type
($7E3C33) is 1. B, L or R close the pointer.

This patch:
  * Snap:      when A opens the cross-hair, the pointer jumps to the on-screen enemy nearest Jake
               (enemies = the combatant list $1FCC/$1FCE that the game keeps for fights).
  * Cycle:     in combat mode L / R jump to the next on-screen enemy to the left / right (wraps around).
               With no enemy on screen L / R still close the pointer as before. B still cancels.
  * Auto-fire: holding A over a valid target keeps firing with every weapon (the vanilla 'type 1' path).
               Releasing A or losing the target stops; the fire rate is the weapon's normal one.
Code lives at $BFE800 (file $1FE800); the ROM is expanded to 2 MB if needed.
"""
import sys, zlib
from build_runners import Asm, lorom, make_ips, RTL80

CODE = 0xBFE800
CX, CY, V, T, YB2, XL = 0x7FB7C0, 0x7FB7C2, 0x7FB7C4, 0x7FB7C6, 0x7FB7C8, 0x7FB7CA
BEST, BX, BY, CUR, BK, WK, FLIP = 0x7FB7CC, 0x7FB7CE, 0x7FB7D0, 0x7FB7D2, 0x7FB7D4, 0x7FB7D6, 0x7FB7D8
OBJ, LATCH, LX, LY, LKEY = 0x7FB7DA, 0x7FB7DC, 0x7FB7DE, 0x7FB7E0, 0x7FB7E2


_n = [0]
def far(a, op, lab):                                   # long conditional branch: inverted short branch over a BRL
    _n[0] += 1; skip = 'far%d' % _n[0]
    a.rel(op ^ 0x20, skip); a.brl(lab); a.label(skip)


PTR_X, PTR_Y = (3, 239), (3, 206)                      # pointer limits ($80BEC8)
def clamp(a, lim):                                     # A (signed) into lim
    _n[0] += 1; k = 'cl%d' % _n[0]
    a.imm(0xC9, lim[1]); a.rel(0x30, k + 'lo'); a.rel(0x90, k + 'lo'); a.imm(0xA9, lim[1])   # >= max (unsigned, non-neg)
    a.label(k + 'lo'); a.imm(0xC9, 0x8000); a.rel(0xB0, k + 'set'); a.imm(0xC9, lim[0]); a.rel(0xB0, k + 'ok')
    a.label(k + 'set'); a.imm(0xA9, lim[0])
    a.label(k + 'ok')


def asr(a, n):
    for _ in range(n): a.imm(0xC9, 0x8000); a.b(0x6A)      # CMP #$8000 ; ROR  (signed shift right)


def build_code():
    a = Asm(CODE)

    # ---- center: X = object. Carry clear + CX/CY = pointer pixel that hovers the object's box (same maths as the
    #      hover test at $80BCE7), carry set if the object can't be hovered or is off screen. Keeps X.
    a.label('c_bad'); a.b(0x38, 0x60)
    a.label('center')
    a.b(0xBD); a.w(0x10AC); far(a, 0xF0, 'c_bad')                                   # LDA $10AC,X : visible?
    a.lda_lx(0x7E3F04); a.b(0x0A); a.sta_l(T); a.b(0x0A); a.b(0x18); a.adc_l(T)   # sprite * 6
    a.b(0xDA, 0xAA); a.lda_lx(0x8CEFB0); a.b(0xFA)                                 # PHX TAX LDA $8CEFB0,X PLX
    a.imm(0xC9, 0xFFFF); far(a, 0xF0, 'c_bad')
    # vertical: box is  top < y <= bottom  (top = top2 asr 1, bottom = bottom2 lsr 1)
    a.b(0x38); a.b(0xAD); a.w(0x0202); a.b(0x38); a.b(0xFD); a.w(0x0F4C); a.b(0x38); a.b(0xFD); a.w(0x0EF4)
    a.b(0x38); a.b(0xED); a.w(0x0CE2); far(a, 0x30, 'c_bad'); a.b(0x4A, 0x4A); a.sta_l(V)
    a.b(0x0A); a.b(0x38); a.b(0xFF); a.l(0x7E421C); a.b(0x38); a.b(0xFF); a.l(0x7E42CC); far(a, 0x30, 'c_bad')
    a.b(0x4A); a.sta_l(YB2)                                                        # bottom
    a.lda_l(V); a.b(0x38); a.b(0xFF); a.l(0x7E437C); a.b(0x0A); a.b(0x38); a.b(0xFF); a.l(0x7E4274)
    a.b(0x38); a.b(0xFF); a.l(0x7E4324); asr(a, 1); a.sta_l(T)                      # top
    a.b(0x38); a.adc_l(YB2); asr(a, 1)                                             # (top + bottom + 1) / 2
    clamp(a, PTR_Y)
    a.sta_l(CY); a.b(0x38); a.b(0xEF); a.l(T); far(a, 0x30, 'c_bad'); far(a, 0xF0, 'c_bad')        # y > top
    a.lda_l(YB2); a.b(0x38); a.b(0xEF); a.l(CY); far(a, 0x30, 'c_bad')                           # y <= bottom
    # horizontal: box is  left < x <= right
    a.b(0x18); a.b(0xAD); a.w(0x0200); a.b(0x7D); a.w(0x0E9C); a.b(0x38); a.b(0xFD); a.w(0x0E44)
    a.b(0x38); a.b(0xED); a.w(0x0CE0); asr(a, 2); a.sta_l(V)
    a.b(0x18); a.b(0x7F); a.l(0x7E42CC); a.b(0x38); a.b(0xFF); a.l(0x7E4274); a.sta_l(XL)        # left
    a.lda_l(V); a.b(0x38); a.b(0xFF); a.l(0x7E421C); a.b(0x18); a.b(0x7F); a.l(0x7E4324); a.sta_l(T)  # right
    a.b(0x38); a.adc_l(XL); asr(a, 1)                                                          # (l + r + 1) / 2
    clamp(a, PTR_X)
    a.sta_l(CX); a.b(0x38); a.b(0xEF); a.l(XL); far(a, 0x30, 'c_bad2'); far(a, 0xF0, 'c_bad2')     # x > left
    a.lda_l(T); a.b(0x38); a.b(0xEF); a.l(CX); far(a, 0x30, 'c_bad2')                            # x <= right
    a.b(0x18, 0x60)
    a.label('c_bad2'); a.b(0x38, 0x60)

    # ---- valid: X = object; carry clear if it is a shootable on-screen enemy (CX/CY set)
    a.label('valid')
    a.b(0xBD); a.w(0x1474); far(a, 0x10, 'c_bad2')                                   # LDA $1474,X : BPL -> not a target
    a.brl('center')

    # ---- near: carry clear if the pointer is still within 4 px of where we last put it (the game can nudge it a pixel)
    a.label('near')
    for reg, last in ((0x01F0, LX), (0x01F2, LY)):
        a.b(0xAD); a.w(reg); a.b(0x38); a.b(0xEF); a.l(last)
        a.rel(0x10, 'nr_p%X' % reg); a.imm(0x49, 0xFFFF); a.b(0x1A)
        a.label('nr_p%X' % reg); a.imm(0xC9, 0x0500); a.rel(0xB0, 'nr_far')
    a.b(0x18, 0x60)
    a.label('nr_far'); a.b(0x38, 0x60)

    # ---- set the pointer to CX/CY
    a.label('setptr')
    a.lda_l(CX); a.b(0xEB); a.imm(0x29, 0xFF00); a.b(0x8D); a.w(0x01F0)
    a.sta_l(LX)
    a.lda_l(CY); a.b(0xEB); a.imm(0x29, 0xFF00); a.b(0x8D); a.w(0x01F2); a.sta_l(LY)
    a.b(0x8A); a.imm(0x29, 0xFF); a.sta_l(T); a.lda_l(CX); a.b(0xEB); a.imm(0x29, 0xFF00); a.b(0x0F); a.l(T)
    a.sta_l(LKEY)                                                                  # key of the object we aimed at
    a.b(0x60)

    # ---- latch: JSL from $809DA6 (joypad edge update, every frame; replaces STA $01EA / LDA $01E6).
    #      Native #CF isn't run every frame, so new L/R presses are kept here until the cycle hook sees them.
    a.label('latch')
    a.b(0x8D); a.w(0x01EA); a.imm(0x29, 0x0030); a.b(0x0F); a.l(LATCH); a.sta_l(LATCH)
    a.b(0xAD); a.w(0x01E6); a.b(0x6B)

    # ---- nearest: put the pointer on the valid enemy nearest the pointer's current spot. Carry set if none.
    a.label('nearest')
    a.imm(0xA9, 0xFFFF); a.sta_l(BEST)
    a.b(0xAD); a.w(0x1FCC); a.rel(0x30, 'n_none'); a.b(0xA8)                       # LDA $1FCC : BMI none : TAY
    a.label('n_loop')
    a.b(0xBE); a.w(0x1FCE); a.jsr('valid'); a.rel(0xB0, 'n_next')                  # LDX $1FCE,Y
    a.b(0xAD); a.w(0x01F0); a.b(0xEB); a.imm(0x29, 0xFF); a.b(0x38); a.b(0xEF); a.l(CX)   # |ptr_x - cx|
    a.rel(0x10, 'n_p1'); a.imm(0x49, 0xFFFF); a.b(0x1A)
    a.label('n_p1'); a.sta_l(T)
    a.b(0xAD); a.w(0x01F2); a.b(0xEB); a.imm(0x29, 0xFF); a.b(0x38); a.b(0xEF); a.l(CY)   # |ptr_y - cy|
    a.rel(0x10, 'n_p2'); a.imm(0x49, 0xFFFF); a.b(0x1A)
    a.label('n_p2'); a.b(0x18); a.adc_l(T); a.cmp_l(BEST); a.rel(0xB0, 'n_next')
    a.sta_l(BEST); a.lda_l(CX); a.sta_l(BX); a.lda_l(CY); a.sta_l(BY); a.b(0x8A); a.sta_l(OBJ)
    a.label('n_next'); a.b(0x88, 0x88); a.rel(0x10, 'n_loop')
    a.lda_l(BEST); a.imm(0xC9, 0xFFFF); a.rel(0xF0, 'n_none')
    a.lda_l(BX); a.sta_l(CX); a.lda_l(BY); a.sta_l(CY); a.lda_l(OBJ); a.b(0xAA); a.jsr('setptr')
    a.b(0x18, 0x60)
    a.label('n_none'); a.b(0x38, 0x60)

    # ---- inlist: carry clear if object X is in the combatant list. Keeps X, clobbers Y.
    a.label('inlist')
    a.b(0xAC); a.w(0x1FCC); a.rel(0x30, 'n_none')                                  # LDY $1FCC
    a.label('i_loop'); a.b(0x8A); a.b(0xD9); a.w(0x1FCE); a.rel(0xF0, 'i_yes')      # TXA : CMP $1FCE,Y
    a.b(0x88, 0x88); a.rel(0x10, 'i_loop'); a.b(0x38, 0x60)
    a.label('i_yes'); a.b(0x18, 0x60)

    # ---- snap: JSL from $80E07A (replaces JSR $BC50 / LDA $7E3C34)
    a.label('snap')
    a.call80(0x80BC50)                                                             # vanilla: cross-hair on Jake
    a.imm(0xA9, 0); a.sta_l(LATCH)
    a.jsr('nearest')                                                               # -> enemy nearest Jake
    a.lda_l(0x7E3C34); a.b(0x6B)                                                   # replaced instruction

    # ---- cycle: JSL from $80E0F8 (replaces LDA $1D79 / ORA $1D7B; the BEQ after it uses our flags)
    a.label('cycle')
    a.lda_l(LATCH); a.b(0x0D); a.w(0x01EA); a.sta_l(T); a.imm(0xA9, 0); a.sta_l(LATCH)   # L/R since last call
    a.b(0xAD); a.w(0x1D79); a.b(0x0D); a.w(0x1D7B); a.rel(0xD0, 'y_go'); a.b(0x6B)   # not aiming: vanilla
    a.label('y_go')
    a.lda_l(T); a.imm(0x29, 0x0030); far(a, 0xF0, 'lock')                # no new L/R press
    a.imm(0x29, 0x0010); a.rel(0xF0, 'y_left'); a.imm(0xA9, 0); a.bra('y_dir')
    a.label('y_left'); a.imm(0xA9, 0xFFFF)
    a.label('y_dir'); a.sta_l(FLIP)                                                # R: keys as is, L: keys inverted
    # current key: the enemy we put the pointer on, if the pointer hasn't moved since; else pointer x <<8 | $80
    #   (the game's hover result $01FA lags a few frames behind, so it isn't used)
    a.jsr('near'); a.rel(0xB0, 'y_nohov')
    a.lda_l(LKEY); a.bra('y_cur')
    a.label('y_nohov'); a.b(0xAD); a.w(0x01F0); a.imm(0x29, 0xFF00); a.imm(0x09, 0x0080)
    a.label('y_cur'); a.b(0x4F); a.l(FLIP); a.sta_l(CUR)                           # EOR FLIP
    a.imm(0xA9, 0xFFFF); a.sta_l(BK); a.sta_l(WK)
    a.b(0xAD); a.w(0x1FCC); far(a, 0x30, 'y_mode'); a.b(0xA8)
    a.label('y_loop')
    a.b(0xBE); a.w(0x1FCE); a.jsr('valid'); a.rel(0xB0, 'y_next')
    a.b(0x8A); a.imm(0x29, 0xFF); a.sta_l(T); a.lda_l(CX); a.b(0xEB); a.imm(0x29, 0xFF00); a.b(0x0F); a.l(T)
    a.b(0x4F); a.l(FLIP)                                                           # key
    a.cmp_l(WK); a.rel(0xB0, 'y_w'); a.sta_l(WK)                                   # smallest overall (wrap)
    a.label('y_w'); a.cmp_l(CUR); a.rel(0xF0, 'y_next'); a.rel(0x90, 'y_next')     # must be after the current one
    a.cmp_l(BK); a.rel(0xB0, 'y_next'); a.sta_l(BK)                                # smallest after current
    a.label('y_next'); a.b(0x88, 0x88); a.rel(0x10, 'y_loop')
    a.lda_l(WK); a.imm(0xC9, 0xFFFF); far(a, 0xF0, 'y_mode')                        # no enemy: L/R cancel as before
    a.lda_l(BK); a.imm(0xC9, 0xFFFF); a.rel(0xD0, 'y_have'); a.lda_l(WK)
    a.label('y_have'); a.b(0x4F); a.l(FLIP); a.imm(0x29, 0xFF); a.b(0xAA)          # object
    a.jsr('center'); far(a, 0xB0, 'y_mode'); a.jsr('setptr')
    a.b(0xAD); a.w(0x01EA); a.imm(0x29, 0xFFCF); a.b(0x8D); a.w(0x01EA)            # L/R used up: don't cancel
    a.bra('y_mode')

    # ---- lock-on while A is held: the pointer follows the enemy it was put on (or the one hovered); when that
    #      enemy drops, it moves to the nearest other enemy on screen. Moving the pointer by hand breaks the lock.
    a.label('lock')
    a.b(0xAD); a.w(0x01E6); a.imm(0x29, 0x0080); a.rel(0xF0, 'y_mode')             # A not held
    a.jsr('near'); a.rel(0xB0, 'k_hov')
    a.lda_l(LKEY); a.imm(0x29, 0xFF); a.b(0xAA)                                    # locked object
    a.jsr('inlist'); a.rel(0xB0, 'k_lost'); a.jsr('valid'); a.rel(0xB0, 'k_lost')
    a.jsr('setptr'); a.bra('y_mode')                                               # follow it
    a.label('k_lost'); a.jsr('nearest'); a.bra('y_mode')                           # next one
    a.label('k_hov'); a.b(0xAD); a.w(0x01F6); a.rel(0x30, 'y_mode')                # hovering something?
    a.b(0xAE); a.w(0x01FA); a.jsr('inlist'); a.rel(0xB0, 'y_mode'); a.jsr('valid'); a.rel(0xB0, 'y_mode')
    a.jsr('setptr')                                                                # lock onto it
    a.label('y_mode'); a.b(0xAD); a.w(0x1D79); a.b(0x0D); a.w(0x1D7B)
    a.b(0x6B)
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
    assert rom[lorom(RTL80)] == 0x6B
    put(0x80E07A, bytes.fromhex('2050BCAF343C7E'), jsl(L['snap']) + b'\xEA\xEA\xEA')
    put(0x80E0F8, bytes.fromhex('AD791D0D7B1D'), jsl(L['cycle']) + b'\xEA\xEA')
    put(0x809DA6, bytes.fromhex('8DEA01ADE601'), jsl(L['latch']) + b'\xEA\xEA')
    put(0x80E130, bytes.fromhex('D013'), b'\xEA\xEA')                              # every weapon: held A fires
    rom[0x7FD7] = 0x0B
    rom[0x7FDC:0x7FE0] = b'\xFF\xFF\x00\x00'; s = sum(rom) & 0xFFFF
    rom[0x7FDC:0x7FDE] = (s ^ 0xFFFF).to_bytes(2, 'little'); rom[0x7FDE:0x7FE0] = s.to_bytes(2, 'little')
    return bytes(rom)


if __name__ == '__main__':
    src = open(sys.argv[1], 'rb').read(); out = sys.argv[2]
    new = patch(src)
    open(out + '.sfc', 'wb').write(new); open(out + '.ips', 'wb').write(make_ips(src, new))
    print('code', len(build_code()[0]), 'bytes; ROM CRC32 %08X' % zlib.crc32(new))
