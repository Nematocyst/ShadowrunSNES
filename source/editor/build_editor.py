"""Builds map_editor.html (one self-contained page) from editor_template.html + srcore.js + map names."""
import sys, os, base64
HERE = os.path.dirname(os.path.abspath(__file__))
maps_json, preview_png, out = sys.argv[1], sys.argv[2], sys.argv[3]
t = open(os.path.join(HERE, 'editor_template.html')).read()
core = open(os.path.join(HERE, 'srcore.js')).read()
t = t.replace('/*SRCORE*/', core).replace('/*MAPS*/', open(maps_json).read().replace('</', '<\\/'))
t = t.replace('/*TYPECLASS*/', open(os.path.join(HERE, '..', 'data', 'type_class.json')).read())
t = t.replace('/*PREVIEW*/', base64.b64encode(open(preview_png, 'rb').read()).decode())
open(out, 'w').write(t); print(out, len(t))
