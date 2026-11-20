"""Merges window logs from the emulator (fz_*.json: text id -> {"w,h,cursor": count}) into the text editor meta as
meta.eng_win = {"XXXX": [[w, h, col, row], ...]}. The logs come from a test ROM whose text decoder entry $80FE33
records (text id $02, window $00: width $7E2020,X, height $7E2040,X, cursor $7E20C0,X - $7E2060,X) while random
button presses drive the menus (fuzz.py in the notes).  python3 build_eng_windows.py meta.json fz_*.json"""
import json, sys
meta_path, logs = sys.argv[1], sys.argv[2:]
merged = {}
for f in logs:
    for tid, wins in json.load(open(f)).items():
        for k, n in wins.items():
            w, h, cur = map(int, k.split(','))
            if not (3 <= w <= 32 and 3 <= h <= 28) or cur < 0 or cur >= (w - 2) * (h - 2): continue
            key = (w, h, cur % (w - 2), cur // (w - 2))
            merged.setdefault(tid, {}); merged[tid][key] = merged[tid].get(key, 0) + n
meta = json.load(open(meta_path))
meta['eng_win'] = {tid: [list(k) for k, n in sorted(v.items(), key=lambda kv: -kv[1])][:6] for tid, v in merged.items()}
json.dump(meta, open(meta_path, 'w'))
print(len(meta['eng_win']), 'texts with measured game windows')
