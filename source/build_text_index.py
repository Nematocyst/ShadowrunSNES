"""Index of every text in Shadowrun (SNES) and where the game uses it, for the text editor.

python3 build_text_index.py shadowrun.sfc sdump/index.json OUT.json
Each entry: {"id": text id (= address in bank $9D/$9E), "g": group, "l": [labels]}. Texts themselves are not stored:
the editor decodes them from the user's ROM.
Groups: conv (conversation answers, labelled by person + topic), msg (message table $80D980, labelled by the
scripts that show it), kw (conversation keywords $8D8000), name (hover names $8CEFB0 / runner names $809705),
other (decodes cleanly between known texts but nothing known points at it).
"""
import sys, os, json, re
HERE = os.path.dirname(os.path.abspath(__file__))
romf, idxf, out = sys.argv[1], sys.argv[2], sys.argv[3]
sys.argv = [sys.argv[0], romf, '/nonexistent']
src = open(os.path.join(HERE, 'dump_scripts.py')).read().split('# ---------------------------------------------------------------- decoding one script')[0]
g = {'__name__': 'ds', '__doc__': ''}; exec(compile(src, 'dump_scripts.py', 'exec'), g)
rom = g['rom']; RW = g['RW']; L = g['L']; text = g['text']
idx = json.load(open(idxf))

labels = {}; groups = {}
def add(tid, grp, lab):
    if tid in (0, 0xFFFF) or tid >= 0xC000: return
    labels.setdefault(tid, []);
    if lab not in labels[tid]: labels[tid].append(lab)
    order = ['conv', 'msg', 'kw', 'name', 'other']
    if tid not in groups or order.index(grp) < order.index(groups[tid]): groups[tid] = grp

def who_names(s):
    names = []
    for u in s['used']:
        names += re.findall(r'"([^"]+)"', u)
    if s.get('title'): names.append(s['title'])
    return list(dict.fromkeys(names))

conv_people = {}
for s in idx:
    for c in s['convs']:
        conv_people.setdefault(c, []).extend(who_names(s))
for n in range(g['NCONV']):
    try: entries = g['conv'](n)
    except Exception: continue
    ppl = ', '.join(dict.fromkeys(conv_people.get(n, []))) or 'conversation %d' % n
    for e in entries:
        add(e['tid'], 'conv', '%s · %s' % (ppl, g['topic_name'](e['topic'], e['kws'])))

msg_users = {}
for s in idx:
    for m in set(int(x) for x in re.findall(r'msg (\d+):', s['text'])):
        nm = who_names(s); msg_users.setdefault(m, []).append('script $%03X%s' % (s['id'], (' (' + ', '.join(nm[:2]) + ')') if nm else ''))
for i in range(0x264):
    u = msg_users.get(i, [])
    add(RW(0x80D980 + 2 * i), 'msg', 'Message %d' % i + (': ' + '; '.join(u[:3]) + (' +%d more' % (len(u) - 3) if len(u) > 3 else '') if u else ' (engine or menus)'))
for k in range(64): add(RW(0x8D8000 + 2 * k), 'kw', 'Keyword %d' % k)
for s in range(0x113): add(RW(0x8CEFB0 + 6 * s), 'name', 'Hover name of sprite $%02X' % s)
for i in range(13): add(RW(0x809705 + 2 * i), 'name', 'Runner name %d' % i)

# byte length of a text (to find the unreferenced ones between known texts)
def tlen(tid):
    bank = 0x9D + (1 if tid & 0x8000 else 0); p = L((bank << 16) | (tid | 0x8000)); bitpos = 0
    while bitpos < 40000:
        x = 0
        while True:
            if (rom[p + (bitpos >> 3)] >> (7 - (bitpos & 7))) & 1: x += 2
            bitpos += 1
            w = rom[0xE8000 + x] | rom[0xE8001 + x] << 8
            if w & 0x8000: break
            x = w
        w &= 0x7F7F
        for c in (w >> 8, w & 0xFF):
            if c == 0: break
            if c == 0x0A: return p, (bitpos + 7) // 8
    return p, None
known = {}
for t in labels:
    p, n = tlen(t)
    if n: known[p] = (t, n)
lo = min(known); hi = max(p + known[p][1] for p in known); p = lo
while p < hi:
    if p in known: p += known[p][1]; continue
    tid = (p - 0xE8000) if p < 0xF0000 else ((p - 0xF0000) | 0x8000)
    q, n = tlen(tid)
    if not n or n > 2000: p += 1; continue
    s = text(tid)
    if sum(1 for ch in s if ch.isalpha()) < len(s) * 0.5: p += 1; continue
    add(tid, 'other', 'Not referenced by anything known (may be unused)'); known[p] = (tid, n); p += n
res = [dict(id=t, g=groups[t], l=labels[t]) for t in sorted(labels)]
json.dump(res, open(out, 'w'), separators=(',', ':'))
from collections import Counter
print(len(res), 'texts', Counter(groups.values()), 'text area file $%X-$%X' % (lo, hi))
# compact meta for the editor (labels are rebuilt from the user's ROM at run time, so Expanded Dialogue texts appear too)
meta = dict(conv_people={n: list(dict.fromkeys(v)) for n, v in conv_people.items()},
            msg_users={i: v for i, v in msg_users.items()},
            other=[t for t in labels if groups[t] == 'other'], nconv=g['NCONV'])
json.dump(meta, open(out.replace('.json', '_meta.json'), 'w'), separators=(',', ':'))
print('meta bytes', len(json.dumps(meta)))
