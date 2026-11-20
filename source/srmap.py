"""Shadowrun (SNES) map renderer: builds a map's two background layers straight from the ROM.

A Python port of the game's map builder ($81A117 layout loader, $81903E piece placer, $818E57 tile merger).

Data chain
  location -> map data ($8D92AF+9*loc): +0 layout number, +1 music, +2 exit-zone pointer, +4 objects...
  layout n -> 3-byte pointer $8BFA53+3n -> compressed layout (srlz). Decompressed:
      word  (-> $0D2E)
      byte  tile/height set (pointers $8DF1B2/$8DF1BE, used for walk/occlusion shapes)
      byte  shape count, then shapes: word w, then word (w >= 0) or byte+word (w < 0)   [walls/heights, not drawn]
      byte  count, then pieces for layer A (BG, drawn first)
      byte  count, then pieces for layer B (foreground, BG priority bit set)
  piece entry (5 bytes): word w, byte z (signed, *8), byte x, byte y
      w bit 15 = mirror, bit 14 / 13 = high (sign) bits of y / x, bits 0-12 = piece number
  piece number p -> word $8AC36A+2p -> piece record in bank $8A:
      +0 block count, +1 cell offset (normal), +3 cell offset (mirrored), +5 depth offset,
      +8 blocks, 5 bytes each: word b (bit 15 = mirror, rest = block number), byte row, byte column, byte depth
  block number b -> 3-byte pointer $96C45E+3b -> block (banks $96+):
      +0 low nibble = columns-1, high nibble = rows-1
      +1 bit 7 = one depth byte per column (else one per tile), bits 0-6 = palette number
      then column by column, row by row: [depth byte] tile word (0 = nothing). Tile word: bits 0-13 tile id
      (srlz.map_tile), bit 14 = flip horizontally, bit 15 = flip vertically.
  Each 8x8 cell of a layer keeps up to 3 tiles sorted by depth (bigger depth = further back); a tile further
  back than a full cell's three is dropped, otherwise the furthest one is pushed out. The cell's palette is the
  palette of its nearest tile. Tiles are merged back to front, colour 0 transparent.
  BG palette p -> 16 colours at $8CF622 + $20*p.
  A layer is 96 columns x 64 rows of 8x8 cells (768x512 px), stored column by column in the game.
Usage: python3 srmap.py shadowrun.sfc LOC_HEX [out.png]      (render a location's map)
       python3 srmap.py shadowrun.sfc piece P_HEX [out.png]   (render one building block)
Verified: for all 194 real maps the two layer buffers this builds equal the game's own ($7E:7684 / $7E:4684 +
merged-tile triples $A684/$AE84/$B684 + palette slots $0D1A), cell for cell (384,596 cells).
"""
import sys, os
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import srlz

COLS, ROWS = 96, 64


def L(a): return ((a & 0x7F0000) >> 1) | (a & 0x7FFF)


class Map:
    def __init__(self, rom):
        self.rom = rom
    def b(self, a): return self.rom[L(a)]
    def w(self, a): return self.rom[L(a)] | self.rom[L(a + 1)] << 8
    def w3(self, a): return self.b(a) | self.b(a + 1) << 8 | self.b(a + 2) << 16

    def map_data(self, loc):
        p = self.w(0x8D92AF + 9 * loc); return ((0x99 + (p >> 15)) << 16) | (p | 0x8000)

    def layout_number(self, loc): return self.b(self.map_data(loc))

    def layout(self, n):
        data, _ = srlz.decompress(self.rom, self.w3(0x8BFA53 + 3 * n))
        d = data; i = 2
        tset = d[i]; i += 1
        nshape = d[i]; i += 1
        shapes = []
        for _ in range(nshape):
            w = d[i] | d[i + 1] << 8; i += 2
            if w & 0x8000: shapes.append((w, d[i], d[i + 1] | d[i + 2] << 8)); i += 3
            else: shapes.append((w, d[i] | d[i + 1] << 8)); i += 2
        layers = []
        for _ in range(2):
            n = d[i] if i < len(d) else 0; i += 1; pcs = []
            for _ in range(n):
                pcs.append((d[i] | d[i + 1] << 8, d[i + 2], d[i + 3], d[i + 4])); i += 5
            layers.append(pcs)
        return dict(word0=d[0] | d[1] << 8, tile_set=tset, shapes=shapes, layers=layers, size=len(d), used=i)

    # ------------------------------------------------------------------ building
    def build(self, n):
        lay = self.layout(n)
        self.pal_slots = []                      # palette numbers in the order the game allocates CGRAM slots
        out = []
        floor = self.floor(lay)
        for li, pieces in enumerate(lay['layers']):
            cells = [None] * (COLS * ROWS)       # each: dict(t=[tiles back..front], d=[depths], pal=slot)
            if li == 0: self.draw_floor(floor, lay['tile_set'], cells)
            for pc in pieces: self.place_piece(pc, cells)
            out.append(cells)
        return out, lay

    # ------------------------------------------------------------------ floor ("shapes", $818DE2 + $818EDF)
    def floor(self, lay):
        """Fill the floor grid (byte offsets like $7F:CA14: 0x80 bytes per grid column, 2 bytes per entry)."""
        g = {}
        def st(x, v):
            if x < 0xFFF: g[x] = v & 0xFFFF
        def line(x, n, v, step):               # $818D09 (step $7E) / $818D23 (step $82)
            while n >= 0 and not n & 0x8000:
                st(x, v); x = (x + step) & 0xFFFF; n -= 1
            return x
        for sh in lay['shapes']:
            w = sh[0]; x = w & 0x3FFE
            if not w & 0x8000:
                v = sh[1]; val, n = v & 0xFF, v >> 8
                line(x, n, val, 0x82 if w & 0x4000 else 0x7E)
            else:
                val = sh[1]; v = sh[2]; c2C, c29 = v & 0xFF, v >> 8
                if w & 0x4000:                   # $818D3D: a framed area (corners/edges get val+1..val+6)
                    save = val; val += 1
                    if x >= 0x80: st(x - 0x80, val + 6)
                    x0 = x; x = (x - 2) & 0xFFFF
                    x = line(x, c2C - 1, val, 0x7E)
                    val += 1; st(x, val + 3); x = (x + 0x82) & 0xFFFF
                    x = line(x, c29 - 1, val, 0x82)
                    val += 1; x = line((x0 + 2) & 0xFFFF, c29 - 1, val, 0x82)
                    val += 1; st(x, val + 2); x = (x + 0x7E) & 0xFFFF
                    x = line(x, c2C - 1, val, 0x7E)
                    st(x, val + 4)
                    x = x0; val = save
                # $818DC0: fill rows
                while True:
                    line(x, c2C, val, 0x7E)
                    c29 -= 1
                    if c29 < 0: break
                    x = (x + 0x80) & 0xFFFF
                    line(x, c2C - 1, val, 0x7E)
                    x = (x + 2) & 0xFFFF
        return g

    def draw_floor(self, g, tset, cells):
        p11 = 0x8D0000 | self.w(0x8DF1B2 + 2 * tset); p14 = 0x8D0000 | self.w(0x8DF1BE + 2 * tset)
        x = 0xBBE
        while x >= 0:
            v = g.get(x + 0x400, 0)            # $818EDF reads the grid at $7F:CE14 = grid + $400
            if v:
                pal = self.slot(self.b(p14 + v)); base = p11 + v * 16
                c0 = (x >> 7) * 4; r0 = x & 0x3F
                for i, (dc, dr) in enumerate(((0, 0), (1, 0), (2, 0), (3, 0), (0, 1), (1, 1), (2, 1), (3, 1))):
                    t = self.w(base + 2 * i)
                    if t:
                        col = c0 + dc; row = r0 + dr
                        if 0 <= col < COLS and 0 <= row < ROWS: cells[col * ROWS + row] = dict(t=[t], d=[0xFFFF], pal=pal)
            x -= 2
            if x >= 0: x &= 0xFFBF

    def slot(self, pid):
        if pid not in self.pal_slots: self.pal_slots.append(pid)
        return self.pal_slots.index(pid) + 1

    def place_piece(self, pc, cells):
        w, zb, xb, yb = pc
        flip29 = 0x4000 if w & 0x8000 else 0
        rec = 0x8A0000 | self.w(0x8AC36A + ((w << 1) & 0x3FFF))
        s38 = 0xFF00 if w & 0x4000 else 0
        s35 = 0xFF00 if w & 0x2000 else 0
        z = ((zb - 256) if zb & 0x80 else zb) * 8 & 0xFFFF
        x = ((xb | s35) * 4) & 0xFFFF
        y = ((yb | s38) * 4) & 0xFFFF
        d2F = ((x + y) & 0xFFFF) >> 1
        # row term. NOTE: the listing at $8190B8 reads as three LSRs (/8), but /4 is what reproduces the
        # game's buffers exactly (checked cell by cell on all 194 maps), so /4 it is.
        a = (-((d2F + z - 0x300) & 0xFFFF)) & 0xFFFF; a >>= 2
        if a & 0x2000: a |= 0xC000
        b = (((y - x + 0x280) & 0xFFFF) >> 3); b = ((b & 0xFF) << 8) | (b >> 8)
        c2C = (a + b) & 0xFFFF
        c2C = (c2C + self.w(rec + (3 if flip29 else 1))) & 0xFFFF
        d2F = (self.w(rec + 5) + d2F) & 0xFFFF
        nblk = self.b(rec)
        Y = 8
        for _ in range(nblk):
            wb = self.w(rec + Y); X = ((wb << 1) + wb) & 0x7FFF
            blk = self.w3(0x96C45E + X); Y += 2
            f35 = (0x4000 if wb & 0x8000 else 0) ^ flip29
            v = self.w(rec + Y); Y += 2
            pos = ((v & 0xFF) + c2C) & 0xFFFF
            pos = (pos - (v & 0xFF00)) & 0xFFFF if flip29 else (pos + (v & 0xFF00)) & 0xFFFF
            col0 = pos
            d3E = (self.b(rec + Y) + d2F) & 0xFFFF; Y += 1
            self.place_block(blk, pos, f35, d3E, cells)

    def place_block(self, blk, pos, f35, d3E, cells):
        b0 = self.b(blk); cols = b0 & 15; rows = b0 >> 4; left = rows
        b1 = self.b(blk + 1); flag = 0x7FFE if b1 & 0x80 else 0
        pal = self.slot(b1 & 0x7F)
        ty = 2; d50 = d3E; colpos = pos
        while True:
            flag = (flag + 1) & 0xFFFF
            if not flag & 0x8000: d50 = (self.b(blk + ty) + d3E) & 0xFFFF
            if pos < 0x2000 or pos >= 0x8000 or pos & 0x80:
                if not flag & 0x8000: ty += 1
                ty += 2
            else:
                if not flag & 0x8000: ty += 1
                t = self.w(blk + ty); ty += 2
                if t: self.put(cells, pos, t ^ f35, d50, pal)
            left -= 1
            if left >= 0: pos = (pos + 2) & 0xFFFF; continue
            if (flag + 1) & 0x8000: flag = 0x7FFE
            cols -= 1
            if cols < 0: break
            left = rows
            colpos = (colpos - 0x100) & 0xFFFF if f35 else (colpos + 0x100) & 0xFFFF
            pos = colpos

    def put(self, cells, pos, t, d, pal):
        col = (pos >> 8) - 32; row = (pos & 0x7F) >> 1
        k = col * ROWS + row
        c = cells[k]
        if c is None: cells[k] = dict(t=[t], d=[d], pal=pal); return
        T, D = c['t'], c['d']; n = len(T)
        p = 0
        while p < n and d < D[p]: p += 1       # entries further back than the new tile
        if n == 3:
            if p == 0: return                  # further back than three tiles: hidden
            del T[0]; del D[0]; p -= 1          # push the furthest out
        T.insert(p, t); D.insert(p, d)
        if p == len(T) - 1: c['pal'] = pal      # nearest tile decides the palette

    # ------------------------------------------------------------------ drawing
    def bg_palette(self, pid):
        a = 0x8CF622 + 0x20 * pid; out = []
        for i in range(16):
            v = self.w(a + 2 * i); out.append(((v & 31) << 3, ((v >> 5) & 31) << 3, ((v >> 10) & 31) << 3))
        return out

    _tiles = {}

    def tile(self, t):
        key = t & 0x3FFF
        if key not in self._tiles:
            d = srlz.map_tile(self.rom, key); img = np.zeros((8, 8), np.uint8)
            for p in range(4):
                for yy in range(8):
                    bb = d[p * 8 + yy]
                    for xx in range(8): img[yy, xx] |= ((bb >> (7 - xx)) & 1) << p
            self._tiles[key] = img
        img = self._tiles[key]
        if t & 0x4000: img = img[:, ::-1]
        if t & 0x8000: img = img[::-1, :]
        return img

    def piece_cells(self, p, flip=False):
        """One piece on its own (for catalogues). Returns (cells, None)."""
        self.pal_slots = []; cells = [None] * (COLS * ROWS)
        self.place_piece(((p & 0x1FFF) | (0x8000 if flip else 0), 0, 0x70, 0x70), cells)
        return [cells, [None] * (COLS * ROWS)], None

    def render_piece(self, p, flip=False):
        cl, _ = self.piece_cells(p, flip)
        img = self.draw(cl, (0,))
        ys, xs = np.nonzero(img.any(axis=2))
        if not len(ys): return None
        return img[ys.min():ys.max() + 1, xs.min():xs.max() + 1]

    def render(self, loc=None, layout=None, layers=(0, 1)):
        n = self.layout_number(loc) if layout is None else layout
        cells_by_layer, lay = self.build(n)
        return self.draw(cells_by_layer, layers), lay

    def draw(self, cells_by_layer, layers=(0, 1)):
        pals = [None] + [self.bg_palette(p) for p in self.pal_slots]
        img = np.zeros((ROWS * 8, COLS * 8, 3), np.uint8)
        for li in layers:
            for k, c in enumerate(cells_by_layer[li]):
                if c is None: continue
                col, row = divmod(k, ROWS)
                px = np.zeros((8, 8), np.uint8)
                for t in c['t']:
                    ti = self.tile(t); px = np.where(ti > 0, ti, px)
                P = pals[c['pal']] if c['pal'] < len(pals) else pals[1]
                blk = img[row * 8:row * 8 + 8, col * 8:col * 8 + 8]
                for v in range(1, 16): blk[px == v] = P[v]
        return img


if __name__ == '__main__':
    from PIL import Image
    rom = open(sys.argv[1], 'rb').read(); m = Map(rom)
    if sys.argv[2] == 'piece':
        p = int(sys.argv[3], 16); out = sys.argv[4] if len(sys.argv) > 4 else 'piece_%03X.png' % p
        Image.fromarray(m.render_piece(p)).save(out); print('->', out)
    else:
        loc = int(sys.argv[2], 16)
        img, lay = m.render(loc)
        out = sys.argv[3] if len(sys.argv) > 3 else 'map_%03X_rom.png' % loc
        Image.fromarray(img).save(out); print('layout', hex(m.layout_number(loc)), 'pieces', [len(x) for x in lay['layers']], '->', out)
