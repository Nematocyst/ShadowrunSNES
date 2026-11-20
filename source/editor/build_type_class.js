// node build_type_class.js shadowrun.sfc ../data/type_class.json
// Which character types cannot get their own save slot when copied (map editor): items (their scripts mark them taken /
// give them to Jake: natives #C5 / #6F; the inventory only lists real types) and hireable runners (#78; the party keeps
// the record). selfref = the type's script names its own type id (it may look at the original's record).
const SV = require('./srvm.js'), fs = require('fs');
const u = new Uint8Array(fs.readFileSync(process.argv[2])), vm = new SV.VM(u);
const memo = new Map();
function natives(id, d) {
  if (memo.has(id)) return memo.get(id); const s = new Set(); memo.set(id, s); if (id >= SV.NSCR) return s;
  for (const i of vm.decode(id)) { if (i.name === 'native') s.add(i.arg); if (i.name === 'script' && d < 4) for (const x of natives(i.arg, d + 1)) s.add(x); }
  return s;
}
const L = a => ((a & 0x7F0000) >> 1) | (a & 0x7FFF), w = a => u[L(a)] | (u[L(a + 1)] << 8);
const b = a => u[L(a)];
function convScripts(n) {      // entry scripts of conversation n ($80947A -> bank $8D; see dump_scripts.py conv())
  const base = 0x8D0000 | w(0x80947A + 2 * n), out = []; let y = 4;
  for (let k = 0; k < 80; k++) { const t = b(base + y); if (t === 0xF8) break;
    const ln = b(base + y + 1), fl = b(base + y + 2), q = base + y + 3 + (fl & 0x0F); if (fl & 0x80) out.push(w(q)); y += 1 + ln; }
  return out;
}
const hireConv = new Set(); for (let n = 0; n < 139; n++) if (convScripts(n).some(s => natives(s, 0).has(0x78))) hireConv.add(n);
function convsOf(id, d, acc) {   // conversations a script opens: push conv; push self; native #94
  if (id >= SV.NSCR || d > 4) return acc; const ins = vm.decode(id);
  ins.forEach((i, k) => { if (i.name === 'native' && i.arg === 0x94 && k >= 2 && /push/.test(ins[k - 2].name)) acc.add(ins[k - 2].name === 'push0' ? 0 : ins[k - 2].arg);
    if (i.name === 'script') convsOf(i.arg, d + 1, acc); });
  return acc;
}
const RUNNER_TYPES = [0x0A4F, 0x0D2E, 0x1458, 0x079A, 0x089D, 0x1B6D, 0x0B52, 0x15D2, 0x0BA6, 0x078C, 0x0B3D, 0x098B];   // notes: runner name table
const items = [], runners = [...RUNNER_TYPES], selfref = [];
for (let t = 0; t < 0x209F; t += 7) {
  if (!w(0x8DB032 + t)) continue;
  const scr = w(0x8DB036 + t), n = natives(scr, 0);
  if (n.has(0x6F) || n.has(0xC5)) items.push(t);
  else if (RUNNER_TYPES.includes(t)) {} else if (n.has(0x78) || [...convsOf(scr, 0, new Set())].some(c => hireConv.has(c))) runners.push(t);
  if (scr < SV.NSCR && vm.decode(scr).some(i => /push/.test(i.name) && i.arg === t)) selfref.push(t);
}
fs.writeFileSync(process.argv[3], JSON.stringify({ items, runners, selfref }));
console.log('items', items.length, 'runners', runners.length, 'selfref', selfref.length);
