"""Dump every Shadowrun (SNES) script as readable pseudo-code + raw bytecode, with cross-references.

Usage: python3 dump_scripts.py ROM OUTDIR [zones.json]
  OUTDIR/scripts/script_XXX.txt  one file per script (pseudo-code, then raw listing)
  OUTDIR/all_scripts.txt         everything in one file
  OUTDIR/index.json              per-script summary (used by the HTML browser)
  OUTDIR/locations.txt           each location: objects placed there, exits, zone scripts

Pseudo-code notes
  * Natives and script calls print their arguments in PUSH order (first pushed first).
  * self = local byte 0 in scripts attached to an object type (the engine passes the object as the
    first argument; opcode $C2 is a one-byte 'push local 0'). In other scripts it prints as L.b0.
  * L.b5 / L.w5 = local byte/word at offset 5 of the thread's locals (arguments are the first locals).
  * gb[$xxxx] / gw[$xxxx] = byte/word at $7E:xxxx. var[n] = game variable n ($7E3BBB+n).
  * Natives whose purpose is unknown print as native_XX. Names ending in '?' are best guesses.
  * arg1..argN = the script's arguments in push order (arg1 pushed first); the script pops them into locals.
  * The LAST argument of a native is what the native routine sees as $00 (often the object), the one
    before it $02, and so on.
  * jz/jnz consume the value they test. A value left on the stack at a jump prints as 'push <expr>';
    a value taken from an earlier block prints as 'pop()'.
zones.json comes from an emulator sweep (exit zones are only easy to find once a map has loaded).
"""
import sys, os, json, collections

rom = open(sys.argv[1], 'rb').read()
OUT = sys.argv[2]
ZONES = json.load(open(sys.argv[3])) if len(sys.argv) > 3 else {}
NSCR = 936


def L(a): return ((a & 0x7F0000) >> 1) | (a & 0x7FFF)
def RB(a): return rom[L(a)]
def RW(a): return rom[L(a)] | rom[L(a) + 1] << 8
def snes(off): return 0x800000 | ((off >> 15) << 16) | 0x8000 | (off & 0x7FFF)


# ---------------------------------------------------------------- text
def text(tid):
    bank = 0x9D + (1 if tid & 0x8000 else 0); p = L((bank << 16) | (tid | 0x8000))
    bitpos = 0; out = []
    while True:
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
            if c == 0x0A: return ''.join(out)
            out.append(chr(c) if 32 <= c < 127 else ' ' if c in (0x0D, 0x0B) else '<%02X>' % c)
        if len(out) > 1500: return ''.join(out) + '...'


def msg_text(i):
    if not 0 <= i < 0x800: return None
    try: return text(RW(0x80D980 + 2 * i))
    except Exception: return None


RUNNER_NAMES = {}   # party members show their own name ($809683 types -> $809705 text ids) when hired
for _i in range(13):
    try: RUNNER_NAMES[RW(0x809683 + 2 * _i)] = text(RW(0x809705 + 2 * _i))
    except Exception: pass


def sprite_name(spr):
    """Hover label: per-sprite 6-byte entries at $8CEFB0 = [name text id][attr0][attr1] (natives #19/#5C read
    the attrs). The hover code ($80BD9A) indexes it by the object's live sprite ($7E3F04,X); $FFFF = cannot be
    pointed at. Sprite 0 in the type table means the object is created by a script, which picks the sprite."""
    if not 0 < spr < 0x200: return ''
    t = RW(0x8CEFB0 + 6 * spr)
    if t in (0, 0xFFFF): return ''
    try: s = text(t)
    except Exception: return ''
    return s if 0 < len(s) < 40 and '<' not in s else ''


KNOWN = {   # scripts identified while building the Runner Pack (see shadowrun_notes.md)
    0x0011: 'weapon item: Strength check + equip', 0x0320: 'armor item: Strength check + equip',
    0x028C: 'display-case shop item', 0x02CC: 'street doc cyberware purchase', 0x00F4: 'street doc cyberware shelf',
    0x00C4: 'street doc', 0x01D4: 'sleep (bed) -> rest menu', 0x02AA: 'item menu (bed)', 0x00F9: 'save game',
    0x01D9: "Jake's control script", 0x01AD: 'runner AI', 0x0328: 'runner AI (mages)', 0x01E9: 'runner AI',
    0x0194: 'runner leaves the party', 0x0330: 'runner dismisses itself (heal, unhire)', 0x003F: 'hire price block',
    0x0162: 'hire runner', 0x007E: 'random enemy appears? (roll + area cap)', 0x0060: 'area init (resets enemy count)',
    0x01E4: 'arena manager', 0x0299: 'arena prize', 0x02D0: 'arena fight offer', 0x0118: 'arena offer yes/no',
    0x0134: 'arena King prize', 0x0390: 'arena fighter appears if flagged', 0x039E: 'Glutman',
    0x0026: 'ending/dream scene picker (var 44)', 0x026F: 'ending recap scene', 0x0045: 'Jake fires (cut-scene)',
    0x00BB: 'ending scene step 3', 0x0097: 'ending roll call', 0x010C: 'generic enemy AI', 0x027B: 'generic enemy AI',
    0x02A9: 'generic enemy AI', 0x007A: 'generic enemy AI', 0x00FB: 'generic enemy AI', 0x00A0: 'generic enemy AI',
    0x010D: 'generic enemy AI', 0x0335: 'generic enemy AI', 0x035B: 'generic enemy AI', 0x01C2: 'enemy AI helper',
    0x018A: 'guard', 0x031A: 'guard', 0x0167: 'guard', 0x0317: 'guard', 0x006C: 'guard', 0x020D: 'guard',
    0x014D: 'weapon item (Jake only)', 0x026B: 'armor item (Jake only)',
}


# ---------------------------------------------------------------- script directory
def sloc(sid): return L((RB(0x82D970 + sid) << 16) | RW(0x82DD18 + 2 * sid))
def sargs(sid): return RB(0x82E810 + sid) // 2
def sret(sid): return RB(0x82E468 + sid) != 0


def nargs(n): return RB(0x82D895 + n)
def nret(n): return RB(0x82D7BA + n) != 0


OPS = {
    0x00: ('push.b', 1), 0x02: ('push.lb', 1), 0x04: ('push.gb', 2), 0x0A: ('push.sb', 1),
    0x0C: ('push.lsb', 1), 0x0E: ('push.gsb', 2), 0x14: ('push.w', 2), 0x16: ('push.lw', 1),
    0x18: ('push.gw', 2), 0x2C: ('pop.lb', 1), 0x2E: ('pop.gb', 2), 0x34: ('pop.lw', 1),
    0x36: ('pop.gw', 2), 0x44: ('jz', 2), 0x46: ('jnz', 2), 0x48: ('jmp', 2), 0x4C: ('call', 2),
    0x50: ('ret', 0), 0x52: ('script', 2), 0x54: ('halt', 0), 0x56: ('end', 0),
    0x58: ('native', 1), 0x5C: ('add', 0), 0x5E: ('sub', 0), 0x60: ('mul', 0), 0x62: ('mul.s', 0),
    0x64: ('mul.s', 0), 0x66: ('mul.s', 0), 0x68: ('div', 0), 0x6A: ('div.s', 0), 0x6C: ('div.s', 0),
    0x6E: ('div.s', 0), 0x70: ('mod', 0), 0x72: ('mod.s', 0), 0x74: ('mod.s', 0), 0x76: ('mod.s', 0),
    0x78: ('neg', 0), 0x7A: ('shl', 0), 0x7C: ('shr', 0), 0x7E: ('and', 0), 0x80: ('or', 0),
    0x82: ('xor', 0), 0x84: ('not', 0), 0x86: ('inc', 0), 0x88: ('dec', 0), 0x8A: ('lt', 0),
    0x8C: ('lt.s', 0), 0x8E: ('lt.s', 0), 0x92: ('le', 0), 0x94: ('le.s', 0), 0x96: ('le.s', 0),
    0x9A: ('gt', 0), 0x9C: ('gt.s', 0), 0x9E: ('gt.s', 0), 0xA2: ('ge', 0), 0xA4: ('ge.s', 0),
    0xA6: ('ge.s', 0), 0xAA: ('eq', 0), 0xAC: ('eq', 0), 0xAE: ('eq', 0), 0xB0: ('eq', 0),
    0xB2: ('ne', 0), 0xB4: ('ne', 0), 0xB6: ('ne', 0), 0xB8: ('ne', 0), 0xBA: ('dup', 0),
    0xBC: ('drop', 0), 0xBE: ('bool', 0), 0xC0: ('push0', 0), 0xC2: ('push.lb0', 0),
}
BIN = {'add': '+', 'sub': '-', 'mul': '*', 'mul.s': '*', 'div': '/', 'div.s': '/', 'mod': '%', 'mod.s': '%',
       'shl': '<<', 'shr': '>>', 'and': '&', 'or': '|', 'xor': '^', 'lt': '<', 'lt.s': '<', 'le': '<=',
       'le.s': '<=', 'gt': '>', 'gt.s': '>', 'ge': '>=', 'ge.s': '>=', 'eq': '==', 'ne': '!='}
UN = {'neg': '-', 'not': '~', 'inc': '1+', 'dec': '-1+', 'bool': 'bool'}

NATIVES = {   # '?' = purpose inferred from what the 65816 routine touches; see shadowrun_notes.md
    # object record (5 bytes: +0 flags2, +1 flags, +2 HP, +3 owner word)
    0x06: 'GET_REC0', 0x9C: 'SET_REC0', 0x02: 'GET_FLAGS', 0x33: 'OR_FLAGS', 0x7A: 'AND_FLAGS', 0x95: 'STORE_FLAGS',
    0x08: 'GET_HP', 0x9F: 'SET_HP', 0x2B: 'DEC_HP', 0x27: 'REFILL_HP', 0xCA: 'REFILL_MAGIC',
    0x0C: 'GET_OWNER', 0x70: 'CLEAR_OWNER', 0x6F: 'GIVE_TO_JAKE?', 0xC4: 'MARK_GONE', 0xC5: 'IS_TAKEN',
    # record of an object TYPE (arg = type id)
    0xC2: 'GET_TYPE_REC0', 0x66: 'SET_TYPE_REC0', 0xBA: 'GET_TYPE_FLAGS', 0x0D: 'OR_TYPE_FLAGS',
    0x4B: 'AND_TYPE_FLAGS', 0x60: 'STORE_TYPE_FLAGS', 0x68: 'SET_TYPE_HP', 0xCC: 'GET_TYPE_OWNER',
    0xBB: 'SET_TYPE_OWNER', 0x42: 'TYPE_OWNED_BY', 0x74: 'OWNER_JAKE?', 0x75: 'GIVE_ITEM', 0xCD: 'UNUSED_CD',
    # type / sprite info
    0xCB: 'GET_TYPE', 0x1F: 'TYPE_SPRITE', 0x19: 'TYPE_SPRITE_ATTR0', 0x5C: 'TYPE_SPRITE_ATTR1',
    0x40: 'OBJ_SPRITE_ATTR0', 0xB1: 'SPRITE_POINT_FREE?',
    # objects
    0x28: 'JAKE', 0x84: 'JAKE_ALT', 0xA8: 'CREATE_OBJECT', 0xB8: 'REMOVE_SELF', 0xAE: 'RESET_ACTIONS',
    0x92: 'GET_OBJ_BITS', 0x3F: 'SET_OBJ_BITS', 0xCE: 'OR_OBJ_BITS', 0x2C: 'AND_OBJ_BITS',
    0x64: 'PAUSE_OBJECT', 0x9D: 'RESUME_OBJECT', 0x5B: 'DETACH_THREAD?', 0x76: 'ATTACH_THREAD?',
    0xB2: 'SET_DRAW_FLAGS?', 0xA3: 'GET_DRAW_FLAGS?', 0x49: 'DRAW_FLAG_ON?', 0xB4: 'SET_EXAMINE_TEXT',
    # position, facing, animation
    0x4F: 'GET_X', 0x50: 'GET_Y', 0x51: 'GET_Z', 0x82: 'SET_POS', 0x9B: 'ADD_Z', 0xB5: 'PLACE_AT_POINT',
    0x0A: 'DISTANCE_TO_JAKE', 0x91: 'X_DISTANCE', 0x5D: 'GET_DIRECTION', 0x6A: 'SET_DIRECTION',
    0x1B: 'FACE', 0x6C: 'FACE_JAKE', 0x29: 'DIRECTION_TO_JAKE',
    0xD1: 'ANIMATE', 0xD0: 'PLAY_ANIM?', 0x6E: 'ANIM_FINISHED?', 0x22: 'GET_BASE_ANIM', 0x24: 'SET_BASE_ANIM',
    0x14: 'ADD_BASE_ANIM', 0x30: 'SUB_BASE_ANIM',
    # movement: velocity ($0D3C..) and path targets ($40BC active, mode 0 direct / 1 axis-by-axis?)
    0x79: 'SET_VELOCITY', 0x4D: 'STOP_VELOCITY', 0x44: 'GET_VEL_X', 0x46: 'GET_VEL_Y', 0x47: 'GET_VEL_Z',
    0x73: 'MOVE_TOWARD', 0x62: 'LOB_TOWARD', 0xD8: 'LOB_TO_POINT',
    0x80: 'WALK_TO_POINT', 0x1D: 'WALK_TO_POINT_AXIS?', 0x2F: 'WALK_TO_XY', 0xB9: 'WALK_TO_XY_AXIS?',
    0x25: 'FOLLOW', 0xB0: 'FOLLOW_AXIS?', 0x21: 'FOLLOW_JAKE', 0xAD: 'FOLLOW_JAKE_AXIS?', 0x3B: 'STOP_WALKING',
    0xA7: 'WALK_TO_CURSOR', 0x43: 'WALK_TO_CURSOR_AXIS?', 0x1A: 'STEP_IN_FROM_ENTRY?', 0x0B: 'TAKE_FORMATION_SPOT',
    # combat
    0xAB: 'ADD_COMBATANT', 0xBF: 'REMOVE_COMBATANT', 0x59: 'COMBAT_ACTIVE', 0x5F: 'IN_COMBAT',
    0x48: 'PREV_COMBATANT', 0x4E: 'RANDOM_VISIBLE_COMBATANT', 0x07: 'RANDOM_PARTY_TARGET',
    0x85: 'NEAREST_PARTY_TARGET', 0x69: 'CAN_HIT', 0x10: 'ATTACK', 0x5A: 'ATTACK_WITH_WEAPON',
    0x58: 'JAKE_ATTACK_CURSOR', 0x7C: 'AREA_DAMAGE?',
    # Jake, runners, stats, money
    0x01: 'SELECT_CHARACTER', 0x0F: 'GET_STRENGTH', 0x41: 'GET_STAT0?', 0x90: 'GET_STAT1?', 0xD3: 'GET_STAT4?',
    0x23: 'EQUIP_WEAPON', 0x34: 'EQUIP_ARMOR', 0x26: 'ADD_COUNT?', 0xC6: 'CARRIED_COUNT',
    0xAA: 'SPEND_MAGIC', 0x8B: 'ADD_MAGIC', 0x78: 'HIRE_RUNNER', 0x83: 'DISMISS_RUNNER', 0xD5: 'RUNNER_TIME_LEFT',
    0x98: 'ADD_NUYEN', 0xBE: 'PAY', 0xB6: 'SUB_NUYEN', 0x7B: 'ADD_KARMA', 0xA0: 'SUB_KARMA', 0x7D: 'JACK_IN?',
    # story state
    0x57: 'GET_VAR', 0x12: 'SET_VAR', 0x9A: 'OR_VAR', 0x03: 'AND_VAR', 0xD4: 'GET_PROGRESS', 0xDA: 'RAISE_PROGRESS',
    0x97: 'KNOWS_KEYWORD', 0x71: 'LEARN_KEYWORD', 0x8F: 'FORGET_KEYWORD', 0x6D: 'ADD_CHOICE', 0x89: 'CHOOSE_FROM_LIST',
    0x7E: 'CURRENT_MAP', 0x17: 'MAP_OF_LOCATION', 0x56: 'WARP', 0x54: 'WARP_ENTRY',
    0xC8: 'START_CORTEX_TIMER', 0x2A: 'CORTEX_TIMER_OFF?', 0xC3: 'CORTEX_TIMER_ACTIVE',
    0x11: 'LEAVE_MAIN_LOOP_A?', 0xD9: 'LEAVE_MAIN_LOOP_B?', 0x93: 'RUN_PENDING_SCRIPT?',
    # text, menus, conversations
    0x99: 'TEXT_BOX', 0xD6: 'TEXT_APPEND', 0xC7: 'FLOATER', 0x72: 'YES_NO', 0x94: 'CONVERSATION',
    0x7F: 'END_CONVERSATION', 0x87: 'RESET_CONVERSATION?', 0xA6: 'CLOSE_TEXT_BOXES', 0x3D: 'OPEN_WINDOW',
    0x96: 'CLOSE_WINDOW', 0x86: 'WINDOW_PRINT_POS?', 0x0E: 'WINDOW_SET?', 0x53: 'WINDOW_SET2?',
    0x04: 'PRINT_BIG_NUMBER', 0x15: 'PRINT_NUMBER', 0x13: 'ACTION_MENU', 0x3C: 'REST_MENU', 0xAF: 'STATUS_SCREEN',
    0x1C: 'STATUS_SCREEN_CURSOR',
    # cursor and input
    0xCF: 'JAKE_INPUT', 0xA2: 'WAIT_BUTTON', 0x61: 'JOY_PRESSED', 0xD2: 'JOY_HELD', 0x88: 'CURSOR_X',
    0x8A: 'CURSOR_Y', 0xBC: 'PICK_OBJECT', 0xA5: 'PICK_OBJECT_FROM', 0xC9: 'PICK_OBJECT_NEAR?', 0xC0: 'PICK_TYPE?',
    0xD7: 'PICK_TYPE2?', 0x8E: 'PICK_TYPE3?', 0xA4: 'HIDE_CURSOR', 0x45: 'HIDE_CURSOR_REFRESH',
    0xC1: 'LAST_MENU_RESULT?', 0x4A: 'CURSOR_ON_JAKE', 0x2E: 'CURSOR_ON_JAKE2', 0x6B: 'CURSOR_HOME', 0x67: 'CURSOR_POS_B',
    0xB7: 'CURSOR_POS_B2', 0x8D: 'CURSOR_RESET?',
    # timing, sound, screen
    0x9E: 'WAIT', 0x3E: 'RANDOM', 0x63: 'RAND_RAW', 0xB3: 'HALVE_SIGNED', 0x4C: 'PLAY_SFX?',
    0x52: 'PLAY_SFX_AT?', 0x55: 'SCREEN_EFFECT?', 0x2D: 'LAYER_TOGGLE?', 0x20: 'SCREEN_20?',
    # cut-scene effects (ring of objects $1D0B.., sine table $80D399)
    0x09: 'RING_CREATE', 0x77: 'RING4_CREATE', 0x1E: 'RING_UPDATE', 0xA9: 'RING_MOVE', 0x18: 'RING_RESET',
    0x05: 'RING_PARAM_5D', 0xA1: 'RING_PARAM_5F', 0xBD: 'RING_PARAM_61', 0x16: 'RING_PARAM_63',
    0x5E: 'BOB_A', 0x65: 'BOB_B', 0xAC: 'ORBIT_START', 0x8C: 'ORBIT_STEP', 0x81: 'ORBIT_81?',
    0x31: 'ORBIT_SLOT0', 0x32: 'ORBIT_SLOT1', 0x35: 'ORBIT_SLOT2', 0x36: 'ORBIT_SLOT3', 0x37: 'ORBIT_SLOT4',
    0x38: 'ORBIT_SLOT5', 0x39: 'ORBIT_SLOT6', 0x3A: 'ORBIT_SLOT7',
    0x00: 'BROKEN_00',
}
GLOBALS = {0x3C11: 'karma', 0x3C00: 'max_stamina', 0x3BFB: 'body', 0x3BFC: 'quickness', 0x3BFD: 'strength',
           0x3BFF: 'charisma', 0x2DE2: 'next_location', 0x3C18: 'dermal', 0x3C19: 'wired'}


def gname(a, w):
    if a in GLOBALS: return GLOBALS[a]
    if not w and 0x3BBB <= a < 0x3BBB + 64: return 'var[%d]' % (a - 0x3BBB)
    return ('gw[$%04X]' if w else 'gb[$%04X]') % a


def num(v):
    return str(v) if v < 10 else '%d' % v if v < 0x100 else '$%04X' % v


# ---------------------------------------------------------------- object types, placements, conversations
TYPES = {}
for t in range(0, 0x20A0, 7):
    s = RW(0x8DB036 + t)
    if s < NSCR: TYPES[t] = dict(flags=RB(0x8DB031 + t), rec=RW(0x8DB032 + t), spr=RW(0x8DB034 + t), script=s)


def loc_objs(loc):
    p = RW(0x8D92AF + 9 * loc); addr = ((0x99 + (p >> 15)) << 16) | (p | 0x8000)
    n = RB(addr + 4); out = []
    if n > 60: return addr, None
    for k in range(n):
        w1 = RW(addr + 5 + 6 * k); w2 = RW(addr + 7 + 6 * k); t = RW(addr + 9 + 6 * k)
        out.append(dict(x=w1 & 0x7FF, y=w2 & 0x7FF, type=t))
    return addr, out


OBJ_SCRIPTS = {d['script'] for d in TYPES.values()}
NLOC = 0x1FC
MAPS = collections.OrderedDict()     # map addr -> list of locations
LOCMAP = {}
for loc in range(NLOC):
    a, o = loc_objs(loc)
    if o is None or any(d['type'] not in TYPES for d in o): continue
    MAPS.setdefault(a, []).append(loc); LOCMAP[loc] = a


def zones_for(loc):
    z = ZONES.get(str(loc))
    if not z: return None
    if 'same_as' in z: z = ZONES.get(str(z['same_as']), {})
    zs = z.get('zones')
    if zs is None or any(v[0] > 0x800 or v[1] > 0x800 for _, v in zs): return None
    return zs


NCONV = 139


def conv(n):
    p = RW(0x80947A + 2 * n); base = 0x8D0000 | p; y = 4; out = []
    for _ in range(80):
        t = RB(base + y)
        if t == 0xF8: break
        ln = RB(base + y + 1); fl = RB(base + y + 2); k = fl & 0x0F
        kws = [RB(base + y + 3 + i) for i in range(k)]; q = base + y + 3 + k; scr = None
        if fl & 0x80: scr = RW(q); q += 2
        out.append(dict(topic=t, kws=kws, script=scr, tid=RW(q))); y += 1 + ln
    return out


def keyword(k):
    if k >= 64: return '#%d' % k
    try: return text(RW(0x8D8000 + 2 * k))
    except Exception: return '#%d' % k


def topic_name(t, kws):
    return {0xFF: 'greeting', 0xFE: 'Talk', 0xFD: 'default answer'}.get(t, 'keyword "%s"' % keyword(t)) + \
        (' (needs %s)' % ', '.join('"%s"' % keyword(k) for k in kws) if kws else '')


CONVS = {}
for n in range(NCONV):
    try: CONVS[n] = conv(n)
    except Exception: pass

# ---------------------------------------------------------------- decoding one script
def decode(sid):
    """Returns list of (offset, op, name, arg, raw bytes) for every reachable instruction."""
    base = sloc(sid) + 2; seen = {}; todo = [0]
    while todo:
        pc = todo.pop()
        while pc not in seen and 0 <= pc < 0x4000:
            op = rom[base + pc]
            if op not in OPS:
                seen[pc] = (pc, op, '??', None, rom[base + pc:base + pc + 1]); break
            name, n = OPS[op]; arg = int.from_bytes(rom[base + pc + 1:base + pc + 1 + n], 'little') if n else None
            seen[pc] = (pc, op, name, arg, rom[base + pc:base + pc + 1 + n])
            if name in ('jz', 'jnz', 'call'): todo.append(arg)
            if name == 'jmp': todo.append(arg); break
            if name in ('end', 'ret', 'halt'): break
            if name == 'script' and arg >= NSCR: break
            pc += 1 + n
    return [seen[k] for k in sorted(seen)], base


def effect(name, arg, sigs):
    if name.startswith('push'): return 0, 1
    if name.startswith('pop.') or name in ('drop', 'jz', 'jnz', 'end'): return 1, 0
    if name in BIN: return 2, 1
    if name in UN: return 1, 1
    if name == 'dup': return 1, 2
    if name == 'native': return nargs(arg), int(nret(arg))
    if name == 'script': return (sargs(arg), int(sret(arg))) if arg < NSCR else (0, 0)
    if name == 'call': return sigs.get(arg) or (0, 0)
    return 0, 0


def sub_sig(byp, target, sigs, depth=0):
    """(args, results) of an in-script subroutine, or None when its paths disagree."""
    if depth > 4: return None
    found = set(); seen = set(); todo = [(target, 0, 0)]
    while todo:
        pc, d, mn = todo.pop()
        if (pc, d) in seen or pc not in byp or len(seen) > 4000: continue
        seen.add((pc, d))
        _, op, name, arg, raw = byp[pc]
        if name == 'call' and arg not in sigs:
            sigs[arg] = sub_sig(byp, arg, sigs, depth + 1) if arg != target else None
            if sigs[arg] is None: return None
        po, pu = effect(name, arg, sigs); d -= po; mn = min(mn, d); d += pu
        if name == 'ret': found.add((-mn, d - mn)); continue
        if name in ('end', 'halt', '??'): continue
        if name in ('jz', 'jnz', 'jmp'): todo.append((arg, d, mn))
        if name != 'jmp': todo.append((pc + len(raw), d, mn))
    return found.pop() if len(found) == 1 else None


def pseudo(sid, ins):
    """Simple per-block expression rebuilder. Returns (lines, refs) where refs collects texts/scripts/etc."""
    refs = dict(scripts=set(), natives=set(), msgs=set(), convs=set(), warps=set(), globals=set(), creates=set())
    targets = {i[3] for i in ins if i[2] in ('jz', 'jnz', 'jmp', 'call')}
    subs = {i[3] for i in ins if i[2] == 'call'}
    byp = {i[0]: i for i in ins}; sigs = {}
    for t in subs:
        if t not in sigs: sigs[t] = sub_sig(byp, t, sigs)
    L0 = 'self' if sid in OBJ_SCRIPTS else 'L.b0'
    lines = []; st = []; note = []; tmp = {'n': 0}; entry = [sargs(sid), True]   # args left to pop at entry, still in entry block

    def pop():
        if st: return st.pop()
        if entry[1] and entry[0] > 0:
            entry[0] -= 1; return 'arg%d' % (entry[0] + 1)
        return 'pop()'

    def flush():
        while st: lines.append('    push %s' % st.pop(0))

    def emit(pc, s):
        lines.append('%04X  %s' % (pc, s))
        for n in note: lines.append('        ; ' + n)
        note.clear()

    prev_end = None
    for pc, op, name, arg, raw in ins:
        if pc in targets or (prev_end is not None and pc != prev_end):
            entry[1] = False; flush(); lines.append(('sub_%04X:' if pc in subs else 'L_%04X:') % pc)
        prev_end = pc + len(raw)
        if name in ('push.b', 'push.w'): st.append(num(arg))
        elif name == 'push.sb': st.append(str(arg - 256 if arg & 0x80 else arg))
        elif name == 'push0': st.append('0')
        elif name == 'push.lb0': st.append(L0)
        elif name in ('push.lb', 'push.lsb'): st.append(L0 if arg == 0 else 'L.b%d' % arg)
        elif name == 'push.lw': st.append('L.w%d' % arg)
        elif name in ('push.gb', 'push.gsb', 'push.gw'):
            st.append(gname(arg, name == 'push.gw')); refs['globals'].add(arg)
        elif name == 'pop.lb' and arg == 0 and L0 == 'self':
            emit(pc, 'self = %s' % pop())
        elif name in ('pop.lb', 'pop.lw'):
            emit(pc, 'L.%s%d = %s' % ('b' if name == 'pop.lb' else 'w', arg, pop()))
        elif name in ('pop.gb', 'pop.gw'):
            refs['globals'].add(arg); emit(pc, '%s = %s' % (gname(arg, name == 'pop.gw'), pop()))
        elif name in BIN:
            b = pop(); a = pop(); st.append('(%s %s %s)' % (a, BIN[name], b))
        elif name in UN:
            a = pop()
            st.append({'neg': '(-%s)', 'not': '(~%s)', 'inc': '(%s + 1)', 'dec': '(%s - 1)', 'bool': 'bool(%s)'}[name] % a)
        elif name == 'dup':
            a = pop()
            if '(' in a:
                tmp['n'] += 1; t = 't%d' % tmp['n']; emit(pc, '%s = %s' % (t, a)); a = t
            st += [a, a]
        elif name == 'drop':
            a = pop()
            if a not in ('pop()',) and not a.replace('$', '').isalnum(): emit(pc, a)
        elif name in ('jz', 'jnz'):
            c = pop(); flush()
            emit(pc, 'if %s%s goto L_%04X' % ('not ' if name == 'jz' else '', c, arg))
        elif name == 'jmp':
            flush(); emit(pc, 'goto L_%04X' % arg)
        elif name == 'call':
            sg = sigs.get(arg)
            if sg and sg[1] <= 1:
                args = [pop() for _ in range(sg[0])][::-1]; c = 'sub_%04X(%s)' % (arg, ', '.join(args))
                if sg[1]: st.append(c)
                else: emit(pc, c)
            else:
                flush(); emit(pc, 'gosub sub_%04X' % arg)
        elif name == 'ret':
            flush(); emit(pc, 'return')
        elif name == 'end':
            v = pop(); flush(); emit(pc, 'end%s' % ('' if v == 'pop()' else ' (value %s)' % v))
        elif name == 'halt':
            flush(); emit(pc, 'halt (invalid opcode $54)')
        elif name == 'script':
            refs['scripts'].add(arg)
            if arg >= NSCR:
                flush(); emit(pc, 'script $%03X  ; outside the directory' % arg); continue
            n = sargs(arg); args = [pop() for _ in range(n)][::-1]
            call = 'script_%03X(%s)' % (arg, ', '.join(args))
            if sret(arg): st.append(call)
            else: emit(pc, call)
        elif name == 'native':
            refs['natives'].add(arg)
            n = nargs(arg); args = [pop() for _ in range(n)][::-1]
            nm = NATIVES.get(arg, 'native_%02X' % arg)
            def const(s):
                try: return int(s.replace('$', '0x'), 0)
                except Exception: return None
            if arg in (0x99, 0xD6) and args and const(args[-1]) is not None:
                m = const(args[-1]); refs['msgs'].add(m); t = msg_text(m)
                if t is not None: note.append('msg %d: "%s"' % (m, t))
            if arg == 0xB4 and len(args) == 2 and const(args[0]) is not None:
                m = const(args[0]); refs['msgs'].add(m); t = msg_text(m)
                if t is not None: note.append('msg %d: "%s"' % (m, t))
            if arg == 0xC7 and len(args) == 7 and const(args[1]) is not None:
                m = const(args[1]); refs['msgs'].add(m); t = msg_text(m)
                if t is not None: note.append('msg %d: "%s"' % (m, t))
            if arg == 0xA8 and len(args) == 5 and const(args[0]) is not None and const(args[0]) < NSCR:
                sc = const(args[0]); sp = const(args[4]); refs['scripts'].add(sc)
                nm = sprite_name(sp) if sp is not None else ''
                refs['creates'].add((sc, sp if sp is not None else -1))
                note.append('new object runs script $%03X%s' % (sc, (' with sprite $%02X' % sp if sp is not None else '') +
                                                               (' "%s"' % nm if nm else '')))
            if arg == 0x94:
                for a in args:
                    c = const(a)
                    if c is not None and c in CONVS:
                        refs['convs'].add(c); note.append('conversation %d (see below)' % c)
            if arg in (0x56, 0x54) and args:
                c = const(args[0])
                if c is not None and c < NLOC: refs['warps'].add(c); note.append('to location $%03X' % c)
            call = '%s(%s)' % (nm, ', '.join(args))
            if nret(arg): st.append(call)
            else: emit(pc, call)
        else:
            flush(); emit(pc, '?? opcode $%02X' % op)
    flush()
    return lines, refs


def raw_listing(ins, base):
    out = []
    for pc, op, name, arg, raw in ins:
        a = ''
        if arg is not None:
            a = ('L_%04X' % arg) if name in ('jz', 'jnz', 'jmp', 'call') else \
                ('$%03X' % arg) if name == 'script' else \
                ('$%02X %s' % (arg, NATIVES.get(arg, ''))) if name == 'native' else \
                ('$%04X' % arg) if len(raw) == 3 else str(arg)
        out.append('%04X  %06X  %-9s %-10s %s' % (pc, snes(base + pc), raw.hex(' '), name, a))
    return out


# ---------------------------------------------------------------- cross references
used_by = collections.defaultdict(list)
type_locs = collections.defaultdict(set)
unplaced = collections.defaultdict(list)
for a, locs in MAPS.items():
    _, o = loc_objs(locs[0])
    for d in o: type_locs[d['type']].update(locs)
for t, d in TYPES.items():
    where = ', '.join('$%03X' % l for l in sorted(type_locs.get(t, ())))
    nm = RUNNER_NAMES.get(t) or sprite_name(d['spr']); nm = ' "%s"' % nm if nm else ''
    if where: used_by[d['script']].append('object type $%04X%s (sprite $%02X, record $%04X) placed at %s' % (
        t, nm, d['spr'], d['rec'], where))
    else: unplaced[d['script']].append('$%04X%s' % (t, nm))
for n, es in CONVS.items():
    for e in es:
        if e['script'] is not None and e['script'] < NSCR:
            used_by[e['script']].append('conversation %d, topic %s' % (n, topic_name(e['topic'], e['kws'])))
for sc, ts in unplaced.items():
    used_by[sc].append('object type%s %s (not placed on a map: item, spawned or unused)' % (
        's' if len(ts) > 1 else '', ', '.join(ts[:12]) + (' +%d more' % (len(ts) - 12) if len(ts) > 12 else '')))
zone_scripts = collections.defaultdict(set)
for loc in range(NLOC):
    zs = zones_for(loc)
    if zs and loc in LOCMAP and loc == MAPS[LOCMAP[loc]][0]:
        for pas, v in zs:
            if pas == 0 and v[6] < NSCR: zone_scripts[v[6]].update(MAPS[LOCMAP[loc]])
for s, locs in zone_scripts.items():
    used_by[s].append('floor zone (runs while Jake stands in it) at ' + ', '.join('$%03X' % l for l in sorted(locs)))

decoded = {}; called_by = collections.defaultdict(set); created = collections.defaultdict(set)
for sid in range(NSCR):
    ins, base = decode(sid); lines, refs = pseudo(sid, ins); decoded[sid] = (ins, base, lines, refs)
    for c in refs['scripts']: called_by[c].add(sid)
    for c, sp in refs['creates']: created[c].add((sp, sid))
for c, items in created.items():
    for sp, sid in sorted(items):
        nm = sprite_name(sp) if sp >= 0 else ''
        used_by[c].append('object created by script $%03X%s%s' % (sid, ' with sprite $%02X' % sp if sp >= 0 else '',
                                                                ' "%s"' % nm if nm else ''))


def summary(sid):
    ins, base, lines, refs = decoded[sid]
    u = list(used_by.get(sid, []))
    if called_by.get(sid): u.append('called (or given to a new object) by script ' + ', '.join('$%03X' % c for c in sorted(called_by[sid])))
    return u


def greeting(c):
    for e in CONVS.get(c, []):
        if e['topic'] == 0xFF:
            try: return text(e['tid'])
            except Exception: return ''
    return ''


def title(sid):
    if sid in KNOWN: return KNOWN[sid]
    names = []
    for u in used_by.get(sid, []):
        if u.startswith('object type') or u.startswith('object created'):
            for n in u.split('"')[1::2]:
                if n not in names: names.append(n)
    if names: return ', '.join(names[:3]) + (' +%d' % (len(names) - 3) if len(names) > 3 else '')
    ins, base, lines, refs = decoded[sid]
    for c in sorted(refs['convs']):
        g = greeting(c)
        if g: return 'talks: "%s"' % (g[:48] + ('...' if len(g) > 48 else ''))
    for s in used_by.get(sid, []):
        if s.startswith('conversation'): return s.split(',')[0] + ' topic script'
    for m in sorted(refs['msgs']):
        t = msg_text(m)
        if t: return 'shows: "%s"' % (t[:48] + ('...' if len(t) > 48 else ''))
    if 0x23 in refs['natives']: return 'weapon item'
    if 0x34 in refs['natives']: return 'armor item'
    if refs['warps'] and len(ins) < 40: return 'door to ' + ', '.join('$%03X' % w for w in sorted(refs['warps']))
    if 0xAB in refs['natives']: return 'combatant'
    for s in used_by.get(sid, []):
        if s.startswith('floor zone'): return 'floor zone'
    if called_by.get(sid): return 'helper'
    return ''


os.makedirs(os.path.join(OUT, 'scripts'), exist_ok=True)
allf = open(os.path.join(OUT, 'all_scripts.txt'), 'w'); index = []
allf.write(__doc__ + '\n')
for sid in range(NSCR):
    ins, base, lines, refs = decoded[sid]
    hdr = ['=' * 78,
           'Script $%03X  (%d)  %s' % (sid, sid, title(sid)),
           'SNES $%06X  file $%05X  args: %d word(s)  returns a value: %s  size: %d bytes reached' % (
               snes(base - 2), base - 2, sargs(sid), 'yes' if sret(sid) else 'no', sum(len(i[4]) for i in ins)),
           '=' * 78]
    u = summary(sid)
    body = hdr + (['Used by:'] + ['  - ' + s for s in u] if u else ['Used by: (no reference found; may be started from engine code)'])
    if refs['scripts']: body.append('Calls scripts: ' + ', '.join('$%03X' % c for c in sorted(refs['scripts'])))
    if refs['warps']: body.append('Warps to: ' + ', '.join('$%03X' % c for c in sorted(refs['warps'])))
    if refs['natives']:
        body.append('Natives: ' + ', '.join(NATIVES.get(n, 'native_%02X' % n) for n in sorted(refs['natives'])))
    body += ['', '-- pseudo-code --'] + lines
    for c in sorted(refs['convs']):
        body += ['', '-- conversation %d --' % c]
        for e in CONVS[c]:
            try: t = text(e['tid'])
            except Exception: t = '?'
            body.append('  %s%s: "%s"' % (topic_name(e['topic'], e['kws']),
                                          ' -> script $%03X' % e['script'] if e['script'] is not None else '', t))
    body += ['', '-- raw bytecode --'] + raw_listing(ins, base) + ['']
    txt = '\n'.join(body)
    open(os.path.join(OUT, 'scripts', 'script_%03X.txt' % sid), 'w').write(txt)
    allf.write(txt + '\n')
    index.append(dict(id=sid, title=title(sid), used=u, calls=sorted(refs['scripts']), natives=sorted(refs['natives']),
                      warps=sorted(refs['warps']), convs=sorted(refs['convs']), args=sargs(sid), ret=sret(sid),
                      size=sum(len(i[4]) for i in ins), text=txt))
allf.close()
json.dump(index, open(os.path.join(OUT, 'index.json'), 'w'))

# ---------------------------------------------------------------- locations file
with open(os.path.join(OUT, 'locations.txt'), 'w') as f:
    f.write('Locations grouped by map. Several location ids share a map (one per door you can arrive through).\n')
    f.write('Exits: box x1,y1 - x2,y2 -> destination location. Floor zones run a script while Jake stands inside.\n\n')
    for a, locs in MAPS.items():
        f.write('=' * 70 + '\nLocations %s   map data $%06X\n' % (', '.join('$%03X' % l for l in locs), a))
        _, o = loc_objs(locs[0])
        for d in o:
            t = TYPES[d['type']]; nm = RUNNER_NAMES.get(d['type']) or sprite_name(t['spr'])
            f.write('  object type $%04X %-20s at (%3d,%3d)  script $%03X  %s\n' % (
                d['type'], '"%s"' % nm if nm else '', d['x'], d['y'], t['script'], '' if nm else title(t['script'])))
        zs = zones_for(locs[0])
        for pas, v in zs or []:
            if pas == 1: f.write('  exit  (%d,%d)-(%d,%d) -> location $%03X\n' % (v[0], v[1], v[3], v[4], v[6]))
            else: f.write('  floor zone (%d,%d)-(%d,%d) runs script $%03X\n' % (v[0], v[1], v[3], v[4], v[6]))
        f.write('\n')
print('scripts', NSCR, 'types', len(TYPES), 'maps', len(MAPS), 'convs', len(CONVS))
