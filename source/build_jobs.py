"""Glutman's jobs (part of the Arena Leagues patch module: shares its hooks, bank $BE code, text and script tables).

Glutman leaves the story after hiding Jake in the car yards (his record owner = $1538). From then on he stands at
The Cage entrance (map of locations $008/$01C) as a fixer:
  * Talk -> a random job (one of JOBS), yes/no. A job = a door on a street (his man waits there and opens it) that
    leads into a guarded office floor (one exit, disabled while you're inside), where you either kill a boss
    (a stronger copy of one of the floor's guards) or get to the floor's computer terminal.
  * Done -> walk back out through the room's entrance, talk to Glutman, get paid. Next job after one sleep.
State (inside the saved block, unused by the game): $7E3BF9 job state (0 free, 1 active, 2 done, 3 paid / wait for
a sleep), $7E3BFA job number. Work bytes (not saved): $7E234C arrival (1 = entering the job room, 2 = leaving it),
$7E234D 'talking to our Glutman', $7E234E destination of the active trigger, records $7E2350.. (boss, escorts,
Glutman, contact).
"""
from srasm import Script

STATE, JOB = 0x3BF9, 0x3BFA                 # bank $7E, saved
ARRIVE, GTALK, GDEST = 0x234C, 0x234D, 0x234E
REC_BOSS, REC_ESC1, REC_ESC2, REC_GLUT, REC_CONTACT, REC_TRIG = 0x2350, 0x2355, 0x235A, 0x235F, 0x2364, 0x2369
GLUT_T, GLUT_REC, GLUT_MAP, GLUT_POS = 0x03BF, 0x2EFA, 0x067C, (0x248, 0x1F4, 0x44)
CONTACT_T = 0x0FCE                          # a man from The Cage crowd
TRIG_T = 0x0DEB                             # the arena's exit marker type (no picture): invisible triggers
SP = 0x7F6840                               # spawn parameters (words): spr scr x y z type rec + temps
SP_SPR, SP_SCR, SP_X, SP_Y, SP_Z, SP_TYPE, SP_REC, SP_T1, SP_T2, SP_OBJ = (SP + 2 * i for i in range(10))
SAVEDP = 0x7F6880                           # direct page copy around our map-load work (64 bytes)
EMPTY_ZONES = None                          # filled by emit: two zero counts = no exits

# job: street location to come back to (its entry is where the contact waits), interior (office floor) location,
#      kind ('kill' / 'hack'), target spot, boss/escort guard types with their health, pay, wording
JOBS = [
    dict(street=0x017, room=0x1E1, kind='kill', boss=(0x1378, 45), esc=(0x5A9, 30), pay=7000,
         where='Brick building on Tenth Street, arched door.', short='Tenth Street, arched door'),
    dict(street=0x022, room=0x1E2, kind='hack', boss=(0x5C5, 33), esc=(0xA1E, 27), pay=8000,
         where='Gray tower Downtown, green doors.', short='Downtown, green doors'),
    dict(street=0x03F, room=0x1E3, kind='kill', boss=(0x914, 39), esc=(0x586, 30), pay=9000,
         where='Old stone tower, dark doorway.', short='stone tower, dark doorway'),
    dict(street=0x000, room=0x1E4, kind='hack', boss=(0x5DA, 34), esc=(0xAD4, 27), pay=10000,
         where='Brick building by the blue shop sign.', short='brick building by the blue sign'),
    dict(street=0x017, room=0x1E5, kind='hack', boss=(0x60B, 40), esc=(0x5BE, 40), pay=11000,
         where='Brick building on Tenth Street, arched door.', short='Tenth Street, arched door'),
    dict(street=0x022, room=0x1E6, kind='kill', boss=(0x8FF, 40), esc=(0x5E1, 34), pay=12000,
         where='Gray tower Downtown, green doors.', short='Downtown, green doors'),
    dict(street=0x03F, room=0x1E7, kind='kill', boss=(0x136A, 46), esc=(0x5EF, 40), pay=13000,
         where='Old stone tower, dark doorway.', short='stone tower, dark doorway'),
]
NJOBS = len(JOBS)
# spots for Glutman's man near each street entrance, best first (found offline: 24-32 from the entrance and as far
# as possible from the map's exit zones, so walking up to him never takes Jake through a door)
CONTACT_SPOTS = {0x017: [(371, 212), (370, 190), (371, 167), (377, 206)],
                 0x022: [(530, 384), (529, 362), (536, 378), (521, 362)],
                 0x03F: [(232, 407), (209, 416), (215, 422), (200, 439)],
                 0x000: [(484, 514), (499, 530), (492, 514), (516, 546)]}
BOSS_X = 3                                  # boss health = guard health x 3 (max 255)


def money(v): return '{:,}'.format(v)


def texts():
    """job texts in order; returns (list of strings, dict name -> index into that list)"""
    t = []; ix = {}
    def add(name, s): ix[name] = len(t); t.append(s)
    add('greet', "Jake! Glutman never forget a friend. You need nuyen? I got work, ya. Talk to me.")
    add('accept', "Good! My man waits at the door. He open the lock for you. Don't make me wait, ya!")
    add('decline', "Okay, okay. You come back when you want work.")
    add('cool', "No work today. Come back tomorrow, ya.")
    add('door', "Glutman sent you? Lock is open. Go!")
    add('killed', "Target down! Get out and see Glutman.")
    add('hacked', "DATA FILE OBTAINED. Get out and see Glutman.")
    add('locked', "Only Glutman's man has the key for this door.")
    for k, j in enumerate(JOBS):
        what = 'Kill the boss inside.' if j['kind'] == 'kill' else 'Get to the computer inside.'
        add('offer%d' % k, "%s My man opens it. %s %s nuyen?" % (j['where'], what, money(j['pay'])))
        add('remind%d' % k, "Job not done yet! %s. %s" % (j['short'][0].upper() + j['short'][1:],
                                                          'Kill the boss.' if j['kind'] == 'kill' else 'Get to the computer.'))
        add('paid%d' % k, "You do good work, ya! Here's %s nuyen. Come back tomorrow, maybe more work." % money(j['pay']))
    return t, ix


def scripts(T, MSG):
    """our scripts; T = text name -> message index (>= $0F00) understood by the text hooks. Returns dict name -> blob
    in a fixed order (see ORDER)."""
    out = {}

    # Glutman at The Cage: wait to be talked to, run conversation 72 (Glutman's own) with our flag up
    s = Script(); s.pop_lb(0)
    s.push(5); s.push(0); s.self_(); s.native(0xD1)                          # standing animation (else unseen)
    s.label('top'); s.push(0); s.push(2); s.native(0x9E); s.drop()          # wait for 'Talk'
    s.push(1); s.set_gb(GTALK)
    s.push(72); s.self_(); s.native(0x94)                                    # conversation (blocks until Exit)
    s.push(0); s.set_gb(GTALK)
    s.jmp('top')
    out['glut'] = s.done()

    # 'Talk' answer inside that conversation (run by the conversation hook)
    s = Script(); s.pop_lb(0)
    s.gb(STATE); s.push(3); s.eq(); s.jz('n3')
    s.push(T['cool']); s.native(0x99); s.end()
    s.label('n3')
    s.gb(STATE); s.push(2); s.eq(); s.jz('n2')
    s.gb(JOB); s.push(1000); s.mul(); s.push(JOBS[0]['pay']); s.add(); s.native(0x98)   # pay = 7,000 + 1,000 x job
    s.gb(JOB); s.push(3); s.mul(); s.push(T['paid0']); s.add(); s.native(0x99)   # texts: offer, remind, paid per job
    s.push(3); s.set_gb(STATE); s.end()
    s.label('n2')
    s.gb(STATE); s.push(1); s.eq(); s.jz('n1')
    s.gb(JOB); s.push(3); s.mul(); s.push(T['remind0']); s.add(); s.native(0x99)   # texts: offer, remind, paid per job; s.end()
    s.label('n1')                                                            # free: pick a job, not the last one
    s.push(NJOBS - 1); s.native(0x3E)                                        # random(0..N-2)
    s.dup(); s.gb(JOB); s.lt(); s.jnz('lower')                               # r < last: keep r
    s.push(1); s.add()                                                       # else r+1 (skips the last job)
    s.label('lower')
    s.set_gb(JOB)
    s.gb(JOB); s.push(3); s.mul(); s.push(T['offer0']); s.add(); s.native(0x99)   # texts: offer, remind, paid per job
    s.push(8); s.push(24); s.native(0x72); s.jz('no')                        # yes / no
    s.push(1); s.set_gb(STATE)
    s.push(T['accept']); s.native(0x99); s.end()
    s.label('no'); s.push(T['decline']); s.native(0x99); s.end()
    out['talk'] = s.done()

    def floater(s, msg, h):
        s.push(150); s.push(msg); s.push(0x0400); s.push(h); s.push(26); s.push(3); s.push(2); s.native(0xC7)

    # Glutman's man at the door: opens it once you walk up to him (after you've stepped away from him once)
    s = Script(); s.pop_lb(0); s.push(0); s.pop_lb(1)
    s.push(5); s.push(0); s.self_(); s.native(0xD1)                          # standing animation
    s.label('top'); s.wait(10)
    s.gb(STATE); s.push(1); s.eq(); s.jz('top')
    s.lb(1); s.jnz('armed')
    s.self_(); s.native(0x0A); s.push(40); s.gt(); s.jz('top')
    s.push(1); s.pop_lb(1); s.jmp('top')
    s.label('armed')
    s.self_(); s.native(0x0A); s.push(20); s.lt(); s.jz('top')
    floater(s, T['door'], 3); s.wait(45)
    s.push(1); s.set_gb(ARRIVE)
    s.gw(GDEST); s.native(0x56); s.end()
    out['door'] = s.done()

    # the room's way out (no animation = not drawn; at the entrance) + 'boss down' watch
    s = Script(); s.pop_lb(0); s.push(0); s.pop_lb(1)
    s.label('top'); s.wait(10)
    s.gb(STATE); s.push(1); s.eq(); s.jz('nb')
    s.gb(REC_BOSS + 2); s.push(0); s.eq(); s.jz('nb')                        # boss health 0: dead
    s.push(2); s.set_gb(STATE); floater(s, T['killed'], 3)
    s.label('nb')
    s.lb(1); s.jnz('armed')
    s.self_(); s.native(0x0A); s.push(40); s.gt(); s.jz('top')
    s.push(1); s.pop_lb(1); s.jmp('top')
    s.label('armed')
    s.self_(); s.native(0x0A); s.push(16); s.lt(); s.jz('top')
    s.push(2); s.set_gb(ARRIVE)
    s.gw(GDEST); s.native(0x56); s.end()
    out['exit'] = s.done()

    # the data terminal on the target spot
    s = Script(); s.pop_lb(0)
    s.push(5); s.push(0); s.self_(); s.native(0xD1)                          # its picture
    s.label('top'); s.wait(10)
    s.gb(STATE); s.push(1); s.eq(); s.jz('top')
    s.self_(); s.native(0x0A); s.push(24); s.lt(); s.jz('top')
    s.push(2); s.set_gb(STATE); floater(s, T['hacked'], 4); s.end()
    out['comp'] = s.done()
    return out


ORDER = ['glut', 'talk', 'door', 'exit', 'comp']


# ---------------------------------------------------------------- 65816 side
JS = 64                                    # bytes per job record
F = dict(smap=0, sloc=2, room=4, kind=6, tx=8, ty=10, tz=12, btype=14, bspr=16, bscr=18, bhp=20,
         etype=22, espr=24, escr=26, ehp=28, rx=30, ry=32, rz=34, cx=36, cy=38, cz=40, ttype=42, tspr=44, s0=46, s1=50, s2=54, s3=58)


def room_objects(RW, RB, loc):
    p = RW(0x8D92AF + 9 * loc); base = ((0x99 + (p >> 15)) << 16) | (p | 0x8000)
    out = []
    for k in range(RB(base + 4)):
        w1 = RW(base + 5 + 6 * k); w2 = RW(base + 7 + 6 * k); t = RW(base + 9 + 6 * k)
        out.append(dict(x=w1 & 0x7FF, y=w2 & 0x7FF, z=((w1 >> 11) & 31) | (((w2 >> 11) & 31) << 5), type=t,
                        spr=RW(0x8DB034 + t), scr=RW(0x8DB036 + t)))
    return out


def far_post(RW, RB, j):
    """the room's guard post farthest from its entrance: the boss / the data terminal goes there"""
    e = 0x8D92AF + 9 * j['room']; ex, ey = RW(e + 3), RW(e + 5)
    posts = [o for o in room_objects(RW, RB, j['room']) if o['spr'] != 0xB2 and o['scr'] != 0x31]
    o = max(posts, key=lambda o: (o['x'] - ex) ** 2 + (o['y'] - ey) ** 2)
    return (o['x'], o['y'], 64)


def terminal_type(RW, RB, j):
    return [o for o in room_objects(RW, RB, j['room']) if o['spr'] == 0xB2][0]['type']


def job_table(RW, RB):
    out = bytearray()
    for j in JOBS:
        j['target'] = far_post(RW, RB, j)
        loc9 = lambda l: 0x8D92AF + 9 * l
        w = dict(smap=RW(loc9(j['street'])), sloc=j['street'], room=j['room'], kind=0 if j['kind'] == 'kill' else 1,
                 tx=j['target'][0], ty=j['target'][1], tz=j['target'][2],
                 btype=j['boss'][0], bspr=RW(0x8DB034 + j['boss'][0]), bscr=RW(0x8DB036 + j['boss'][0]),
                 bhp=min(255, j['boss'][1] * (BOSS_X if j['kind'] == 'kill' else 1)),
                 etype=j['esc'][0], espr=RW(0x8DB034 + j['esc'][0]), escr=RW(0x8DB036 + j['esc'][0]), ehp=j['esc'][1], ttype=terminal_type(RW, RB, j), tspr=0xB2,
                 **{'s%d' % i: 0 for i in range(4)},
                 rx=RW(loc9(j['room']) + 3), ry=RW(loc9(j['room']) + 5), rz=RW(loc9(j['room']) + 7),
                 cx=RW(loc9(j['street']) + 3), cy=RW(loc9(j['street']) + 5), cz=RW(loc9(j['street']) + 7))
        rec = bytearray(JS)
        for k, off in F.items(): rec[off:off + 2] = (w[k] & 0xFFFF).to_bytes(2, 'little')
        for i, (x, y) in enumerate(CONTACT_SPOTS[j['street']]):
            rec[F['s%d' % i]:F['s%d' % i] + 4] = x.to_bytes(2, 'little') + y.to_bytes(2, 'little')
        out += rec
    return bytes(out)


def emit(a, sid, tptr_index, RW, RB, RTL80, CODE):
    """sid: script name -> id; tptr_index: text name -> global text number. Adds labels 'topic', 'mapload',
    'jobsleep' and the data they use."""
    lx = lambda op, addr: (a.b(op), a.l(addr))
    def rec_init(addr, hp):                                      # 00 00 hp FF FF at $7E:addr
        a.imm(0xA9, 0); a.sta_l(0x7E0000 + addr); a.imm(0xA9, hp); a.sta_l(0x7E0000 + addr + 2)
        a.imm(0xA9, 0xFFFF); a.sta_l(0x7E0000 + addr + 3)
    def set_sp(var, v): a.imm(0xA9, v); a.sta_l(var)
    def job_y():                                                 # Y = job * 64
        a.lda_l(0x7E0000 + JOB); a.imm(0x29, 0xFF); a.b(0x0A, 0x0A, 0x0A, 0x0A, 0x0A, 0x0A); a.b(0xA8)
    def ldj(field): a.b(0xBB); a.lda_lx(F[field]); a.fix.append(('long', len(a.code) - 3, 'jobs'))   # tyx; lda jobs+f,X
    def byte(addr):                                              # A = byte at $7E:addr
        a.lda_l(0x7E0000 + addr); a.imm(0x29, 0xFF)

    # ---- the 'Talk' / greeting answers of conversation 72 while our Glutman talks.
    #      JSL from $809123 (replaces STA $1D / LDA $14 / STA $00) ----
    a.label('topic')
    a.b(0x85, 0x1D); a.b(0x48)
    byte(GTALK); a.rel(0xF0, 'tp_orig')
    a.b(0x68); a.imm(0xC9, 0xFFFF); a.rel(0xF0, 'tp_greet'); a.imm(0xC9, 0xFFFE); a.rel(0xF0, 'tp_talk')
    a.bra('tp_orig2')
    a.label('tp_orig'); a.b(0x68)
    a.label('tp_orig2'); a.b(0xA5, 0x14, 0x85, 0x00); a.b(0x6B)
    a.label('tp_greet')
    a.b(0xA5, 0x14, 0x85, 0x00); a.call80(0x80FA31); a.b(0x64, 0x02, 0x64, 0x04); a.call80(0x80FA76)
    a.imm(0xA2, 2 * tptr_index['greet']); a.lda_lx(0); a.fix.append(('long', len(a.code) - 3, 'tptr'))
    a.b(0x85, 0xCF); a.b(0xE2, 0x20); a.b(0xA9, CODE >> 16); a.b(0x85, 0xD1); a.b(0xC2, 0x20)
    a.b(0xA5, 0x14, 0x85, 0x00)
    ret = a.pc() + 1 + 3 + 3 + 1 + 4
    a.b(0x4B); a.b(0xF4); a.w(ret - 1); a.b(0xF4); a.w(RTL80 - 1); a.b(0x8B); a.b(0x5C); a.l(0x80FE44)
    assert a.pc() == ret
    a.bra('tp_exit')
    a.label('tp_talk')
    a.imm(0xA2, sid['talk']); a.b(0xA5, 0x26, 0x85, 0x00); a.call80(0x80C31A); a.call80(0x80C19A)
    a.label('tp_exit')
    a.b(0xE2, 0x20, 0x68, 0x68, 0x68, 0xC2, 0x20); a.b(0x5C); a.l(0x80918C)        # leave $809123 (its RTS)

    # ---- object maker: SP_* -> new object, X = object (negative: no slot) ----
    a.label('mkobj')
    a.lda_l(SP_X); a.b(0x85, 0x02); a.lda_l(SP_Y); a.b(0x85, 0x04); a.lda_l(SP_Z); a.b(0x85, 0x06)
    a.lda_l(SP_SPR); a.b(0x85, 0x00); a.lda_l(SP_SCR); a.b(0x85, 0x08)
    a.call80(0x80A7C2)
    a.b(0x8A); a.rel(0x10, 'mk_ok'); a.b(0x60)
    a.label('mk_ok'); a.b(0xA6, 0x00)
    a.lda_l(SP_TYPE); a.b(0x9D); a.w(0x1526)
    a.b(0xDA); a.b(0xAA); a.lda_lx(0x8DB031); a.b(0xFA); a.imm(0x29, 0xC0); a.b(0xEB, 0x0A); a.imm(0x69, 0)
    a.b(0x9D); a.w(0x141C)
    a.lda_l(SP_REC); a.b(0x9D); a.w(0x13C4)
    a.b(0x60)
    # ---- step object X aside from (SP_X, SP_Y) by 14: first side the wall test allows ----
    a.label('aside')
    for k, (dx, dy, test) in enumerate(((14, 0, 0x8080B2), (0, 14, 0x8081B4), (-14, 0, 0x808133), (0, -14, 0x808238))):
        a.lda_l(SP_X); a.b(0x0A, 0x0A, 0x18); a.imm(0x69, (dx * 4) & 0xFFFF); a.b(0x9D); a.w(0x0E44)
        a.lda_l(SP_Y); a.b(0x0A, 0x0A, 0x18); a.imm(0x69, (dy * 4) & 0xFFFF); a.b(0x9D); a.w(0x0E9C)
        a.b(0xDA); a.call80(test); a.b(0xFA)
        a.rel(0xB0, 'as_k%d' % k); a.imm(0xC9, 5); a.rel(0xB0, 'as_s%d' % k)
        a.label('as_k%d' % k); a.brl('as_ok')
        a.label('as_s%d' % k)
    a.lda_l(SP_X); a.b(0x0A, 0x0A); a.b(0x9D); a.w(0x0E44); a.lda_l(SP_Y); a.b(0x0A, 0x0A); a.b(0x9D); a.w(0x0E9C)
    a.label('as_ok')
    a.b(0xBD); a.w(0x0E44); a.b(0x18); a.b(0x7D); a.w(0x0E9C); a.b(0x4A); a.b(0x9D); a.w(0x0F4C)
    a.b(0x60)

    # ---- map load (JSL from $80A4DE, replaces JSR $A3F1 / JSL $819AE6) ----
    a.label('mapload')
    a.b(0x08, 0xC2, 0x30, 0x8B)
    a.call80(0x80A3F1)
    a.b(0xE2, 0x20); a.b(0xA9, 0); a.sta_l(0x7E0000 + GTALK); a.b(0xC2, 0x20)   # nobody is talking to our Glutman
    a.imm(0xA2, 0); a.imm(0xA0, SAVEDP & 0xFFFF); a.imm(0xA9, 63); a.b(0x54, SAVEDP >> 16, 0x7E)
    a.b(0xF4); a.w(0x8080); a.b(0xAB, 0xAB)
    a.lda_l(0x7E2DE2); a.b(0x0A, 0x0A, 0x0A, 0x18); a.adc_l(0x7E2DE2); a.b(0xAA); a.lda_lx(0x8D92AF)
    a.sta_l(SP_T1)                                               # map pointer of this location
    # a) Glutman back at The Cage once his story part is over
    a.imm(0xC9, GLUT_MAP); a.rel(0xD0, 'ml_b')
    a.lda_l(0x7E0000 + GLUT_REC + 3); a.imm(0xC9, 0x1538); a.rel(0xD0, 'ml_b')
    rec_init(REC_GLUT, 30)
    set_sp(SP_SPR, RW(0x8DB034 + GLUT_T)); set_sp(SP_SCR, sid['glut'])
    set_sp(SP_X, GLUT_POS[0]); set_sp(SP_Y, GLUT_POS[1]); set_sp(SP_Z, GLUT_POS[2])
    set_sp(SP_TYPE, GLUT_T); set_sp(SP_REC, REC_GLUT); a.jsr('mkobj')
    a.label('ml_b')
    # b) active job, its street: Glutman's man next to the entrance
    byte(STATE); a.imm(0xC9, 1); a.rel(0xF0, 'ml_b1'); a.brl('ml_c0')
    a.label('ml_b1')
    job_y(); ldj('smap'); a.cmp_l(SP_T1); a.rel(0xF0, 'ml_b2'); a.brl('ml_c0')
    a.label('ml_b2')
    ldj('room'); a.sta_l(0x7E0000 + GDEST)
    rec_init(REC_CONTACT, 30)
    ldj('cx'); a.sta_l(SP_X); ldj('cy'); a.sta_l(SP_Y); ldj('cz'); a.sta_l(SP_Z)
    set_sp(SP_SPR, RW(0x8DB034 + CONTACT_T)); set_sp(SP_SCR, sid['door']); set_sp(SP_TYPE, CONTACT_T)
    set_sp(SP_REC, REC_CONTACT); a.jsr('mkobj'); a.b(0x8A); a.rel(0x10, 'ml_cs'); a.brl('ml_c0')
    a.label('ml_cs')                                             # first listed spot the wall test accepts
    a.b(0x8A); a.sta_l(SP_OBJ)
    for i in range(4):
        job_y(); a.b(0xBB); a.lda_lx(F['s%d' % i]); a.fix.append(('long', len(a.code) - 3, 'jobs')); a.sta_l(SP_T2)
        a.lda_lx(F['s%d' % i] + 2); a.fix.append(('long', len(a.code) - 3, 'jobs')); a.b(0x48)
        a.lda_l(SP_OBJ); a.b(0xAA)
        a.lda_l(SP_T2); a.b(0x0A, 0x0A); a.b(0x9D); a.w(0x0E44)
        a.b(0x68); a.b(0x0A, 0x0A); a.b(0x9D); a.w(0x0E9C)
        a.call80(0x8080B2)
        a.rel(0xB0, 'ml_cok%d' % i); a.imm(0xC9, 5); a.rel(0xB0, 'ml_cno%d' % i)
        a.label('ml_cok%d' % i); a.brl('ml_cok')
        a.label('ml_cno%d' % i)
    a.lda_l(SP_OBJ); a.b(0xAA); a.jsr('aside'); a.brl('ml_c0')
    a.label('ml_cok')
    a.lda_l(SP_OBJ); a.b(0xAA)
    a.b(0xBD); a.w(0x0E44); a.b(0x18); a.b(0x7D); a.w(0x0E9C); a.b(0x4A); a.b(0x9D); a.w(0x0F4C)
    a.label('ml_c0')
    # c) arriving in the job's room
    byte(ARRIVE); a.imm(0xC9, 1); a.rel(0xF0, 'ml_c1'); a.brl('ml_d')
    a.label('ml_c1')
    a.imm(0xA9, 0); a.sta_l(0x7E0000 + ARRIVE)
    byte(STATE); a.b(0x3A); a.imm(0xC9, 2); a.rel(0x90, 'ml_c1b'); a.brl('ml_out')   # job active or done
    a.label('ml_c1b')
    job_y(); ldj('room'); a.cmp_l(0x7E2DE2); a.rel(0xD0, 'ml_cx')
    a.cmp_l(0x7E0000 + GDEST); a.rel(0xF0, 'ml_c2')                          # and we came through his door
    a.label('ml_cx'); a.brl('ml_out')
    a.label('ml_c2')
    ldj('sloc'); a.sta_l(0x7E0000 + GDEST)
    a.imm(0xA9, 0); a.fix.append(('abs', len(a.code) - 2, 'nozones')); a.sta_l(0x7E009D)   # no exits in here
    a.b(0xE2, 0x20); a.b(0xA9, CODE >> 16); a.sta_l(0x7E009F); a.b(0xC2, 0x20)
    rec_init(REC_TRIG, 30)
    ldj('rx'); a.sta_l(SP_X); ldj('ry'); a.sta_l(SP_Y); ldj('rz'); a.sta_l(SP_Z)
    set_sp(SP_SPR, RW(0x8DB034 + TRIG_T)); set_sp(SP_SCR, sid['exit']); set_sp(SP_TYPE, TRIG_T)
    set_sp(SP_REC, REC_TRIG); a.jsr('mkobj')
    byte(STATE); a.imm(0xC9, 1); a.rel(0xF0, 'ml_c3'); a.brl('ml_out')
    a.label('ml_c3')
    job_y()
    # boss (or, on a computer job, a normal guard) on the target spot
    a.imm(0xA9, 0); a.sta_l(0x7E0000 + REC_BOSS); ldj('bhp'); a.sta_l(0x7E0000 + REC_BOSS + 2)
    a.imm(0xA9, 0xFFFF); a.sta_l(0x7E0000 + REC_BOSS + 3)
    ldj('tx'); a.sta_l(SP_X); ldj('ty'); a.sta_l(SP_Y); ldj('tz'); a.sta_l(SP_Z)
    ldj('bspr'); a.sta_l(SP_SPR); ldj('bscr'); a.sta_l(SP_SCR); ldj('btype'); a.sta_l(SP_TYPE)
    set_sp(SP_REC, REC_BOSS); a.b(0x5A); a.jsr('mkobj'); a.b(0x7A)
    # escort guard
    a.imm(0xA9, 0); a.sta_l(0x7E0000 + REC_ESC1); ldj('ehp'); a.sta_l(0x7E0000 + REC_ESC1 + 2)
    a.imm(0xA9, 0xFFFF); a.sta_l(0x7E0000 + REC_ESC1 + 3)
    ldj('espr'); a.sta_l(SP_SPR); ldj('escr'); a.sta_l(SP_SCR); ldj('etype'); a.sta_l(SP_TYPE)
    set_sp(SP_REC, REC_ESC1); a.b(0x5A); a.jsr('mkobj'); a.b(0x7A)
    a.b(0x8A); a.rel(0x30, 'ml_f'); a.b(0x5A); a.jsr('aside'); a.b(0x7A)
    a.label('ml_f')
    # computer job: the trigger on the target spot
    ldj('kind'); a.rel(0xF0, 'ml_out')
    rec_init(REC_ESC2, 30)
    ldj('tx'); a.sta_l(SP_X); ldj('ty'); a.sta_l(SP_Y); ldj('tz'); a.sta_l(SP_Z)
    ldj('tspr'); a.sta_l(SP_SPR); set_sp(SP_SCR, sid['comp']); ldj('ttype'); a.sta_l(SP_TYPE)
    set_sp(SP_REC, REC_ESC2); a.jsr('mkobj')
    a.bra('ml_out')
    a.label('ml_d')
    byte(ARRIVE); a.imm(0xC9, 2); a.rel(0xD0, 'ml_out')
    a.imm(0xA9, 0); a.sta_l(0x7E0000 + ARRIVE)
    a.label('ml_out')
    a.imm(0xA2, SAVEDP & 0xFFFF); a.imm(0xA0, 0); a.imm(0xA9, 63); a.b(0x54, 0x7E, SAVEDP >> 16)
    a.b(0xAB, 0x28)
    a.b(0x22); a.l(0x819AE6)
    a.b(0x6B)

    # ---- sleeping: a paid job opens the next one ----
    a.label('jobsleep')
    a.b(0x08, 0xE2, 0x20)
    a.lda_l(0x7E0000 + STATE); a.b(0xC9, 3); a.rel(0xD0, 'js_out'); a.b(0xA9, 0); a.sta_l(0x7E0000 + STATE)
    a.label('js_out'); a.b(0x28, 0x60)

    a.label('nozones'); a.b(0, 0)
    a.label('jobs'); a.b(*job_table(RW, RB))
