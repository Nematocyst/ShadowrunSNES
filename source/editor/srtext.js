// Shadowrun (SNES) text core: Huffman decode/encode with the game's own tree, text inventory, font preview,
// and writing edited texts back (in place when they fit, otherwise into a pool with a redirect hook).
// Format: text id < $C000 -> bytes at $9D:(id|$8000) (bank $9E when id bit 15 is set); bit stream MSB first.
// Tree at $9D:8000: node = two words (bit 0 / bit 1); word bit 15 set = leaf with 1-2 chars (high byte first,
// $00 = none); $0A ends the text. Decoder $80FE33/$80FE44 -> buffer $7E21A0 -> renderer $80FB03 (wraps by pixel
// width, font $95:F2D0 8 bytes/char, widths $81:ABC8, '|' = emphasised word until the next space).
// Expanded Dialogue: ids >= $C000 -> 3-byte pointers at $A0:8100 + 3*(id-$C000) (hook JML $A08000 at $80FE33).
// Our hook: JML $B48000 at $80FE44 (the shared entry): looks the 24-bit pointer up in a table at $B4:8100
// (word: end offset = 6*count, then [old ptr 3][new ptr 3] entries) and swaps it. Relocated texts live at $B5:8000+.
(function (root) {
'use strict';
const L = a => ((a & 0x7F0000) >> 1) | (a & 0x7FFF);
const MAXLEN = 250;           // decoded characters; vanilla max is 218, the buffer at $7E21A0 must not reach $7E2300
const HOOK = 0xB48000, TABLE = 0xB48100, POOL_FIRST = 0xB5, POOL_LAST = 0xB7;

function rb(u8, a) { return u8[L(a)]; }
function rw(u8, a) { return u8[L(a)] | (u8[L(a + 1)] << 8); }

class Texts {
  constructor(u8) {
    this.u8 = u8; this.leaves = []; this.codes = new Map();   // key "c1,c2" -> bit string
    const walk = (x, code) => {
      for (const b of [0, 1]) {
        const w = rw(u8, 0x9D8000 + x + 2 * b);
        if (w & 0x8000) { const c1 = (w >> 8) & 0x7F, c2 = w & 0x7F; this.leaves.push([c1, c2, code + b]); this.codes.set(c1 + ',' + c2, code + b); }
        else walk(w, code + b);
      }
    };
    walk(0, '');
    this.single = new Set(this.leaves.filter(l => l[1] === 0).map(l => l[0]));
    this.ed = rb(u8, 0x80FE33) === 0x5C && rw(u8, 0x80FE34) === 0x8000 && rb(u8, 0x80FE36) === 0xA0;
    this.hooked = rb(u8, 0x80FE44) === 0x5C && rw(u8, 0x80FE45) === (HOOK & 0xFFFF) && rb(u8, 0x80FE47) === (HOOK >> 16);
    this.redirects = new Map();   // original ptr -> pool ptr
    if (this.hooked && u8.length >= 0x200000) {
      const end = rw(u8, TABLE);
      for (let o = 0; o < end && o < 0x7E00; o += 6) {
        const a = rw(u8, TABLE + 2 + o) | (rb(u8, TABLE + 4 + o) << 16), b = rw(u8, TABLE + 5 + o) | (rb(u8, TABLE + 7 + o) << 16);
        this.redirects.set(a, b);
      }
    }
  }
  basePtr(id) {
    if (id >= 0xC000) { if (!this.ed) return null; const t = 0xA08100 + 3 * (id - 0xC000); return rw(this.u8, t) | (rb(this.u8, t + 2) << 16); }
    return ((0x9D + (id & 0x8000 ? 1 : 0)) << 16) | (id | 0x8000);
  }
  ptr(id) { const b = this.basePtr(id); return b == null ? null : (this.redirects.get(b) || b); }
  // decode at a 24-bit pointer -> {codes: [char codes], bytes: length in bytes}
  decodeAt(p) {
    const u8 = this.u8, out = []; let bit = 0;
    const base = L(p);
    for (let guard = 0; guard < 4000; guard++) {
      let x = 0, w;
      for (;;) {
        if ((u8[base + (bit >> 3)] >> (7 - (bit & 7))) & 1) x += 2;
        bit++; w = u8[0xE8000 + x] | (u8[0xE8001 + x] << 8);
        if (w & 0x8000) break; x = w;
        if (x > 0x2000) return null;
      }
      const c1 = (w >> 8) & 0x7F, c2 = w & 0x7F;
      if (c1 === 0x0A) return { codes: out, bytes: (bit + 7) >> 3 };
      out.push(c1);
      if (c2) { if (c2 === 0x0A) return { codes: out, bytes: (bit + 7) >> 3 }; out.push(c2); }
    }
    return null;
  }
  decode(id) { const p = this.ptr(id); return p == null ? null : this.decodeAt(p); }
  // optimal encoding with the fixed tree (1- and 2-char leaves), ending with a leaf that holds $0A
  encode(codes) {
    const n = codes.length, INF = 1e9, best = new Array(n + 1).fill(INF), from = new Array(n + 1);
    best[0] = 0;
    for (let i = 0; i < n; i++) {
      if (best[i] >= INF) continue;
      const one = this.codes.get(codes[i] + ',0');
      if (one && best[i] + one.length < best[i + 1]) { best[i + 1] = best[i] + one.length; from[i + 1] = [i, one]; }
      if (i + 1 < n) { const two = this.codes.get(codes[i] + ',' + codes[i + 1]); if (two && best[i] + two.length < best[i + 2]) { best[i + 2] = best[i] + two.length; from[i + 2] = [i, two]; } }
    }
    // terminator: (0A,0) after everything, or (c,0A) covering the last char
    let endBits = null, endBest = INF;
    const t1 = this.codes.get('10,0');
    if (t1 && best[n] < INF) { endBest = best[n] + t1.length; endBits = { at: n, code: t1 }; }
    if (n > 0 && best[n - 1] < INF) { const t2 = this.codes.get(codes[n - 1] + ',10'); if (t2 && best[n - 1] + t2.length < endBest) { endBest = best[n - 1] + t2.length; endBits = { at: n - 1, code: t2 }; } }
    if (!endBits) throw new Error('cannot encode');
    const parts = [endBits.code]; let i = endBits.at;
    while (i > 0) { if (!from[i]) throw new Error('character not in the game font: ' + codes[i - 1]); parts.push(from[i][1]); i = from[i][0]; }
    const bits = parts.reverse().join('');
    const out = new Uint8Array((bits.length + 7) >> 3);
    for (let k = 0; k < bits.length; k++) if (bits[k] === '1') out[k >> 3] |= 0x80 >> (k & 7);
    return out;
  }
  canEncode(code) { return this.single.has(code); }
  // ---- inventory: every text the game points at, with where it is used
  inventory(meta) {
    const u8 = this.u8, list = new Map();
    const add = (id, g, label) => { if (!id || id === 0xFFFF) return; if (id >= 0xC000 && !this.ed) return;
      let e = list.get(id); if (!e) { e = { id, g, l: [] }; list.set(id, e); } if (!e.l.includes(label)) e.l.push(label);
      const order = ['conv', 'msg', 'menu', 'kw', 'name', 'other']; if (order.indexOf(g) < order.indexOf(e.g)) e.g = g; };
    const kwName = k => { const d = this.decode(rw(u8, 0x8D8000 + 2 * k)); return d ? String.fromCharCode(...d.codes).replace(/\|/g, '') : '#' + k; };
    const topic = (t, kws) => ({ 0xFF: 'greeting', 0xFE: 'Talk', 0xFD: 'default answer' }[t] || ('keyword "' + (t < 64 ? kwName(t) : '#' + t) + '"')) + (kws.length ? ' (needs ' + kws.map(k => '"' + kwName(k) + '"').join(', ') + ')' : '');
    for (let n = 0; n < (meta.nconv || 139); n++) {
      const base = 0x8D0000 | rw(u8, 0x80947A + 2 * n); let y = 4;
      const ppl = (meta.conv_people[n] || []).join(', ') || 'conversation ' + n;
      for (let k = 0; k < 80; k++) {
        const t = rb(u8, base + y); if (t === 0xF8) break;
        const ln = rb(u8, base + y + 1), fl = rb(u8, base + y + 2), nk = fl & 15, kws = [];
        for (let i = 0; i < nk; i++) kws.push(rb(u8, base + y + 3 + i));
        let q = base + y + 3 + nk; if (fl & 0x80) q += 2;
        const tid = rw(u8, q);
        add(tid, 'conv', ppl + ' · ' + topic(t, kws) + (tid >= 0xC000 ? ' (Expanded Dialogue)' : ''));
        if (!ln) break; y += 1 + ln;
      }
    }
    for (let i = 0; i < 0x264; i++) { const u = meta.msg_users[i] || [], mid = rw(u8, 0x80D980 + 2 * i); add(mid, 'msg', 'Message ' + i + (u.length ? ': ' + u.slice(0, 3).join('; ') + (u.length > 3 ? ' +' + (u.length - 3) + ' more' : '') : ' (engine or menus)'));  const me = list.get(mid); if (me && !(me.msg = me.msg || []).includes(i)) me.msg.push(i); }
    for (let k = 0; k < 64; k++) add(rw(u8, 0x8D8000 + 2 * k), 'kw', 'Keyword ' + k);
    for (let s = 0; s < 0x113; s++) add(rw(u8, 0x8CEFB0 + 6 * s), 'name', 'Hover name of sprite $' + s.toString(16).toUpperCase().padStart(2, '0'));
    for (let i = 0; i < 13; i++) add(rw(u8, 0x809705 + 2 * i), 'name', 'Runner name ' + i);
    for (const [hid, wins] of Object.entries(meta.eng_win || {})) { const ws = wins.map(w => w[0] + '×' + w[1]); add(parseInt(hid, 16), 'menu', 'Game menu or screen, window ' + [...new Set(ws)].slice(0, 3).join(', ') + ' tiles'); }
    for (const id of meta.other || []) if (!(meta.eng_win || {})[id.toString(16).toUpperCase().padStart(4, '0')]) add(id, 'other', 'Not referenced by anything known (may be unused)');
    const out = [];
    for (const e of list.values()) { const d = this.decode(e.id); if (d && d.codes.length <= 1500) { e.codes = d.codes; e.bytes = d.bytes; e.ptr = this.ptr(e.id); e.base = this.basePtr(e.id); out.push(e); } }
    out.sort((a, b) => a.id - b.id);
    return out;
  }
}

// ---- string <-> codes. Printable ASCII as is; other glyphs as {XX} (hex code).
function toCodes(s) {
  const out = []; let i = 0;
  while (i < s.length) {
    const m = /^\{([0-9A-Fa-f]{2})\}/.exec(s.slice(i));
    if (m) { out.push(parseInt(m[1], 16)); i += 4; continue; }
    const ch = s[i]; i++;
    if (ch === '\n' || ch === '\r') { out.push(32); continue; }
    out.push(ch.charCodeAt(0));
  }
  return out;
}
function fromCodes(codes) { return codes.map(c => (c >= 32 && c < 127 && c !== 123 && c !== 125) ? String.fromCharCode(c) : '{' + c.toString(16).toUpperCase().padStart(2, '0') + '}').join(''); }

// ---- writing
function hookCode() {
  const b = [], lab = {}, fix = [];
  const emit = (...x) => b.push(...x), here = () => b.length;
  const long = (op, a) => emit(op, a & 0xFF, (a >> 8) & 0xFF, a >> 16);
  const br = (op, name) => { emit(op, 0); fix.push([b.length - 1, name]); };
  emit(0x08, 0xC2, 0x30, 0x48, 0xDA, 0xA2, 0x00, 0x00);          // php; rep #$30; pha; phx; ldx #0
  lab.loop = here(); emit(0x8A); long(0xCF, TABLE); br(0xB0, 'done'); // txa; cmp.l TABLE; bcs done
  long(0xBF, TABLE + 2); emit(0xC5, 0xCF); br(0xD0, 'next');         // lda.l TABLE+2,x; cmp $CF; bne next
  long(0xBF, TABLE + 3); emit(0xC5, 0xD0); br(0xD0, 'next');         // lda.l TABLE+3,x; cmp $D0; bne next
  long(0xBF, TABLE + 5); emit(0x85, 0xCF);                           // lda.l TABLE+5,x; sta $CF
  long(0xBF, TABLE + 6); emit(0x85, 0xD0); br(0x80, 'done');         // lda.l TABLE+6,x; sta $D0; bra done
  lab.next = here(); emit(0x8A, 0x18, 0x69, 0x06, 0x00, 0xAA); br(0x80, 'loop');
  lab.done = here(); emit(0xFA, 0x68, 0x28, 0xF4, 0x7E, 0x7E, 0xAB); long(0x5C, 0x80FE48); // plx; pla; plp; pea $7E7E; plb; jml $80FE48
  for (const [at, name] of fix) { const d = lab[name] - (at + 1); if (d < -128 || d > 127) throw new Error('branch'); b[at] = d & 0xFF; }
  return Uint8Array.from(b);
}
// edits: Map(id -> codes). inv: inventory (for slot sizes). Returns {rom, report}
function applyTextEdits(romU8, inv, edits) {
  let out = new Uint8Array(romU8); const T = new Texts(out), report = [];
  // spans of every known text at its BASE pointer, to know how much room each one has in place
  const spans = [];
  for (const e of inv) { if (e.base == null) continue; const d = T.decodeAt(e.base); if (d) spans.push([e.base, e.base + d.bytes, e.id]); }
  spans.sort((a, b) => a[0] - b[0]);
  const roomAt = base => {               // bytes free from base until the next text starts; 0 if base is inside another text
    let room = Infinity;
    for (const [s, e] of spans) {
      if (s < base && e > base) return 0;
      if (s > base && (s >> 16) === (base >> 16)) { room = Math.min(room, s - base); }
    }
    if (room === Infinity) { const d = T.decodeAt(base); room = d ? d.bytes : 0; }
    return room;
  };
  const pool = new Map();    // base ptr -> bytes (texts that must live in the pool)
  for (const [base, p] of T.redirects) {                    // keep earlier relocations that are not edited now
    const id = inv.find(e => e.base === base); if (id && edits.has(id.id)) continue;
    const d = T.decodeAt(p); if (d) pool.set(base, out.slice(L(p), L(p) + d.bytes));
  }
  for (const [id, codes] of edits) {
    if (codes.length > MAXLEN) throw new Error('text $' + id.toString(16) + ' is longer than ' + MAXLEN + ' characters');
    const base = T.basePtr(id); if (base == null) throw new Error('unknown text id ' + id);
    const enc = T.encode(codes), room = roomAt(base);
    if (enc.length <= room) { out.set(enc, L(base)); pool.delete(base); report.push({ id, where: 'in place', size: enc.length, room }); }
    else { pool.set(base, enc); report.push({ id, where: 'moved', size: enc.length, room }); }
  }
  if (pool.size || T.hooked) {
    if (out.length < 0x200000) { const big = new Uint8Array(0x200000); big.set(out); out = big; out[0x7FD7] = 0x0B; }
    // hook + table + pool, rebuilt from scratch
    for (let bk = POOL_FIRST; bk <= POOL_LAST; bk++) out.fill(0, L((bk << 16) | 0x8000), L((bk << 16) | 0x8000) + 0x8000);
    out.fill(0, L(HOOK), L(HOOK) + 0x8000);
    out.set(hookCode(), L(HOOK));
    let bank = POOL_FIRST, addr = 0x8000, o = 0;
    const entries = [...pool].sort((a, b) => a[0] - b[0]);
    if (entries.length * 6 + 2 > 0x7E00) throw new Error('too many moved texts');
    for (const [base, bytes] of entries) {
      if (addr + bytes.length + 2 > 0x10000) { bank++; addr = 0x8000; }
      if (bank > POOL_LAST) throw new Error('text pool full');
      const p = (bank << 16) | addr; out.set(bytes, L(p)); addr += bytes.length + 1;   // +1: the decoder reads words
      const t = L(TABLE + 2 + o); out[t] = base & 0xFF; out[t + 1] = (base >> 8) & 0xFF; out[t + 2] = base >> 16; out[t + 3] = p & 0xFF; out[t + 4] = (p >> 8) & 0xFF; out[t + 5] = p >> 16;
      o += 6;
      const r = report.find(x => x.where === 'moved' && T.basePtr(x.id) === base); if (r) r.addr = p;
    }
    out[L(TABLE)] = o & 0xFF; out[L(TABLE) + 1] = o >> 8;
    out[L(0x80FE44)] = 0x5C; out[L(0x80FE45)] = HOOK & 0xFF; out[L(0x80FE46)] = (HOOK >> 8) & 0xFF; out[L(0x80FE47)] = HOOK >> 16;
  }
  return { rom: out, report };
}

// ---- font preview: glyph rows for char code c (8 rows, 1bpp, MSB = left) and width in pixels
function glyph(u8, c) { const rows = []; for (let y = 0; y < 8; y++) rows.push(u8[L(0x95F2D0 + c * 8 + y)]); return { rows, w: u8[L(0x81ABC8 + c)] }; }

const api = { Texts, toCodes, fromCodes, applyTextEdits, glyph, hookCode, MAXLEN };
if (typeof module !== 'undefined') module.exports = api; else root.ST = api;
})(typeof window !== 'undefined' ? window : globalThis);
