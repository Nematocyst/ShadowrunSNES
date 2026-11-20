// node build_msg_windows.js shadowrun.sfc ../data/text_index_meta.json
// Adds meta.msg_win = {message index: [[kind, w, h, script], ...]} to the text editor's meta, from the scripts:
//   'f' = floater, native #C7(dur, msg, style, h, w, y, x): window w x h tiles, text (w-2)*8 px wide, h-2 lines
//         (measured: wraps at exactly (w-2)*8 with the "word >= room left" rule, for w = 16 and 24)
//   'c' = native #99 / #D6 (text box / append): printed into the open conversation window
//   'm' = native #6D (add choice): an entry in the choose-from-list menu ($80E199: window 16 x 7 at 14,5); one line,
//         must be narrower than 104 px (measured: 103 fits, 104 breaks the menu)
const SV = require('./srvm.js'), fs = require('fs');
const vm = new SV.VM(new Uint8Array(fs.readFileSync(process.argv[2])));
const lit = i => !i || !/^push/.test(i.name) || /push\.(l|g)/.test(i.name) ? null : i.name === 'push0' ? 0 : i.name === 'push.sb' ? (i.arg < 128 ? i.arg : i.arg - 256) : i.arg;
const win = {};
const add = (m, e) => { const k = JSON.stringify(e.slice(0, 3)); (win[m] = win[m] || []); if (!win[m].some(x => JSON.stringify(x.slice(0, 3)) === k)) win[m].push(e); };
for (let id = 0; id < SV.NSCR; id++) {
  const ins = vm.decode(id);
  ins.forEach((it, k) => {
    if (it.name !== 'native') return; const n = it.arg, na = vm.nativeArgs(n), a = [];
    for (let j = k - na; j < k; j++) a.push(lit(ins[j]));
    if (n === 0xC7 && a[1] != null && a[3] != null && a[4] != null) add(a[1], ['f', a[4], a[3], id]);
    if ((n === 0x99 || n === 0xD6) && a[0] != null) add(a[0], ['c', 0, 0, id]);
    if (n === 0x6D && a[0] != null) add(a[0], ['m', 16, 7, id]);
  });
}
const meta = JSON.parse(fs.readFileSync(process.argv[3])); meta.msg_win = win;
fs.writeFileSync(process.argv[3], JSON.stringify(meta));
console.log('messages with known windows:', Object.keys(win).length, 'kinds', ['f', 'c', 'm'].map(k => k + '=' + Object.values(win).filter(l => l.some(e => e[0] === k)).length).join(' '));
