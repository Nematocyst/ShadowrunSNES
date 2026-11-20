// Shadowrun (SNES) map core: decompress / compress layouts, build and draw maps, collision boxes, ROM writing, IPS.
// Port of srlz.py + srmap.py (checked cell for cell against the game). Runs in the browser and in node.
(function (root) {
'use strict';
const COLS = 96, ROWS = 64;
const L = a => ((a & 0x7F0000) >> 1) | (a & 0x7FFF);
const POOL_FIRST = 0xB0, POOL_LAST = 0xB3, POOL_SIG = [0x53, 0x52, 0x4D, 0x41, 0x50]; // 'SRMAP'
const LIMITS = { bytes: 2048, boxes: 260, buckets: 1000, perLayer: 255, tiles: 1010, palettes: 7, shapes: 255 };

class Rom {
  constructor(u8) { this.d = u8; }
  b(a) { return this.d[L(a)]; }
  w(a) { return this.d[L(a)] | (this.d[L(a + 1)] << 8); }
  w3(a) { return this.b(a) | (this.b(a + 1) << 8) | (this.b(a + 2) << 16); }
}

// ---------------------------------------------------------------- LZ ($809E1E)
function bitlen(v) { let k = 0; while (v) { k++; v >>= 1; } return k; }
function kbits(rom, pos) { return pos < 256 ? rom.b(0x809FB6 + pos) : rom.b(0x809FB6 + ((pos >> 8) & 0xFF)) + 8; }

function decompress(rom, addr, size) {
  const bank = addr & 0xFF0000, base = addr & 0xFFFF;
  const rb = off => rom.b(bank | ((base + off) & 0xFFFF));
  const total = size == null ? (rb(0) | (rb(1) << 8)) : size;
  let pos = (rb(2) | (rb(3) << 8)) + 2, lit = 4, cnt = 0, reg = 0;
  const bit = () => { if (!cnt) { reg = (rb(pos) << 8) | rb(pos + 1); pos += 2; cnt = 16; }
    cnt--; const v = (reg >> 15) & 1; reg = (reg << 1) & 0xFFFF; return v; };
  const gamma = () => { let a = 1; while (!bit()) a = a * 2 + bit(); return a; };
  const out = [];
  outer: for (;;) {
    let n = gamma(); while (n--) out.push(rb(lit++));
    if (out.length >= total) break;
    for (;;) {
      const p = out.length, k = kbits(rom, p);
      let off = 0; for (let i = 0; i < k; i++) off = off * 2 + bit();
      const ln = gamma() + 2; for (let i = 0; i < ln; i++) out.push(out[off + i]);
      if (out.length >= total) break outer;
      if (!bit()) break;
    }
  }
  return { data: Uint8Array.from(out.slice(0, total)), used: Math.max(lit, pos) };
}

function gammaBits(v) { return 2 * bitlen(v) - 1; }
// Optimal-parse compressor for the same format. k(pos) = bit length of pos (the ROM table at $809FB6 is exactly that).
function compress(data) {
  const n = data.length, INF = 1e18;
  if (n === 0) throw new Error('empty');
  const maxlen = new Int32Array(n);
  for (let i = 1; i < n; i++) {
    let best = 0;
    for (let off = 0; off < i; off++) {
      let l = 0; while (i + l < n && data[off + l] === data[i + l]) l++;
      if (l > best) { best = l; if (i + best >= n) break; }
    }
    maxlen[i] = best;
  }
  // f = last token a match, g = last token a literal run
  const f = new Float64Array(n + 1).fill(INF), g = new Float64Array(n + 1).fill(INF);
  const fp = new Int32Array(n + 1), gp = new Int32Array(n + 1), fs = new Int8Array(n + 1);
  for (let j = 1; j <= n; j++) { g[j] = gammaBits(j) + 8 * j; gp[j] = 0; }
  for (let i = 1; i <= n; i++) {
    // literal run after a match at i (flag bit 0)
    if (f[i] < INF && i < n) {
      for (let j = i + 1; j <= n; j++) {
        const c = f[i] + 1 + gammaBits(j - i) + 8 * (j - i);
        if (c < g[j]) { g[j] = c; gp[j] = i; }
      }
    }
    if (i >= n) break;
    const ml = maxlen[i]; if (ml < 3) continue;
    const k = bitlen(i);
    const fromG = g[i], fromF = f[i] < INF ? f[i] + 1 : INF;
    const base = Math.min(fromG, fromF), src = fromG <= fromF ? 0 : 1;
    if (base >= INF) continue;
    for (let l = 3; l <= ml; l++) {
      const c = base + k + gammaBits(l - 2);
      if (c < f[i + l]) { f[i + l] = c; fp[i + l] = i; fs[i + l] = src; }
    }
  }
  // backtrack
  const toks = []; let j = n, st = f[n] < g[n] ? 0 : 1; // 0 = match, 1 = literal
  while (j > 0) {
    if (st === 0) { const i = fp[j]; toks.push({ t: 'm', at: i, len: j - i }); st = fs[j] === 0 ? 1 : 0; j = i; }
    else { const i = gp[j]; toks.push({ t: 'l', at: i, len: j - i }); j = i; st = 0; }
  }
  toks.reverse();
  // emit
  const bits = [], lits = [];
  const putBits = (v, k) => { for (let i = k - 1; i >= 0; i--) bits.push((v >> i) & 1); };
  const putGamma = v => { const k = bitlen(v); for (let i = k - 2; i >= 0; i--) { bits.push(0); bits.push((v >> i) & 1); } bits.push(1); };
  for (let t = 0; t < toks.length; t++) {
    const tk = toks[t];
    if (tk.t === 'l') { putGamma(tk.len); for (let i = 0; i < tk.len; i++) lits.push(data[tk.at + i]); }
    else {
      if (t > 0 && toks[t - 1].t === 'm') bits.push(1);
      let off = -1;
      for (let o = 0; o < tk.at; o++) { let l = 0; while (l < tk.len && data[o + l] === data[tk.at + l]) l++; if (l === tk.len) { off = o; break; } }
      if (off < 0) throw new Error('compress: lost match');
      putBits(off, bitlen(tk.at)); putGamma(tk.len - 2);
    }
    if (tk.t === 'm' && t + 1 < toks.length && toks[t + 1].t === 'l') bits.push(0);
  }
  while (bits.length % 16) bits.push(0);
  const out = [n & 0xFF, n >> 8, (2 + lits.length) & 0xFF, (2 + lits.length) >> 8, ...lits];
  for (let i = 0; i < bits.length; i += 8) { let v = 0; for (let b = 0; b < 8; b++) v = v * 2 + bits[i + b]; out.push(v); }
  return Uint8Array.from(out);
}

// ---------------------------------------------------------------- layouts
// Map data relocation (map editor): $80A3DA = JML $B88610; per-location override table at $B8:8000 (3 bytes per
// location, 0 = use the vanilla pointer), 'SRMAPDATA' at $B8:8600, relocated blocks from $B8:8800 to $BB:FFFF.
// The vanilla word at $8D92AF stays: natives #7E/#17 return it as the map's identity.
const MD_TABLE = 0xB88000, MD_SIG = 0xB88600, MD_HOOK = 0xB88610, MD_POOL = 0xB88800, MD_LAST = 0xBB;
function mdHooked(rom) { return rom.d.length >= 0x200000 && rom.b(0x80A3DA) === 0x5C && rom.w(0x80A3DB) === (MD_HOOK & 0xFFFF) && rom.b(0x80A3DD) === (MD_HOOK >> 16); }
function vanillaMapData(rom, loc) { const p = rom.w(0x8D92AF + 9 * loc); return ((0x99 + (p >> 15)) << 16) | (p | 0x8000); }
function mapData(rom, loc) {
  if (mdHooked(rom)) { const o = rom.w3(MD_TABLE + 3 * loc); if (o >> 16) return o; }
  return vanillaMapData(rom, loc);
}
function layoutNumber(rom, loc) { return rom.b(mapData(rom, loc)); }
function layoutPtr(rom, n) { return rom.w3(0x8BFA53 + 3 * n); }

function parseLayout(d) {
  let i = 2; const tset = d[i++]; const ns = d[i++]; const s0 = i;
  for (let s = 0; s < ns; s++) { const w = d[i] | (d[i + 1] << 8); i += 2; i += (w & 0x8000) ? 3 : 2; }
  const shapes = d.slice(s0, i), layers = [];
  for (let l = 0; l < 2; l++) {
    const c = i < d.length ? d[i] : 0; i++; const pcs = [];
    for (let k = 0; k < c; k++) { pcs.push(decodePiece(d[i] | (d[i + 1] << 8), d[i + 2], d[i + 3], d[i + 4])); i += 5; }
    layers.push(pcs);
  }
  return { word0: d[0] | (d[1] << 8), tset, nshapes: ns, shapes: Array.from(shapes), layers, trailing: Array.from(d.slice(Math.min(i, d.length))) };
}
function decodePiece(w, zb, xb, yb) {
  return { p: w & 0x1FFF, m: !!(w & 0x8000), x: (w & 0x2000) ? xb - 256 : xb, y: (w & 0x4000) ? yb - 256 : yb, z: zb & 0x80 ? zb - 256 : zb };
}
function encodePiece(pc) {
  const w = (pc.p & 0x1FFF) | (pc.m ? 0x8000 : 0) | (pc.y < 0 ? 0x4000 : 0) | (pc.x < 0 ? 0x2000 : 0);
  return [w & 0xFF, w >> 8, pc.z & 0xFF, pc.x & 0xFF, pc.y & 0xFF];
}
function serializeLayout(lay) {
  let ns = lay.nshapes, sh = lay.shapes;
  if (lay.fgrid) { const e = floorShapes(lay); ns = e.n; sh = e.bytes; }
  if (ns > 255) throw new Error('floor too complex (' + ns + ' runs, the game allows 255)');
  const out = [lay.word0 & 0xFF, lay.word0 >> 8, lay.tset, ns, ...sh];
  for (const pcs of lay.layers) { out.push(pcs.length); for (const pc of pcs) out.push(...encodePiece(pc)); }
  out.push(...(lay.trailing || []));
  return Uint8Array.from(out);
}
// ---------------------------------------------------------------- floors
// The floor is a 24 x 32 grid of 32x16 px metatiles (k = col*32 + row); grid byte offset = $400 + col*$80 + row*2.
function floorGrid(rom, lay) {
  const g = new Builder(rom).floor({ ...lay, fgrid: null }), out = new Array(24 * 32).fill(0);
  g.forEach((v, x) => { if (x < 0x400 || x > 0xFBE || (x & 0x41)) return; const k = ((x - 0x400) >> 7) * 32 + ((x & 0x3F) >> 1); if (k >= 0 && k < out.length) out[k] = v & 0xFF; });
  return out;
}
// Greedy runs of equal metatiles along one diagonal (shape w >= 0: 4 bytes, step $82 = col+1,row+1 or $7E = col+1,row-1).
function encodeFloor(grid, withZero) {   // withZero: cells to write are >= 0 (0 = erase), -1 = leave alone
  let best = null;
  const skip = withZero ? -1 : 0;
  for (const dr of [1, -1]) {
    const left = grid.slice(), bytes = []; let n = 0;
    for (let c = 0; c < 24; c++) for (let r = 0; r < 32; r++) {
      const v = left[c * 32 + r]; if (v === skip || (!withZero && !v)) continue;
      let len = 0;
      while (len < 255 && c + len + 1 < 24 && r + dr * (len + 1) >= 0 && r + dr * (len + 1) < 32 && left[(c + len + 1) * 32 + r + dr * (len + 1)] === v) len++;
      for (let i = 0; i <= len; i++) left[(c + i) * 32 + r + dr * i] = skip;
      const w = (0x400 + c * 0x80 + r * 2) | (dr > 0 ? 0x4000 : 0);
      bytes.push(w & 0xFF, w >> 8, v, len); n++;
    }
    if (!best || n < best.n) best = { n, bytes };
  }
  return best;
}
// Shapes for an edited floor: the original shapes plus runs for only the cells that changed (later shapes
// overwrite earlier ones), or a full re-encode when that is smaller.
function gridFromShapes(lay) {
  const g = new Builder(null).floor({ ...lay, fgrid: null }), out = new Array(24 * 32).fill(0);
  g.forEach((v, x) => { if (x < 0x400 || x > 0xFBE || (x & 0x41)) return; out[((x - 0x400) >> 7) * 32 + ((x & 0x3F) >> 1)] = v & 0xFF; });
  return out;
}
function floorShapes(lay) {
  const full = encodeFloor(lay.fgrid), base = gridFromShapes(lay);
  const diff = lay.fgrid.map((v, k) => (v === base[k] ? -1 : v));
  const d = encodeFloor(diff, true);
  const both = { n: lay.nshapes + d.n, bytes: [...lay.shapes, ...d.bytes] };
  return both.bytes.length <= full.bytes.length ? both : full;
}
function metatileCount(rom, tset) { return (rom.w(0x8DF1BE + 2 * tset) - rom.w(0x8DF1B2 + 2 * tset)) >> 4; }

function readLayout(rom, n) { return parseLayout(decompress(rom, layoutPtr(rom, n)).data); }

// ---------------------------------------------------------------- building (port of srmap.Map)
class Builder {
  constructor(rom) { this.rom = rom; this.tiles = new Map(); this.pals = new Map(); }
  slot(pid) { let i = this.palSlots.indexOf(pid); if (i < 0) { this.palSlots.push(pid); i = this.palSlots.length - 1; } return i + 1; }
  build(lay) {
    this.palSlots = [];
    const out = [];
    const grid = this.floor(lay);
    lay.layers.forEach((pcs, li) => {
      const cells = new Array(COLS * ROWS).fill(null);
      if (li === 0) this.drawFloor(grid, lay.tset, cells);
      pcs.forEach((pc, k) => this.placePiece(pc, cells, li * 1000 + k));
      out.push(cells);
    });
    return out;
  }
  floor(lay) {
    if (lay.fgrid) { const g = new Map(); lay.fgrid.forEach((v, k) => { if (v) g.set(0x400 + Math.floor(k / 32) * 0x80 + (k % 32) * 2, v); }); return g; }
    const g = new Map(), d = lay.shapes; let i = 0;
    const st = (x, v) => { if (x < 0xFFF) g.set(x, v & 0xFFFF); };
    const line = (x, n, v, step) => { while (n >= 0 && !(n & 0x8000)) { st(x, v); x = (x + step) & 0xFFFF; n--; } return x; };
    for (let s = 0; s < lay.nshapes; s++) {
      const w = d[i] | (d[i + 1] << 8); i += 2; let x = w & 0x3FFE;
      if (!(w & 0x8000)) {
        const v = d[i] | (d[i + 1] << 8); i += 2;
        line(x, v >> 8, v & 0xFF, (w & 0x4000) ? 0x82 : 0x7E);
      } else {
        let val = d[i]; const v = d[i + 1] | (d[i + 2] << 8); i += 3;
        const c2C = v & 0xFF; let c29 = v >> 8;
        if (w & 0x4000) {
          const save = val; val += 1;
          if (x >= 0x80) st(x - 0x80, val + 6);
          const x0 = x; x = (x - 2) & 0xFFFF;
          x = line(x, c2C - 1, val, 0x7E);
          val += 1; st(x, val + 3); x = (x + 0x82) & 0xFFFF;
          x = line(x, c29 - 1, val, 0x82);
          val += 1; x = line((x0 + 2) & 0xFFFF, c29 - 1, val, 0x82);
          val += 1; st(x, val + 2); x = (x + 0x7E) & 0xFFFF;
          x = line(x, c2C - 1, val, 0x7E);
          st(x, val + 4);
          x = x0; val = save;
        }
        for (;;) {
          line(x, c2C, val, 0x7E);
          c29--; if (c29 < 0) break;
          x = (x + 0x80) & 0xFFFF; line(x, c2C - 1, val, 0x7E); x = (x + 2) & 0xFFFF;
        }
      }
    }
    return g;
  }
  drawFloor(g, tset, cells) {
    const R = this.rom, p11 = 0x8D0000 | R.w(0x8DF1B2 + 2 * tset), p14 = 0x8D0000 | R.w(0x8DF1BE + 2 * tset);
    const D = [[0, 0], [1, 0], [2, 0], [3, 0], [0, 1], [1, 1], [2, 1], [3, 1]];
    let x = 0xBBE;
    while (x >= 0) {
      const v = g.get(x + 0x400) || 0;
      if (v) {
        const pal = this.slot(R.b(p14 + v)), base = p11 + v * 16, c0 = (x >> 7) * 4, r0 = x & 0x3F;
        for (let i = 0; i < 8; i++) {
          const t = R.w(base + 2 * i);
          if (t) { const col = c0 + D[i][0], row = r0 + D[i][1];
            if (col >= 0 && col < COLS && row >= 0 && row < ROWS) cells[col * ROWS + row] = { t: [t], d: [0xFFFF], o: [-1], pal }; }
        }
      }
      x -= 2; if (x >= 0) x &= 0xFFBF;
    }
  }
  pieceRec(p) { return 0x8A0000 | this.rom.w(0x8AC36A + ((p << 1) & 0x3FFF)); }
  placePiece(pc, cells, owner) {
    const R = this.rom, flip29 = pc.m ? 0x4000 : 0, rec = this.pieceRec(pc.p);
    const z = (pc.z * 8) & 0xFFFF, x = (pc.x * 4) & 0xFFFF, y = (pc.y * 4) & 0xFFFF;
    let d2F = ((x + y) & 0xFFFF) >> 1;
    let a = (-((d2F + z - 0x300) & 0xFFFF)) & 0xFFFF; a >>= 2; if (a & 0x2000) a |= 0xC000;
    let b = ((y - x + 0x280) & 0xFFFF) >> 3; b = ((b & 0xFF) << 8) | (b >> 8);
    let c2C = (a + b) & 0xFFFF;
    c2C = (c2C + R.w(rec + (flip29 ? 3 : 1))) & 0xFFFF;
    d2F = (R.w(rec + 5) + d2F) & 0xFFFF;
    const nblk = R.b(rec); let Y = 8;
    for (let k = 0; k < nblk; k++) {
      const wb = R.w(rec + Y), X = ((wb << 1) + wb) & 0x7FFF, blk = R.w3(0x96C45E + X); Y += 2;
      const f35 = ((wb & 0x8000) ? 0x4000 : 0) ^ flip29;
      const v = R.w(rec + Y); Y += 2;
      let pos = ((v & 0xFF) + c2C) & 0xFFFF;
      pos = flip29 ? (pos - (v & 0xFF00)) & 0xFFFF : (pos + (v & 0xFF00)) & 0xFFFF;
      const d3E = (R.b(rec + Y) + d2F) & 0xFFFF; Y += 1;
      this.placeBlock(blk, pos, f35, d3E, cells, owner);
    }
  }
  placeBlock(blk, pos, f35, d3E, cells, owner) {
    const R = this.rom, b0 = R.b(blk); let cols = b0 & 15; const rows = b0 >> 4; let left = rows;
    const b1 = R.b(blk + 1); let flag = (b1 & 0x80) ? 0x7FFE : 0;
    const pal = this.slot(b1 & 0x7F);
    let ty = 2, d50 = d3E, colpos = pos;
    for (;;) {
      flag = (flag + 1) & 0xFFFF;
      if (!(flag & 0x8000)) d50 = (R.b(blk + ty) + d3E) & 0xFFFF;
      if (pos < 0x2000 || pos >= 0x8000 || (pos & 0x80)) { if (!(flag & 0x8000)) ty += 1; ty += 2; }
      else { if (!(flag & 0x8000)) ty += 1; const t = R.w(blk + ty); ty += 2; if (t) this.put(cells, pos, t ^ f35, d50, pal, owner); }
      left--;
      if (left >= 0) { pos = (pos + 2) & 0xFFFF; continue; }
      if (((flag + 1) & 0xFFFF) & 0x8000) flag = 0x7FFE;
      cols--; if (cols < 0) break;
      left = rows; colpos = f35 ? (colpos - 0x100) & 0xFFFF : (colpos + 0x100) & 0xFFFF; pos = colpos;
    }
  }
  put(cells, pos, t, d, pal, owner) {
    const col = (pos >> 8) - 32, row = (pos & 0x7F) >> 1, k = col * ROWS + row;
    if (col < 0 || col >= COLS) return;
    const c = cells[k];
    if (!c) { cells[k] = { t: [t], d: [d], o: [owner], pal }; return; }
    const T = c.t, D = c.d, O = c.o, n = T.length; let p = 0;
    while (p < n && d < D[p]) p++;
    if (n === 3) { if (p === 0) return; T.shift(); D.shift(); O.shift(); p--; }
    T.splice(p, 0, t); D.splice(p, 0, d); O.splice(p, 0, owner);
    if (p === T.length - 1) c.pal = pal;
  }
  // ---------------- drawing
  tile(t) {
    const key = t & 0x3FFF; let img = this.tiles.get(key);
    if (!img) {
      const R = this.rom, ga = ((0x82 + ((key >> 10) & 15)) << 16) | R.w(0x8DA431 + ((key >> 1) & 0x1FFE));
      const d = decompress(R, ga, 0x80).data, o = (key & 3) * 32; img = new Uint8Array(64);
      for (let p = 0; p < 4; p++) for (let yy = 0; yy < 8; yy++) { const bb = d[o + p * 8 + yy]; for (let xx = 0; xx < 8; xx++) img[yy * 8 + xx] |= ((bb >> (7 - xx)) & 1) << p; }
      this.tiles.set(key, img);
    }
    return img;
  }
  palette(pid) {
    let P = this.pals.get(pid);
    if (!P) { P = []; const a = 0x8CF622 + 0x20 * pid;
      for (let i = 0; i < 16; i++) { const v = this.rom.w(a + 2 * i); P.push([(v & 31) << 3, ((v >> 5) & 31) << 3, ((v >> 10) & 31) << 3]); }
      this.pals.set(pid, P); }
    return P;
  }
  // rgba: Uint8ClampedArray 768*512*4. owners: Int32Array(96*64) front owner per cell (or null)
  draw(cellsByLayer, layers, rgba, owners, hide) {
    const pals = [null, ...this.palSlots.map(p => this.palette(p))];
    const W = COLS * 8;
    for (const li of layers) {
      cellsByLayer[li].forEach((c, k) => {
        if (!c) return;
        const col = Math.floor(k / ROWS), row = k % ROWS;
        const px = new Uint8Array(64); let front = -2;
        for (let i = 0; i < c.t.length; i++) {
          if (hide && hide.has(c.o[i])) continue;
          const t = c.t[i], ti = this.tile(t), hf = t & 0x4000, vf = t & 0x8000;
          for (let yy = 0; yy < 8; yy++) for (let xx = 0; xx < 8; xx++) {
            const v = ti[(vf ? 7 - yy : yy) * 8 + (hf ? 7 - xx : xx)]; if (v) px[yy * 8 + xx] = v;
          }
          front = c.o[i];
        }
        if (front === -2) return;
        if (owners) owners[k] = front;
        const P = pals[c.pal] || pals[1];
        for (let yy = 0; yy < 8; yy++) for (let xx = 0; xx < 8; xx++) {
          const v = px[yy * 8 + xx]; if (!v) continue;
          const o = ((row * 8 + yy) * W + col * 8 + xx) * 4; rgba[o] = P[v][0]; rgba[o + 1] = P[v][1]; rgba[o + 2] = P[v][2]; rgba[o + 3] = 255;
        }
      });
    }
  }
}

// ---------------------------------------------------------------- collision ($8184DE) and map data
const sx = v => (v & 0x80 ? v - 256 : v);
function pieceBoxes(rom, pc) {
  if (pc.x < 0 || pc.y < 0 || pc.z < 0) return [];          // the game skips these
  const rec = 0x8A0000 | rom.w(0x8AC36A + ((pc.p << 1) & 0x3FFF)), n = rom.b(rec + 7);
  let Y = 8 + 5 * rom.b(rec); const X0 = pc.x * 4, Y0 = pc.y * 4, Z0 = pc.z * 8, out = [];
  for (let i = 0; i < n; i++) {
    const b = []; for (let j = 0; j < 6; j++) b.push(rom.b(rec + Y + j)); Y += 6;
    let x1, x2, y1, y2;
    if (pc.m) { y1 = sx(b[0]) + Y0; y2 = y1 + b[1]; x1 = sx(b[2]) + X0; x2 = x1 + b[3]; }
    else { x1 = sx(b[0]) + X0; x2 = x1 + b[1]; y1 = sx(b[2]) + Y0; y2 = y1 + b[3]; }
    const z1 = sx(b[4]) + Z0; out.push([x1, y1, z1, x2, y2, z1 + b[5]]);
  }
  return out;
}
// ------------------------------------------------------------ separate item copies (new item types)
// Items are listed in the inventory by TYPE (the menu walks every type and shows those whose record owner is the
// character), so a copy that is a separate item needs a type of its own. The type table ($8DB031 + type, 7-byte
// entries: flags, record word, sprite word, script word; types 0..$2098) is moved to $A3:8000 so it can grow: the
// 39 'lda $8DB03x,X' in bank $80 (and any in the Runner Pack's and our own code banks) are repointed. New types
// $209F + 7k copy the original's entry with their own record ($7E21E0 + 5k). 'SRTYP' 1 at $A3:FFE0, count word
// $A3:FFE6, original type of each new one at $A3:F000 + 2k. Inventory loop start ($80E563 ldx #$208A) -> last type.
const TT_OLD = 0x8DB031, TT_NEW = 0xA38000, TT_SIG = 0xA3FFE0, TT_ORIGS = 0xA3F000, TT_FIRST = 0x209F, TT_INV = 0x80E564;
const TT_SCAN = [0x80, 0xAB, 0xBE, 0xBF];
function ttHooked(rom) { return rom.d.length >= 0x200000 && [0x53, 0x52, 0x54, 0x59, 0x50].every((c, i) => rom.b(TT_SIG + i) === c); }
function ttBase(rom) { return ttHooked(rom) ? TT_NEW : TT_OLD; }
function itemCopyList(rom) {      // original type of every new item type, by k
  if (rom._it) return rom._it; const l = []; rom._it = l; if (!ttHooked(rom)) return l;
  const n = rom.w(TT_SIG + 6); for (let k = 0; k < n; k++) l.push(rom.w(TT_ORIGS + 2 * k)); return l;
}
const typeRecord = (rom, t) => rom.w(ttBase(rom) + 1 + t);
function installItems(out, base, list) {
  const R = new Rom(out);
  if (!ttHooked(base)) {
    out.set(base.d.slice(L(TT_OLD), L(TT_OLD) + TT_FIRST), L(TT_NEW));
    for (const bk of TT_SCAN) { const s = L(bk << 16 | 0x8000); if (s + 0x8000 > out.length) continue;
      for (let i = s; i < s + 0x8000 - 3; i++) if (out[i] === 0xBF && out[i + 2] === 0xB0 && out[i + 3] === 0x8D && out[i + 1] >= 0x31 && out[i + 1] <= 0x36) {
        const a = TT_NEW + out[i + 1] - 0x31; out[i + 1] = a & 0xFF; out[i + 2] = (a >> 8) & 0xFF; out[i + 3] = a >> 16; } }
  }
  if (list.length > IT_MAX) throw new Error('at most ' + IT_MAX + ' separate item copies');
  out.fill(0, L(TT_NEW + TT_FIRST), L(TT_NEW) + 0x8000);
  list.forEach((t, k) => { const e = L(TT_NEW + TT_FIRST + 7 * k), r = (IT_RAM & 0xFFFF) + 5 * k;
    out.set(base.d.slice(L(ttBase(base) + t), L(ttBase(base) + t) + 7), e); out[e + 1] = r & 0xFF; out[e + 2] = r >> 8;
    out[L(TT_ORIGS + 2 * k)] = t & 0xFF; out[L(TT_ORIGS + 2 * k) + 1] = t >> 8; });
  out.set([0x53, 0x52, 0x54, 0x59, 0x50, 1, list.length & 0xFF, list.length >> 8], L(TT_SIG));
  const last = list.length ? TT_FIRST + 7 * (list.length - 1) : 0x208A; out[L(TT_INV)] = last & 0xFF; out[L(TT_INV) + 1] = last >> 8;
  return list.length;
}
// ------------------------------------------------------------ per-character scripts
// A placed character can run another script than its type's. Bank $A9: 'SROBJ' 1, entry count word $A9:8008,
// original bytes of $80A3A8 at $A9:8010, code at $A9:8020, table from $A9:8100: 5 bytes each = 24-bit ROM address of
// the object's 6-byte entry in its map data block, script word. Hook $80A3A8 (lda $8DB036,X / sta $08, in the map
// object loader: X = type, Y = offset after the object, [$86] = the map data block).
const OS_SIG = 0xA98000, OS_ORIG = 0xA98010, OS_CODE = 0xA98020, OS_TAB = 0xA98100, OS_SITE = 0x80A3A8, OS_MAX = 0x1800;
// new scripts made by the Script Editor ('SRNEW' at $AC:A200, count word at $AC:A206) are numbered from $400
function newScriptCount(rom) { return rom.d.length >= 0x200000 && [0x53, 0x52, 0x4E, 0x45, 0x57].every((c, i) => rom.b(0xACA200 + i) === c) ? rom.w(0xACA206) : 0; }
const NEW_SCRIPT_BASE = 0x400;
function scriptExists(rom, id) { return (id >= 0 && id < 936) || (id >= NEW_SCRIPT_BASE && id < NEW_SCRIPT_BASE + newScriptCount(rom)); }
function osHooked(rom) { return rom.d.length >= 0x200000 && [0x53, 0x52, 0x4F, 0x42, 0x4A].every((c, i) => rom.b(OS_SIG + i) === c); }
function readObjScripts(rom) {
  if (rom._os) return rom._os; const m = new Map(); rom._os = m; if (!osHooked(rom)) return m;
  const n = rom.w(OS_SIG + 8); for (let k = 0; k < n; k++) m.set(rom.w3(OS_TAB + 5 * k), rom.w(OS_TAB + 5 * k + 3));
  return m;
}
const typeScript = (rom, type) => rom.w(ttBase(rom) + 5 + type);
function osCode(orig) {
  const b = [], long = (op, v) => b.push(op, v & 0xFF, (v >> 8) & 0xFF, v >> 16);
  b.push(0xDA, 0x98, 0x18, 0x65, 0x86, 0x38, 0xE9, 0x06, 0x00, 0x48, 0xA2, 0x00, 0x00);   // phx; tya; clc; adc $86; sec; sbc #6; pha; ldx #0
  const loop = b.length;
  b.push(0x8A); long(0xCF, OS_SIG + 8); b.push(0xB0, 0); const jnf = b.length - 1;          // txa; cmp count*5; bcs not found
  long(0xBF, OS_TAB); b.push(0xC3, 0x01, 0xD0, 0); const jn1 = b.length - 1;                // lda tab,X; cmp 1,S; bne next
  b.push(0xE2, 0x20); long(0xBF, OS_TAB + 2); b.push(0xC5, 0x88, 0xC2, 0x20, 0xD0, 0); const jn2 = b.length - 1;   // bank == $88?
  long(0xBF, OS_TAB + 3); b.push(0x85, 0x08, 0x68, 0xFA, 0x6B);                            // sta $08; pla; plx; rtl
  b[jn1] = b.length - jn1 - 1; b[jn2] = b.length - jn2 - 1;
  b.push(0x8A, 0x18, 0x69, 0x05, 0x00, 0xAA, 0x80, 0); b[b.length - 1] = (loop - b.length) & 0xFF;   // next: x += 5; bra loop
  b[jnf] = b.length - jnf - 1;
  b.push(0x68, 0xFA, ...orig, 0x6B);                                                        // pla; plx; original; rtl
  return Uint8Array.from(b);
}
// table for the finished ROM: edited maps from their objects' .script, other maps keep what they had
function installObjScripts(out, base, mdEdits) {
  const oldT = readObjScripts(base), ed = new Map(), R = new Rom(out), entries = new Map();
  if (mdEdits) for (const [loc, md] of mdEdits) ed.set(base.w(0x8D92AF + 9 * loc), md);
  for (let loc = 0; loc < 0x1FC; loc++) {
    const pw = base.w(0x8D92AF + 9 * loc); let a, a0;
    try { a = mapData(R, loc); a0 = mapData(base, loc); } catch (e) { continue; }
    if (ed.has(pw)) ed.get(pw).objects.forEach((o, i) => { if (o.script != null && o.script !== typeScript(base, o.type)) entries.set(a + 5 + 6 * i, o.script); });
    else { const n = R.b(a + 4); for (let i = 0; i < n; i++) { const s = oldT.get(a0 + 5 + 6 * i); if (s != null) entries.set(a + 5 + 6 * i, s); } }
  }
  const hooked = osHooked(base);
  if (!entries.size && !hooked) return 0;
  const orig = hooked ? base.d.slice(L(OS_ORIG), L(OS_ORIG) + 6) : base.d.slice(L(OS_SITE), L(OS_SITE) + 6);
  out.fill(0, L(0xA98000), L(0xA98000) + 0x8000);
  if (!entries.size) { out.set(orig, L(OS_SITE)); return 0; }
  if (entries.size > OS_MAX) throw new Error('too many characters with their own script');
  out.set([0x53, 0x52, 0x4F, 0x42, 0x4A, 1], L(OS_SIG)); const n5 = 5 * entries.size; out[L(OS_SIG + 8)] = n5 & 0xFF; out[L(OS_SIG + 9)] = n5 >> 8;
  out.set(orig, L(OS_ORIG)); out.set(osCode([...orig]), L(OS_CODE));
  [...entries].forEach(([a, sc], k) => out.set([a & 0xFF, (a >> 8) & 0xFF, a >> 16, sc & 0xFF, sc >> 8], L(OS_TAB + 5 * k)));
  const p = L(OS_SITE); out.set([0x22, OS_CODE & 0xFF, (OS_CODE >> 8) & 0xFF, OS_CODE >> 16, 0xEA, 0xEA], p);
  return entries.size;
}
function mapInfo(rom, loc) {
  const a = mapData(rom, loc), n = rom.b(a + 4), objs = [];
  for (let i = 0; i < n; i++) {
    const w1 = rom.w(a + 5 + 6 * i), w2 = rom.w(a + 7 + 6 * i), t = rom.w(a + 9 + 6 * i);
    const o = { x: w1 & 0x7FF, y: w2 & 0x7FF, z: (w1 >> 11) | ((w2 >> 11) << 5), type: t };
    const sc = readObjScripts(rom).get(a + 5 + 6 * i); if (sc != null) o.script = sc;
    if (t >= TT_FIRST) { const k = (t - TT_FIRST) / 7, l = itemCopyList(rom); if (Number.isInteger(k) && k < l.length) o.itemOf = l[k]; }
    objs.push(o);
  }
  let p = a + 5 + 6 * n; const lists = [];
  for (let k = 0; k < 3; k++) {
    const c = rom.b(p); p++; const Lb = [];
    for (let i = 0; i < c; i++) {
      const ws = []; for (let j = 0; j < 6; j++) { let v = rom.w(p + 2 * j); if (v & 0x8000) v -= 0x10000; ws.push(v); } p += 12;
      if (k) { ws.push(rom.w(p)); p += 2; }
      Lb.push(ws);
    }
    lists.push(Lb);
  }
  // walking points ($F3: x, y, z words; scripts name them by number, natives #80 WALK_TO_POINT / #B5 PLACE_AT_POINT)
  // and line-of-sight blockers ($FC: x1 y1 z1 x2 y2 z2 words, $81A25F)
  const words = (n) => { const c = rom.b(p), out = []; p++; for (let i = 0; i < c; i++) { const e = []; for (let j = 0; j < n; j++) { let v = rom.w(p + 2 * j); if (v & 0x8000) v -= 0x10000; e.push(v); } out.push(e); p += 2 * n; } return out; };
  const points = words(3), los = words(6);
  // camera limits: word at +2 -> table in the same bank: 8-byte entries ended by $FFFF
  const cw = rom.w(a + 2), cam = [];
  if (cw >= 0x8000) { const ca = (a & 0xFF0000) | cw; for (let i = 0; i < 16; i++) { const v = rom.w(ca + 8 * i); cam.push(v & 0xFF, v >> 8); if (v === 0xFFFF) break; for (let j = 2; j < 8; j++) cam.push(rom.b(ca + 8 * i + j)); } }
  // camera limits ($818A05, only the first entry counts): words minX', maxX', minY', maxY' with X' = x + 12, Y' = y + 12
  // of the followed character (Jake) -> the camera follows him only while he is inside [x1..x2] x [y1..y2]
  const cw16 = i => cam[i] | (cam[i + 1] << 8);
  const camBox = cam.length >= 10 ? [cw16(0) - 12, cw16(4) - 12, cw16(2) - 12, cw16(6) - 12] : null;
  return { layout: rom.b(a), music: rom.b(a + 1), camWord: cw, cam, camBox, objects: objs, walls: lists[0], zones: lists[1], exits: lists[2], points, los };
}
// Map data block: +0 layout, +1 music, +2 word -> camera-limit table (same bank), +4 object count, 6-byte objects
// (w1 = x | (z & 31) << 11, w2 = y | (z >> 5) << 11, type), walls (count + 12 bytes), floor zones (count + 14),
// exits (count + 14), walking points (count + 6), line-of-sight blockers (count + 12), then the camera table.
// Same counts as the ROM -> rewritten in place; otherwise the block is moved to the pool in banks $B8-$BB.
// A switched-off box = all zero with z $7FFF (never entered).
const OFF_BOX = [0, 0, 0x7FFF, 0, 0, 0x7FFF];
function readMapData(rom, loc) {
  const info = mapInfo(rom, loc); return { ptr: rom.w(0x8D92AF + 9 * loc), ...info };
}
function serializeMapData(md, addr) {     // addr: where the block will live (for the camera pointer)
  const out = [md.layout, md.music, 0, 0, md.objects.length];
  const w16 = v => out.push(v & 0xFF, (v >> 8) & 0xFF);
  for (const o of md.objects) { w16((o.x & 0x7FF) | ((o.z & 31) << 11)); w16((o.y & 0x7FF) | (((o.z >> 5) & 31) << 11)); w16(o.type); }
  [md.walls, md.zones, md.exits].forEach((list, k) => { out.push(list.length); for (const b of list) { for (let j = 0; j < 6; j++) w16(b[j]); if (k) w16(b[6]); } });
  for (const list of [md.points, md.los]) { out.push(list.length); for (const e of list) for (const v of e) w16(v); }
  let cw = md.camWord;
  if ('camBox' in md) md = { ...md, cam: md.camBox || (md.cam && md.cam.length) ? camBytes(md.camBox) : [] };
  if (md.cam && md.cam.length) { cw = (addr & 0xFFFF) + out.length; out.push(...md.cam); }
  out[2] = cw & 0xFF; out[3] = (cw >> 8) & 0xFF;
  if (['objects', 'walls', 'zones', 'exits', 'points', 'los'].some(k => md[k].length > 255)) throw new Error('too many entries');
  return Uint8Array.from(out);
}
function camBytes(box) {   // [x1, y1, x2, y2] or null -> table bytes (one entry + $FFFF, or just $FFFF)
  if (!box) return [0xFF, 0xFF];
  const x1 = Math.min(box[0], box[2]), x2 = Math.max(box[0], box[2]), y1 = Math.min(box[1], box[3]), y2 = Math.max(box[1], box[3]);
  const out = []; for (const v of [x1 + 12, x2 + 12, y1 + 12, y2 + 12]) out.push(v & 0xFF, (v >> 8) & 0xFF);
  return [...out, 0xFF, 0xFF];
}
function sameCounts(a, b) { return ['objects', 'walls', 'zones', 'exits', 'points', 'los'].every(k => a[k].length === b[k].length) && !!a.camBox === !!b.camBox; }
function writeMapData(out, rom, loc, md) {     // in place (same counts as the block currently in the ROM)
  const a = mapData(rom, loc), n = rom.b(a + 4);
  if (md.objects.length !== n) throw new Error('object count changed');
  const w16 = (addr, v) => { out[L(addr)] = v & 0xFF; out[L(addr + 1)] = (v >> 8) & 0xFF; };
  out[L(a + 1)] = md.music & 0xFF;                                     // music track ($FF = keep playing)
  md.objects.forEach((o, i) => { w16(a + 5 + 6 * i, (o.x & 0x7FF) | ((o.z & 31) << 11)); w16(a + 7 + 6 * i, (o.y & 0x7FF) | (((o.z >> 5) & 31) << 11)); w16(a + 9 + 6 * i, o.type); });
  let p = a + 5 + 6 * n;
  [md.walls, md.zones, md.exits].forEach((list, k) => {
    if (rom.b(p) !== list.length) throw new Error('box count changed'); p++;
    for (const b of list) { for (let j = 0; j < 6; j++) w16(p + 2 * j, b[j]); p += 12; if (k) { w16(p, b[6]); p += 2; } }
  });
  if (md.camBox && rom.w(a + 2) >= 0x8000) { const ca = (a & 0xFF0000) | rom.w(a + 2); camBytes(md.camBox).slice(0, 8).forEach((v, i) => { out[L(ca + i)] = v; }); }
  [[md.points, 3], [md.los, 6]].forEach(([list, n]) => {
    if (rom.b(p) !== list.length) throw new Error('point count changed'); p++;
    for (const e of list) { for (let j = 0; j < n; j++) w16(p + 2 * j, e[j]); p += 2 * n; }
  });
}
function mdHookCode() {
  const b = [], lab = {}, fix = [];
  const emit = (...x) => b.push(...x), long = (op, a) => emit(op, a & 0xFF, (a >> 8) & 0xFF, a >> 16);
  const br = (op, name) => { emit(op, 0); fix.push([b.length - 1, name]); };
  emit(0xDA, 0x48);                                   // phx; pha
  long(0xAF, 0x7E2DE2); emit(0x0A, 0x18); long(0x6F, 0x7E2DE2); emit(0xAA);   // lda loc; asl; clc; adc loc; tax (loc*3)
  long(0xBF, MD_TABLE + 1); emit(0x29, 0x00, 0xFF); br(0xF0, 'van');           // lda table+1,x; and #$FF00; beq vanilla
  long(0xBF, MD_TABLE); emit(0x85, 0x86);                                      // lda table,x; sta $86
  emit(0xE2, 0x20); long(0xBF, MD_TABLE + 2); br(0x80, 'store');               // sep #$20; lda table+2,x; bra store
  lab.van = b.length; emit(0x68, 0x48, 0x0A, 0xE2, 0x20, 0xA9, 0x99, 0x69, 0x00); // pla; pha; asl; sep #$20; lda #$99; adc #0
  lab.store = b.length; emit(0x85, 0x88, 0x8D, 0xF8, 0x0C, 0x85, 0x9F, 0x85, 0x9C, 0x85, 0xF5, 0x85, 0xFE, 0xC2, 0x20, 0x68, 0xFA);
  long(0x5C, 0x80A3F0);                                                         // ...; rep #$20; pla; plx; jml $80A3F0 (rts)
  for (const [at, name] of fix) b[at] = (lab[name] - (at + 1)) & 0xFF;
  return Uint8Array.from(b);
}
// ---------------------------------------------------------------- own save slots for copied characters
// A character type with a save record (◆) placed a second time shares that record with the original (the copy may not
// appear, and killing one removes the other). Copies marked "own" get a private record instead:
//  * map load ($80A343 start -> JSL): copies on the map that was just left write their state back (gone = record owner
//    != $FFFF) and the pool of 19 live records at $7E:22A0 (5 bytes each) is emptied;
//  * each placed object ($80A38E: lda $8DB032,X / sta $23 -> JSL): if (this location's vanilla pointer word, object
//    offset) is in the copy table at $AB:9000, the object gets the next pool record: rec0/flags/HP from the type's
//    new-game record, owner $FFFF (or $1538 = gone when its gone flag is set, so the loader skips it);
//  * save ($81B141) / load ($81B15B): gone flags of copies 0-23 <-> 3 bytes + a check byte at SRAM slot + $FFA (the 4
//    bytes after the Runner Pack's table; vanilla leaves them as $AA filler). A bad check byte = all copies alive;
//  * new game ($809878): all copies alive.
// The original instructions of each hook site are copied into the code (vanilla or the Runner Pack's JSLs), so the
// patch works on either; apply it after the Runner Pack. Table entry (7 bytes): pointer word, object offset (Y after
// the object's 6 bytes = 11 + 6 * index), copy id, rec0, flags, HP.
const CP_SIG = 0xAB8000, CP_ORIG = 0xAB8010, CP_CODE = 0xAB8100, CP_TABLE = 0xAB9000, CP_POOL = 19;
// 24 copies fit the 4 spare bytes of each save slot; more need the bigger (16 KB) save file: header $FFD8 = 4, flags
// of all 256 ids at SRAM $2000 (slot 1) / $2200 (slot 2) after 'CPv1'. CP_BIG ($AB:800A) = 1 turns that on.
const CP_TAIL = 24, CP_MAX = 24, CP_MAX_BIG = 256, CP_BIG = 0xAB800A;
// separate item copies (new item types): count byte $AB:800B, starting records at $AB:8800 (5 bytes each), live records
// in WRAM $7E21E0 (free in vanilla and Runner Pack, checked across 15 maps, menus, save/load), saved at SRAM $2400 / $2500.
const CP_ITEMS = 0xAB800B, CP_ITPL = 0xAB8800, IT_RAM = 0x7E21E0, IT_MAX = 36;
const CP_SITES = [[0x81B141, 9], [0x81B15B, 9], [0x809878, 6], [0x80A343, 5], [0x80A38E, 6]];   // save, load, new, start, rec
const CP_VANILLA = ['A2E02DA9030F54707E', 'A0E02DA9030F547E70', 'A23E00A90000', 'A00400B786', 'BF32B08D8523'];
const CP_RAM = { GONE: 0x7FB000, POOL: 0x7FC5D0, NEXT: 0x7FC5F6, TMPY: 0x7FC5F8, TMPX: 0x7FC5FA, TMPID: 0x7FC5FC, T: 0x7FC5FE,
  TB: 0x7FC598, I0: 0x7FC594, I2: 0x7FC596, PW: 0x7FC592 };
const CP_RECS = 0x22A0;
function cpHooked(rom) { return rom.d.length >= 0x200000 && [0x53, 0x52, 0x43, 0x4F, 0x50, 0x59].every((c, i) => rom.b(CP_SIG + i) === c); }
function cpOriginals(rom) {      // the bytes each hook site held before this patch
  if (cpHooked(rom)) { let p = CP_ORIG; return CP_SITES.map(([, n]) => { const s = []; for (let i = 0; i < n; i++) s.push(rom.b(p++)); return s; }); }
  return CP_SITES.map(([a, n]) => { const s = []; for (let i = 0; i < n; i++) s.push(rom.b(a + i)); return s; });
}
function readCopyTable(rom) {    // [{pw, index, id}]
  if (!cpHooked(rom)) return [];
  const n = rom.w(CP_SIG + 8) / 7, out = [];
  for (let i = 0; i < n; i++) { const a = CP_TABLE + 7 * i; out.push({ pw: rom.w(a), index: (rom.b(a + 2) - 11) / 6, id: rom.b(a + 3) }); }
  return out;
}
function cpCode(orig, nItems) {
  nItems = nItems || 0; const IT5 = 5 * nItems - 1;
  const b = [], lab = {}, fix = [], org = CP_CODE & 0xFFFF;
  const R = CP_RAM, a16 = v => [v & 0xFF, (v >> 8) & 0xFF];
  const e = (...x) => b.push(...x), abs = (op, v) => e(op, ...a16(v)), long = (op, v) => e(op, v & 0xFF, (v >> 8) & 0xFF, v >> 16);
  const imm = (op, v) => e(op, ...a16(v));
  const br = (op, name) => { e(op, 0); fix.push(['rel', b.length - 1, name]); };
  const jsr = name => { e(0x20, 0, 0); fix.push(['abs', b.length - 2, name]); };
  const L_ = name => { lab[name] = b.length; };
  const dbin = () => e(0x8B, 0xF4, 0x7F, 0x7F, 0xAB, 0xAB);      // phb; pea $7F7F; plb; plb  (DB = $7F)
  const G = R.GONE & 0xFFFF;                                      // gone flags: one byte per copy id, bank $7F
  const entry = [];
  // --- save: Y = slot offset (A/X/Y 16-bit)
  entry.push(b.length);
  e(0x08, 0x5A); e(...orig[0]);                                   // php; phy; original copy (vanilla MVN or Runner Pack JSL)
  e(0xC2, 0x30); dbin(); jsr('sync');
  imm(0xA9, 0); abs(0x8D, R.TB); abs(0x8D, R.TB + 2); imm(0xA2, CP_TAIL - 1);
  L_('pk'); e(0xE2, 0x20); abs(0xBD, G); e(0x4A, 0xC2, 0x20); abs(0x2E, R.TB); abs(0x2E, R.TB + 2); e(0xCA); br(0x10, 'pk');  // ids 0-23 -> 24 bits
  e(0xA3, 0x02); e(0xAA);                                          // lda 2,S (slot; stack: B, Y); tax
  abs(0xAD, R.TB); long(0x9F, 0x700FFA);                           // tail: 3 bytes + check at slot + $FFA
  e(0xE2, 0x20); abs(0xAD, R.TB + 2); long(0x9F, 0x700FFC);
  abs(0x4D, R.TB); abs(0x4D, R.TB + 1); e(0x49, 0x5A); long(0x9F, 0x700FFD); e(0xC2, 0x20);
  long(0xAF, CP_BIG); imm(0x29, 0xFF); br(0xF0, 'sv_it');        // bigger save file? copy all 256 flags to SRAM $2000/$2200
  e(0xA3, 0x02); jsr('ext'); e(0xAA);                              // X = SRAM offset of this slot's block
  imm(0xA9, 0x5043); long(0x9F, 0x700000); imm(0xA9, 0x3176); long(0x9F, 0x700002);   // 'CPv1'
  e(0x8A, 0x18); imm(0x69, 4); e(0xA8); imm(0xA2, G); imm(0xA9, 0xFF); e(0x54, 0x70, 0x7F);   // mvn $70,$7F (256 bytes)
  L_('sv_it');
  if (nItems) {   // separate item copies: their records ($7E21E0, 5 bytes each) -> SRAM $2400 / $2500 after 'IT'
    e(0xA3, 0x02); jsr('ext2'); e(0xAA); imm(0xA9, 0x5449); long(0x9F, 0x700000);
    e(0x8A, 0x18); imm(0x69, 2); e(0xA8); imm(0xA2, IT_RAM & 0xFFFF); imm(0xA9, IT5); e(0x54, 0x70, 0x7E);
  }
  L_('sv_done'); e(0xAB, 0x7A, 0x28, 0x6B);                        // plb; ply; plp; rtl
  // --- load: X = slot offset
  entry.push(b.length);
  e(0x08, 0xDA); e(...orig[1]);                                   // php; phx; original copy
  e(0xC2, 0x30); dbin(); jsr('zero');
  e(0xA3, 0x02); e(0xAA);                                          // lda 2,S; tax (slot)
  e(0xE2, 0x20); long(0xBF, 0x700FFA); long(0x5F, 0x700FFB); long(0x5F, 0x700FFC); e(0x49, 0x5A); long(0xDF, 0x700FFD);
  e(0xC2, 0x20); br(0xD0, 'ld_ext');                               // bad check byte -> no tail flags
  long(0xBF, 0x700FFA); abs(0x8D, R.TB); long(0xBF, 0x700FFC); imm(0x29, 0xFF); abs(0x8D, R.TB + 2);
  imm(0xA2, 0);
  L_('up'); abs(0x4E, R.TB + 2); abs(0x6E, R.TB); e(0xE2, 0x20, 0xA9, 0x00);   // sep #$20; lda #0
  e(0x2A); abs(0x9D, G); e(0xC2, 0x20, 0xE8); imm(0xE0, CP_TAIL); br(0xD0, 'up');
  L_('ld_ext'); long(0xAF, CP_BIG); imm(0x29, 0xFF); br(0xF0, 'ld_done');
  e(0xA3, 0x02); jsr('ext'); e(0xAA);
  long(0xBF, 0x700000); imm(0xC9, 0x5043); br(0xD0, 'ld_done'); long(0xBF, 0x700002); imm(0xC9, 0x3176); br(0xD0, 'ld_done');
  e(0x8A, 0x18); imm(0x69, 4); e(0xAA); imm(0xA0, G); imm(0xA9, 0xFF); e(0x54, 0x7F, 0x70);   // mvn $7F,$70
  e(0xF4, 0x7F, 0x7F, 0xAB, 0xAB);                                 // DB = $7F again
  L_('ld_done');
  if (nItems) {   // item records back from SRAM, or their starting values for a save made before they existed
    e(0xA3, 0x02); jsr('ext2'); e(0xAA); long(0xBF, 0x700000); imm(0xC9, 0x5449); br(0xD0, 'ld_tpl');
    e(0x8A, 0x18); imm(0x69, 2); e(0xAA); imm(0xA0, IT_RAM & 0xFFFF); imm(0xA9, IT5); e(0x54, 0x7E, 0x70); br(0x80, 'ld_aft');
    L_('ld_tpl'); imm(0xA2, CP_ITPL & 0xFFFF); imm(0xA0, IT_RAM & 0xFFFF); imm(0xA9, IT5); e(0x54, 0x7E, CP_ITPL >> 16);
    L_('ld_aft'); e(0xF4, 0x7F, 0x7F, 0xAB, 0xAB);
  }
  jsr('clear'); e(0xAB, 0xFA, 0x28, 0x6B);          // plb; plx; plp; rtl
  // --- new game (A/X 16-bit)
  entry.push(b.length);
  e(0x08, 0xC2, 0x30); dbin(); jsr('zero'); jsr('clear');
  if (nItems) { imm(0xA2, CP_ITPL & 0xFFFF); imm(0xA0, IT_RAM & 0xFFFF); imm(0xA9, IT5); e(0x54, 0x7E, CP_ITPL >> 16); }
  e(0xAB, 0x28); e(...orig[2]); e(0x6B);
  // --- map load start
  entry.push(b.length);
  e(0x08, 0xC2, 0x30, 0x48, 0xDA, 0x5A); dbin(); jsr('sync'); jsr('clear');
  long(0xAF, 0x7E2DE2); e(0x0A, 0x0A, 0x0A, 0x18); long(0x6F, 0x7E2DE2); e(0xAA); long(0xBF, 0x8D92AF); abs(0x8D, R.PW);
  e(0xAB, 0x7A, 0xFA, 0x68, 0x28); e(...orig[3]); e(0x6B);
  // --- per object: X = type, Y = offset after the object (A/X/Y 16-bit); return A = record, flags from A
  entry.push(b.length);
  e(...orig[4]); br(0xD0, 'rc_go'); e(0x6B);
  L_('rc_go'); e(0xDA, 0x5A); dbin(); e(0x98); abs(0x8D, R.TMPY); imm(0xA2, 0);
  L_('rc_l'); e(0x8A); long(0xCF, CP_SIG + 8); br(0xF0, 'rc_nf');        // table length in bytes at $AB:8008
  long(0xBF, CP_TABLE); abs(0xCD, R.PW); br(0xD0, 'rc_n');
  long(0xBF, CP_TABLE + 2); imm(0x29, 0xFF); abs(0xCD, R.TMPY); br(0xD0, 'rc_n'); br(0x80, 'rc_f');
  L_('rc_n'); e(0x8A, 0x18); imm(0x69, 7); e(0xAA); br(0x80, 'rc_l');
  L_('rc_nf'); e(0xAB, 0x7A, 0xFA, 0xA5, 0x23, 0x6B);              // plb; ply; plx; lda $23; rtl
  L_('rc_f'); abs(0xAD, R.NEXT); imm(0xC9, 2 * CP_POOL); br(0xB0, 'rc_nf');
  abs(0x8E, R.TMPX); e(0xA8);                                      // stx TMPX; tay (Y = 2k)
  long(0xBF, CP_TABLE + 3); imm(0x29, 0xFF); e(0x99, ...a16(R.POOL)); abs(0x8D, R.TMPID);   // POOL[k] = id; TMPID = id
  long(0xBF, CP_TABLE + 4); abs(0x8D, R.I0); long(0xBF, CP_TABLE + 6); abs(0x8D, R.I2);
  e(0x98, 0x4A); abs(0x8D, R.T); e(0x0A, 0x0A, 0x18); abs(0x6D, R.T); e(0xAA);   // X = 5k
  abs(0xAD, R.I0); long(0x9F, 0x7E0000 + CP_RECS); abs(0xAD, R.I2); long(0x9F, 0x7E0002 + CP_RECS);
  abs(0xAC, R.TMPID); e(0xB9, ...a16(G)); imm(0x29, 0xFF); br(0xF0, 'rc_al'); imm(0xA9, 0x1538); br(0x80, 'rc_so');
  L_('rc_al'); imm(0xA9, 0xFFFF);
  L_('rc_so'); long(0x9F, 0x7E0003 + CP_RECS);
  e(0x8A, 0x18); imm(0x69, CP_RECS); e(0x85, 0x23);
  abs(0xAD, R.NEXT); e(0x1A, 0x1A); abs(0x8D, R.NEXT);
  e(0xAB, 0x7A, 0xFA, 0xA5, 0x23, 0x6B);
  // --- sync: live pool records -> gone flags (DB = $7F, 16-bit)
  L_('sync'); imm(0xA2, 0); imm(0xA0, 0);
  L_('sy_l'); abs(0xBD, R.POOL); br(0x30, 'sy_n'); abs(0x8D, R.TMPID);
  e(0xDA, 0xBB); long(0xBF, 0x7E0003 + CP_RECS); imm(0xC9, 0xFFFF); br(0xF0, 'sy_a');   // phx; tyx; lda owner
  abs(0xAE, R.TMPID); e(0xE2, 0x20, 0xA9, 0x01); abs(0x9D, G); e(0xC2, 0x20);
  L_('sy_a'); e(0xFA);
  L_('sy_n'); e(0x98, 0x18); imm(0x69, 5); e(0xA8, 0xE8, 0xE8); imm(0xE0, 2 * CP_POOL); br(0xD0, 'sy_l'); e(0x60);
  // --- clear the pool
  L_('clear'); imm(0xA2, 2 * (CP_POOL - 1)); imm(0xA9, 0xFFFF);
  L_('cl'); abs(0x9D, R.POOL); e(0xCA, 0xCA); br(0x10, 'cl'); abs(0x9C, R.NEXT); e(0x60);
  // --- all copies alive
  L_('zero'); imm(0xA2, 0xFE); imm(0xA9, 0);
  L_('zl'); abs(0x9D, G); e(0xCA, 0xCA); br(0x10, 'zl'); e(0x60);
  // --- A = slot offset ($0000 / $0FFE) -> SRAM offset of its block ($2000 / $2200; 4 + 256 bytes each)
  L_('ext'); imm(0xC9, 0); br(0xF0, 'ex0'); imm(0xA9, 0x2200); e(0x60);
  L_('ex0'); imm(0xA9, 0x2000); e(0x60);
  L_('ext2'); imm(0xC9, 0); br(0xF0, 'ex2'); imm(0xA9, 0x2500); e(0x60);
  L_('ex2'); imm(0xA9, 0x2400); e(0x60);
  for (const [k, at, name] of fix) {
    if (k === 'rel') { const d = lab[name] - (at + 1); if (d < -128 || d > 127) throw new Error('branch ' + name); b[at] = d & 0xFF; }
    else { const t = org + lab[name]; b[at] = t & 0xFF; b[at + 1] = t >> 8; }
  }
  return { code: Uint8Array.from(b), entry: entry.map(x => CP_CODE + x) };
}

// copies: Map(pointer word -> [{index, type, id}]) for the blocks edited now; the rest of the table is kept
function installCopies(out, base, copies, items) {
  items = items || []; const nItems = items.length;
  const rom = new Rom(out), entries = readCopyTable(base).filter(c => !copies.has(c.pw));
  const used = new Set(entries.map(c => c.id));
  for (const list of copies.values()) for (const c of list) if (c.id != null) used.add(c.id);
  for (const [pw, list] of copies) {
    if (list.length > CP_POOL) throw new Error('a map can have at most ' + CP_POOL + ' copies with their own save slot');
    for (const c of list) { if (c.id == null) { let id = 0; while (used.has(id)) id++; c.id = id; used.add(id); } entries.push({ pw, index: c.index, id: c.id }); }
  }
  if (entries.some(c => c.id >= CP_MAX_BIG)) throw new Error('at most ' + CP_MAX_BIG + ' copies with their own save slot in the whole game');
  const big = entries.some(c => c.id >= CP_TAIL);
  if (!entries.length && !nItems && !cpHooked(base)) return 0;
  const init = decompress(base, 0x8BFC42).data;
  const orig = cpOriginals(base), { code, entry } = cpCode(orig, nItems);
  out.fill(0, L(0xAB8000), L(0xAB8000) + 0x8000);
  out.set([0x53, 0x52, 0x43, 0x4F, 0x50, 0x59, 1], L(CP_SIG)); out[L(CP_SIG + 8)] = (7 * entries.length) & 0xFF; out[L(CP_SIG + 9)] = (7 * entries.length) >> 8;
  out.set(orig.flat(), L(CP_ORIG)); out.set(code, L(CP_CODE)); out[L(CP_BIG)] = big ? 1 : 0;
  if ((big || nItems) && out[L(0x80FFD8)] < 4) out[L(0x80FFD8)] = 4;   // save file 16 KB: room for the flags of all 256 copies / item records
  out[L(CP_ITEMS)] = nItems;
  items.forEach((t, k) => { const rec = typeRecord(base, t), r = rec - 0x2E00, iv = rec && r >= 0 && r + 3 <= init.length ? [init[r], init[r + 1], init[r + 2]] : [0, 0, 0];
    out.set([...iv, 0xFF, 0xFF], L(CP_ITPL + 5 * k)); });
  const typeAt = (pw, index) => { for (let loc = 0; loc < 0x1FC; loc++) if (base.w(0x8D92AF + 9 * loc) === pw) { const md = mapInfo(rom, loc); return md.objects[index] && md.objects[index].type; } return null; };
  entries.sort((a, b) => a.id - b.id).forEach((c, i) => {
    const t = typeAt(c.pw, c.index), rec = t == null ? 0 : typeRecord(base, t), r = rec - 0x2E00;
    const iv = rec && r >= 0 && r + 3 <= init.length ? [init[r], init[r + 1], init[r + 2]] : [0, 0, 0];
    out.set([c.pw & 0xFF, c.pw >> 8, 11 + 6 * c.index, c.id, ...iv], L(CP_TABLE + 7 * i));
  });
  CP_SITES.forEach(([a, n], k) => { const p = L(a), t = entry[k]; out[p] = 0x22; out[p + 1] = t & 0xFF; out[p + 2] = (t >> 8) & 0xFF; out[p + 3] = t >> 16; for (let i = 4; i < n; i++) out[p + i] = 0xEA; });
  return entries.length;
}
function buckets(b) {
  const r = (v1, v2) => (((v2 & 0x3C0) >> 6) - ((v1 & 0x3C0) >> 6) + 1);
  return Math.max(1, r(b[0], b[3])) * Math.max(1, r(b[1], b[4]));
}
function stats(rom, lay, info) {
  let bytes; try { bytes = serializeLayout(lay).length; } catch (e) { bytes = 99999; }
  const pb = [].concat(...lay.layers.map(l => [].concat(...l.map(pc => pieceBoxes(rom, pc)))));
  const extra = info ? [...info.walls, ...info.zones, ...info.exits] : [];
  const boxes = pb.length + extra.length;
  const bk = pb.concat(extra.map(e => e.slice(0, 6))).reduce((s, b) => s + buckets(b), 0);
  return { bytes, boxes, buckets: bk, layerA: lay.layers[0].length, layerB: lay.layers[1].length };
}

// Distinct merged 8x8 tiles the game must make ($818E57): deduplicated per layer, a whole-cell flip counts as
// the same tile, and both layers share one pool of 1023 slots. Checked against the game on 188 maps (exact or a few
// more in the game, from doors and other run-time changes).
function tileCount(cellsByLayer) {
  let tot = 0;
  for (const cells of cellsByLayer) {
    const s = new Set();
    for (const c of cells) {
      if (!c) continue;
      let best = null;
      for (const f of [0, 0x4000, 0x8000, 0xC000]) { const k = c.t.map(t => t ^ f).join(','); if (best === null || k < best) best = k; }
      s.add(best);
    }
    tot += s.size;
  }
  return tot;
}
function overLimits(rom, lay, info, builder) {
  const bld = builder || new Builder(rom), s = stats(rom, lay, info); s.tiles = tileCount(bld.build(lay)); s.palettes = bld.palSlots.length;
  s.shapes = lay.fgrid ? floorShapes(lay).n : lay.nshapes;
  const over = [];
  if (s.palettes > LIMITS.palettes) over.push('palettes');
  if (s.shapes > LIMITS.shapes) over.push('floor runs');
  if (s.bytes > LIMITS.bytes) over.push('layout data');
  if (s.layerA > LIMITS.perLayer || s.layerB > LIMITS.perLayer) over.push('blocks per layer');
  if (s.tiles > LIMITS.tiles) over.push('tiles');
  if (s.boxes > LIMITS.boxes) over.push('wall boxes');
  if (s.buckets > LIMITS.buckets) over.push('wall lookups');
  return { stats: s, over };
}

// ---------------------------------------------------------------- writing
// edits: Map(layoutNumber -> layout object). Returns a new Uint8Array (maybe 2 MB) and a report.
function applyEdits(romU8, edits, mdEdits, opts) {
  let out = new Uint8Array(romU8); let rom = new Rom(out); const report = [];
  // separate item copies: give each a new type before the map data is written (o.newItem on a fresh copy; o.itemOf
  // = original type on one that already has its type)
  const items = itemCopyList(new Rom(romU8)).slice(); let freshItems = 0;
  if (mdEdits) {
    for (const md of mdEdits.values()) for (const o of md.objects) if (o.itemOf != null && o.type >= TT_FIRST) { const k = (o.type - TT_FIRST) / 7; if (items[k] == null) items[k] = o.itemOf; }
    for (const md of mdEdits.values()) for (const o of md.objects) if (o.newItem && o.type < TT_FIRST) {
      let k = items.findIndex(x => x == null); if (k < 0) k = items.length; items[k] = o.type; o.itemOf = o.type; o.type = TT_FIRST + 7 * k; delete o.newItem; freshItems++; }
    for (let k = 0; k < items.length; k++) if (items[k] == null) throw new Error('item copy list has a gap');
  }
  const base = new Rom(romU8), moveMd = new Map();     // vanilla pointer word -> {loc, md}
  if (mdHooked(base)) for (let loc = 0; loc < 0x1FC; loc++) {       // keep blocks moved earlier
    const o = base.w3(MD_TABLE + 3 * loc); if (!(o >> 16)) continue;
    const pw = base.w(0x8D92AF + 9 * loc); if (!moveMd.has(pw)) moveMd.set(pw, { loc, md: readMapData(base, loc), kept: true });
  }
  if (mdEdits) for (const [loc, md] of mdEdits) {
    const pw = base.w(0x8D92AF + 9 * loc), relocated = moveMd.has(pw);
    if (!relocated && !(opts && opts.forceMove) && sameCounts(md, mapInfo(base, loc))) { writeMapData(out, base, loc, md); report.push({ map: loc, where: 'map data in place' }); }
    else moveMd.set(pw, { loc, md });
  }
  const inPool = a => { const b = a >> 16; return b >= POOL_FIRST && b <= POOL_LAST; };
  // collect everything that has to live in the pool: layouts already there + edits that do not fit in place
  const poolItems = new Map();
  if (out.length >= 0x200000) for (let n = 0; n < 165; n++) {
    const a = layoutPtr(rom, n); if (inPool(a) && !edits.has(n)) { const d = decompress(rom, a); poolItems.set(n, out.slice(L(a), L(a) + d.used)); }
  }
  // in-place room: the original stream, but never past the next layout (streams share a straddling last byte)
  const starts = []; for (let n = 0; n < 165; n++) starts.push(layoutPtr(rom, n));
  const room = {};
  for (let n = 0; n < 165; n++) {
    const a = starts[n]; if (inPool(a)) continue;
    let used = decompress(rom, a).used;
    const nxt = starts.filter(s => s > a && (s >> 16) === (a >> 16));
    used = nxt.length ? Math.min(used, Math.min(...nxt) - a) : used - 1;
    room[n] = used;
  }
  for (const [n, lay] of edits) {
    const raw = serializeLayout(lay); const comp = compress(raw);
    const a = layoutPtr(rom, n);
    if (!inPool(a)) {
      const used = room[n];
      if (comp.length <= used) { out.set(comp, L(a)); report.push({ n, where: 'in place', addr: a, size: comp.length, raw: raw.length }); continue; }
    }
    poolItems.set(n, comp);
  }
  if (poolItems.size) {
    if (out.length < 0x200000) { const big = new Uint8Array(0x200000); big.set(out); out = big; out[0x7FD7] = 0x0B; rom = new Rom(out); }
    // wipe the old pool and lay it out again
    const wasPool = POOL_SIG.every((c, i) => out[L((POOL_FIRST << 16) | 0x8000) + i] === c);
    if (wasPool) for (let b = POOL_FIRST; b <= POOL_LAST; b++) out.fill(0, L(b << 16 | 0x8000), L(b << 16 | 0x8000) + 0x8000);
    out.set(POOL_SIG, L(POOL_FIRST << 16 | 0x8000)); out[L(POOL_FIRST << 16 | 0x8005)] = 1;
    let bank = POOL_FIRST, addr = 0x8010;
    for (const [n, comp] of [...poolItems].sort((p, q) => p[0] - q[0])) {
      if (addr + comp.length > 0x10000) { bank++; addr = 0x8000; }
      if (bank > POOL_LAST) throw new Error('map pool full');
      const a = (bank << 16) | addr; out.set(comp, L(a)); addr += comp.length;
      const t = L(0x8BFA53 + 3 * n); out[t] = a & 0xFF; out[t + 1] = (a >> 8) & 0xFF; out[t + 2] = a >> 16;
      if (edits.has(n)) report.push({ n, where: 'expansion', addr: a, size: comp.length, raw: serializeLayout(edits.get(n)).length });
    }
  }
  if (moveMd.size || mdHooked(base)) {
    if (out.length < 0x200000) { const big = new Uint8Array(0x200000); big.set(out); out = big; out[0x7FD7] = 0x0B; }
    for (let bk = MD_TABLE >> 16; bk <= MD_LAST; bk++) out.fill(0, L((bk << 16) | 0x8000), L((bk << 16) | 0x8000) + 0x8000);
    out.set([0x53, 0x52, 0x4D, 0x41, 0x50, 0x44, 0x41, 0x54, 0x41], L(MD_SIG));
    out.set(mdHookCode(), L(MD_HOOK));
    let bank = MD_POOL >> 16, addr = MD_POOL & 0xFFFF;
    const R0 = new Rom(romU8);
    for (const [pw, v] of [...moveMd].sort((a, b) => a[0] - b[0])) {
      let bytes = serializeMapData(v.md, (bank << 16) | addr);
      if (addr + bytes.length > 0x10000) { bank++; addr = 0x8000; bytes = serializeMapData(v.md, (bank << 16) | addr); }
      if (bank > MD_LAST) throw new Error('map data pool full');
      const a = (bank << 16) | addr; out.set(bytes, L(a)); addr += bytes.length;
      for (let loc = 0; loc < 0x1FC; loc++) if (R0.w(0x8D92AF + 9 * loc) === pw) { const t = L(MD_TABLE + 3 * loc); out[t] = a & 0xFF; out[t + 1] = (a >> 8) & 0xFF; out[t + 2] = a >> 16; }
      if (!v.kept) report.push({ map: v.loc, where: 'map data moved', addr: a, size: bytes.length });
    }
    const j = L(0x80A3DA); out[j] = 0x5C; out[j + 1] = MD_HOOK & 0xFF; out[j + 2] = (MD_HOOK >> 8) & 0xFF; out[j + 3] = MD_HOOK >> 16;
  }
  // own save slots for copies (objects with .own set)
  const copies = new Map();
  if (mdEdits) for (const [loc, md] of mdEdits) {
    const pw = base.w(0x8D92AF + 9 * loc), list = [];
    md.objects.forEach((o, i) => { if (o.own != null && o.own !== false && o.itemOf == null && !o.newItem && typeRecord(base, o.type)) list.push({ index: i, type: o.type, id: typeof o.own === 'number' ? o.own : null }); });
    copies.set(pw, list);
  }
  if (copies.size || cpHooked(base) || items.length) {
    if ([...copies.values()].some(l => l.length) || cpHooked(base) || items.length) {
      if (out.length < 0x200000) { const big = new Uint8Array(0x200000); big.set(out); out = big; out[0x7FD7] = 0x0B; }
      const n = installCopies(out, base, copies, items); if (n) report.push({ where: 'own save slots', copies: n, big: out[L(CP_BIG)] === 1 });
      if (mdEdits) for (const [loc, md] of mdEdits) { const l = copies.get(base.w(0x8D92AF + 9 * loc)); if (l) for (const c of l) md.objects[c.index].own = c.id; }
    }
  }
  if (items.length || ttHooked(base)) {
    if (out.length < 0x200000) { const big = new Uint8Array(0x200000); big.set(out); out = big; out[0x7FD7] = 0x0B; }
    const n = installItems(out, base, items); if (n) report.push({ where: 'item copies', items: n, fresh: freshItems });
  }
  // characters running another script than their type's
  if ((mdEdits && [...mdEdits.values()].some(md => md.objects.some(o => o.script != null))) || osHooked(base)) {
    if (out.length < 0x200000) { const big = new Uint8Array(0x200000); big.set(out); out = big; out[0x7FD7] = 0x0B; }
    const n = installObjScripts(out, base, mdEdits); if (n) report.push({ where: 'character scripts', scripts: n });
  }
  return { rom: out, report };
}

function ipsDiff(oldU8, newU8) {
  const out = [0x50, 0x41, 0x54, 0x43, 0x48], n = newU8.length, grew = n > oldU8.length;
  const old = i => (i < oldU8.length ? oldU8[i] : 0);
  let i = 0;
  while (i < n) {
    if (old(i) === newU8[i]) { i++; continue; }
    let j = i;
    while (j < n && j - i < 0xFFFF && (old(j) !== newU8[j] || (j + 1 < n && old(j + 1) !== newU8[j + 1]))) j++;
    let s = i; if (s === 0x454F46) s--;
    out.push(s >> 16, (s >> 8) & 0xFF, s & 0xFF, ((j - s) >> 8) & 0xFF, (j - s) & 0xFF);
    for (let k = s; k < j; k++) out.push(newU8[k]);
    i = j;
  }
  if (grew) { const s = n - 1; out.push(s >> 16, (s >> 8) & 0xFF, s & 0xFF, 0, 1, newU8[n - 1]); }
  out.push(0x45, 0x4F, 0x46);
  return Uint8Array.from(out);
}

function crc32(u8) {
  let c, crc = 0xFFFFFFFF; const T = crc32.T || (crc32.T = Array.from({ length: 256 }, (_, n) => { c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1; return c >>> 0; }));
  for (let i = 0; i < u8.length; i++) crc = T[(crc ^ u8[i]) & 0xFF] ^ (crc >>> 8);
  return (crc ^ 0xFFFFFFFF) >>> 0;
}

// world (collision units: piece x*4, y*4, z*8) -> map pixel
const project = (X, Y, Z) => [Y - X + 384, 768 - (X + Y) / 2 - Z];

const api = { COLS, ROWS, LIMITS, L, Rom, decompress, compress, mapData, layoutNumber, layoutPtr, parseLayout, serializeLayout,
  readLayout, decodePiece, encodePiece, Builder, pieceBoxes, mapInfo, stats, tileCount, overLimits, floorGrid, encodeFloor, metatileCount, readMapData, writeMapData, serializeMapData, sameCounts, mdHooked, vanillaMapData, OFF_BOX, applyEdits, ipsDiff, readCopyTable, cpHooked, cpCode, CP_MAX, CP_MAX_BIG, CP_TAIL, CP_POOL, readObjScripts, osHooked, itemCopyList, ttBase, ttHooked, typeRecord, TT_FIRST, IT_MAX, newScriptCount, scriptExists, typeScript, NEW_SCRIPT_BASE, crc32, project, bitlen };
if (typeof module !== 'undefined') module.exports = api; else root.SR = api;
})(typeof window !== 'undefined' ? window : globalThis);
