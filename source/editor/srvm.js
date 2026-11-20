// Shadowrun (SNES) script VM tools: decompile scripts to SRScript text and compile SRScript back to bytecode.
// VM (interpreter $80F353, handlers via $80F27E): 16-bit values on the 65816 stack; locals = thread DP+$13+n.
// Script directory: bank $82D970+id, address $82DD18+2*id, argument bytes $82E810+id, returns-value flag
// $82E468+id. A script = [locals size][stack size] then code; jump/call operands are offsets from the code start.
// Natives: op $58 n, argument count $82D895+n, returns-value flag $82D7BA+n; the LAST pushed argument is the
// routine's $00.
(function (root) {
'use strict';
const L = a => ((a & 0x7F0000) >> 1) | (a & 0x7FFF);
const NSCR = 936;
// brand-new scripts: ids $400-$5FF (the Runner Pack uses 936-950 for its own). Directory of the new ones at
// $AC:A400 (7 bytes each: address 3, argument bytes, returns flag, length word); header 'SRNEW' 1 at $AC:A200
// with the entry count at $AC:A206 and the original bytes of the three hooked directory reads at $AC:A210 / A230 / A238.
const NEW_BASE = 0x400, NEW_MAX = 0x200, NEWHDR = 0xACA200, NEWTAB = 0xACA400, NEWCODE = 0xACA240;
const HOOKS = [[0x80C298, 25], [0x80F433, 7], [0x80F473, 7]];   // directory (bank/args/address), op $52 args, op $52 returns
function readNewDir(u8) {
  const m = new Map(); if (u8.length < 0x200000) return m;
  const b = a => u8[L(a)], w = a => u8[L(a)] | (u8[L(a + 1)] << 8);
  if (String.fromCharCode(...u8.slice(L(NEWHDR), L(NEWHDR) + 5)) !== 'SRNEW') return m;
  const n = w(NEWHDR + 6);
  for (let k = 0; k < n && k < NEW_MAX; k++) { const e = NEWTAB + 7 * k; if (!b(e + 2)) continue;
    m.set(NEW_BASE + k, { addr: w(e) | (b(e + 2) << 16), args: b(e + 3) >> 1, ret: b(e + 4) !== 0, len: w(e + 5) }); }
  return m;
}

// opcode -> [mnemonic, operand bytes]
const OPS = {
  0x00: ['push.b', 1], 0x02: ['push.lb', 1], 0x04: ['push.gb', 2], 0x0A: ['push.sb', 1], 0x0C: ['push.lsb', 1],
  0x0E: ['push.gsb', 2], 0x14: ['push.w', 2], 0x16: ['push.lw', 1], 0x18: ['push.gw', 2], 0x2C: ['pop.lb', 1],
  0x2E: ['pop.gb', 2], 0x34: ['pop.lw', 1], 0x36: ['pop.gw', 2], 0x44: ['jz', 2], 0x46: ['jnz', 2], 0x48: ['jmp', 2],
  0x4C: ['call', 2], 0x50: ['ret', 0], 0x52: ['script', 2], 0x54: ['halt', 0], 0x56: ['end', 0], 0x58: ['native', 1],
  0xBA: ['dup', 0], 0xBC: ['drop', 0], 0xC0: ['push0', 0], 0xC2: ['push.lb0', 0],
};
// two-operand ops: opcode -> [operator or function name]. Variants: _sl = left operand signed, _sr = right
// operand signed, _ss = both. $B0 works exactly like $AA (==) and $B8 like $B2 (!=).
const BIN = {
  0x5C: '+', 0x5E: '-', 0x60: '*', 0x62: 'mul_sl', 0x64: 'mul_sr', 0x66: 'mul_ss', 0x68: '/', 0x6A: 'div_sl', 0x6C: 'div_sr',
  0x6E: 'div_ss', 0x70: '%', 0x72: 'mod_sl', 0x74: 'mod_sr', 0x76: 'mod_ss', 0x7A: '<<', 0x7C: '>>', 0x7E: '&', 0x80: '|',
  0x82: '^', 0x8A: '<', 0x8C: 'lt_sl', 0x8E: 'lt_sr', 0x92: '<=', 0x94: 'le_sl', 0x96: 'le_sr', 0x9A: '>', 0x9C: 'gt_sl',
  0x9E: 'gt_sr', 0xA2: '>=', 0xA4: 'ge_sl', 0xA6: 'ge_sr', 0xAA: '==', 0xAC: 'eq_sl', 0xAE: 'eq_sr', 0xB0: '==',
  0xB2: '!=', 0xB4: 'ne_sl', 0xB6: 'ne_sr', 0xB8: '!=',
};
const UN = { 0x78: 'neg', 0x84: '~', 0x86: 'inc', 0x88: 'dec', 0xBE: 'bool' };
for (const [k, v] of Object.entries(BIN)) OPS[k] = [/^[a-z]/.test(v) ? v : 'bin' + v, 0];
for (const [k, v] of Object.entries(UN)) OPS[k] = [v === '~' ? 'not' : v, 0];
const BIN_OP = {}; for (const [k, v] of Object.entries(BIN)) if (!(+k === 0xB0 || +k === 0xB8)) BIN_OP[v] = +k;
const UN_OP = { neg: 0x78, '~': 0x84, inc: 0x86, dec: 0x88, bool: 0xBE };
const SAME = { 0xB0: 0xAA, 0xB8: 0xB2 };

const NATIVES = /*NATIVES*/{};
const GLOBALS = { 0x3C11: 'karma', 0x3C00: 'max_stamina', 0x3BFB: 'body', 0x3BFC: 'quickness', 0x3BFD: 'strength',
  0x3BFF: 'charisma', 0x2DE2: 'next_location', 0x3C18: 'dermal', 0x3C19: 'wired' };
const GLOBAL_ADDR = {}; for (const [k, v] of Object.entries(GLOBALS)) GLOBAL_ADDR[v] = +k;
const NATIVE_ID = {}; for (const [k, v] of Object.entries(NATIVES)) { NATIVE_ID[v.replace('?', '')] = +k; }

const hex = (n, w) => '$' + n.toString(16).toUpperCase().padStart(w, '0');

class VM {
  constructor(u8) { this.u8 = u8; this.newDir = readNewDir(u8); this.pending = new Map(); this.gone = new Set(); }
  // pending: id -> [args, returns] of new scripts being written in the editor (not in this ROM yet)
  known(id) { return id < NSCR || ((this.newDir.has(id) || this.pending.has(id)) && !this.gone.has(id)); }   // gone: new scripts deleted in the editor
  inRom(id) { return id < NSCR || this.newDir.has(id); }
  b(a) { return this.u8[L(a)]; }
  w(a) { return this.u8[L(a)] | (this.u8[L(a + 1)] << 8); }
  scriptAddr(id) { if (id >= NSCR) { const n = this.newDir.get(id); return n ? n.addr : 0; } return (this.b(0x82D970 + id) << 16) | this.w(0x82DD18 + 2 * id); }
  scriptArgs(id) { const p = this.pending.get(id); if (p) return p[0]; if (id < NSCR) return this.b(0x82E810 + id) >> 1; const n = this.newDir.get(id); return n ? n.args : 1; }
  scriptRet(id) { const p = this.pending.get(id); if (p) return p[1]; if (id < NSCR) return this.b(0x82E468 + id) !== 0; const n = this.newDir.get(id); return n ? n.ret : false; }
  nativeArgs(n) { return this.b(0x82D895 + n); }
  nativeRet(n) { return this.b(0x82D7BA + n) !== 0; }
  header(id) { const a = this.scriptAddr(id); return [this.b(a), this.b(a + 1)]; }
  // reachable instructions: [{pc, op, name, arg, len}]
  decode(id) {
    const base = this.scriptAddr(id) + 2, seen = new Map(), todo = [0];
    while (todo.length) {
      let pc = todo.pop();
      while (!seen.has(pc) && pc >= 0 && pc < 0x4000) {
        const op = this.b(base + pc), d = OPS[op];
        if (!d) { seen.set(pc, { pc, op, name: '??', arg: null, len: 1 }); break; }
        const [name, n] = d; const arg = n === 1 ? this.b(base + pc + 1) : n === 2 ? this.w(base + pc + 1) : null;
        seen.set(pc, { pc, op, name, arg, len: 1 + n });
        if (name === 'jz' || name === 'jnz' || name === 'call') todo.push(arg);
        if (name === 'jmp') { todo.push(arg); break; }
        if (name === 'end' || name === 'ret' || name === 'halt') break;
        if (name === 'script' && !this.known(arg)) break;
        pc += 1 + n;
      }
    }
    return [...seen.values()].sort((a, b) => a.pc - b.pc);
  }
  // stack effect [pops, pushes]
  effect(ins, sigs) {
    const { name, op, arg } = ins;
    if (name.startsWith('push')) return [0, 1];
    if (name.startsWith('pop.') || name === 'drop' || name === 'jz' || name === 'jnz' || name === 'end') return [1, 0];
    if (BIN[op] != null) return [2, 1];
    if (UN[op] != null) return [1, 1];
    if (name === 'dup') return [1, 2];
    if (name === 'native') return [this.nativeArgs(arg), this.nativeRet(arg) ? 1 : 0];
    if (name === 'script') return this.known(arg) ? [this.scriptArgs(arg), this.scriptRet(arg) ? 1 : 0] : [0, 0];
    if (name === 'call') return (sigs && sigs.get(arg)) || [0, 0];
    return [0, 0];
  }
  subSig(byPc, target, sigs, depth) {
    if (depth > 4) return null;
    const found = new Set(), seen = new Set(), todo = [[target, 0, 0]];
    while (todo.length) {
      const [pc, d0, mn0] = todo.pop(); let d = d0, mn = mn0;
      const key = pc + ':' + d; if (seen.has(key) || !byPc.has(pc) || seen.size > 4000) continue; seen.add(key);
      const ins = byPc.get(pc);
      if (ins.name === 'call' && !sigs.has(ins.arg)) { sigs.set(ins.arg, ins.arg !== target ? this.subSig(byPc, ins.arg, sigs, depth + 1) : null); if (!sigs.get(ins.arg)) return null; }
      const [po, pu] = this.effect(ins, sigs); d -= po; mn = Math.min(mn, d); d += pu;
      if (ins.name === 'ret') { found.add((-mn) + ',' + (d - mn)); continue; }
      if (ins.name === 'end' || ins.name === 'halt' || ins.name === '??') continue;
      if (ins.name === 'jz' || ins.name === 'jnz' || ins.name === 'jmp') todo.push([ins.arg, d, mn]);
      if (ins.name !== 'jmp') todo.push([pc + ins.len, d, mn]);
    }
    return found.size === 1 ? [...found][0].split(',').map(Number) : null;
  }
  // ------------------------------------------------------------ decompiler
  decompile(id, annotate) {
    const ins = this.decode(id), byPc = new Map(ins.map(i => [i.pc, i]));
    const targets = new Set(ins.filter(i => ['jz', 'jnz', 'jmp', 'call'].includes(i.name)).map(i => i.arg));
    const subs = new Set(ins.filter(i => i.name === 'call').map(i => i.arg));
    const jumpTargets = new Set(ins.filter(i => ['jz', 'jnz', 'jmp'].includes(i.name)).map(i => i.arg));
    const sigs = new Map(); for (const t of subs) if (!sigs.has(t)) sigs.set(t, this.subSig(byPc, t, sigs, 0));
    const lines = [], st = []; let entryArgs = this.scriptArgs(id), inEntry = true, prevEnd = null;
    const [h0, h1] = this.header(id);
    lines.push('script ' + hex(id, 3) + ' args ' + this.scriptArgs(id) + ' returns ' + (this.scriptRet(id) ? 'yes' : 'no') + ' locals ' + h0 + ' stack ' + h1);
    const pop = () => { if (st.length) return st.pop(); if (inEntry && entryArgs > 0) { entryArgs--; return 'arg' + (entryArgs + 1); } return 'pop()'; };
    const flush = () => { while (st.length) lines.push('    push ' + st.shift()); };
    const emit = (s, note) => { lines.push('    ' + s + (note ? '    ; ' + note : '')); };
    const lit = i => {
      if (i.name === 'push0') return '0';
      if (i.name === 'push.b') return i.arg === 0 ? '$00' : String(i.arg);
      if (i.name === 'push.sb') return i.arg & 0x80 ? String(i.arg - 256) : '+' + i.arg;
      return hex(i.arg, 4);
    };
    const gname = (a, kind) => {
      if (kind === 'gw') return GLOBALS[a] && a !== 0x3C18 && a !== 0x3C19 ? GLOBALS[a] + '.w' : 'gw[' + hex(a, 4) + ']';
      if (kind === 'gb' && GLOBALS[a]) return GLOBALS[a];
      if (kind === 'gb' && a >= 0x3BBB && a < 0x3BBB + 64) return 'var[' + (a - 0x3BBB) + ']';
      return kind + '[' + hex(a, 4) + ']';
    };
    for (const i of ins) {
      if (targets.has(i.pc) || (prevEnd != null && i.pc !== prevEnd)) {
        inEntry = false; flush(); const h4 = i.pc.toString(16).toUpperCase().padStart(4, '0');
        if (subs.has(i.pc)) lines.push('sub_' + h4 + ':');
        if (!subs.has(i.pc) || jumpTargets.has(i.pc)) lines.push('L_' + h4 + ':');
      }
      prevEnd = i.pc + i.len;
      const n = i.name, a = i.arg;
      if (n === 'push0' || n === 'push.b' || n === 'push.sb' || n === 'push.w') st.push(lit(i));
      else if (n === 'push.lb0') st.push('self');
      else if (n === 'push.lb') st.push('L.b' + a);
      else if (n === 'push.lsb') st.push('L.sb' + a);
      else if (n === 'push.lw') st.push('L.w' + a);
      else if (n === 'push.gb') st.push(gname(a, 'gb'));
      else if (n === 'push.gsb') st.push(gname(a, 'gsb'));
      else if (n === 'push.gw') st.push(gname(a, 'gw'));
      else if (n === 'pop.lb') emit((a === 0 ? 'self' : 'L.b' + a) + ' = ' + pop());
      else if (n === 'pop.lw') emit('L.w' + a + ' = ' + pop());
      else if (n === 'pop.gb') emit(gname(a, 'gb') + ' = ' + pop());
      else if (n === 'pop.gw') emit(gname(a, 'gw') + ' = ' + pop());
      else if (BIN[i.op] != null) { const y = pop(), x = pop(), o = BIN[i.op]; st.push(/^[a-z]/.test(o) ? o + '(' + x + ', ' + y + ')' : '(' + x + ' ' + o + ' ' + y + ')'); }
      else if (UN[i.op] != null) { const x = pop(), o = UN[i.op]; st.push(o === '~' ? '(~' + x + ')' : o + '(' + x + ')'); }
      else if (n === 'dup') { const x = pop(); flush(); emit('push dup(' + x + ')'); }
      else if (n === 'drop') { const x = pop(); if (x === 'pop()' || /^arg\d+$/.test(x)) { flush(); emit('drop'); } else { flush(); emit(/^sub_/.test(x) ? 'drop ' + x : x); } }
      else if (n === 'jz' || n === 'jnz') { const c = pop(); flush(); emit('if ' + (n === 'jz' ? 'not ' : '') + c + ' goto L_' + a.toString(16).toUpperCase().padStart(4, '0')); }
      else if (n === 'jmp') { flush(); emit('goto L_' + a.toString(16).toUpperCase().padStart(4, '0')); }
      else if (n === 'call') {
        const sg = sigs.get(a), nm = 'sub_' + a.toString(16).toUpperCase().padStart(4, '0');
        if (sg && sg[1] <= 1) { const args = []; for (let k = 0; k < sg[0]; k++) args.unshift(pop()); const c = nm + '(' + args.join(', ') + ')'; if (sg[1]) st.push(c); else { flush(); emit(c); } }
        else { flush(); emit('gosub ' + nm); }
      }
      else if (n === 'ret') { flush(); emit('return'); }
      else if (n === 'end') { const v = pop(); flush(); emit(v === 'pop()' || /^arg\d+$/.test(v) ? 'end' : 'end ' + v); }
      else if (n === 'halt') { flush(); emit('halt'); }
      else if (n === 'script') {
        if (!this.known(a)) { flush(); emit('script_' + a.toString(16).toUpperCase().padStart(3, '0') + '()', 'outside the directory'); continue; }
        const args = []; for (let k = 0; k < this.scriptArgs(a); k++) args.unshift(pop());
        const c = 'script_' + a.toString(16).toUpperCase().padStart(3, '0') + '(' + args.join(', ') + ')';
        if (this.scriptRet(a)) st.push(c); else { flush(); emit(c, annotate && annotate('script', a, args)); }
      }
      else if (n === 'native') {
        const args = []; for (let k = 0; k < this.nativeArgs(a); k++) args.unshift(pop());
        const nm = NATIVES[a] ? NATIVES[a].replace('?', '') : 'native_' + a.toString(16).toUpperCase().padStart(2, '0');
        const c = nm + '(' + args.join(', ') + ')';
        if (this.nativeRet(a)) st.push(c); else { flush(); emit(c, annotate && annotate('native', a, args)); }
      }
      else { flush(); emit('opcode_' + i.op.toString(16).toUpperCase().padStart(2, '0') + '()', 'unknown opcode'); }
    }
    flush();
    return lines.join('\n') + '\n';
  }
}

// ------------------------------------------------------------ compiler
class CompileError extends Error { constructor(msg, line) { super('line ' + line + ': ' + msg); this.line = line; this.msg = msg; } }
function tokenize(src, lineNo) {
  const toks = []; let i = 0;
  const re = /\s*(?:(\$[0-9A-Fa-f]+)|(\+\d+)|(\d+)|([A-Za-z_][A-Za-z0-9_.]*\??)|(<<|>>|<=|>=|==|!=|[-+*/%&|^~()<>=,{}\[\]:]))/y;
  while (i < src.length) {
    if (/^\s*(;|\/\/)/.test(src.slice(i))) break;
    if (/^\s*$/.test(src.slice(i))) break;
    re.lastIndex = i; const m = re.exec(src);
    if (!m) throw new CompileError('cannot read "' + src.slice(i).trim().slice(0, 20) + '"', lineNo);
    i = re.lastIndex;
    const prev = toks[toks.length - 1], afterValue = prev && (prev.t === 'num' || prev.t === 'id' || prev.s === ')' || prev.s === ']');
    if (m[1]) toks.push({ t: 'num', s: m[1] }); else if (m[2]) { if (afterValue) { toks.push({ t: 'op', s: '+' }); toks.push({ t: 'num', s: m[2].slice(1) }); } else toks.push({ t: 'num', s: m[2] }); } else if (m[3]) toks.push({ t: 'num', s: m[3] });
    else if (m[4]) toks.push({ t: 'id', s: m[4] }); else toks.push({ t: 'op', s: m[5] });
  }
  return toks;
}
function numToPush(s, neg, line) {   // literal text -> [opcode, operand bytes]
  let v;
  if (s[0] === '$') {
    v = parseInt(s.slice(1), 16); const digits = s.length - 1;
    if (neg) v = -v;
    if (digits === 4 && !neg) return [0x14, v & 0xFF, v >> 8];
    if (digits === 2 && !neg) return [0x00, v];
  } else if (s[0] === '+') { v = parseInt(s.slice(1), 10); if (v > 127) throw new CompileError('+N literals are signed bytes (0..127)', line); return [0x0A, v]; }
  else { v = parseInt(s, 10); if (neg) v = -v; }
  if (v < -32768 || v > 65535) throw new CompileError('number out of range: ' + (neg ? '-' : '') + s, line);
  if (v === 0) return [0xC0];
  if (v > 0 && v < 256) return [0x00, v];
  if (v < 0 && v >= -128) return [0x0A, v & 0xFF];
  v &= 0xFFFF; return [0x14, v & 0xFF, v >> 8];
}
const PREC = [['|'], ['^'], ['&'], ['==', '!='], ['<', '<=', '>', '>='], ['<<', '>>'], ['+', '-'], ['*', '/', '%']];
const OPNAME = { '+': 0x5C, '-': 0x5E, '*': 0x60, '/': 0x68, '%': 0x70, '<<': 0x7A, '>>': 0x7C, '&': 0x7E, '|': 0x80, '^': 0x82,
  '<': 0x8A, '<=': 0x92, '>': 0x9A, '>=': 0xA2, '==': 0xAA, '!=': 0xB2 };
const VARIANT = {}; for (const [k, v] of Object.entries(BIN)) if (/^[a-z]/.test(v)) VARIANT[v] = +k;

class Compiler {
  constructor(vm, sigOverride) { this.vm = vm; this.sigOverride = sigOverride || {}; }
  scriptSig(id) { const o = this.sigOverride[id]; return o ? o : [this.vm.scriptArgs(id), this.vm.scriptRet(id)]; }
  // parse a full expression from tokens
  parseExpr(tk, line) {
    let p = 0;
    const peek = () => tk[p], next = () => tk[p++];
    const expect = s => { const t = next(); if (!t || t.s !== s) throw new CompileError('expected "' + s + '"' + (t ? ' but found "' + t.s + '"' : ''), line); };
    const bin = lvl => {
      if (lvl === PREC.length) return unary();
      let left = bin(lvl + 1);
      while (peek() && peek().t === 'op' && PREC[lvl].includes(peek().s)) { const o = next().s; const right = bin(lvl + 1); left = { k: 'bin', op: OPNAME[o], a: left, b: right }; }
      return left;
    };
    const unary = () => {
      const t = peek();
      if (t && t.t === 'op' && t.s === '-') { next(); const u = peek(); if (u && u.t === 'num') { next(); return { k: 'num', code: numToPush(u.s, true, line) }; } return { k: 'un', op: 0x78, a: unary() }; }
      if (t && t.t === 'op' && t.s === '~') { next(); return { k: 'un', op: 0x84, a: unary() }; }
      return primary();
    };
    const args = () => { expect('('); const out = []; if (peek() && peek().s === ')') { next(); return out; }
      for (;;) { out.push(bin(0)); const t = next(); if (!t) throw new CompileError('missing ")"', line); if (t.s === ')') return out; if (t.s !== ',') throw new CompileError('expected "," or ")"', line); } };
    const primary = () => {
      const t = next(); if (!t) throw new CompileError('expression expected', line);
      if (t.t === 'num') return { k: 'num', code: numToPush(t.s, false, line) };
      if (t.t === 'op' && t.s === '(') { const e = bin(0); expect(')'); return e; }
      if (t.t !== 'id') throw new CompileError('unexpected "' + t.s + '"', line);
      const s = t.s;
      if (peek() && peek().s === '[' && /^(gb|gsb|gw|var)$/.test(s)) { next(); const n = next(); expect(']'); if (!n || n.t !== 'num') throw new CompileError('number expected in []', line);
        const v = n.s[0] === '$' ? parseInt(n.s.slice(1), 16) : parseInt(n.s, 10);
        if (s === 'var') { if (v < 0 || v > 63) throw new CompileError('var[n] has n from 0 to 63', line); return { k: 'g', kind: 'gb', a: 0x3BBB + v }; }
        return { k: 'g', kind: s, a: v }; }
      if (peek() && peek().s === '(') {
        const as = args(), nm = s.replace('?', '');
        if (nm === 'pop' && !as.length) return { k: 'pop' };
        if (nm === 'dup') { if (as.length !== 1) throw new CompileError('dup takes one value', line); return { k: 'dup', a: as[0] }; }
        if (UN_OP[nm] != null && nm !== '~') { if (as.length !== 1) throw new CompileError(nm + ' takes one value', line); return { k: 'un', op: UN_OP[nm], a: as[0] }; }
        if (VARIANT[nm] != null) { if (as.length !== 2) throw new CompileError(nm + ' takes two values', line); return { k: 'bin', op: VARIANT[nm], a: as[0], b: as[1] }; }
        let m;
        if ((m = /^script_([0-9A-Fa-f]{1,3})$/.exec(nm))) { const id = parseInt(m[1], 16); const [na, rt] = this.scriptSig(id);
          if (id >= NEW_BASE && !this.vm.known(id) && !this.sigOverride[id]) throw new CompileError('there is no new script ' + hex(id, 3) + ' (yet)', line);
          if (this.vm.known(id) && as.length !== na) throw new CompileError('script ' + hex(id, 3) + ' takes ' + na + ' argument' + (na === 1 ? '' : 's') + ', not ' + as.length, line);
          return { k: 'script', id, args: as, ret: rt }; }
        if ((m = /^sub_([0-9A-Za-z_]+)$/.exec(nm))) return { k: 'call', label: nm, args: as };
        let nid = NATIVE_ID[nm]; if (nid == null && (m = /^native_([0-9A-Fa-f]{2})$/.exec(nm))) nid = parseInt(m[1], 16);
        if (nid == null) throw new CompileError('unknown command "' + nm + '"', line);
        const na = this.vm.nativeArgs(nid); if (as.length !== na) throw new CompileError(nm + ' takes ' + na + ' argument' + (na === 1 ? '' : 's') + ', not ' + as.length, line);
        return { k: 'native', id: nid, args: as, ret: this.vm.nativeRet(nid) };
      }
      let m;
      if (s === 'self') return { k: 'self' };
      if ((m = /^arg(\d+)$/.exec(s))) return { k: 'pop' };
      if ((m = /^L\.(b|sb|w)(\d+)$/.exec(s))) return { k: 'l', kind: m[1], n: +m[2] };
      if ((m = /^([a-z_]+)(\.w)?$/.exec(s)) && GLOBAL_ADDR[m[1]] != null) return { k: 'g', kind: m[2] ? 'gw' : 'gb', a: GLOBAL_ADDR[m[1]] };
      throw new CompileError('unknown name "' + s + '"', line);
    };
    const e = bin(0);
    if (p < tk.length) throw new CompileError('unexpected "' + tk[p].s + '"', line);
    return e;
  }
  gen(e, out, line) {   // expression -> bytes (pushes exactly one value; 'pop' pushes nothing: the value is already there)
    const k = e.k;
    if (k === 'num') out.code.push(...e.code);
    else if (k === 'pop') {}
    else if (k === 'self') out.code.push(0xC2);
    else if (k === 'l') { if (e.n > 255) throw new CompileError('local number too big', line); out.code.push(e.kind === 'b' ? 0x02 : e.kind === 'sb' ? 0x0C : 0x16, e.n); out.locals = Math.max(out.locals, e.n + (e.kind === 'w' ? 2 : 1)); }
    else if (k === 'g') out.code.push(e.kind === 'gb' ? 0x04 : e.kind === 'gsb' ? 0x0E : 0x18, e.a & 0xFF, e.a >> 8);
    else if (k === 'bin') { this.gen(e.a, out, line); this.gen(e.b, out, line); out.code.push(e.op); }
    else if (k === 'un') { this.gen(e.a, out, line); out.code.push(e.op); }
    else if (k === 'native') { if (!e.ret) throw new CompileError(NATIVES[e.id] + ' does not give a value', line); for (const a of e.args) this.gen(a, out, line); out.code.push(0x58, e.id); }
    else if (k === 'script') { if (!e.ret) throw new CompileError('script ' + hex(e.id, 3) + ' does not give a value', line); for (const a of e.args) this.gen(a, out, line); out.code.push(0x52, e.id & 0xFF, e.id >> 8); }
    else if (k === 'call') { for (const a of e.args) this.gen(a, out, line); out.code.push(0x4C, 0, 0); out.fix.push({ at: out.code.length - 2, label: e.label, line }); }
    else if (k === 'dup') throw new CompileError('dup(...) is only allowed as "push dup(...)"', line);
    else throw new CompileError('cannot use this here', line);
  }
  store(target, out, line) {
    const t = target;
    if (t.k === 'self') out.code.push(0x2C, 0);
    else if (t.k === 'l') { if (t.kind === 'sb') throw new CompileError('write L.b' + t.n + ', not L.sb' + t.n, line); out.code.push(t.kind === 'b' ? 0x2C : 0x34, t.n); out.locals = Math.max(out.locals, t.n + (t.kind === 'w' ? 2 : 1)); }
    else if (t.k === 'g') { if (t.kind === 'gsb') throw new CompileError('write gb[...], not gsb[...]', line); out.code.push(t.kind === 'gb' ? 0x2E : 0x36, t.a & 0xFF, t.a >> 8); }
    else throw new CompileError('cannot assign to this', line);
  }
  // source -> {header:{id,args,ret,locals,stack}, code:Uint8Array, lines}
  compile(src) {
    const out = { code: [], fix: [], labels: new Map(), locals: 0 }, blocks = [];
    let header = null, auto = 0;
    const lines = src.split('\n');
    const label = () => '@' + (auto++);
    const place = (name, line) => { if (out.labels.has(name)) throw new CompileError('label ' + name + ' is defined twice', line); out.labels.set(name, out.code.length); };
    const jump = (op, name, line) => { out.code.push(op, 0, 0); out.fix.push({ at: out.code.length - 2, label: name, line }); };
    for (let li = 0; li < lines.length; li++) {
      const line = li + 1, raw = lines[li]; let tk = tokenize(raw, line); if (!tk.length) continue;
      const s0 = tk[0].s;
      if (s0 === 'script' && tk[0].t === 'id' && (tk.length === 1 || tk[1].t === 'num')) {
        header = { args: 0, ret: false, locals: null, stack: null };
        if (tk[1]) header.id = parseInt(tk[1].s.replace('$', ''), tk[1].s[0] === '$' ? 16 : 10);
        for (let k = 2; k < tk.length; k += 2) { const key = tk[k].s, v = tk[k + 1] && tk[k + 1].s;
          if (key === 'args') header.args = +v; else if (key === 'returns') header.ret = v === 'yes'; else if (key === 'locals') header.locals = +v; else if (key === 'stack') header.stack = +v;
          else throw new CompileError('unknown header word "' + key + '"', line); }
        continue;
      }
      // label
      if (tk.length === 2 && tk[0].t === 'id' && tk[1].s === ':') { place(s0, line); continue; }
      if (tk.length >= 2 && tk[tk.length - 1].s === ':' && tk[0].t === 'id' && tk.length === 2) { place(s0, line); continue; }
      if (raw.trim().endsWith(':') && tk.length === 1 && tk[0].t === 'id') { place(s0, line); continue; }
      // closing brace (with optional else)
      if (s0 === '}') {
        const b = blocks.pop(); if (!b) throw new CompileError('"}" without a matching "{"', line);
        if (tk[1] && tk[1].s === 'else') {
          if (b.kind !== 'if') throw new CompileError('else only follows an if block', line);
          if (!tk[2] || tk[2].s !== '{' || tk.length !== 3) throw new CompileError('write "} else {"', line);
          const end = label(); jump(0x48, end, line); place(b.next, line); blocks.push({ kind: 'else', next: end, line }); continue;
        }
        if (tk.length > 1) throw new CompileError('unexpected text after "}"', line);
        if (b.kind === 'while') { jump(0x48, b.top, line); }
        place(b.next, line); continue;
      }
      if (s0 === 'if' || s0 === 'while') {
        let neg = false, rest = tk.slice(1);
        if (rest[0] && rest[0].s === 'not') { neg = true; rest = rest.slice(1); }
        if (rest.length && rest[rest.length - 1].s === '{') {
          const top = label(), next = label();
          if (s0 === 'while') place(top, line);
          this.gen(this.parseExpr(rest.slice(0, -1), line), out, line);
          jump(neg ? 0x46 : 0x44, next, line);
          blocks.push({ kind: s0, top, next, line }); continue;
        }
        if (s0 === 'if') {
          const gi = rest.findIndex(t => t.s === 'goto');
          if (gi < 1 || gi !== rest.length - 2) throw new CompileError('write "if <condition> goto <label>" or "if <condition> {"', line);
          this.gen(this.parseExpr(rest.slice(0, gi), line), out, line);
          jump(neg ? 0x44 : 0x46, rest[gi + 1].s, line); continue;
        }
        throw new CompileError('write "while <condition> {"', line);
      }
      if (s0 === 'goto') { if (tk.length !== 2) throw new CompileError('write "goto <label>"', line); jump(0x48, tk[1].s, line); continue; }
      if (s0 === 'gosub') { if (tk.length !== 2) throw new CompileError('write "gosub <label>"', line); jump(0x4C, tk[1].s, line); continue; }
      if (s0 === 'return' && tk.length === 1) { out.code.push(0x50); continue; }
      if (s0 === 'halt' && tk.length === 1) { out.code.push(0x54); continue; }
      if (s0 === 'drop') { if (tk.length > 1) this.gen(this.parseExpr(tk.slice(1), line), out, line); out.code.push(0xBC); continue; }
      if (s0 === 'end') { if (tk.length > 1) this.gen(this.parseExpr(tk.slice(1), line), out, line); out.code.push(0x56); continue; }
      if (s0 === 'push') {
        const e = this.parseExpr(tk.slice(1), line);
        if (e.k === 'dup') { this.gen(e.a, out, line); out.code.push(0xBA); } else this.gen(e, out, line);
        continue;
      }
      // assignment?
      const eq = tk.findIndex(t => t.s === '=');
      if (eq > 0) {
        const target = this.parseExpr(tk.slice(0, eq), line), value = this.parseExpr(tk.slice(eq + 1), line);
        this.gen(value, out, line); this.store(target, out, line); continue;
      }
      // call / expression statement
      const e = this.parseExpr(tk, line);
      if (e.k === 'native') { for (const a of e.args) this.gen(a, out, line); out.code.push(0x58, e.id); if (e.ret) out.code.push(0xBC); continue; }
      if (e.k === 'script') { for (const a of e.args) this.gen(a, out, line); out.code.push(0x52, e.id & 0xFF, e.id >> 8); if (e.ret) out.code.push(0xBC); continue; }
      if (e.k === 'call') { this.gen(e, out, line); out.call_result_unknown = true; continue; }
      // any other expression: evaluate and drop
      this.gen(e, out, line); out.code.push(0xBC);
    }
    if (blocks.length) throw new CompileError('"{" opened here is never closed', blocks[blocks.length - 1].line);
    for (const f of out.fix) {
      if (!out.labels.has(f.label)) throw new CompileError('label ' + f.label + ' does not exist', f.line);
      const v = out.labels.get(f.label); out.code[f.at] = v & 0xFF; out.code[f.at + 1] = v >> 8;
    }
    if (out.code.length > 0x3F00) throw new CompileError('script is too long (' + out.code.length + ' bytes)', lines.length);
    return { header: header || { args: 0, ret: false }, code: Uint8Array.from(out.code), locals: out.locals };
  }
}

// instruction stream of raw code bytes (for comparisons and stack analysis)
function decodeBytes(code) {
  const seen = new Map(), todo = [0];
  while (todo.length) {
    let pc = todo.pop();
    while (!seen.has(pc) && pc >= 0 && pc < code.length) {
      const op = code[pc], d = OPS[op]; if (!d) { seen.set(pc, { pc, op, name: '??', arg: null, len: 1 }); break; }
      const [name, n] = d; const arg = n === 1 ? code[pc + 1] : n === 2 ? code[pc + 1] | (code[pc + 2] << 8) : null;
      seen.set(pc, { pc, op, name, arg, len: 1 + n });
      if (name === 'jz' || name === 'jnz' || name === 'call') todo.push(arg);
      if (name === 'jmp') { todo.push(arg); break; }
      if (name === 'end' || name === 'ret' || name === 'halt') break;
      pc += 1 + n;
    }
  }
  return [...seen.values()].sort((a, b) => a.pc - b.pc);
}
// normalised stream: positions replaced by instruction index, equivalent opcodes merged
function normalise(ins) {
  const idx = new Map(ins.map((x, k) => [x.pc, k]));
  return ins.map(x => { let op = SAME[x.op] != null ? SAME[x.op] : x.op; let arg = x.arg;
    if (['jz', 'jnz', 'jmp', 'call'].includes(x.name)) arg = 'i' + idx.get(arg);
    if (x.op === 0x02 && arg === 0) { op = 0xC2; arg = null; }          // push.lb 0 == push.lb0
    return op.toString(16) + (arg == null ? '' : ':' + arg); });
}
// max stack depth reached from the entry (args already on the stack), for the header's stack size
function maxDepth(vm, code, args) {
  const ins = decodeBytes(code), by = new Map(ins.map(i => [i.pc, i])), sigs = new Map();
  for (const i of ins) if (i.name === 'call' && !sigs.has(i.arg)) sigs.set(i.arg, vm.subSig(by, i.arg, sigs, 0));
  let mx = args; const seen = new Set(), todo = [[0, args]];
  while (todo.length) {
    const [pc, d0] = todo.pop(), key = pc + ':' + d0; if (seen.has(key) || !by.has(pc) || seen.size > 20000) continue; seen.add(key);
    const i = by.get(pc); let d = d0;
    if (i.name === 'call') { const sg = sigs.get(i.arg); todo.push([i.arg, d]); d = sg ? d - sg[0] + sg[1] : d; }
    else { const [po, pu] = vm.effect(i, sigs); d = d - po + pu; }
    mx = Math.max(mx, d, d0 + (i.name === 'native' ? 0 : 0));
    if (i.name === 'ret' || i.name === 'end' || i.name === 'halt') continue;
    if (i.name === 'jz' || i.name === 'jnz' || i.name === 'jmp') todo.push([i.arg, d]);
    if (i.name !== 'jmp') todo.push([pc + i.len, d]);
  }
  return mx;
}


// ------------------------------------------------------------ writing scripts into a ROM
// An edited script goes back to its own place when it fits (up to the next script); otherwise into a pool in banks
// $AC-$AE: 'SRSCR' 1 at $AC:8000, count word $AC:8006, registry from $AC:8010 (9 bytes each: id word, original
// address 3, original room word, current length word), script bodies from $AC:A200. The directory ($82D970 bank,
// $82DD18 address, $82E810 argument bytes, $82E468 returns flag) is repointed. Scripts never cross a bank.
const POOL_FIRST = 0xAC, POOL_LAST = 0xAE, REG = 0xAC8000, BODY = 0xACB400;
// hook code for the new scripts: X = script id at all three places (16-bit A/X/Y). Ids outside $400..$400+count
// run the original bytes (vanilla table reads, or the Runner Pack's JSL, turned into a JML).
function newHookCode(origs, org) {
  const b = [], at = [], fix = [];
  const tail = o => { if (o[0] === 0x22) b.push(0x5C, o[1], o[2], o[3]); else { b.push(...o); b.push(0x6B); } };
  const long = (op, v) => b.push(op, v & 0xFF, (v >> 8) & 0xFF, v >> 16);
  const head = () => { b.push(0xDA, 0x8A, 0x38, 0xE9, NEW_BASE & 0xFF, NEW_BASE >> 8, 0x90, 0); const j1 = b.length - 1;   // phx; txa; sec; sbc #$400; bcc orig
    long(0xCF, NEWHDR + 6); b.push(0xB0, 0); const j2 = b.length - 1;                                                      // cmp count; bcs orig
    b.push(0x48, 0x0A, 0x0A, 0x0A, 0x38, 0xE3, 0x01, 0xAA, 0x68); return [j1, j2]; };                                       // X = 7k
  const land = js => { for (const j of js) b[j] = b.length - j - 1; };
  // 0: directory ($80C298): $71 address, $73 bank, $0264 argument bytes, X = 2*id
  at.push(b.length); let js = head();
  long(0xBF, NEWTAB); b.push(0x85, 0x71); long(0xBF, NEWTAB + 2); b.push(0x29, 0xFF, 0x00, 0x85, 0x73);
  long(0xBF, NEWTAB + 3); b.push(0x29, 0xFF, 0x00, 0x8D, 0x64, 0x02, 0x68, 0x0A, 0xAA, 0x6B);
  land(js); b.push(0xFA); tail(origs[0]);
  // 1 and 2: argument bytes ($80F433) / returns flag ($80F473): A and the zero flag from AND #$00FF
  for (const [k, off] of [[1, 3], [2, 4]]) {
    at.push(b.length); js = head(); long(0xBF, NEWTAB + off); b.push(0xFA, 0x29, 0xFF, 0x00, 0x6B);
    land(js); b.push(0xFA); tail(origs[k]);
  }
  for (const j of [...b.keys()]) if (b[j] > 0xFF) throw new Error('hook');
  return { code: Uint8Array.from(b), entry: at.map(x => org + x) };
}
function applyScripts(romU8, edits, opts) {
  let out = new Uint8Array(romU8); const vm = new VM(romU8), report = [];
  const sig = romU8.length >= 0x200000 && String.fromCharCode(...romU8.slice(L(REG), L(REG) + 5)) === 'SRSCR';
  const moved = new Map();
  if (sig) { const n = vm.w(REG + 6); for (let k = 0; k < n; k++) { const e = REG + 0x10 + 9 * k;
    moved.set(vm.w(e), { orig: vm.w(e + 2) | (vm.b(e + 4) << 16), room: vm.w(e + 5), cur: vm.scriptAddr(vm.w(e)), len: vm.w(e + 7) }); } }
  // room of every script in its original place: up to the next script in the same bank
  const starts = []; for (let id = 0; id < NSCR; id++) starts.push(moved.has(id) ? moved.get(id).orig : vm.scriptAddr(id));
  const sorted = [...new Set(starts)].sort((a, b) => a - b);
  const roomOf = (id, a) => {
    if (moved.has(id)) return moved.get(id).room;
    const nxt = sorted.find(s => s > a && (s >> 16) === (a >> 16));
    if (nxt != null) return nxt - a;
    const ins = vm.decode(id); return 2 + Math.max(...ins.map(i => i.pc + i.len));
  };
  const setDir = (id, a) => { out[L(0x82D970 + id)] = a >> 16; out[L(0x82DD18 + 2 * id)] = a & 0xFF; out[L(0x82DD18 + 2 * id) + 1] = (a >> 8) & 0xFF; };
  const pool = new Map();
  for (const [id, m] of moved) if (!edits.has(id)) pool.set(id, { orig: m.orig, room: m.room, bytes: romU8.slice(L(m.cur), L(m.cur) + m.len) });
  // new scripts: the ones already in the ROM, then this export's (null = delete)
  const fresh = new Map();
  for (const [id, n] of vm.newDir) fresh.set(id, { args: n.args, ret: n.ret, bytes: romU8.slice(L(n.addr), L(n.addr) + n.len) });
  for (const [id, s] of edits) {
    if (id >= NEW_BASE && id < NEW_BASE + NEW_MAX) {
      if (!s) { fresh.delete(id); report.push({ id, where: 'deleted' }); continue; }
      const bytes = new Uint8Array(2 + s.code.length); bytes[0] = s.locals; bytes[1] = s.stack; bytes.set(s.code, 2);
      fresh.set(id, { args: s.args, ret: s.ret, bytes }); report.push({ id, where: 'new', size: bytes.length }); continue;
    }
    if (id < 0 || id >= NSCR) throw new Error('script ' + hex(id, 3) + ' is outside the directory (new scripts are numbered from $400)');
    const bytes = new Uint8Array(2 + s.code.length); bytes[0] = s.locals; bytes[1] = s.stack; bytes.set(s.code, 2);
    const orig = moved.has(id) ? moved.get(id).orig : vm.scriptAddr(id), room = roomOf(id, orig);
    if (bytes.length <= room && !(opts && opts.forceMove)) { out.set(bytes, L(orig)); setDir(id, orig); report.push({ id, where: 'in place', size: bytes.length, room }); }
    else { pool.set(id, { orig, room, bytes }); report.push({ id, where: 'moved', size: bytes.length, room }); }
    out[L(0x82E810 + id)] = 2 * s.args; out[L(0x82E468 + id)] = s.ret ? 2 : 0;
  }
  const count = fresh.size ? Math.max(...fresh.keys()) - NEW_BASE + 1 : 0;
  for (let k = 0; k < count; k++) if (!fresh.has(NEW_BASE + k)) throw new Error('new scripts must be numbered without gaps: $' + (NEW_BASE + k).toString(16).toUpperCase() + ' is missing');
  const hadNew = romU8.length >= 0x200000 && String.fromCharCode(...romU8.slice(L(NEWHDR), L(NEWHDR) + 5)) === 'SRNEW';
  // original bytes at the three hooked places (kept in the header so that a re-export can restore or re-chain them)
  const origs = HOOKS.map(([a, n], k) => hadNew ? romU8.slice(L(NEWHDR + [0x10, 0x30, 0x38][k]), L(NEWHDR + [0x10, 0x30, 0x38][k]) + n) : romU8.slice(L(a), L(a) + n));
  if (pool.size || sig || fresh.size || hadNew) {
    if (out.length < 0x200000) { const big = new Uint8Array(0x200000); big.set(out); out = big; out[0x7FD7] = 0x0B; }
    for (let bk = POOL_FIRST; bk <= POOL_LAST; bk++) out.fill(0, L((bk << 16) | 0x8000), L((bk << 16) | 0x8000) + 0x8000);
    out.set([0x53, 0x52, 0x53, 0x43, 0x52, 1], L(REG)); out[L(REG + 6)] = pool.size & 0xFF; out[L(REG + 7)] = pool.size >> 8;
    if (pool.size > (0x2200 - 0x10) / 9) throw new Error('too many moved scripts');
    let bank = BODY >> 16, addr = BODY & 0xFFFF, k = 0;
    const place = bytes => { if (addr + bytes.length > 0x10000) { bank++; addr = 0x8000; } if (bank > POOL_LAST) throw new Error('script pool full');
      const a = (bank << 16) | addr; out.set(bytes, L(a)); addr += bytes.length; return a; };
    for (const [id, p] of [...pool].sort((a, b) => a[0] - b[0])) {
      const a = place(p.bytes); setDir(id, a);
      const e = L(REG + 0x10 + 9 * k++); out.set([id & 0xFF, id >> 8, p.orig & 0xFF, (p.orig >> 8) & 0xFF, p.orig >> 16, p.room & 0xFF, p.room >> 8, p.bytes.length & 0xFF, p.bytes.length >> 8], e);
      const r = report.find(x => x.id === id && x.where === 'moved'); if (r) r.addr = a;
    }
    if (count) {
      out.set([0x53, 0x52, 0x4E, 0x45, 0x57, 1, count & 0xFF, count >> 8], L(NEWHDR));
      origs.forEach((o, i) => out.set(o, L(NEWHDR + [0x10, 0x30, 0x38][i])));
      for (let i = 0; i < count; i++) { const f = fresh.get(NEW_BASE + i), a = place(f.bytes);
        out.set([a & 0xFF, (a >> 8) & 0xFF, a >> 16, 2 * f.args, f.ret ? 2 : 0, f.bytes.length & 0xFF, f.bytes.length >> 8], L(NEWTAB + 7 * i));
        const r = report.find(x => x.id === NEW_BASE + i && x.where === 'new'); if (r) r.addr = a; }
      const { code, entry } = newHookCode(origs.map(o => [...o]), NEWCODE);
      if (NEWCODE + code.length > NEWTAB) throw new Error('hook code too long');
      out.set(code, L(NEWCODE));
      HOOKS.forEach(([a, n], i) => { const p = L(a), t = entry[i]; out.set([0x22, t & 0xFF, (t >> 8) & 0xFF, t >> 16], p); for (let j = 4; j < n; j++) out[p + j] = 0xEA; });
    } else if (hadNew) HOOKS.forEach(([a], i) => out.set(origs[i], L(a)));   // last new script deleted: put the old bytes back
  }
  return { rom: out, report };
}
// compile source to what applyScripts needs; header sizes are never made smaller than the original's
function build(vm, src, id) {
  const C = new Compiler(vm), r = C.compile(src);
  const h = r.header; if (h.id != null && id != null && h.id !== id) throw new CompileError('this text says script ' + hex(h.id, 3) + ' at the top', 1);
  const sid = id != null ? id : h.id; const [o0, o1] = vm.inRom(sid) ? vm.header(sid) : [0, 0];
  // stack size: keep the original unless the new code goes deeper than the old one did (same estimate on both;
  // changing the size changes thread memory layout, so unchanged scripts must keep it exactly)
  let stack = o1;
  if (vm.inRom(sid)) { const a = vm.scriptAddr(sid) + 2, ins = vm.decode(sid), end = Math.max(...ins.map(i => i.pc + i.len));
    const old = maxDepth(vm, vm.u8.slice(L(a), L(a) + end), vm.scriptArgs(sid)), now = maxDepth(vm, r.code, h.args);
    if (now > old) stack = o1 + 2 * (now - old); }
  else stack = 2 * maxDepth(vm, r.code, h.args) + 4;
  if (h.stack) stack = Math.max(stack, h.stack);
  return { id: sid, code: r.code, args: h.args, ret: h.ret, locals: Math.max(o0, r.locals, h.locals || 0), stack };
}

const api = { applyScripts, build, VM, NEW_BASE, NEW_MAX, Compiler, CompileError, decodeBytes, normalise, maxDepth, NATIVES, NATIVE_ID, OPS, NSCR, L, hex };
if (typeof module !== 'undefined') module.exports = api; else root.SV = api;
})(typeof window !== 'undefined' ? window : globalThis);
