"""Shadowrun (SNES) extra sprite palettes: give a sprite its own palette instead of a shared one.

How the game colours sprites
  animation record (bank $8C) +2 = palette id -> object field $1264. Every draw pass $80AA97 gives each palette id
  in use one of the 8 OBJ palettes (table $1802 + 2*id = slot*2, list $17F2 = ids in slot order, $17F0 = next slot*2;
  reset by $81A7FC each pass). In NMI, $81A8D5 DMAs 15 colours of each listed id from $8D:F1CC + 32*id to CGRAM
  $81 + 16*slot. Ids 0-69 exist and all 70 are used; $1802's table ends at $188C (the sprite mask grid follows) and
  palette data after id 69 is other data. The original game uses at most 7 slots in ordinary scenes.

This patch (bank $AF, RAM $7F:C630-$7F:C67F)
  $AF:8000 'SRPAL' 1, $AF:8006 word = extra ids used, $AF:8010 + n = original id of extra id 70+n (fallback),
  $AF:9000 + 32*n = colours of extra id 70+n (ids 70-109, 40 extra palettes).
  $80AA97 -> JML $AF8100 (JSL core; JML $80AAB2): ids < 70 as before; ids 70+ use the slot table at $7F:C630 and,
  when 7 slots are already taken, fall back to their original shared id (old colours instead of a broken screen).
  A 9th palette in one pass (never seen in the original game, max 7) now shares slot 7 instead of overwriting
  CGRAM / the $1802 table.
  $81A8D1 (last store of the per-pass reset + RTL) -> JML $AF8180: also clears $7F:C630.
  $81A8E1 (NMI upload body) -> JSL $AF8200: reads ids 70+ from bank $AF.
  Runner Pack sprite cache: its inline copy of $80AA97 (pattern B9 64 12 0A AA BD 02 18 ...) is redirected to the core.
  Apply after the Runner Pack (or anything else that rebuilds bank $BF).
Usage (library): install(rom) ; pid = new_palette(rom, colours15, original_id) ; set_sprite_palette(rom, sprite, old, new)
"""
import struct

BASE_ID, MAX_EXTRA = 70, 40
SIG = 0xAF8000; COUNT = 0xAF8006; ORIG = 0xAF8010; CORE = 0xAF8100; CLEAR = 0xAF8180; NMI = 0xAF8200; DATA = 0xAF9000
EXT = 0x7FC630
CACHE_PATTERN = bytes.fromhex('B964120AAABD0218')


def L(a): return ((a & 0x7F0000) >> 1) | (a & 0x7FFF)


def _b(*x): return bytes(x)
def _w(v): return struct.pack('<H', v & 0xFFFF)
def _l(v): return bytes((v & 0xFF, (v >> 8) & 0xFF, (v >> 16) & 0xFF))


def core_code():
    """allocator, JSL-callable: A = palette id in, A = slot*2 out (X clobbered). RTL."""
    c = bytearray(); lab = {}; fix = []
    def br(op, name): c.extend(_b(op, 0)); fix.append((len(c) - 1, name))
    c += _b(0xC9) + _w(BASE_ID); br(0xB0, 'ext')                                   # cmp #70; bcs ext
    lab['van'] = len(c)
    c += _b(0x0A, 0xAA, 0xBD) + _w(0x1802); br(0x10, 'done')                       # asl; tax; lda $1802,x; bpl done
    c += _b(0xAD) + _w(0x17F0) + _b(0xC9) + _w(16); br(0xB0, 'full')              # 8 slots taken: no 9th (would
    c += _b(0x9D) + _w(0x1802) + _b(0x86, 0x6B, 0xAA, 0xA5, 0x6B, 0x9D) + _w(0x17F2)   # (a 9th would overwrite CGRAM and $1802)
    c += _b(0x8A, 0xE8, 0xE8, 0x8E) + _w(0x17F0)                                 # ... txa; inx; inx; stx $17F0
    lab['done'] = len(c); c += _b(0x6B)                                          # rtl
    lab['full'] = len(c); c += _b(0xA9) + _w(14) + _b(0x6B)                      # lda #14 (share slot 7); rtl
    lab['ext'] = len(c)
    c += _b(0xC9) + _w(BASE_ID + MAX_EXTRA); br(0xB0, 'van')                      # out of range: treat as vanilla
    c += _b(0x0A, 0xAA, 0xBF) + _l(EXT - 2 * BASE_ID); br(0x10, 'done')          # asl; tax; lda ext-140,x; bpl done
    c += _b(0xAD) + _w(0x17F0) + _b(0xC9) + _w(14); br(0xB0, 'fall')              # lda $17F0; cmp #14; bcs fallback
    c += _b(0x9F) + _l(EXT - 2 * BASE_ID) + _b(0x86, 0x6B, 0xAA, 0xA5, 0x6B, 0x9D) + _w(0x17F2)
    c += _b(0x8A, 0xE8, 0xE8, 0x8E) + _w(0x17F0) + _b(0x6B)
    lab['fall'] = len(c)
    c += _b(0x8A, 0x4A, 0xAA, 0xBF) + _l(ORIG - BASE_ID) + _b(0x29, 0xFF, 0x00)   # txa; lsr; tax; lda orig-70,x; and #$FF
    br(0x80, 'van')
    for at, name in fix:
        d = lab[name] - (at + 1); assert -128 <= d <= 127; c[at] = d & 0xFF
    return bytes(c)


def entry_code():  # at $AF:8100 is the core; the JML target from $80AA97 sits after it
    return _b(0x22) + _l(CORE) + _b(0x5C) + _l(0x80AAB2)


def clear_code():
    c = bytearray(_b(0x8D) + _w(0x188C) + _b(0xDA, 0xA2) + _w(2 * MAX_EXTRA - 2))  # sta $188C; phx; ldx #78
    loop = len(c); c += _b(0x9F) + _l(EXT) + _b(0xCA, 0xCA, 0x10, 0)              # sta ext,x; dex; dex; bpl loop
    c[-1] = (loop - len(c)) & 0xFF
    c += _b(0xFA, 0x6B)                                                            # plx; rtl
    return bytes(c)


def nmi_code():
    c = bytearray(); fix = []; lab = {}
    def br(op, name): c.extend(_b(op, 0)); fix.append((len(c) - 1, name))
    c += _b(0xB9) + _w(0x17F2) + _b(0xC9) + _w(2 * BASE_ID); br(0xB0, 'ext')        # lda $17F2,y (id*2); cmp #140
    c += _b(0x0A, 0x0A, 0x0A, 0x0A, 0x18, 0x69) + _w(0xF1CC) + _b(0x8D) + _w(0x4342) + _b(0xE2, 0x20, 0xA9, 0x8D); br(0x80, 'com')
    lab['ext'] = len(c)
    c += _b(0x38, 0xE9) + _w(2 * BASE_ID) + _b(0x0A, 0x0A, 0x0A, 0x0A, 0x18, 0x69) + _w((DATA + 2) & 0xFFFF)
    c += _b(0x8D) + _w(0x4342) + _b(0xE2, 0x20, 0xA9, DATA >> 16)
    lab['com'] = len(c)
    c += _b(0x8D) + _w(0x4344) + _b(0xC2, 0x20, 0xA9) + _w(0x001E) + _b(0x8D) + _w(0x4345)
    c += _b(0xE2, 0x20, 0x98, 0x0A, 0x0A, 0x0A, 0x18, 0x69, 0x81, 0x8D) + _w(0x2121)
    c += _b(0xA9, 0x10, 0x8D) + _w(0x420B) + _b(0xC2, 0x20, 0x6B)
    for at, name in fix:
        c[at] = (lab[name] - (at + 1)) & 0xFF
    return bytes(c)


def installed(rom): return len(rom) >= 0x200000 and rom[L(SIG):L(SIG) + 5] == b'SRPAL'


def install(rom):
    """rom: bytearray (expanded to 2 MB if needed). Idempotent."""
    if len(rom) < 0x200000:
        rom.extend(b'\0' * (0x200000 - len(rom))); rom[0x7FD7] = 0x0B
    v = lambda a, n: bytes(rom[L(a):L(a) + n])
    if not installed(rom):
        assert v(0x80AA97, 5) == bytes.fromhex('0AAABD0218'), 'unexpected code at $80AA97'
        assert v(0x81A8D1, 4) == bytes.fromhex('8D8C186B'), 'unexpected code at $81A8D1'
        assert v(0x81A8E1, 3) == bytes.fromhex('B9F217'), 'unexpected code at $81A8E1'
        rom[L(SIG):L(SIG) + 6] = b'SRPAL\x01'; rom[L(COUNT):L(COUNT) + 2] = b'\0\0'
    core = core_code(); ent = CORE + len(core)
    rom[L(CORE):L(CORE) + len(core)] = core
    e = entry_code(); rom[L(ent):L(ent) + len(e)] = e
    cl = clear_code(); rom[L(CLEAR):L(CLEAR) + len(cl)] = cl
    nm = nmi_code(); rom[L(NMI):L(NMI) + len(nm)] = nm
    rom[L(0x80AA97):L(0x80AA97) + 4] = _b(0x5C) + _l(ent)
    rom[L(0x81A8D1):L(0x81A8D1) + 4] = _b(0x5C) + _l(CLEAR)
    body = _b(0x22) + _l(NMI); n = 0x81A90B - 0x81A8E1
    rom[L(0x81A8E1):L(0x81A8E1) + n] = body + b'\xEA' * (n - len(body))
    # Runner Pack sprite cache: inline copy of the allocator (30 bytes from LDA $1264,Y) -> JSL core
    i = bytes(rom).find(CACHE_PATTERN, 0x100000)
    while i >= 0:
        seq = bytes(rom[i:i + 30])
        if seq[8] == 0x10 and seq[27] == 0x8E and seq[28:30] == b'\xF0\x17':
            rom[i:i + 30] = _b(0xB9) + _w(0x1264) + _b(0x22) + _l(CORE) + b'\xEA' * 23
        i = bytes(rom).find(CACHE_PATTERN, i + 1)
    return rom


def count(rom): return rom[L(COUNT)] | rom[L(COUNT) + 1] << 8 if installed(rom) else 0


def pal_addr(pid):
    """file offset of the 16 colours of palette id pid (shared or extra)"""
    return L(DATA + 32 * (pid - BASE_ID)) if pid >= BASE_ID else L(0x8DF1CA + 32 * pid)


def new_palette(rom, colours, orig):
    """colours: 16 SNES 15-bit words. Returns the new palette id."""
    install(rom); n = count(rom)
    if n >= MAX_EXTRA: raise SystemExit('All %d extra palettes are in use.' % MAX_EXTRA)
    pid = BASE_ID + n
    rom[pal_addr(pid):pal_addr(pid) + 32] = b''.join(_w(c) for c in colours)
    rom[L(ORIG + n)] = orig if orig < BASE_ID else rom[L(ORIG + orig - BASE_ID)]
    rom[L(COUNT):L(COUNT) + 2] = _w(n + 1)
    return pid


def sprite_records(rom, s):
    """animation record addresses (bank $8C) of sprite s, and the sprites sharing its animation table"""
    RW = lambda a: rom[L(a)] | rom[L(a) + 1] << 8
    T = RW(0x8CED8A + 2 * s); first = RW(0x8C0000 | T); n = (first - T) // 2
    if not 0 < n < 40: return [], [s]
    recs = [RW(0x8C0000 | ((T + 2 * k) & 0xFFFF)) for k in range(n)]
    group = [o for o in range(0x113) if RW(0x8CED8A + 2 * o) == T]
    return recs, group


def set_sprite_palette(rom, s, old, new):
    """point every animation record of sprite s that uses palette `old` at `new`. Returns records changed."""
    recs, _ = sprite_records(rom, s); n = 0
    for r in set(recs):
        a = L(0x8C0000 | r) + 2
        if rom[a] == old: rom[a] = new; n += 1
    return n
