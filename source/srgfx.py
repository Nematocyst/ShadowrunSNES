"""Shadowrun (SNES) sprite graphics: decode and render every sprite's animations from the ROM.

Format (worked out from draw_object $80B1DB, the frame loader $80AC52-$80AD80 and PLAY_ANIM $80A91E):
  * sprite id -> $8CED8A + 2*id: pointer (bank $8C) to that sprite's animation table: one word per animation.
    The number of animations = (first animation pointer - table) / 2.
  * animation record (bank $8C): +0 ?, +1 frame delay (bit 7 = loop), +2 palette id, +3..+7 hitbox/offsets,
    +8..+15 one byte per facing (8 facings): offset of that facing's frame list, counted from record+8.
    The frame list is a run of words; a facing's frames run up to the next facing's offset.
  * frame word: bit 15 picks bank $9C (else $9B), low 15 bits | $8000 = address of a frame record:
      [n] [2n graphics words] [x origin] [y origin] [rows<<4 | cols] [rows*cols cell bytes, column by column]
    cell byte: bit 5 = empty, bit 6 = flip horizontally, bit 7 = flip vertically. Each non-empty cell takes the
    next two graphics words: the 16x8 top half and the 16x8 bottom half.
  * graphics word: bank = $8E + (word & $3F), address = word & $FFC0 -> 64 bytes = two 8x8 4bpp tiles side by side.
    Sprite graphics are NOT compressed; they sit in banks $8E-$95 and are DMA'd to VRAM as the frame changes.
  * palette id p -> 16 colours (15-bit BGR) at $8DF1CA + $20*p; colour 0 is transparent.
Usage: python3 srgfx.py shadowrun.sfc OUTDIR      -> OUTDIR/sprite_XX.png for every sprite + index.json
"""
import sys, os, json
import numpy as np
from PIL import Image

rom = None


def L(a): return ((a & 0x7F0000) >> 1) | (a & 0x7FFF)
def RW(a): return rom[L(a)] | rom[L(a) + 1] << 8


def tile4(b):
    img = np.zeros((8, 8), np.uint8)
    for y in range(8):
        for p in range(4):
            byte = b[(p // 2) * 16 + y * 2 + (p & 1)]
            for x in range(8): img[y, x] |= ((byte >> (7 - x)) & 1) << p
    return img


def strip(word):
    o = L(((0x8E + (word & 0x3F)) << 16) | (word & 0xFFC0) | 0x8000)
    h = np.zeros((8, 16), np.uint8); h[:, :8] = tile4(rom[o:o + 32]); h[:, 8:] = tile4(rom[o + 32:o + 64]); return h


def palette(pid):
    a = L(0x8DF1CA + 0x20 * pid) if pid < 70 else L(0xAF9000 + 0x20 * (pid - 70)); out = []   # 70+: srpal.py extras
    for i in range(16):
        w = rom[a + 2 * i] | rom[a + 2 * i + 1] << 8
        out.append(((w & 31) << 3, ((w >> 5) & 31) << 3, ((w >> 10) & 31) << 3))
    return out


def frame(word):
    """-> (index image int16 with -1 = transparent, (x origin, y origin))"""
    p = L(((0x9C if word & 0x8000 else 0x9B) << 16) | word | 0x8000)
    n = rom[p]; words = [rom[p + 1 + 2 * i] | rom[p + 2 + 2 * i] << 8 for i in range(2 * n)]
    h = p + 1 + 4 * n; cols, rows = rom[h + 2] & 15, rom[h + 2] >> 4
    img = np.full((rows * 16, cols * 16), -1, np.int16); k = 0
    for c in range(cols):
        for r in range(rows):
            cb = rom[h + 3 + c * rows + r]
            if cb & 0x20 or k + 1 >= len(words) + 1: continue
            cell = np.zeros((16, 16), np.uint8); cell[:8] = strip(words[k]); cell[8:] = strip(words[k + 1]); k += 2
            if cb & 0x40: cell = cell[:, ::-1]
            if cb & 0x80: cell = cell[::-1, :]
            img[r * 16:r * 16 + 16, c * 16:c * 16 + 16] = np.where(cell > 0, cell.astype(np.int16), -1)
    return img, (rom[h], rom[h + 1])


_REC = None


def _records():
    """sorted addresses of every animation record (they are packed in bank $8C), used to bound frame lists"""
    global _REC
    if _REC is None:
        r = set()
        for sp in range(0x113):
            T = RW(0x8CED8A + 2 * sp); first = RW(0x8C0000 | T); n = (first - T) // 2
            if 0 < n < 40:
                r.add(T)
                for k in range(n): r.add(RW(0x8C0000 | ((T + 2 * k) & 0xFFFF)))
        _REC = sorted(r)
    return _REC


def valid_frame(w):
    try:
        p = L(((0x9C if w & 0x8000 else 0x9B) << 16) | w | 0x8000); n = rom[p]
        if not 0 < n <= 24: return False
        h = p + 1 + 4 * n; c, r = rom[h + 2] & 15, rom[h + 2] >> 4
        return 0 < c <= 8 and 0 < r <= 8
    except Exception: return False


def animations(s):
    T = RW(0x8CED8A + 2 * s); first = RW(0x8C0000 | T); n = (first - T) // 2
    if not 0 < n < 40: return []
    recs = _records(); out = []
    for k in range(n):
        A = RW(0x8C0000 | ((T + 2 * k) & 0xFFFF)); b = rom[L(0x8C0000 | A):L(0x8C0000 | A) + 16]
        idx = list(b[8:16])
        if any(i % 2 or i > 240 or 0 < i < 8 for i in idx) or not any(idx): continue
        nxt = min([r for r in recs if r > A] + [A + 256])
        facings = []
        for f in range(8):
            if not idx[f]: facings.append([]); continue
            later = [i for i in idx if i > idx[f]]
            end = min(later) if later else (nxt - A - 8)
            ws = []
            for j in range(max(1, (end - idx[f]) // 2)):
                w = RW(0x8C0000 | ((A + 8 + idx[f] + 2 * j) & 0xFFFF))
                if not valid_frame(w): break
                ws.append(w)
                if len(ws) >= 24: break
            facings.append(ws)
        out.append(dict(index=k, record=0x8C0000 | A, palette=b[2], delay=b[1], facings=facings))
    return out


def sheet(s, bg=(40, 40, 48)):
    """columns = animations, rows = the 8 facings. Returns (PIL image, info) or (None, None)."""
    blocks, info, seen = [], [], set()
    for a in animations(s):
        if a['record'] in seen: continue
        seen.add(a['record']); P = palette(a['palette']); blk = []
        for fr in a['facings']:
            line = []
            for w in fr:
                try: img, org = frame(w)
                except Exception: continue
                if img.size == 0: continue
                rgb = np.zeros(img.shape + (3,), np.uint8); rgb[:] = bg
                for c in range(1, 16): rgb[img == c] = P[c]
                line.append(rgb)
            blk.append(line)
        blk = [line for line in blk if line] or blk
        if any(blk): blocks.append(blk); info.append(dict(anim=a['index'], palette=a['palette'], frames=max(len(f) for f in a['facings'])))
    if not blocks: return None, None
    H = max(t.shape[0] for blk in blocks for line in blk for t in line) + 4
    widths = [max(sum(t.shape[1] + 2 for t in line) for line in blk) + 8 for blk in blocks]
    out = np.zeros((H * 8 + 4, sum(widths) + 4, 3), np.uint8); out[:] = (24, 24, 30); x0 = 4
    for bw, blk in zip(widths, blocks):
        for r, line in enumerate(blk[:8]):
            x = x0
            for rgb in line:
                h, w = rgb.shape[:2]; y = r * H + (H - 4 - h) + 4; out[y:y + h, x:x + w] = rgb; x += w + 2
        out[:, x0 + bw - 5:x0 + bw - 4] = (60, 60, 72); x0 += bw
    return Image.fromarray(out), info


if __name__ == '__main__':
    rom = open(sys.argv[1], 'rb').read(); OUT = sys.argv[2]; os.makedirs(OUT, exist_ok=True)
    sys.argv = [sys.argv[0], sys.argv[1], '/nonexistent']
    names = {}
    try:   # sprite names from the hover-label table
        HERE = os.path.dirname(os.path.abspath(__file__))
        src = open(os.path.join(HERE, 'dump_scripts.py')).read().split('# ---------------------------------------------------------------- object types')[0]
        g = {'__name__': 'ds', '__doc__': ''}; exec(compile(src, 'dump_scripts.py', 'exec'), g)
        for s in range(0x113):
            sp = g['sprite_name'](s) if 'sprite_name' in g else ''
            names[s] = sp
    except Exception as ex: print('names unavailable:', ex)
    index = []
    for s in range(0x113):
        try: im, info = sheet(s)
        except Exception as ex: im = None; print('sprite %02X failed: %s' % (s, ex))
        if im is None: continue
        im.save(os.path.join(OUT, 'sprite_%02X.png' % s))
        index.append(dict(sprite=s, name=names.get(s, ''), anims=info, size=im.size))
    json.dump(index, open(os.path.join(OUT, 'index.json'), 'w'), indent=1)
    print('sprites rendered:', len(index))
