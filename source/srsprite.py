"""Shadowrun (SNES) sprite editor round trip: export an editable sheet, import the edited PNG back into the ROM.

  python3 srsprite.py export ROM SPRITE_HEX [OUT.png]          -> sprite_XX_edit.png
  python3 srsprite.py import ROM EDITED.png [SPRITE_HEX] [OUT] [--own]  -> OUT.sfc + OUT.ips + report
      --own: a recoloured palette that other sprites also use becomes this sprite's own palette (srpal.py)
      instead of recolouring everyone who shares it. Apply after the Runner Pack.
      (the sprite number is taken from the file name 'sprite_XX...' when not given)
  python3 srsprite.py list ROM                                  -> sprite numbers with names

The editable sheet
  * Top rows: one row of 16 swatches per palette the sprite uses (swatch 0 = transparent, not editable).
    Change a swatch colour to recolour every pixel that uses it. Palettes are shared between sprites
    (Jake's palette is also used by others), and the import report lists who else is affected.
  * Below: one block per animation, one row per facing, frames left to right, exactly as the game stores them.
    Magenta (255,0,255) inside a frame = transparent. Dark grey around frames is ignored.
  * Draw only with the palette's colours. Other colours snap to the nearest palette colour (reported).
  * The same 16x16 graphics cell is often reused by several frames, facings (mirrored) and animations.
    Editing any one copy changes all of them; if two copies were edited differently, the first edited copy
    wins and the report says so. Cells drawn as grey have no graphics in the ROM and cannot be painted.
  * The SNES stores colours as 15-bit, so swatch colours are rounded to multiples of 8.
"""
import sys, os, re, json
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import srgfx, srpal

GREY = (40, 40, 48); KEY = (255, 0, 255); EMPTY = (64, 64, 76)
SW = 8          # swatch size
GAP = 2


def L(a): return ((a & 0x7F0000) >> 1) | (a & 0x7FFF)


def frame_cells(rom, word):
    """-> dict(w, h, cells=[(x, y, top_word, bottom_word, hflip, vflip) or (x, y, None...) for empty])"""
    p = L(((0x9C if word & 0x8000 else 0x9B) << 16) | word | 0x8000)
    n = rom[p]; words = [rom[p + 1 + 2 * i] | rom[p + 2 + 2 * i] << 8 for i in range(2 * n)]
    h = p + 1 + 4 * n; cols, rows = rom[h + 2] & 15, rom[h + 2] >> 4
    cells = []; k = 0
    for c in range(cols):
        for r in range(rows):
            cb = rom[h + 3 + c * rows + r]
            if cb & 0x20 or k + 1 >= len(words) + 1:
                cells.append((c * 16, r * 16, None, None, False, False)); continue
            cells.append((c * 16, r * 16, words[k], words[k + 1], bool(cb & 0x40), bool(cb & 0x80))); k += 2
    return dict(w=cols * 16, h=rows * 16, cells=cells, rec=p, nwords=2 * n)


def layout(rom, s):
    """Deterministic sheet layout for sprite s (same on export and import)."""
    srgfx.rom = rom; srgfx._REC = None
    anims, seen = [], set()
    for a in srgfx.animations(s):
        if a['record'] in seen: continue
        seen.add(a['record']); anims.append(a)
    pals = []
    for a in anims:
        if a['palette'] not in pals: pals.append(a['palette'])
    top = len(pals) * (SW + GAP) + 6
    blocks = []; x0 = 4; maxh = 16
    for a in anims:
        fr = []
        for f, words in enumerate(a['facings']):
            row = []
            for w in words:
                try: fc = frame_cells(rom, w)
                except Exception: continue
                if fc['w'] and fc['h']: row.append((w, fc))
            fr.append(row)
        if not any(fr): continue
        bw = max(sum(fc['w'] + GAP for w, fc in row) for row in fr if row) + 6
        maxh = max([maxh] + [fc['h'] for row in fr for w, fc in row])
        blocks.append(dict(anim=a['index'], palette=a['palette'], x=x0, rows=fr)); x0 += bw
    rowh = maxh + 4
    frames = []
    for b in blocks:
        for f, row in enumerate(b['rows']):
            x = b['x']
            for w, fc in row:
                y = top + f * rowh + (rowh - 4 - fc['h'])
                frames.append(dict(anim=b['anim'], facing=f, word=w, x=x, y=y, palette=b['palette'], **fc))
                x += fc['w'] + GAP
    return dict(sprite=s, palettes=pals, width=max(x0, 16 * (SW + GAP)) + 4, height=top + 8 * rowh + 4, frames=frames)


def strip_pixels(rom, word):
    return srgfx.strip(word)


def cell_pixels(rom, top, bot):
    c = np.zeros((16, 16), np.uint8); c[:8] = srgfx.strip(top); c[8:] = srgfx.strip(bot); return c


def encode_tile(px):
    """8x8 indices -> 32 bytes SNES 4bpp"""
    b = bytearray(32)
    for y in range(8):
        for x in range(8):
            v = int(px[y, x]); m = 0x80 >> x
            if v & 1: b[y * 2] |= m
            if v & 2: b[y * 2 + 1] |= m
            if v & 4: b[16 + y * 2] |= m
            if v & 8: b[16 + y * 2 + 1] |= m
    return bytes(b)


def strip_addr(word): return L(((0x8E + (word & 0x3F)) << 16) | (word & 0xFFC0) | 0x8000)
def pal_addr(pid): return srpal.pal_addr(pid)


def snes_color(rgb): r, g, b = rgb; return (r >> 3) | ((g >> 3) << 5) | ((b >> 3) << 10)
def rgb_color(w): return ((w & 31) << 3, ((w >> 5) & 31) << 3, ((w >> 10) & 31) << 3)


def read_palette(rom, pid):
    a = pal_addr(pid); return [rgb_color(rom[a + 2 * i] | rom[a + 2 * i + 1] << 8) for i in range(16)]


def export(rom, s, path):
    lay = layout(rom, s)
    img = np.zeros((lay['height'], lay['width'], 3), np.uint8); img[:] = GREY
    for i, pid in enumerate(lay['palettes']):
        P = read_palette(rom, pid); y = 4 + i * (SW + GAP)
        for k in range(16):
            x = 4 + k * (SW + GAP); img[y:y + SW, x:x + SW] = KEY if k == 0 else P[k]
    for fr in lay['frames']:
        P = read_palette(rom, fr['palette'])
        for (cx, cy, top, bot, hf, vf) in fr['cells']:
            X, Y = fr['x'] + cx, fr['y'] + cy
            if top is None: img[Y:Y + 16, X:X + 16] = EMPTY; continue
            c = cell_pixels(rom, top, bot)
            if hf: c = c[:, ::-1]
            if vf: c = c[::-1, :]
            rgb = np.zeros((16, 16, 3), np.uint8); rgb[:] = KEY
            for k in range(1, 16): rgb[c == k] = P[k]
            img[Y:Y + 16, X:X + 16] = rgb
    Image.fromarray(img).save(path)
    return lay


_USERS = {}


def _scan(rom):
    key = id(rom)
    if key not in _USERS:
        strips, recs, pals = {}, {}, {}
        for sp in range(0x113):
            try: lay = layout(rom, sp)
            except Exception: continue
            pals[sp] = lay['palettes']
            for fr in lay['frames']:
                recs.setdefault(fr['rec'], set()).add(sp)
                for c in fr['cells']:
                    if c[2] is None: continue
                    for w in (c[2], c[3]): strips.setdefault(w, set()).add((sp, (c[2], c[3])))
        _USERS[key] = (strips, recs, pals)
    return _USERS[key]


def strip_users(rom): return _scan(rom)[0]
def rec_users(rom): return _scan(rom)[1]
def sprite_palettes(rom): return _scan(rom)[2]


# Free space for copied strips: $BC:8000-$BD:FFFF (unused by the Runner Pack and Expanded Dialogue).
# $BC:8000 holds 'SRSPR' + a 16-bit count of strips handed out; strips follow from $BC:8040, 64 bytes each.
POOL = L(0xBC8000); POOL_END = L(0xBDFFFF) + 1


def ensure_2mb(new):
    if len(new) < 0x200000:
        new.extend(b'\0' * (0x200000 - len(new))); new[0x7FD7] = 0x0B      # header ROM size: 16 Mbit
    return new


def alloc_strip(new):
    ensure_2mb(new)
    if new[POOL:POOL + 5] != b'SRSPR':
        if any(new[POOL:POOL_END]): raise SystemExit('$BC:8000-$BD:FFFF is not empty in this ROM; cannot add graphics there.')
        new[POOL:POOL + 5] = b'SRSPR'; new[POOL + 5:POOL + 7] = b'\0\0'
    n = new[POOL + 5] | new[POOL + 6] << 8
    off = POOL + 0x40 + 64 * n
    if off + 64 > POOL_END: raise SystemExit('The sprite graphics pool is full (1023 strips).')
    new[POOL + 5] = (n + 1) & 0xFF; new[POOL + 6] = (n + 1) >> 8
    snes = 0x800000 | ((off >> 15) << 16) | 0x8000 | (off & 0x7FFF)
    return (snes & 0xFFC0) | (((snes >> 16) - 0x8E) & 0x3F)


def ips_diff(old, new):
    grew_from = len(old)
    out = bytearray(b'PATCH'); old = bytes(old) + b'\0' * max(0, len(new) - len(old)); i = 0; n = len(new)
    while i < n:
        if old[i] == new[i]: i += 1; continue
        j = i
        while j < n and j - i < 0xFFFF and (old[j] != new[j] or (j + 1 < n and old[j + 1] != new[j + 1])): j += 1
        start = i
        if start == 0x454F46: start -= 1        # 'EOF' offset is reserved
        out += start.to_bytes(3, 'big') + (j - start).to_bytes(2, 'big') + new[start:j]; i = j
    if len(new) > grew_from: out += (len(new) - 1).to_bytes(3, 'big') + b'\0\x01' + new[-1:]   # pin the new file size
    out += b'EOF'; return bytes(out)


def import_(rom, s, path, own=False):
    lay = layout(rom, s); src = np.array(Image.open(path).convert('RGB')).astype(np.int32)
    if src.shape[0] < lay['height'] or src.shape[1] < lay['width']:
        raise SystemExit('The image is %dx%d but sprite %02X needs %dx%d. Was it resized or cropped?' % (
            src.shape[1], src.shape[0], s, lay['width'], lay['height']))
    new = bytearray(rom); rep = dict(sprite='%02X' % s, palettes_changed=[], cells_changed=0, pixels_snapped=0,
                                     conflicts=0, painted_empty=0, shared_palette_users={})
    # palettes
    newpal = {}
    for i, pid in enumerate(lay['palettes']):
        old = read_palette(rom, pid); P = list(old); y = 4 + i * (SW + GAP)
        for k in range(1, 16):
            x = 4 + k * (SW + GAP); c = tuple(int(v) for v in src[y + SW // 2, x + SW // 2])
            c = tuple((v >> 3) << 3 for v in c)
            if c != old[k]: P[k] = c
        newpal[pid] = (old, P)
        if P != old:
            others = [o for o, pals in sprite_palettes(rom).items() if pid in pals and o not in srpal.sprite_records(rom, s)[1]]
            if own and others:      # give this sprite (and sprites sharing its animations) a palette of its own
                cols = [rom[pal_addr(pid)] | rom[pal_addr(pid) + 1] << 8] + [snes_color(P[k]) for k in range(1, 16)]
                npid = srpal.new_palette(new, cols, pid)
                for o in srpal.sprite_records(rom, s)[1]: srpal.set_sprite_palette(new, o, pid, npid)
                rep.setdefault('own_palettes', {})['%02X' % pid] = '%02X' % npid
                continue
            rep['palettes_changed'].append('%02X' % pid); a = pal_addr(pid)
            for k in range(1, 16):
                w = snes_color(P[k]); new[a + 2 * k] = w & 0xFF; new[a + 2 * k + 1] = w >> 8
    # cells
    decided = {}
    for fr in lay['frames']:
        old, P = newpal[fr['palette']]
        newarr = np.array(P[1:], np.int32); oldarr = np.array(old[1:], np.int32)
        for (cx, cy, top, bot, hf, vf) in fr['cells']:
            X, Y = fr['x'] + cx, fr['y'] + cy; blk = src[Y:Y + 16, X:X + 16]
            if top is None:
                if (np.abs(blk - np.array(EMPTY)).sum(axis=2) > 0).any(): rep['painted_empty'] += 1
                continue
            orig = cell_pixels(rom, top, bot)
            if hf: orig = orig[:, ::-1]
            if vf: orig = orig[::-1, :]
            Pn = np.array(P, np.int32); Po = np.array(old, np.int32)
            q = (blk >> 3) << 3
            keep = (orig > 0) & (((q == Pn[orig]).all(axis=2)) | ((q == Po[orig]).all(axis=2)))
            iskey = (np.abs(blk - np.array(KEY)) <= 8).all(axis=2)
            idx = np.where(keep, orig, 0).astype(np.uint8)
            for yy, xx in zip(*np.nonzero(~keep & ~iskey)):
                c = q[yy, xx]
                hit = np.where((newarr == c).all(axis=1))[0]
                if not len(hit): hit = np.where((oldarr == c).all(axis=1))[0]
                if len(hit): idx[yy, xx] = hit[0] + 1; continue
                idx[yy, xx] = int(np.argmin(((newarr - blk[yy, xx]) ** 2).sum(axis=1))) + 1; rep['pixels_snapped'] += 1
            if hf: idx = idx[:, ::-1]
            if vf: idx = idx[::-1, :]
            key = (top, bot); orig = cell_pixels(rom, top, bot)
            if key in decided:
                if not np.array_equal(decided[key], idx) and not np.array_equal(idx, orig):
                    if np.array_equal(decided[key], orig): decided[key] = idx      # this copy is the edited one
                    else: rep['conflicts'] += 1
                continue
            decided[key] = idx
    changed = {k: v for k, v in decided.items() if not np.array_equal(v, cell_pixels(rom, *k))}
    rep['cells_changed'] = len(changed)
    if changed:
        users = strip_users(rom)
        mine_recs = {fr['rec']: fr['nwords'] for fr in lay['frames']}
        remap = {}                                       # cell (top, bot) -> new (top, bot)
        for key, idx in changed.items():
            newkey = list(key)
            for h, (word, half) in enumerate(((key[0], idx[:8]), (key[1], idx[8:]))):
                data = encode_tile(half[:, :8]) + encode_tile(half[:, 8:])
                if users.get(word, set()) <= {(s, key)}:     # strip used only by this cell of this sprite
                    a = strip_addr(word); new[a:a + 64] = data
                else:                                        # shared: give this cell its own copy
                    nw = alloc_strip(new); a = strip_addr(nw); new[a:a + 64] = data; newkey[h] = nw
            if tuple(newkey) != key: remap[key] = tuple(newkey)
        if remap:
            rep['strips_copied'] = sum((a != b) + (c != d) for (a, c), (b, d) in remap.items())
            touched = set()
            for rec, nw in mine_recs.items():
                for i in range(0, nw, 2):
                    o = rec + 1 + 2 * i
                    pair = (rom[o] | rom[o + 1] << 8, rom[o + 2] | rom[o + 3] << 8)
                    if pair in remap:
                        t, b2 = remap[pair]; new[o:o + 4] = bytes([t & 0xFF, t >> 8, b2 & 0xFF, b2 >> 8]); touched.add(rec)
            ru = rec_users(rom)
            rep['frames_shared_with_other_sprites'] = sorted({'%02X' % o for r in touched for o in ru.get(r, set()) - {s}})
    # who else uses the palettes we changed
    if rep['palettes_changed']:
        for other, pals in sprite_palettes(rom).items():
            if other == s: continue
            for pid in pals:
                if '%02X' % pid in rep['palettes_changed']: rep['shared_palette_users'].setdefault('%02X' % pid, []).append('%02X' % other)
    srgfx.rom = rom; srgfx._REC = None
    return bytes(new), rep


def names(rom):
    try:
        src = open(os.path.join(HERE, 'dump_scripts.py')).read().split('# ---------------------------------------------------------------- object types')[0]
        argv = sys.argv; sys.argv = ['x', '/dev/null', '/nonexistent']
        g = {'__name__': 'ds', '__doc__': ''}
        import builtins
        g['open'] = lambda f, m='r', *a: builtins.open(ROMPATH if f == '/dev/null' else f, m, *a)
        exec(compile(src, 'dump_scripts.py', 'exec'), g); sys.argv = argv
        return {s: g['sprite_name'](s) for s in range(0x113)}
    except Exception: return {}


if __name__ == '__main__':
    cmd, ROMPATH = sys.argv[1], sys.argv[2]
    rom = open(ROMPATH, 'rb').read()
    if cmd == 'export':
        s = int(sys.argv[3], 16); out = sys.argv[4] if len(sys.argv) > 4 else 'sprite_%02X_edit.png' % s
        lay = export(rom, s, out); print('wrote', out, '%dx%d' % (lay['width'], lay['height']), 'palettes', ['%02X' % p for p in lay['palettes']])
    elif cmd == 'import':
        own = '--own' in sys.argv; args = [a for a in sys.argv if a != '--own']
        path = args[3]
        m = re.search(r'sprite_([0-9A-Fa-f]{2})', os.path.basename(path))
        s = int(args[4], 16) if len(args) > 4 else int(m.group(1), 16)
        out = args[5] if len(args) > 5 else os.path.splitext(path)[0] + '_patched'
        new, rep = import_(rom, s, path, own)
        open(out + '.sfc', 'wb').write(new); open(out + '.ips', 'wb').write(ips_diff(rom, new))
        print(json.dumps(rep, indent=1)); print('wrote', out + '.sfc', out + '.ips')
    elif cmd == 'list':
        for s, n in sorted(names(rom).items()): print('%02X %s' % (s, n))
