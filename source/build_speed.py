"""Build "Shadowrun: Less Slowdown" (sprite cache). Standalone; stacks with the other patches.

  python3 build_speed.py IN_ROM OUT_PREFIX

Every main-loop pass the game rebuilds every visible object's sprites ($80B8AF -> $80B1DB per object): it checks each
8x8 block against the scenery's priority maps and draws scenery pieces over hidden parts. In crowded rooms that is more
than half of all the work, and most objects haven't changed since the last pass.

This patch keeps, per object slot, the sprite entries (OAM low 4 bytes + 2 high bits each) and flag bits that $80B1DB
produced, keyed by everything they depend on: frame pointer, screen position and depth as $80B1DB derives them, camera,
palette ($1314), priority mode ($141C), VRAM slot and location. When the key matches, the saved entries are copied
instead of recomputed. Objects are recomputed at least every AGE_MAX passes; objects with more than MAXE entries are
never cached.
"""
import sys, zlib
from build_runners import Asm, lorom, make_ips

CODE = 0xBFEC00                      # after Smart Targeting ($BFE800..)
TABLES = 0xBFF400                    # 1 KB high-bit extraction table + small tables
MAXE = 16                            # sprite entries kept per object
AGE_MAX = 16                         # recompute at least this often (main-loop passes)
NKEY = 10
ES = 6                               # per entry: 4 OAM bytes + high bits (word)
REC = 2 + 2 * NKEY + 6 + ES * MAXE   # 124 bytes: age (or $FFFF), key, n, outbits, $1C90, entries
SLOTS = 44
BASE_A, BASE_B = 0x7FA900, 0x7FB900   # slots 0-21 / 22-43 (free RAM, see notes)
O_AGE, O_KEY, O_N, O_OUT, O_C90, O_ENT = 0, 2, 2 + 2 * NKEY, 4 + 2 * NKEY, 6 + 2 * NKEY, 8 + 2 * NKEY
R = lambda off: 0x7F0000 + off       # long,X address of a record field (X = record address)
FR, OBJ, CB, START, IN74, NN = 0x7FC600, 0x7FC602, 0x7FC604, 0x7FC606, 0x7FC608, 0x7FC60A
LPASS, LCX, LCY, SCRL = 0x7FC60C, 0x7FC60E, 0x7FC610, 0x7FC612   # per-pass camera check
KEEP = [0xFF, 0xFC, 0xF0, 0xC0]       # high-table bits to keep after q written entries
DK = 0x10                            # key words in direct page $10-$23 ($80B1DB overwrites $0E-$6B anyway)


def bases():
    return [(BASE_A + REC * s) if s < 22 else (BASE_B + REC * (s - 22)) for s in range(SLOTS)]


def tables():
    t = bytearray()
    for sh in range(4):                                   # $000-$3FF: (byte >> 2*sh) & 3
        t += bytes(((b >> (2 * sh)) & 3) for b in range(256))
    for sh in range(4):                                   # $400-$40F: bits << 2*sh   (index sh*4 + bits)
        t += bytes((bits << (2 * sh)) for bits in range(4))
    t += bytes((~(3 << (2 * sh))) & 0xFF for sh in range(4))   # $410-$413: keep-mask
    t += bytes(12)
    for pos in range(4): t += bytes([(1 << (2 * pos)) - 1, 0])    # $420: keep bits before pos (word each)
    return bytes(t)


def build_code(verify=False):
    assert BASE_A + 22 * REC <= 0x7FB600 and BASE_B + 22 * REC <= 0x7FC600, 'cache does not fit'
    T1, SHL, MASK = TABLES, TABLES + 0x400, TABLES + 0x410
    LOWKEEP = TABLES + 0x420                                                  # word per pos*2: bits before pos
    DISP = TABLES + 0x428                                                     # body addresses - 1
    a = Asm(CODE)
    # JSL from $80B8DF (replaces PHY / TXY / JSR $B1DB / PLY). In: A = frame pointer, X = object, Y = list index.
    a.label('spr')
    a.b(0x5A)                                                                  # phy (list index)
    a.sta_l(FR); a.b(0x8A); a.sta_l(OBJ); a.b(0xA8)                           # Y = object
    a.lda_lx(0); a.fix.append(('long', len(a.code) - 3, 'btab')); a.sta_l(CB)
    # VRAM slot of the object's graphics, exactly as $80AA97 (allocates it this pass if needed)
    a.b(0xB9); a.w(0x1264); a.b(0x0A, 0xAA); a.b(0xBD); a.w(0x1802); a.rel(0x10, 'vs_ok')
    a.b(0xAD); a.w(0x17F0); a.b(0x9D); a.w(0x1802); a.b(0x86, 0x6B, 0xAA, 0xA5, 0x6B); a.b(0x9D); a.w(0x17F2)
    a.b(0x8A, 0xE8, 0xE8); a.b(0x8E); a.w(0x17F0)
    a.label('vs_ok'); a.b(0x85, DK + 16)
    a.lda_l(FR); a.b(0x85, DK + 0)
    # screen y / x as $80B1DB derives them, at half resolution (its frame offsets are even, so this is exact)
    a.b(0x38); a.imm(0xA9, 0x0C00); a.b(0xF9); a.w(0x0F4C); a.b(0x38); a.b(0xF9); a.w(0x0EF4)
    a.imm(0xC9, 0x8000); a.b(0x6A, 0x85, DK + 2)
    a.b(0x18); a.imm(0xA9, 0x0600); a.b(0x79); a.w(0x0E9C); a.b(0x38); a.b(0xF9); a.w(0x0E44)
    a.imm(0xC9, 0x8000); a.b(0x6A, 0x85, DK + 4)
    a.b(0xB9); a.w(0x0F4C); a.b(0x4A, 0x4A, 0x85, DK + 6)                      # depth >> 2
    a.b(0xAD); a.w(0x0CE0); a.b(0x4A, 0x4A, 0x85, DK + 8)                      # camera >> 2
    a.b(0xAD); a.w(0x0CE2); a.b(0x4A, 0x4A, 0x85, DK + 10)
    a.b(0xB9); a.w(0x1314); a.b(0x85, DK + 12)
    a.b(0xB9); a.w(0x141C); a.b(0x85, DK + 14)
    a.lda_l(0x7E2DE2); a.b(0x85, DK + 18)
    # hit?
    # camera moved this pass? then everything changes anyway: just run the game's routine (no cache overhead)
    a.b(0xAD); a.w(0x1C92); a.cmp_l(LPASS); a.rel(0xF0, 'cam_k')               # NMI count = pass id
    a.sta_l(LPASS); a.imm(0xA9, 0); a.sta_l(SCRL)
    a.b(0xAD); a.w(0x0CE0); a.cmp_l(LCX); a.rel(0xD0, 'cam_m')
    a.b(0xAD); a.w(0x0CE2); a.cmp_l(LCY); a.rel(0xF0, 'cam_k')
    a.label('cam_m'); a.b(0xAD); a.w(0x0CE0); a.sta_l(LCX); a.b(0xAD); a.w(0x0CE2); a.sta_l(LCY)
    a.imm(0xA9, 1); a.sta_l(SCRL)
    a.label('cam_k')
    a.lda_l(CB); a.b(0xAA)
    a.lda_l(SCRL); a.rel(0xF0, 'cam_s')
    a.imm(0xA9, 0xFFFF); a.sta_lx(R(O_AGE))
    a.lda_l(FR); a.call80(0x80B1DB); a.brl('out')
    a.label('cam_s')
    a.lda_lx(R(O_AGE)); a.imm(0xC9, AGE_MAX); a.rel(0xB0, 'miss')              # $FFFF (invalid) or too old
    for k in range(NKEY):
        a.b(0xA5, DK + 2 * k); a.b(0xDF); a.l(R(O_KEY + 2 * k)); a.rel(0xD0, 'miss_%d' % k)
    a.brl('hit')
    for k in range(NKEY): a.label('miss_%d' % k)
    a.label('miss')
    for k in range(NKEY):                                                      # key -> record (DP dies below)
        a.b(0xA5, DK + 2 * k); a.sta_lx(R(O_KEY + 2 * k))
    a.b(0xA5, 0x84); a.sta_l(START)
    a.b(0xB9); a.w(0x1474); a.imm(0x29, 0xF5FB); a.sta_l(IN74)
    a.lda_l(FR); a.call80(0x80B1DB)                                            # the game's own routine (Y = object)
    a.lda_l(OBJ); a.b(0xA8)
    a.lda_l(CB); a.b(0xAA)
    a.b(0xA5, 0x84); a.b(0x38); a.b(0xEF); a.l(START); a.b(0x4A, 0x4A); a.sta_l(NN)
    a.imm(0xC9, MAXE + 1); a.rel(0xB0, 'st_no')                                 # too many: don't cache
    a.b(0xA5, 0x84); a.b(0xC9); a.w(0x01FC); a.rel(0x90, 'st_ok')              # OAM (nearly) full: list may be cut
    a.label('st_no'); a.imm(0xA9, 0xFFFF); a.sta_lx(R(O_AGE)); a.brl('out')
    a.label('st_ok0')
    a.label('st_ok')
    a.lda_l(NN); a.sta_lx(R(O_N))
    a.b(0xB9); a.w(0x1474); a.b(0x4F); a.l(IN74); a.sta_lx(R(O_OUT))           # bits it set
    a.b(0xAD); a.w(0x1C90); a.sta_lx(R(O_C90))
    a.imm(0xA9, 0); a.sta_lx(R(O_AGE))
    a.lda_l(NN); a.rel(0xD0, 'st_go'); a.brl('out')
    a.label('st_go'); a.b(0x85, 0x0E)                                          # count in DP $0E
    a.b(0x8B, 0xF4, 0x7E, 0x7E, 0xAB, 0xAB)                                    # phb; DB = $7E
    a.lda_l(START); a.b(0xA8)
    a.label('st_l')
    a.b(0xB9); a.w(0x3CE4); a.sta_lx(R(O_ENT))
    a.b(0xB9); a.w(0x3CE6); a.sta_lx(R(O_ENT + 2))
    a.b(0xDA)                                                                  # phx
    a.b(0x98, 0x4A, 0x4A, 0x4A, 0x4A, 0xAA)                                    # X = Y/16
    a.b(0xBD); a.w(0x3EE4); a.imm(0x29, 0xFF); a.b(0x85, 0x10)                 # high-table byte
    a.b(0x98); a.imm(0x29, 0x000C); a.b(0xEB, 0x4A, 0x4A); a.b(0x05, 0x10); a.b(0xAA)   # ((Y>>2)&3)<<8 | byte
    a.lda_lx(T1); a.b(0xFA)                                                    # bits; plx
    a.sta_lx(R(O_ENT + 4))
    a.b(0x8A, 0x18); a.imm(0x69, ES); a.b(0xAA); a.b(0xC8, 0xC8, 0xC8, 0xC8)   # record += 6, OAM += 4
    a.b(0xC6, 0x0E); a.rel(0xD0, 'st_l')
    a.b(0xAB)                                                                  # plb
    a.brl('out')

    # ---- hit: copy the saved entries into the OAM buffer
    a.label('hit')
    if not verify:
        a.jsr('replay'); a.brl('out')
    else:                                                                      # TEST BUILD: replay, then recompute and compare
        VB = 0x7FA880                                                          # 64 bytes low + 8 bytes high table
        a.b(0xA5, 0x84); a.sta_l(START)
        a.b(0xB9); a.w(0x1474); a.imm(0x29, 0xF5FB); a.sta_l(IN74)
        a.lda_l(START); a.b(0x4A, 0x4A, 0x4A, 0x4A); a.b(0xAA)                 # snapshot high table bytes
        for k in range(0, 8, 2): a.lda_lx(0x7E3EE4 + k); a.sta_l(0x7FA8D0 + k)
        a.lda_l(CB); a.b(0xAA)
        a.jsr('replay')
        a.lda_l(OBJ); a.b(0xA8)
        a.b(0xA5, 0x84); a.sta_l(0x7FA8E0)                                     # replay end
        a.lda_l(START); a.b(0xAA)
        for k in range(0, 64, 2): a.lda_lx(0x7E3CE4 + k); a.sta_l(VB + k)
        a.lda_l(START); a.b(0x4A, 0x4A, 0x4A, 0x4A); a.b(0xAA)
        for k in range(0, 8, 2): a.lda_lx(0x7E3EE4 + k); a.sta_l(VB + 64 + k); a.lda_l(0x7FA8D0 + k); a.sta_lx(0x7E3EE4 + k)
        a.lda_l(START); a.b(0x85, 0x84)
        a.lda_l(FR); a.call80(0x80B1DB)                                        # recompute (final result = the game's)
        a.lda_l(OBJ); a.b(0xA8)
        a.b(0xA5, 0x84); a.cmp_l(0x7FA8E0); a.rel(0xF0, 'v_c1'); a.imm(0xA9, 1); a.sta_l(0x7FA868); a.brl('v_bad')
        a.label('v_c1')
        a.b(0x38); a.b(0xEF); a.l(START); a.b(0x85, 0x0E)                     # bytes written
        a.lda_l(START); a.b(0xAA); a.imm(0xA0, 0)
        a.label('v_l')
        a.b(0xC4, 0x0E); a.rel(0xB0, 'v_hi')
        a.b(0x98, 0x18); a.adc_l(START); a.b(0xAA); a.lda_lx(0x7E3CE4); a.b(0x85, 0x10)
        a.b(0xBB); a.lda_lx(VB); a.b(0xC5, 0x10); a.rel(0xF0, 'v_ok1'); a.b(0x98); a.sta_l(0x7FA86A); a.imm(0xA9, 2); a.sta_l(0x7FA868); a.brl('v_bad')
        a.label('v_ok1')
        a.b(0xC8, 0xC8); a.bra('v_l')
        a.label('v_hi')
        # compare the high-table bytes touched (entries START/4 .. end/4)
        a.lda_l(START); a.b(0x4A, 0x4A, 0x4A, 0x4A); a.b(0xAA)
        for k in range(0, 8, 2):
            a.lda_lx(0x7E3EE4 + k); a.cmp_l(VB + 64 + k); a.rel(0xF0, 'v_h%d' % k); a.imm(0xA9, 3 + k); a.sta_l(0x7FA868); a.brl('v_bad')
            a.label('v_h%d' % k)
        a.lda_l(0x7FA866); a.b(0x1A); a.sta_l(0x7FA866); a.brl('out')
        a.label('v_bad')
        a.lda_l(0x7FA860); a.b(0x1A); a.sta_l(0x7FA860)
        a.lda_l(OBJ); a.sta_l(0x7FA862); a.lda_l(START); a.sta_l(0x7FA864)
        a.lda_l(CB); a.b(0xAA); a.imm(0xA9, 0xFFFF); a.sta_lx(R(O_AGE)); a.brl('out')

    a.label('replay')
    a.lda_lx(R(O_AGE)); a.b(0x1A); a.sta_lx(R(O_AGE))
    a.b(0xB9); a.w(0x1474); a.imm(0x29, 0xF5FB); a.b(0x1F); a.l(R(O_OUT)); a.b(0x99); a.w(0x1474)
    a.lda_lx(R(O_C90)); a.b(0x8D); a.w(0x1C90)
    a.b(0x8C); a.w(0x1C8E)                                                     # sty $1C8E (as $B1DB)
    a.lda_lx(R(O_N)); a.rel(0xD0, 'h_go'); a.b(0x60)
    a.label('h_go'); a.b(0x85, 0x0E)                                          # entries left
    a.b(0x8B, 0xF4, 0x7E, 0x7E, 0xAB, 0xAB)                                    # phb; DB = $7E
    a.b(0xA4, 0x84)                                                            # ldy $84
    # high-table byte for the first entry: keep the bits of earlier entries, then OR ours in as we go
    a.b(0x98, 0x4A, 0x4A, 0x4A, 0x4A, 0x85, 0x14)                              # $14 = byte index (Y/16)
    a.b(0x98); a.imm(0x29, 0x000C); a.b(0x4A, 0x85, 0x12)                      # $12 = pos*2
    a.b(0xDA); a.b(0xA6, 0x14); a.b(0xBD); a.w(0x3EE4); a.b(0xA6, 0x12); a.b(0x3F); a.l(LOWKEEP); a.imm(0x29, 0xFF)
    a.b(0x85, 0x10)                                                            # acc
    a.lda_lx(DISP); a.b(0xFA, 0x48, 0x60)                                      # plx; jump to body[pos] (push-1 + rts)
    for k in range(4):
        a.label('hb%d' % k)
        a.b(0xC0); a.w(0x0200); a.rel(0x90, 'hb%d_g' % k); a.brl('hq%d' % k)    # OAM full
        a.label('hb%d_g' % k)
        a.lda_lx(R(O_ENT)); a.b(0x99); a.w(0x3CE4)
        a.lda_lx(R(O_ENT + 2)); a.b(0x99); a.w(0x3CE6)
        a.b(0xE2, 0x20); a.lda_lx(R(O_ENT + 4)); a.b(0x29, 3)
        for _ in range(2 * k): a.b(0x0A)
        a.b(0x05, 0x10, 0x85, 0x10, 0xC2, 0x20)
        a.b(0x8A, 0x18); a.imm(0x69, ES); a.b(0xAA); a.b(0xC8, 0xC8, 0xC8, 0xC8)
        a.b(0xC6, 0x0E)
        if k < 3:
            a.rel(0xD0, 'hb%d' % (k + 1)); a.brl('hq%d' % (k + 1))
        else:
            a.b(0x08)                                                          # php (Z = done)
            a.b(0xDA, 0xA6, 0x14, 0xA5, 0x10, 0xE2, 0x20); a.b(0x9D); a.w(0x3EE4); a.b(0xC2, 0x20)  # byte complete
            a.b(0xE8, 0x86, 0x14, 0xFA, 0x64, 0x10)                            # next byte, acc = 0
            a.b(0x28); a.rel(0xF0, 'hq0'); a.brl('hb0')
    # finished with q entries of the current byte written: merge with the bits after them
    for q in range(4):
        a.label('hq%d' % q)
        if q == 0:
            a.brl('h_end')                                                     # nothing pending
        else:
            a.b(0xDA, 0xA6, 0x14, 0xE2, 0x20); a.b(0xBD); a.w(0x3EE4); a.b(0x29, KEEP[q], 0x05, 0x10)
            a.b(0x9D); a.w(0x3EE4); a.b(0xC2, 0x20, 0xFA); a.brl('h_end')
    a.label('h_end')
    a.label('h_full')
    a.b(0x84, 0x84)                                                            # sty $84
    a.b(0xAB, 0x60)                                                            # plb; rts
    a.label('out')
    a.b(0x7A, 0x6B)                                                            # ply; rtl
    a.label('btab')
    for b in bases(): a.w(b & 0xFFFF)
    code = a.done()
    assert CODE + len(code) <= TABLES
    return code, a.labels


def patch(rom, verify=False):
    rom = bytearray(rom)
    if len(rom) < 0x200000: rom += b'\x00' * (0x200000 - len(rom))
    code, L = build_code(verify)
    tb = bytearray(tables()); tb += bytes(8)
    for k in range(4): tb[0x428 + 2 * k:0x42A + 2 * k] = ((L['hb%d' % k] - 1) & 0xFFFF).to_bytes(2, 'little')
    for addr, blob in ((CODE, code), (TABLES, bytes(tb))):
        o = lorom(addr); assert all(b == 0 for b in rom[o:o + len(blob)]), 'area not free'
        rom[o:o + len(blob)] = blob
    def put(addr, old, new):
        f = lorom(addr); assert rom[f:f + len(old)] == old, (hex(addr), rom[f:f + len(old)].hex()); rom[f:f + len(new)] = new
    jsl = lambda t: bytes([0x22, t & 0xFF, (t >> 8) & 0xFF, t >> 16])
    put(0x80B8DF, bytes.fromhex('5A9B20DBB17A'), jsl(L['spr']) + b'\xEA\xEA')
    rom[0x7FD7] = 0x0B
    rom[0x7FDC:0x7FE0] = b'\xFF\xFF\x00\x00'; s = sum(rom) & 0xFFFF
    rom[0x7FDC:0x7FDE] = (s ^ 0xFFFF).to_bytes(2, 'little'); rom[0x7FDE:0x7FE0] = s.to_bytes(2, 'little')
    return bytes(rom)


if __name__ == '__main__':
    src = open(sys.argv[1], 'rb').read(); out = sys.argv[2]
    new = patch(src)
    open(out + '.sfc', 'wb').write(new); open(out + '.ips', 'wb').write(make_ips(src, new))
    print('code', len(build_code()[0]), 'bytes; ROM CRC32 %08X' % zlib.crc32(new))
