"""Build the single-page script browser from dump_scripts.py output.
Usage: python3 build_browser.py DUMPDIR OUT.html"""
import sys, json, os

D = sys.argv[1]
idx = json.load(open(os.path.join(D, 'index.json')))
locs = open(os.path.join(D, 'locations.txt')).read()
blocks = [b.strip('\n') for b in locs.split('=' * 70)[1:]]
head = open(os.path.join(D, 'all_scripts.txt')).read().split('=' * 78)[0].strip()
data = dict(scripts=[dict(i=d['id'], t=d['title'], x=d['text'], u=len(d['used']) > 0) for d in idx],
            locs=blocks, about=head)
js = json.dumps(data, separators=(',', ':')).replace('</', '<\\/')
html = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'browser_template.html')).read()
open(sys.argv[2], 'w').write(html.replace('/*DATA*/null', js))
print(len(html) + len(js), 'bytes')
