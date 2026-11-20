"""Builds text_editor.html (one self-contained page) from text_head.part + text_body.part + srtext.js + meta."""
import sys, os, base64
HERE = os.path.dirname(os.path.abspath(__file__))
meta_json, preview_png, out = sys.argv[1], sys.argv[2], sys.argv[3]
t = open(os.path.join(HERE, 'text_head.part')).read() + open(os.path.join(HERE, 'text_body.part')).read()
t = t.replace('/*SRTEXT*/', open(os.path.join(HERE, 'srtext.js')).read()).replace('/*META*/', open(meta_json).read().replace('</', '<\\/'))
t = t.replace('/*PREVIEW*/', base64.b64encode(open(preview_png, 'rb').read()).decode())
open(out, 'w').write(t); print(out, len(t))
