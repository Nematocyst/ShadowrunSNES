// Shadowrun (SNES) sprites in the browser: decode animations/frames (port of srgfx.py) and recolour palettes,
// either shared (every sprite using that palette id) or as a sprite's own palette (srpal.py: extra ids 70-109 in
// bank $AF with hooks at $80AA97, $81A8D1, $81A8E1 and the Runner Pack sprite cache).
(function (root) {
'use strict';
const L = a => ((a & 0x7F0000) >> 1) | (a & 0x7FFF);
const BASE_ID = 70, MAX_EXTRA = 40, SIG = 0xAF8000, COUNT = 0xAF8006, ORIG = 0xAF8010, CORE = 0xAF8100, CLEAR = 0xAF8180, NMI = 0xAF8200, DATA = 0xAF9000;
const CODE = /*SRPALCODE*/null;
const hexb = h => Uint8Array.from(h.match(/../g).map(x => parseInt(x, 16)));

class Sprites {
  constructor(u8) { this.u8 = u8; this._rec = null; this.n = 0x113; }
  b(a) { return this.u8[L(a)]; }
  w(a) { return this.u8[L(a)] | (this.u8[L(a + 1)] << 8); }
  table(s) { return this.w(0x8CED8A + 2 * s); }
  records() {
    if (this._rec) return this._rec;
    const r = new Set();
    for (let sp = 0; sp < this.n; sp++) { const T = this.table(sp), first = this.w(0x8C0000 | T), n = (first - T) >> 1;
      if (n > 0 && n < 40) { r.add(T); for (let k = 0; k < n; k++) r.add(this.w(0x8C0000 | ((T + 2 * k) & 0xFFFF))); } }
    return (this._rec = [...r].sort((a, b) => a - b));
  }
  validFrame(w) {
    const p = ((w & 0x8000 ? 0x9C : 0x9B) << 16) | w | 0x8000, n = this.b(p);
    if (!(n > 0 && n <= 24)) return false;
    const h = p + 1 + 4 * n, c = this.b(h + 2) & 15, r = this.b(h + 2) >> 4; return c > 0 && c <= 8 && r > 0 && r <= 8;
  }
  animations(s) {
    const T = this.table(s), first = this.w(0x8C0000 | T), n = (first - T) >> 1; if (!(n > 0 && n < 40)) return [];
    const recs = this.records(), out = [];
    for (let k = 0; k < n; k++) {
      const A = this.w(0x8C0000 | ((T + 2 * k) & 0xFFFF)), idx = []; for (let i = 8; i < 16; i++) idx.push(this.b(0x8C0000 | (A + i)));
      if (idx.some(i => i % 2 || i > 240 || (i > 0 && i < 8)) || !idx.some(Boolean)) continue;
      const nxt = Math.min(...recs.filter(r => r > A), A + 256), facings = [];
      for (let f = 0; f < 8; f++) {
        if (!idx[f]) { facings.push([]); continue; }
        const later = idx.filter(i => i > idx[f]), end = later.length ? Math.min(...later) : (nxt - A - 8), ws = [];
        for (let j = 0; j < Math.max(1, (end - idx[f]) >> 1); j++) { const w = this.w(0x8C0000 | ((A + 8 + idx[f] + 2 * j) & 0xFFFF)); if (!this.validFrame(w)) break; ws.push(w); if (ws.length >= 24) break; }
        facings.push(ws);
      }
      out.push({ index: k, record: 0x8C0000 | A, palette: this.b(0x8C0000 | (A + 2)), delay: this.b(0x8C0000 | (A + 1)), facings });
    }
    return out;
  }
  tile(o) {   // 8x8 4bpp SNES tile at file offset o -> 64 indices
    const u = this.u8, img = new Uint8Array(64);
    for (let y = 0; y < 8; y++) for (let p = 0; p < 4; p++) { const byte = u[o + ((p >> 1) * 16) + y * 2 + (p & 1)]; for (let x = 0; x < 8; x++) img[y * 8 + x] |= ((byte >> (7 - x)) & 1) << p; }
    return img;
  }
  stripAddr(wd) { return L(((0x8E + (wd & 0x3F)) << 16) | (wd & 0xFFC0) | 0x8000); }
  cellPixels(top, bot) {   // 16x16 indices of a graphics cell (two 16x8 strips of two 8x8 tiles), unflipped
    const cell = new Uint8Array(256);
    for (const [half, wd] of [[0, top], [1, bot]]) {
      const o = this.stripAddr(wd), t0 = this.tile(o), t1 = this.tile(o + 32);
      for (let y = 0; y < 8; y++) for (let x = 0; x < 8; x++) { cell[(half * 8 + y) * 16 + x] = t0[y * 8 + x]; cell[(half * 8 + y) * 16 + 8 + x] = t1[y * 8 + x]; }
    }
    return cell;
  }
  // ov: optional Map('top,bot' -> Uint8Array(256)) of repainted cells
  frame(word, ov) {  // -> {w, h, px: Int16Array (-1 transparent), ox, oy, cells: [{x, y, key, hf, vf}]}
    const p = ((word & 0x8000 ? 0x9C : 0x9B) << 16) | word | 0x8000, n = this.b(p), words = [];
    for (let i = 0; i < 2 * n; i++) words.push(this.w(p + 1 + 2 * i));
    const h = p + 1 + 4 * n, cols = this.b(h + 2) & 15, rows = this.b(h + 2) >> 4, W = cols * 16, H = rows * 16;
    const px = new Int16Array(W * H).fill(-1), cells = []; let k = 0;
    for (let c = 0; c < cols; c++) for (let r = 0; r < rows; r++) {
      const cb = this.b(h + 3 + c * rows + r); if (cb & 0x20 || k + 1 > words.length) continue;
      const key = words[k] + ',' + words[k + 1], cell = ov && ov.has(key) ? ov.get(key) : this.cellPixels(words[k], words[k + 1]);
      cells.push({ x: c * 16, y: r * 16, key, hf: !!(cb & 0x40), vf: !!(cb & 0x80) });
      k += 2;
      for (let y = 0; y < 16; y++) for (let x = 0; x < 16; x++) {
        const sx = cb & 0x40 ? 15 - x : x, sy = cb & 0x80 ? 15 - y : y, v = cell[sy * 16 + sx];
        if (v) px[(r * 16 + y) * W + c * 16 + x] = v;
      }
    }
    return { w: W, h: H, px, ox: this.b(h), oy: this.b(h + 1), cells, rec: p, words };
  }
  // every cell's strips -> the sprites that use them (to know when a repainted strip must be copied)
  stripUsers() {
    if (this._users) return this._users;
    const users = new Map(), recs = new Map();
    for (let sp = 0; sp < this.n; sp++) for (const a of this.animations(sp)) for (const f of a.facings) for (const w of f) {
      let fr; try { fr = this.frame(w); } catch (e) { continue; }
      if (!recs.has(fr.rec)) recs.set(fr.rec, new Set()); recs.get(fr.rec).add(sp);
      for (const c of fr.cells) for (const wd of c.key.split(',').map(Number)) { if (!users.has(wd)) users.set(wd, new Set()); users.get(wd).add(sp + '|' + c.key); }
    }
    return (this._users = { users, recs });
  }
  palAddr(pid) { return pid >= BASE_ID ? L(DATA + 32 * (pid - BASE_ID)) : L(0x8DF1CA + 32 * pid); }
  palette(pid) { const a = this.palAddr(pid), out = []; for (let i = 0; i < 16; i++) out.push(this.u8[a + 2 * i] | (this.u8[a + 2 * i + 1] << 8)); return out; }
  palettesOf(s) { const ps = []; for (const a of this.animations(s)) if (!ps.includes(a.palette)) ps.push(a.palette); return ps; }
  group(s) { const T = this.table(s), g = []; for (let o = 0; o < this.n; o++) if (this.table(o) === T) g.push(o); return g; }
  installed() { return this.u8.length >= 0x200000 && String.fromCharCode(...this.u8.slice(L(SIG), L(SIG) + 5)) === 'SRPAL'; }
  extraCount() { return this.installed() ? this.w(COUNT) : 0; }
}
const rgb = c => [(c & 31) << 3, ((c >> 5) & 31) << 3, ((c >> 10) & 31) << 3];
const snes = (r, g, b) => (r >> 3) | ((g >> 3) << 5) | ((b >> 3) << 10);

function install(out) {
  const S = new Sprites(out), put = (a, bytes) => out.set(bytes, L(a));
  if (!S.installed()) {
    const v = (a, n) => Array.from(out.slice(L(a), L(a) + n)).map(x => x.toString(16).padStart(2, '0')).join('');
    if (v(0x80AA97, 5) !== '0aaabd0218' || v(0x81A8D1, 4) !== '8d8c186b' || v(0x81A8E1, 3) !== 'b9f217') throw new Error('This ROM has unexpected code where the palette hook goes.');
    put(SIG, [0x53, 0x52, 0x50, 0x41, 0x4C, 1]); put(COUNT, [0, 0]);
  }
  const core = hexb(CODE.core), ent = CORE + core.length;
  put(CORE, core); put(ent, [0x22, CORE & 0xFF, (CORE >> 8) & 0xFF, CORE >> 16, 0x5C, 0xB2, 0xAA, 0x80]);
  put(CLEAR, hexb(CODE.clear)); put(NMI, hexb(CODE.nmi));
  put(0x80AA97, [0x5C, ent & 0xFF, (ent >> 8) & 0xFF, ent >> 16]);
  put(0x81A8D1, [0x5C, CLEAR & 0xFF, (CLEAR >> 8) & 0xFF, CLEAR >> 16]);
  const body = new Uint8Array(0x81A90B - 0x81A8E1).fill(0xEA); body.set([0x22, NMI & 0xFF, (NMI >> 8) & 0xFF, NMI >> 16]); put(0x81A8E1, body);
  // Runner Pack sprite cache: inline copy of $80AA97 -> JSL core
  const pat = [0xB9, 0x64, 0x12, 0x0A, 0xAA, 0xBD, 0x02, 0x18];
  for (let i = 0x100000; i + 30 < out.length; i++) {
    let ok = true; for (let j = 0; j < 8; j++) if (out[i + j] !== pat[j]) { ok = false; break; }
    if (ok && out[i + 8] === 0x10 && out[i + 27] === 0x8E && out[i + 28] === 0xF0 && out[i + 29] === 0x17) {
      const rep = new Uint8Array(30).fill(0xEA); rep.set([0xB9, 0x64, 0x12, 0x22, CORE & 0xFF, (CORE >> 8) & 0xFF, CORE >> 16]); out.set(rep, i);
    }
  }
}
// edits: {shared: Map(pid -> colours[16]), own: Map(sprite -> Map(pid -> colours[16]))}
function apply(romU8, edits) {
  let out = new Uint8Array(romU8); const report = [];
  const S0 = new Sprites(romU8);
  for (const [pid, cols] of edits.shared) { const a = S0.palAddr(pid); cols.forEach((c, i) => { if (i) { out[a + 2 * i] = c & 0xFF; out[a + 2 * i + 1] = c >> 8; } }); report.push({ shared: pid }); }
  if (edits.own.size) {
    if (out.length < 0x200000) { const big = new Uint8Array(0x200000); big.set(out); out = big; out[0x7FD7] = 0x0B; }
    install(out);
    const S = new Sprites(out);
    for (const [s, pals] of edits.own) {
      const group = S0.group(s);
      for (const [pid, cols] of pals) {
        // already an extra palette used only by this group? then just recolour it
        const users = []; for (let o = 0; o < S0.n; o++) if (!group.includes(o) && S0.palettesOf(o).includes(pid)) users.push(o);
        let target = pid;
        if (pid < BASE_ID || users.length) {
          const n = S.w(COUNT); if (n >= MAX_EXTRA) throw new Error('All ' + MAX_EXTRA + ' extra palettes are in use.');
          target = BASE_ID + n; out[L(ORIG + n)] = pid < BASE_ID ? pid : out[L(ORIG + pid - BASE_ID)];
          out[L(COUNT)] = (n + 1) & 0xFF; out[L(COUNT) + 1] = (n + 1) >> 8;
          const recs = new Set(); for (const a of S0.animations(s)) if (a.palette === pid) recs.add(a.record);
          for (const r of recs) out[L(r + 2)] = target;
        }
        const a = S.palAddr(target); cols.forEach((c, i) => { out[a + 2 * i] = c & 0xFF; out[a + 2 * i + 1] = c >> 8; });
        report.push({ sprite: s, from: pid, to: target, group });
      }
    }
  }
  if (edits.pixels && edits.pixels.size) {
    if (out.length < 0x200000) { const big = new Uint8Array(0x200000); big.set(out); out = big; out[0x7FD7] = 0x0B; }
    applyPixels(out, S0, edits.pixels, report);
  }
  return { rom: out, report };
}
// ---- repainted pixels. Strips used only by this sprite group's cell are rewritten in place; shared strips get a
// copy in the pool $BC:8000-$BD:FFFF ('SRSPR' + 16-bit count, strips of 64 bytes from $BC:8040; same format as
// srsprite.py) and this group's frame records are repointed to it.
const POOL = 0xBC8000, POOL_END = 0xBDFFFF;
function encodeTile(px, x0, y0) {   // 8x8 from a 16-wide index array -> 32 bytes 4bpp
  const b = new Uint8Array(32);
  for (let y = 0; y < 8; y++) for (let x = 0; x < 8; x++) { const v = px[(y0 + y) * 16 + x0 + x], m = 0x80 >> x;
    if (v & 1) b[y * 2] |= m; if (v & 2) b[y * 2 + 1] |= m; if (v & 4) b[16 + y * 2] |= m; if (v & 8) b[16 + y * 2 + 1] |= m; }
  return b;
}
function allocStrip(out) {
  const p = L(POOL), sig = [0x53, 0x52, 0x53, 0x50, 0x52];
  if (!sig.every((c, i) => out[p + i] === c)) {
    for (let i = p; i <= L(POOL_END); i++) if (out[i]) throw new Error('$BC:8000-$BD:FFFF is not empty in this ROM, so there is no room for copied graphics.');
    out.set(sig, p); out[p + 5] = 0; out[p + 6] = 0;
  }
  const n = out[p + 5] | (out[p + 6] << 8), off = p + 0x40 + 64 * n;
  if (off + 64 > L(POOL_END) + 1) throw new Error('The sprite graphics pool is full.');
  out[p + 5] = (n + 1) & 0xFF; out[p + 6] = (n + 1) >> 8;
  const snesA = 0x800000 | ((off >> 15) << 16) | 0x8000 | (off & 0x7FFF);
  return (snesA & 0xFFC0) | (((snesA >> 16) - 0x8E) & 0x3F);
}
function applyPixels(out, S0, pix, report) {
  const { users, recs } = S0.stripUsers();
  for (const [s, cells] of pix) {
    const group = S0.group(s), remap = new Map(); let copied = 0, inPlace = 0;
    for (const [key, idx] of cells) {
      const [top, bot] = key.split(',').map(Number), orig = S0.cellPixels(top, bot);
      if (idx.every((v, i) => v === orig[i])) continue;
      const nk = [top, bot];
      [[top, 0], [bot, 8]].forEach(([wd, y0], h) => {
        const data = new Uint8Array(64); data.set(encodeTile(idx, 0, y0), 0); data.set(encodeTile(idx, 8, y0), 32);
        const mine = [...(users.get(wd) || [])].every(u => { const [sp, k] = u.split('|'); return group.includes(+sp) && k === key; });
        if (mine) { out.set(data, S0.stripAddr(wd)); inPlace++; }
        else { const nw = allocStrip(out); out.set(data, S0.stripAddr(nw)); nk[h] = nw; copied++; }
      });
      if (nk[0] !== top || nk[1] !== bot) remap.set(key, nk);
    }
    const others = new Set();
    if (remap.size) {
      const seen = new Set();
      for (const a of S0.animations(s)) for (const f of a.facings) for (const w of f) {
        const fr = S0.frame(w); if (seen.has(fr.rec)) continue; seen.add(fr.rec);
        for (let i = 0; i + 1 < fr.words.length; i += 2) {
          const nk = remap.get(fr.words[i] + ',' + fr.words[i + 1]); if (!nk) continue;
          const o = L(fr.rec + 1 + 2 * i); out[o] = nk[0] & 0xFF; out[o + 1] = nk[0] >> 8; out[o + 2] = nk[1] & 0xFF; out[o + 3] = nk[1] >> 8;
          for (const sp of recs.get(fr.rec) || []) if (!group.includes(sp)) others.add(sp);
        }
      }
    }
    report.push({ sprite: s, pixels: true, cells: cells.size, inPlace, copied, others: [...others] });
  }
}
const api = { Sprites, apply, install, rgb, snes, BASE_ID, MAX_EXTRA };
if (typeof module !== 'undefined') module.exports = api; else root.SP = api;
})(typeof window !== 'undefined' ? window : globalThis);
