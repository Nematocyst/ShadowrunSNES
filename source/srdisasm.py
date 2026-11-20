"""Readable, rebuildable disassembly of Shadowrun (SNES, USA).

Usage: python3 srdisasm.py shadowrun.sfc OUTDIR [index.json from dump_scripts.py, for script titles]
Then:  cd OUTDIR && sh build.sh      (assembles with WLA-DX and checks the result is byte-identical)

How it works
  * Code is found by following execution from known entry points (CPU vectors, the 219 script natives, the
    script-VM opcode handlers, routines identified while making the Runner Pack), tracking the 65816 M/X flags
    through REP/SEP/PHP/PLP so immediate operands get the right size. Jump tables behind JMP/JSR (abs,X) are read.
  * Everything not reached as code is data. Known data is decoded in comments: script bytecode (one instruction
    per line), Huffman text (decoded string), and the main tables (natives, script directory, object types,
    locations, sprite names, keywords, conversations...). Unknown data (graphics, maps, music) is plain .db.
  * Every instruction is written with explicit operand sizes (.b/.w/.l), so the rebuild is exact even where the
    analysis guessed wrong. Labels are used for branch/jump/call targets that were decoded as code.
"""
import sys, os, re, collections, json

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import dis65816 as D

ROMPATH, OUT = sys.argv[1], sys.argv[2]
TITLES = {}   # optional: index.json from dump_scripts.py gives each script a readable title
if len(sys.argv) > 3:
    TITLES = {d['id']: d['title'] for d in json.load(open(sys.argv[3]))}
rom = open(ROMPATH, 'rb').read()
NB = len(rom) // 0x8000

# reuse the script/text/table knowledge from dump_scripts.py (everything before its cross-reference pass)
_src = open(os.path.join(HERE, 'dump_scripts.py')).read().split('# ---------------------------------------------------------------- cross references')[0]
_g = {'__name__': 'ds', '__doc__': ''}
_argv = sys.argv; sys.argv = ['dump_scripts.py', ROMPATH, '/nonexistent']
exec(compile(_src, 'dump_scripts.py', 'exec'), _g)
sys.argv = _argv
text, msg_text, sloc, sargs, decode_script = _g['text'], _g['msg_text'], _g['sloc'], _g['sargs'], _g['decode']
NATIVES, TYPES, sprite_name, keyword, KNOWN_SCRIPTS = _g['NATIVES'], _g['TYPES'], _g['sprite_name'], _g['keyword'], _g['KNOWN']
NSCR = 936


def L(a): return ((a & 0x7F0000) >> 1) | (a & 0x7FFF)
def S(off): return 0x800000 | ((off >> 15) << 16) | 0x8000 | (off & 0x7FFF)
def RW(a): return rom[L(a)] | rom[L(a) + 1] << 8


# ============================================================== names for code
NAMES = {
    0x808000: 'check_exit_zones', 0x8080B2: 'wall_test_a', 0x808133: 'wall_test_b', 0x8081B4: 'wall_test_c',
    0x808238: 'wall_test_d', 0x808B16: 'equip_armor', 0x808B9F: 'equip_weapon', 0x809123: 'conv_show_topic',
    0x80918D: 'conv_menu', 0x8092BD: 'text_box_new', 0x8092DE: 'text_box_append', 0x8092EF: 'show_message',
    0x80962E: 'main_loop', 0x809D9D: 'read_joypad', 0x80A173: 'hire_runner', 0x80A242: 'dismiss_runner',
    0x80A287: 'place_party', 0x80A343: 'load_map_objects', 0x80A3F1: 'set_camera', 0x80A44C: 'load_location',
    0x80A4D8: 'map_load_objects', 0x80A654: 'menu_list', 0x80A7C2: 'create_object', 0x80AA3C: 'set_direction',
    0x80B1DB: 'draw_object', 0x80B8AF: 'draw_objects', 0x80BCA8: 'hover_names', 0x80BC82: 'hide_cursor',
    0x80BD9A: 'cursor_settle', 0x80BE08: 'cursor_snap', 0x80C103: 'nmi_counter', 0x80C19A: 'run_thread',
    0x80C298: 'script_lookup', 0x80C31A: 'start_script', 0x80C4EF: 'random', 0x80C530: 'rng',
    0x80CC67: 'warp', 0x80CD82: 'add_karma', 0x80CE3D: 'rest_menu', 0x80CDA6: 'save_menu', 0x80DFDE: 'jake_input',
    0x80EE21: 'karma_screen', 0x80EFD0: 'karma_raise', 0x80F342: 'vm_start', 0x80F353: 'vm_next_op',
    0x80F8F1: 'vm_bad_op', 0x80F91D: 'wait_button', 0x80F92D: 'open_window', 0x80FA08: 'close_window',
    0x80FE33: 'text_decode', 0x80FE44: 'huffman_decode', 0x80FE8B: 'floater_text', 0x81A25F: 'line_of_sight',
    0x81AD4E: 'refresh_screen?', 0x81B05D: 'wait_nmi', 0x81B139: 'load_game', 0x81B154: 'save_game',
    0x81877F: 'map_decompress_zones', 0x819AE6: 'map_load_finish',
}
RAM = {0x0E44: 'obj_x', 0x0E9C: 'obj_y', 0x0EF4: 'obj_z', 0x0D3C: 'obj_vel_x', 0x0D94: 'obj_vel_y', 0x0DEC: 'obj_vel_z',
       0x1526: 'obj_type', 0x13C4: 'obj_record', 0x141C: 'obj_draw_flags', 0x136C: 'obj_thread', 0x1474: 'obj_bits',
       0x11B4: 'obj_facing', 0x1054: 'obj_anim', 0x0F4C: 'obj_depth', 0x0CDE: 'jake_obj', 0x1FCC: 'combat_count',
       0x1FCE: 'combat_list', 0x1FC4: 'party_objs', 0x1F7C: 'selected_char', 0x01E6: 'joy_held', 0x01EA: 'joy_new',
       0x1D7F: 'conv_end', 0x3F04: 'obj_sprite', 0x3F5C: 'obj_frame', 0x2DE2: 'next_location', 0x2DE4: 'progress_bits',
       0x2DE6: 'party_count2', 0x2DF0: 'party_types', 0x3C11: 'karma', 0x3CA3: 'keywords', 0x3BBB: 'game_vars',
       0x1CFC: 'sfx_state?', 0x40BC: 'obj_path_active', 0x4114: 'obj_path_mode', 0x43D4: 'obj_base_anim',
       0x442C: 'obj_examine_msg'}

# ============================================================== known data regions
regions = []   # (start_off, end_off, kind, name, info)


def region(a, n, kind, name, info=None):
    regions.append((L(a), L(a) + n, kind, name, info))


region(0x80F27E, 0xC4, 'wtable', 'vm_opcode_table', 'op')
region(0x82D604, 219 * 2, 'wtable', 'native_table', 'native')
region(0x82D7BA, 219, 'btable', 'native_returns', 'native')
region(0x82D895, 219, 'btable', 'native_argcount', 'native')
region(0x82D970, NSCR, 'btable', 'script_banks', 'script')
region(0x82DD18, NSCR * 2, 'wtable', 'script_addrs', 'script')
region(0x82E468, NSCR, 'btable', 'script_returns', 'script')
region(0x82E810, NSCR, 'btable', 'script_argbytes', 'script')
region(0x80947A, 139 * 2, 'wtable', 'conversation_table', 'conv')
region(0x8D8000, 64 * 2, 'wtable', 'keyword_texts', 'keyword')
region(0x809683, 13 * 2, 'wtable', 'runner_types', None)
region(0x809705, 13 * 2, 'wtable', 'runner_name_texts', 'textid')
region(0x80D399, 0x200, 'raw', 'sine_table', None)
region(0x8CEFB0, 0x113 * 6, 'sprnames', 'sprite_table', None)
region(0x8D92AF, 0x1FC * 9, 'locations', 'location_table', None)
region(0x8DB031, 0x20A0 + 7, 'types', 'object_type_table', None)
region(0x80D980, 0x264 * 2, 'wtable', 'message_table', 'textid')   # ends where native $87 starts ($80DE48)

# scripts: header + every reached instruction (contiguous span)
script_spans = {}
for sid in range(NSCR):
    ins, base = decode_script(sid)
    if not ins: continue
    end = max(pc + len(raw) for pc, op, name, arg, raw in ins)
    script_spans[sid] = (base - 2, base + end, ins)


# text: walk every text start known from the tables, then fill gaps by walking sequentially
def text_bytes(tid):
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


text_ids = set()
for i in range(0x264): text_ids.add(RW(0x80D980 + 2 * i))
for k in range(64): text_ids.add(RW(0x8D8000 + 2 * k))
for s in range(0x113): text_ids.add(RW(0x8CEFB0 + 6 * s))
for i in range(13): text_ids.add(RW(0x809705 + 2 * i))
for n in range(139):
    try:
        for e in _g['conv'](n): text_ids.add(e['tid'])
    except Exception: pass
text_ids = {t for t in text_ids if t not in (0, 0xFFFF) and t < 0xFFF0}
texts = {}   # file offset -> (tid, length)
for t in sorted(text_ids):
    p, n = text_bytes(t)
    if n and n < 2000: texts[p] = (t, n)
# sequential fill: after each known text, keep walking while the next text decodes cleanly
starts = sorted(texts)
lo = min(starts); hi = max(p + texts[p][1] for p in starts)
p = lo
while p < hi:
    if p in texts: p += texts[p][1]; continue
    tid = (p - 0xE8000) if p < 0xF0000 else ((p - 0xF0000) | 0x8000)
    q, n = text_bytes(tid)
    if not n or n > 2000: p += 1; continue
    s = text(tid)
    if sum(1 for ch in s if ch.isalpha()) < len(s) * 0.5: p += 1; continue
    texts[p] = (tid, n); p += n
TEXT_LO, TEXT_HI = lo, hi
region(0x9D8000, lo - 0xE8000, 'raw', 'huffman_tree', None)

# ============================================================== code analysis
code = {}          # off -> (len, m, x)
labels = {}        # off -> name
kinds = {}         # off -> 'sub' | 'loc' | 'tbl'
conflicts = []
data_mask = bytearray(len(rom))
for a, b, k, n, i in regions: data_mask[a:b] = b'\x01' * (b - a)
for sid, (a, b, ins) in script_spans.items(): data_mask[a:b] = b'\x01' * (b - a)
for p, (t, n) in texts.items(): data_mask[p:p + n] = b'\x01' * n
owned = bytearray(len(rom))   # bytes covered by a decoded instruction


def ilen(op, m, x):
    mn, mode = D.OPS[op]; n = D.MODES[mode]
    if n == -1: n = 2 if m else 1
    if n == -2: n = 2 if x else 1
    return 1 + n


def add_label(off, kind, name=None):
    if name: labels[off] = name; kinds[off] = kind; return
    if off in labels and kinds.get(off) == 'sub': return
    if off in labels and kind == 'loc': return
    labels[off] = '%s_%06X' % (kind, S(off)); kinds[off] = kind


work = []


def enqueue(off, m, x, kind):
    if not (0 <= off < len(rom)): return
    work.append((off, m, x, (), kind))


def explore():
    while work:
        off, m, x, pst, kind = work.pop()
        first = True
        while True:
            if off < 0 or off >= len(rom) or data_mask[off]: break
            if off in code:
                if first: add_label(off, kind)
                if code[off][1:] != (m, x): conflicts.append((S(off), code[off][1:], (m, x)))
                break
            if owned[off]: conflicts.append((S(off), 'overlap')); break
            op = rom[off]; mn, mode = D.OPS[op]
            if mn in ('brk', 'cop', 'wdm', 'stp') and not first: break   # likely data
            if mn in ('brk', 'wdm', 'stp'): break
            n = ilen(op, m, x)
            if any(owned[off:off + n]) or any(data_mask[off:off + n]) or (off & 0x7FFF) + n > 0x8000: break
            code[off] = (n, m, x); owned[off:off + n] = b'\x01' * n
            if first: add_label(off, kind); first = False
            v = int.from_bytes(rom[off + 1:off + n], 'little')
            here = S(off); bank = here & 0xFF0000
            nxt = off + n
            if mn == 'rep': m = m or bool(v & 0x20); x = x or bool(v & 0x10)
            elif mn == 'sep': m = m and not (v & 0x20); x = x and not (v & 0x10)
            elif mn == 'php': pst = pst + ((m, x),)
            elif mn == 'plp' and pst: m, x = pst[-1]; pst = pst[:-1]
            elif mn == 'xce': pass
            if mode == 'rel' or mode == 'rell':
                d = v - (256 if v > 127 else 0) if mode == 'rel' else v - (65536 if v > 32767 else 0)
                t = L(bank | ((here + n + d) & 0xFFFF))
                work.append((t, m, x, pst, 'loc'))
                if mn in ('bra', 'brl'): break
                if mn == 'per': pass
            elif mn in ('jsr', 'jmp') and mode == 'abs':
                t = L(bank | v); work.append((t, m, x, pst, 'sub' if mn == 'jsr' else 'loc'))
                if mn == 'jmp': break
            elif mn in ('jsl', 'jml') and mode == 'long':
                if v & 0x8000 and (v >> 16) & 0x7F < NB:
                    work.append((L(v), m, x, (), 'sub' if mn == 'jsl' else 'loc'))
                if mn == 'jml': break
            elif mode == 'iabsx' and mn in ('jmp', 'jsr'):
                tbl = L(bank | v); read_table(tbl, bank, m, x)
                if mn == 'jmp': break
            elif mn in ('jmp', 'jml') or mn in ('rts', 'rtl', 'rti'):
                break
            off = nxt
            first = False


tables = {}   # off -> count


def read_table(tbl, bank, m, x):
    if tbl in tables or data_mask[tbl]: return
    cnt = 0; p = tbl
    while cnt < 96 and (p & 0x7FFF) < 0x7FFE:
        if owned[p] or owned[p + 1] or (p != tbl and p in labels): break
        w = rom[p] | rom[p + 1] << 8
        if w < 0x8000: break
        t = L(bank | w)
        if data_mask[t] or rom[t] in (0x00, 0xFF): break
        cnt += 1; p += 2
    if not cnt: return
    tables[tbl] = cnt; data_mask[tbl:tbl + 2 * cnt] = b'\x01' * (2 * cnt)
    add_label(tbl, 'tbl', 'jtbl_%06X' % S(tbl))
    for i in range(cnt):
        w = rom[tbl + 2 * i] | rom[tbl + 2 * i + 1] << 8
        work.append((L(bank | w), m, x, (), 'loc'))


# entry points
for vec, name in ((0xFFE4, 'vec_cop'), (0xFFE6, 'vec_brk'), (0xFFEA, 'vec_nmi'), (0xFFEE, 'vec_irq'),
                  (0xFFFC, 'vec_reset'), (0xFFFE, 'vec_irq_emu'), (0xFFFA, 'vec_nmi_emu')):
    t = RW(0x800000 | vec)
    if t >= 0x8000:
        o = L(0x800000 | t); big = vec != 0xFFFC
        work.append((o, big, big, (), 'sub')); labels[o] = name; kinds[o] = 'sub'
region(0x80FFB0, 0x50, 'raw', 'rom_header_and_vectors', None)
for a, b, k, n, i in regions[-1:]: data_mask[a:b] = b'\x01' * (b - a)
for n in range(219):
    o = L(0x800000 | RW(0x82D604 + 2 * n)); enqueue(o, True, True, 'sub')
    labels[o] = 'native_%02X_%s' % (n, re.sub(r'[^A-Za-z0-9]', '', NATIVES.get(n, 'X'))); kinds[o] = 'sub'
OPNAMES = _g['OPS']
for op in range(0, 0xC4, 2):
    t = RW(0x80F27E + op)
    if t >= 0x8000:
        o = L(0x800000 | t); enqueue(o, True, True, 'sub')
        if o not in labels or kinds.get(o) != 'sub' or labels[o].startswith('sub_'):
            nm = OPNAMES.get(op, ('op%02X' % op,))[0].replace('.', '_')
            labels[o] = 'vmop_%02X_%s' % (op, nm); kinds[o] = 'sub'
for a, nm in NAMES.items():
    o = L(a); enqueue(o, True, True, 'sub')
explore()
for a, nm in NAMES.items():
    if L(a) in code: labels[L(a)] = nm; kinds[L(a)] = 'sub'

# data labels: absolute operands >= $8000 (assume data bank = code bank) and long operands into ROM
DATA_REFS = collections.Counter()
for off, (n, m, x) in code.items():
    op = rom[off]; mn, mode = D.OPS[op]
    if mn in ('jsr', 'jmp', 'jsl', 'jml', 'pea', 'per') or mode not in ('abs', 'absx', 'absy', 'long', 'longx'): continue
    v = int.from_bytes(rom[off + 1:off + n], 'little')
    if mode.startswith('abs'):
        if v < 0x8000: continue
        t = L((S(off) & 0xFF0000) | v)
    else:
        if not (v & 0x8000) or (v >> 16) & 0x7F >= NB or (v >> 16) in (0x7E, 0x7F): continue
        t = L(v)
    if t in code or owned[t]: continue
    DATA_REFS[t] += 1
    if t not in labels: labels[t] = 'dat_%06X' % S(t); kinds[t] = 'data'

# ============================================================== emit
os.makedirs(OUT, exist_ok=True)
SUFFIX = {'dp': '${:02X}.b', 'dpx': '${:02X}.b,X', 'dpy': '${:02X}.b,Y', 'idp': '(${:02X}.b)', 'idpx': '(${:02X}.b,X)',
          'idpy': '(${:02X}.b),Y', 'ildp': '[${:02X}.b]', 'ildpy': '[${:02X}.b],Y', 'sr': '${:02X}.b,S',
          'isry': '(${:02X}.b,S),Y', 'abs': '${:04X}.w', 'absx': '${:04X}.w,X', 'absy': '${:04X}.w,Y',
          'iabs': '(${:04X}.w)', 'iabsx': '(${:04X}.w,X)', 'ilabs': '[${:04X}.w]', 'long': '${:06X}.l',
          'longx': '${:06X}.l,X'}


def ramnote(mode, v):
    if mode in ('abs', 'absx', 'absy'): a = v
    elif mode in ('long', 'longx') and (v >> 16) in (0x7E, 0x00): a = v & 0xFFFF
    else: return ''
    if a in RAM: return RAM[a]
    if 0x3BBB <= a < 0x3BFB: return 'var[%d]' % (a - 0x3BBB)
    return ''


def fmt_ins(off):
    n, m, x = code[off]; op = rom[off]; mn, mode = D.OPS[op]
    v = int.from_bytes(rom[off + 1:off + n], 'little'); here = S(off); bank = here & 0xFF0000
    note = ''
    if mode in ('imp',): return mn, ''
    if mn == 'pei': return 'pei ($%02X.b)' % v, ''
    if mode == 'acc': return mn + ' A', ''
    if mode == 'imm8': return '%s #$%02X' % (mn, v), ''
    if mode in ('immM', 'immX'): return ('%s #$%02X.b' if n == 2 else '%s #$%04X.w') % (mn, v), ''
    if mode == 'bm': return '%s $%02X,$%02X' % (mn, rom[off + 2], rom[off + 1]), ''
    if mode in ('rel', 'rell'):
        d = v - (256 if v > 127 else 0) if mode == 'rel' else v - (65536 if v > 32767 else 0)
        t = L(bank | ((here + n + d) & 0xFFFF))
        if t in code and t in labels: return '%s %s' % (mn, labels[t]), ''
        return None, 'target $%06X not decoded' % S(t)
    if mn in ('jsr', 'jmp') and mode == 'abs':
        t = L(bank | v)
        if t in code and t in labels: return '%s %s.w' % (mn, labels[t]), ''
    if mn in ('jsl', 'jml') and mode == 'long':
        t = L(v) if v & 0x8000 and (v >> 16) & 0x7F < NB else None
        if t is not None and t in code and t in labels and (v >> 16) == (S(t) >> 16):
            return '%s %s.l' % (mn, labels[t]), ''
    if mode == 'iabsx' and L(bank | v) in tables: note = 'table ' + labels[L(bank | v)]
    note = note or ramnote(mode, v)
    return '%s %s' % (mn, SUFFIX[mode].format(v)), note


def db(bs): return '.db ' + ','.join('$%02X' % b for b in bs)


region_at = {}
for a, b, k, n, i in regions: region_at[a] = (b, k, n, i)
for sid, (a, b, ins) in script_spans.items():
    region_at.setdefault(a, (b, 'script', 'script_%03X' % sid, sid))
for p, (t, n) in texts.items(): region_at.setdefault(p, (p + n, 'text', 'text_%04X' % t, t))
for a in region_at:
    if a not in labels: labels[a] = region_at[a][2]; kinds[a] = 'data'


def render_region(f, a, b, kind, name, info):
    if kind == 'script':
        sid = info; s0, s1, ins = script_spans[sid]
        f.write('; ---- script $%03X  %s  (args %d)\n' % (sid, TITLES.get(sid) or KNOWN_SCRIPTS.get(sid, ''), sargs(sid)))
        f.write('\t%s\t\t; header\n' % db(rom[a:a + 2]))
        p = a + 2; base = a + 2
        for pc, op, nm, arg, raw in ins:
            if base + pc > p: f.write('\t%s\t\t; (unreached)\n' % db(rom[p:base + pc]))
            if base + pc < p: continue
            extra = ''
            if nm == 'native': extra = NATIVES.get(arg, '')
            elif arg is not None: extra = ('$%04X' % arg) if len(raw) == 3 else str(arg)
            f.write('\t%-40s; %04X %s %s\n' % (db(raw), pc, nm, extra))
            p = base + pc + len(raw)
        if p < b: f.write('\t%s\n' % db(rom[p:b]))
        return
    if kind == 'text':
        try: s = text(info)
        except Exception: s = '?'
        f.write('; text $%04X: "%s"\n' % (info, s.replace('\n', ' ')[:200]))
        for q in range(a, b, 16): f.write('\t%s\n' % db(rom[q:min(b, q + 16)]))
        return
    if kind in ('wtable', 'btable'):
        step = 2 if kind == 'wtable' else 1
        for i, q in enumerate(range(a, b, step)):
            val = rom[q] | (rom[q + 1] << 8 if step == 2 else 0)
            c = ''
            if info == 'native': c = 'native $%02X %s' % (i, NATIVES.get(i, ''))
            elif info == 'script': c = 'script $%03X' % i
            elif info == 'op': c = 'opcode $%02X %s' % (i, OPNAMES.get(i, ('',))[0]) if i % 2 == 0 else ''
            elif info == 'conv': c = 'conversation %d' % i
            elif info == 'keyword': c = 'keyword %d "%s"' % (i, keyword(i))
            elif info == 'textid' and step == 2 and val not in (0, 0xFFFF):
                try: c = '"%s"' % text(val)[:60]
                except Exception: c = ''
            f.write('\t%s $%0*X\t\t; %s\n' % ('.dw' if step == 2 else '.db', 4 if step == 2 else 2, val, c))
        return
    if kind == 'sprnames':
        for i, q in enumerate(range(a, b, 6)):
            t = rom[q] | rom[q + 1] << 8
            f.write('\t.dw $%04X,$%04X,$%04X\t; sprite $%02X %s\n' % (t, RW(S(q + 2)), RW(S(q + 4)), i, sprite_name(i)))
        return
    if kind == 'locations':
        for i, q in enumerate(range(a, b, 9)):
            if q + 9 > b: f.write('\t%s\n' % db(rom[q:b])); break
            f.write('\t%s\t; location $%03X\n' % (db(rom[q:q + 9]), i))
        return
    if kind == 'types':
        for q in range(a, b, 7):
            if q + 7 > b: f.write('\t%s\n' % db(rom[q:b])); break
            tt = q - a; d = TYPES.get(tt)
            c = ('type $%04X script $%03X %s' % (tt, d['script'], sprite_name(d['spr']))) if d else 'type $%04X' % tt
            f.write('\t%s\t; %s\n' % (db(rom[q:q + 7]), c))
        return
    for q in range(a, b, 16): f.write('\t%s\n' % db(rom[q:min(b, q + 16)]))


NATIVE_AT = collections.defaultdict(list)
for _n in range(219): NATIVE_AT[L(0x800000 | RW(0x82D604 + 2 * _n))].append(_n)
BANK_NOTES = {0x80: 'engine: main loop, objects, script VM + natives, text, menus', 0x81: 'engine: video, sound I/O, maps, saves; staff credits at $81F27E',
              0x82: 'graphics/data, then script tables ($82D604..) and scripts', 0x83: 'graphics/data, then scripts',
              0x8C: 'includes sprite table $8CEFB0', 0x8D: 'keywords $8D8000, conversations, locations $8D92AF, object types $8DB031',
              0x99: 'map data', 0x9A: 'map data', 0x9B: 'scripts', 0x9C: 'scripts', 0x9D: 'Huffman tree $9D8000 + text',
              0x9E: 'text + scripts', 0x9F: 'scripts (runner and enemy AI)'}
bank_stats = []
for bnk in range(NB):
    fn = 'bank_%02X.asm' % (0x80 + bnk)
    f = open(os.path.join(OUT, fn), 'w')
    lo, hi = bnk * 0x8000, bnk * 0x8000 + 0x8000
    ncode = sum(code[o][0] for o in code if lo <= o < hi)
    nscr = sum(b - a for a, b, i in script_spans.values() if lo <= a < hi)
    ntxt = sum(n for p, (t, n) in texts.items() if lo <= p < hi)
    bank_stats.append((0x80 + bnk, ncode, nscr, ntxt))
    f.write('; Bank $%02X (file $%05X-$%05X): %d bytes code, %d bytes script bytecode, %d bytes text, %d other data\n' % (
        0x80 + bnk, lo, hi - 1, ncode, nscr, ntxt, 0x8000 - ncode - nscr - ntxt))
    if 0x80 + bnk in BANK_NOTES: f.write('; Contents: %s\n' % BANK_NOTES[0x80 + bnk])
    f.write('.BANK %d SLOT 0\n.ORG $0000\n.SECTION "Bank%02X" FORCE\n\n' % (bnk, 0x80 + bnk))
    off = lo; last_code = False
    while off < hi:
        if off in labels:
            if kinds.get(off) == 'sub' and off in code: f.write('\n')
            if off in NATIVE_AT:
                for nn in NATIVE_AT[off]:
                    f.write('; ---- native $%02X %s: %d arg(s), %s\n' % (nn, NATIVES.get(nn, ''), rom[L(0x82D895 + nn)],
                            'returns a value in $00' if rom[L(0x82D7BA + nn)] else 'no return value'))
            if off in DATA_REFS: f.write('; (referenced %d time(s) by code)\n' % DATA_REFS[off])
            f.write('%s:\n' % labels[off])
        if off in code:
            s, note = fmt_ins(off)
            n = code[off][0]
            if s is None: s, note = db(rom[off:off + n]), D.disasm(rom, S(off), 1, code[off][1], code[off][2])[0][20:].strip() + ' ; ' + note
            f.write('\t%-28s; %06X%s\n' % (s, S(off), ('  ' + note) if note else ''))
            off += n; continue
        if off in region_at:
            b, kind, name, info = region_at[off]
            b = min(b, hi)
            render_region(f, off, b, kind, name, info)
            off = b; continue
        # unknown data run: until next label/code/region
        q = off + 1
        while q < hi and q not in labels and q not in code and q not in region_at: q += 1
        f.write('\t; data $%06X-$%06X (%d bytes)\n' % (S(off), S(q - 1), q - off))
        for p in range(off, q, 16):
            chunk = rom[p:min(q, p + 16)]
            pr = sum(1 for c in chunk if 32 <= c < 127 or c == 0) if sum(1 for c in chunk if 65 <= (c | 32) <= 122) >= 4 else 0
            asc = ''.join(chr(c) if 32 <= c < 127 else '.' for c in chunk)
            f.write('\t%-70s%s\n' % (db(chunk), ('; "%s"' % asc) if pr >= len(chunk) * 0.85 and len(chunk) > 3 else ''))
        off = q
    f.write('.ENDS\n'); f.close()

with open(os.path.join(OUT, 'main.s'), 'w') as f:
    f.write('; Shadowrun (SNES, USA) - generated by srdisasm.py\n')
    f.write('.MEMORYMAP\n  SLOTSIZE $8000\n  DEFAULTSLOT 0\n  SLOT 0 $8000\n.ENDME\n.ROMBANKSIZE $8000\n.ROMBANKS %d\n.EMPTYFILL $FF\n.BASE $80\n\n' % NB)
    for bnk in range(NB): f.write('.INCLUDE "bank_%02X.asm"\n' % (0x80 + bnk))
open(os.path.join(OUT, 'linkfile'), 'w').write('[objects]\nmain.o\n')
open(os.path.join(OUT, 'build.sh'), 'w').write('''#!/bin/sh
# Assemble with WLA-DX (wla-65816 + wlalink on PATH) and compare with the original ROM if given.
set -e
cd "$(dirname "$0")"
wla-65816 -o main.o main.s
wlalink -S linkfile shadowrun_rebuilt.sfc
if [ -n "$1" ]; then cmp shadowrun_rebuilt.sfc "$1" && echo "OK: byte-identical"; fi
''')
json.dump(dict(code_bytes=sum(v[0] for v in code.values()), code_ins=len(code), labels=len(labels),
               conflicts=conflicts[:200], tables={('%06X' % S(k)): v for k, v in tables.items()}, banks=bank_stats),
          open(os.path.join(OUT, 'analysis.json'), 'w'), indent=1)
print('instructions', len(code), 'code bytes', sum(v[0] for v in code.values()), 'labels', len(labels),
      'tables', len(tables), 'conflicts', len(conflicts), 'texts', len(texts), 'scripts', len(script_spans))

# ============================================================== README
named = sum(1 for o, n in labels.items() if o in code and not re.match(r'(sub|loc)_', n))
rows = '\n'.join('| $%02X | %d | %d | %d | %d | %s |' % (b, c, sc, t, 0x8000 - c - sc - t, BANK_NOTES.get(b, ''))
                 for b, c, sc, t in bank_stats)
open(os.path.join(OUT, 'README.md'), 'w').write('''# Shadowrun (SNES, USA): readable disassembly

Generated by `srdisasm.py` from the clean ROM (CRC32 3F34DFF0). Rebuilds byte-identical with WLA-DX:

    sh build.sh path/to/shadowrun.sfc      # needs wla-65816 and wlalink on PATH (shadowrun_toolkit/tools/bin)

The build also writes `shadowrun_rebuilt.sym`, a symbol file (bank:address name) that emulators such as
bsnes-plus and Mesen can load, so the labels below show up in their debuggers.

## Files
* `bank_80.asm` ... `bank_9F.asm`: one file per 32 KB ROM bank, addresses as the game sees them ($80:8000-$9F:FFFF).
* `main.s`: memory map and includes. `analysis.json`: coverage numbers, jump tables, M/X conflicts.

## Reading it
* Each instruction line ends with its address. Operand sizes are explicit: `.b` direct page, `.w` absolute,
  `.l` long; immediates are `#$12.b` (8-bit) or `#$1234.w` (16-bit) depending on the M/X flags at that point.
* Labels: `native_3B_STOPWALKING` = script native $3B (with a header comment giving its argument count),
  `vmop_58_native` = script VM opcode handler, named engine routines (`create_object`, `text_decode`,
  `warp`, `main_loop`, ...), `sub_80XXXX` = called routine not yet named, `loc_80XXXX` = jump/branch target,
  `dat_80XXXX` = data the code reads (with how often), `jtbl_` = jump table, `script_XXX` / `text_XXXX` = data.
* Known RAM is named in the comment on the line (`obj_x`, `obj_record`, `karma`, `var[44]` ...).
* Data is decoded where we know the format: script bytecode one instruction per line, Huffman text with the
  decoded string, and the main tables (natives, script directory, conversations, keywords, messages, sprite
  names, locations, object types). Unknown data is plain `.db` with an ASCII column when it looks like text.

## Coverage
{code} bytes of 65816 code in {ins} instructions; {named} code labels have real names, {labels} labels in all.
{nscr} scripts and {ntxt} text strings are decoded in place.

| Bank | Code | Script bytecode | Text | Other data | Contents |
|---|---|---|---|---|---|
{rows}

## Known gaps
* Banks $82-$83 (first ~22 KB each) and $84-$9A are data the code reads indirectly: compressed graphics, map
  data, music/sound (SPC700) and tables. They are plain `.db` until their formats are worked out.
* Code reached only through pointers in RAM (`jmp ($xxxx)`, `jml [$xxxx]`) or pushed return addresses is not
  found, and stays as data. Bank $80 is about {p80}% code, bank $81 {p81}%.
* {conf} places are reached with different M/X flag states; the first state seen is used. Those lines still
  assemble to the original bytes, but the immediate sizes shown there may be wrong for the other caller.
'''.format(code=sum(v[0] for v in code.values()), ins=len(code), named=named, labels=len(labels), nscr=len(script_spans),
           ntxt=len(texts), rows=rows, p80=round(100 * bank_stats[0][1] / 0x8000), p81=round(100 * bank_stats[1][1] / 0x8000),
           conf=len(set(c[0] for c in conflicts))))
