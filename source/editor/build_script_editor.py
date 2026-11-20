"""Builds script_editor.html from script_head.part + script_body.part + srtext.js + srvm.js (+ natives, script meta)."""
import sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
natives, smeta, out = sys.argv[1], sys.argv[2], sys.argv[3]
vm = open(os.path.join(HERE, 'srvm.js')).read().replace('/*NATIVES*/{}', open(natives).read())
t = open(os.path.join(HERE, 'script_head.part')).read() + open(os.path.join(HERE, 'script_body.part')).read()
t = t.replace('/*SRTEXT*/', open(os.path.join(HERE, 'srtext.js')).read()).replace('/*SRVM*/', vm)
t = t.replace('/*SMETA*/', open(smeta).read().replace('</', '<\\/'))
open(out, 'w').write(t); print(out, len(t))
