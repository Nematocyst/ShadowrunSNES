"""Builds sprite_colours.html from sprite_head.part + sprite_body.part + srtext.js + srspr.js (+ srpal code bytes)."""
import sys, os, base64
HERE = os.path.dirname(os.path.abspath(__file__))
code_json, preview_png, out = sys.argv[1], sys.argv[2], sys.argv[3]
spr = open(os.path.join(HERE, 'srspr.js')).read().replace('/*SRPALCODE*/null', open(code_json).read())
t = open(os.path.join(HERE, 'sprite_head.part')).read() + open(os.path.join(HERE, 'sprite_body.part')).read()
t = t.replace('/*SRTEXT*/', open(os.path.join(HERE, 'srtext.js')).read()).replace('/*SRSPR*/', spr)
t = t.replace('/*PREVIEW*/', base64.b64encode(open(preview_png, 'rb').read()).decode())
open(out, 'w').write(t); print(out, len(t))
