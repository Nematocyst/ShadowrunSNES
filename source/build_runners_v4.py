"""Build "Shadowrun: Persistent Runners" (stage 1).

  python3 build_runners.py CLEAN_ROM OUT_PREFIX [--on TOP_OF.sfc]

Stage 1:
  * Runners never time out (the per-map stay countdown at file $0596 is disabled). Death still dismisses them
    (vanilla behaviour: full heal, 'hired' flag cleared, they return to their map spawn).
  * Each runner's 18-byte stat block lives in a RAM table at $7F9818 instead of ROM, so it can change later
    (stage 2: per-runner karma). Layout: $7F9818 signature 'RT', $7F981A 12 x 18 stat blocks (index order of
    $809683), $7F98F2 12 x 2 karma counters.  242 bytes.
  * New game fills the table from the original ROM stats. Save/load copy it into each SRAM slot's spare bytes
    (slot + $F04). Loading a save without the signature (any older save) rebuilds the table from ROM.
  * New code lives in bank $BF (file $1F8000); the ROM is expanded to 2 MB (pad $00), same convention as
    RetchERezzed's Expanded Dialogue so the two coexist.
"""
import sys, zlib

# ---------------------------------------------------------------- tiny 65816 assembler (only what we need)
class Asm:
    def __init__(self, org): self.org = org; self.code = []; self.labels = {}; self.fix = []
    def pc(self): return self.org + len(self.code)
    def label(self, n): self.labels[n] = self.pc()
    def b(self, *bs): self.code += list(bs)
    def w(self, v): self.code += [v & 0xFF, (v >> 8) & 0xFF]
    def l(self, v): self.code += [v & 0xFF, (v >> 8) & 0xFF, (v >> 16) & 0xFF]
    def rel(self, op, lab): self.b(op, 0); self.fix.append(('rel', len(self.code) - 1, lab))
    def jsr(self, lab): self.b(0x20, 0, 0); self.fix.append(('abs', len(self.code) - 2, lab))
    def bra(self, lab): self.rel(0x80, lab)
    def brl(self, lab): self.b(0x82, 0, 0); self.fix.append(('rel16', len(self.code) - 2, lab))
    def call80(self, routine):
        # call a bank-$80 RTS routine from bank $BF: RTS lands on the RTL at $80F261, RTL returns here
        ret = self.pc() + 1 + 3 + 3 + 4
        self.b(0x4B); self.b(0xF4); self.w(ret - 1); self.b(0xF4); self.w(RTL80 - 1); self.b(0x5C); self.l(routine)
        assert self.pc() == ret
    def lda_l(self, a): self.b(0xAF); self.l(a)
    def sta_l(self, a): self.b(0x8F); self.l(a)
    def lda_lx(self, a): self.b(0xBF); self.l(a)
    def sta_lx(self, a): self.b(0x9F); self.l(a)
    def adc_l(self, a): self.b(0x6F); self.l(a)
    def cmp_l(self, a): self.b(0xCF); self.l(a)
    def imm(self, op, v): self.b(op); self.w(v)
    def done(self):
        for kind, at, lab in self.fix:
            t = self.labels[lab]
            if kind == 'rel':
                d = t - (self.org + at + 1); assert -128 <= d < 128, lab; self.code[at] = d & 0xFF
            elif kind == 'rel16':
                d = (t - (self.org + at + 2)) & 0xFFFF; self.code[at] = d & 0xFF; self.code[at + 1] = d >> 8
            elif kind == 'long':
                base = self.code[at] | self.code[at + 1] << 8 | self.code[at + 2] << 16; v = t + base
                self.code[at:at + 3] = [v & 0xFF, (v >> 8) & 0xFF, (v >> 16) & 0xFF]
            else:
                self.code[at] = t & 0xFF; self.code[at + 1] = (t >> 8) & 0xFF
        return bytes(self.code)

def lorom(addr): return ((addr & 0x7F0000) >> 1) | (addr & 0x7FFF)

TABLE = 0x7F9818; SIG = 0x5452            # 'RT'  = save format 1 (stages 1-3, 242 bytes)
SIG2 = 0x3252                              # 'R2'  = save format 2 (adds runner cyberware masks, 246 bytes)
STATS = TABLE + 2; KARMA = STATS + 12 * 18; TABLE_LEN1 = 2 + 12 * 18 + 12 * 2   # 242
DERM = KARMA + 24; WIRED = DERM + 2        # $7F990A / $7F990C: bit idx set = runner has dermal armor / wired reflexes
TABLE_LEN = TABLE_LEN1 + 4                 # 246 (slot + $F04 .. + $FF9, within the 250 spare bytes)
# cyberware shelf objects at the street doc (record = $8DB032+type): owner $1538 = bought/removed from the shelf
CYB_DERM, CYB_WIRED = 0x15C4, 0x192F
CYB_REC = {CYB_DERM: 0x335A, CYB_WIRED: 0x335F}
ROM_PTR = [0x9794, 0x9812, 0x97B8, 0x97CA, 0x97DC, 0x97EE, 0x9800, 0x97A6, 0x9824, 0x9836, 0x9848, 0x985A]  # idx 1..12 (bank $80)
NAMES = ['Spatter', 'Jetboy', 'Norbert', 'Frogtongue', 'Anders', 'Akimi', 'Kitsune', 'Steelflight', 'Jangadance',
         'Hamfist', 'Orifice', 'Dances With Clams']
CODE = 0xBF8000
RTL80 = 0x80F261
# stage 2 work variables (bank $7F, after the saved table, inside the free region)
SEL, BASE, OBJ, WIN, NCNT, TMP, KOFF = 0x7F9910, 0x7F9912, 0x7F9916, 0x7F9918, 0x7F991A, 0x7F991C, 0x7F991E
LIST, MAP, OBJS = 0x7F9920, 0x7F9930, 0x7F9940
KARMA_X = KARMA - 2            # karma of idx i (1..12) at KARMA_X + 2*i
# copy equipping work variables
CP_DP, CP_IDX2, CP_KIND, CP_REQ, CP_S1, CP_S3, CP_TYPE = 0x7F9950, 0x7F9952, 0x7F9954, 0x7F9956, 0x7F9958, 0x7F995A, 0x7F995C
# runner cyberware work variables
DOC_DP, DOC_KIND, DOC_PRICE, DOC_WHO, DOC_OBJ = 0x7F9960, 0x7F9962, 0x7F9964, 0x7F9966, 0x7F9968
TMPA, TMPB, TMPO = 0x7F996A, 0x7F996C, 0x7F996E
DOC_CODE = 0x9EF51B          # code start of the doc's purchase script $02CC
DOC_RESUME = 0x0076          # script offset of 'jz' at F7591: with result 0 it returns to the item's wait loop
RUNNER_AI = (0xAF8E, 0xB19F, 0xB424)   # bank $9F code starts of runner AI scripts $01AD, $0328, $01E9
# Where each shop item's price lives: SNES address of the 16-bit price operand in its shop-case call (script $028C).
# Read at runtime, so price-changing patches (e.g. Rebalanced) are honoured automatically.
SHOP_PRICE_AT = {0x013B: 0x9CDF98, 0x0150: 0x9CDF50, 0x0157: 0x9FCE79, 0x01A4: 0x9FCE9D, 0x0261: 0x9CDF74,
                 0x0276: 0x9FCE8B, 0x032C: 0x9CDDB8, 0x0658: 0x9CDD92, 0x0770: 0x9FCEF7, 0x0850: 0x9CDF62,
                 0x0BF3: 0x9FCEAF, 0x129F: 0x9FCF09, 0x12F3: 0x9CDF86, 0x1696: 0x9FCEE5, 0x17C3: 0x9CDF3E,
                 0x18A3: 0x9FCED3, 0x1944: 0x9CDDA5, 0x1B5F: 0x9FCF1B}
FALLBACK_PRICE = 5000                       # weapons sold nowhere
# armor sold nowhere (or a different object of a shop item, e.g. a second Mesh Jacket): price by protection 0..9+
# anchored on shop prices: Mesh Jacket (2) 5,000 ... Full Bodysuit (8) 30,000
ARMOR_PRICE_BY_PROTECTION = [1000, 2500, 5000, 8000, 12000, 15000, 20000, 25000, 30000, 40000]

def build_code():
    a = Asm(CODE)
    # --- SaveHook (JSL from $81B141; A/X/Y 16-bit, Y = SRAM slot offset) ---
    a.label('save')
    a.b(0xA2); a.w(0x2DE0); a.b(0xA9); a.w(0x0F03); a.b(0x54, 0x70, 0x7E)          # original block copy -> Y = slot+$F04
    a.b(0xA2); a.w(TABLE & 0xFFFF); a.b(0xA9); a.w(TABLE_LEN - 1); a.b(0x54, 0x70, 0x7F)  # runner table -> SRAM
    a.b(0x6B)
    # --- LoadHook (JSL from $81B15B; X = SRAM slot offset) ---
    a.label('load')
    a.b(0xA0); a.w(0x2DE0); a.b(0xA9); a.w(0x0F03); a.b(0x54, 0x7E, 0x70)          # original copy -> X = slot+$F04
    a.b(0xBF); a.l(0x700000)                                                        # lda $700000,X (signature)
    a.b(0xC9); a.w(SIG2); a.rel(0xF0, 'load_v2')
    a.b(0xC9); a.w(SIG); a.rel(0xF0, 'load_v1')
    a.jsr('init'); a.bra('restock')                                                 # no table: build from ROM
    a.label('load_v2')
    a.b(0xA0); a.w(TABLE & 0xFFFF); a.b(0xA9); a.w(TABLE_LEN - 1); a.b(0x54, 0x7F, 0x70); a.bra('restock')
    a.label('load_v1')                                                              # upgrade a format-1 save
    a.b(0xA0); a.w(TABLE & 0xFFFF); a.b(0xA9); a.w(TABLE_LEN1 - 1); a.b(0x54, 0x7F, 0x70)
    a.imm(0xA9, 0); a.sta_l(DERM); a.sta_l(WIRED); a.imm(0xA9, SIG2); a.sta_l(TABLE)
    # put cyberware Jake bought before this patch back on the doc's shelf (so runners can buy it too)
    a.label('restock')
    for t, rec in CYB_REC.items():
        a.lda_l(0x7E0000 + rec + 3); a.imm(0xC9, 0x1538); a.rel(0xD0, 'rs_%X' % t)
        a.imm(0xA9, 0xFFFF); a.sta_l(0x7E0000 + rec + 3)
        a.label('rs_%X' % t)
    a.b(0x6B)
    # --- NewGameHook (JSL from $809915, replaces LDA #$716C / STA $7E3C15) ---
    a.label('newgame')
    a.b(0xA9); a.w(0x716C); a.b(0x8F); a.l(0x7E3C15)
    a.b(0x08, 0x8B, 0xC2, 0x30); a.jsr('init'); a.b(0xAB, 0x28, 0x6B)
    # --- InitTable: copy the 12 ROM stat blocks, write signature, zero karma (A/X/Y 16-bit) ---
    a.label('init')
    for i, src in enumerate(ROM_PTR):
        a.b(0xA2); a.w(src); a.b(0xA0); a.w((STATS + 18 * i) & 0xFFFF); a.b(0xA9); a.w(17); a.b(0x54, 0x7F, 0x80)
    a.b(0xA9); a.w(SIG2); a.b(0x8F); a.l(TABLE)
    a.b(0xA2); a.w(26); a.b(0xA9); a.w(0)                                          # zero karma + cyber masks
    a.label('kz'); a.b(0x9F); a.l(KARMA); a.b(0xCA, 0xCA); a.rel(0x10, 'kz')
    a.b(0x60)

    # ================================================================ STAGE 2
    # All hook sites run with A/X/Y 16-bit, D = 0 and DB = $80 (so $9683/$9705/$1FC4 are readable absolute).
    # --- KarmaGain: native #7B replacement (JSL from $80CD82, followed by RTS). $00 = amount (karma x8 units) ---
    a.label('kgain')
    a.b(0x18); a.lda_l(0x7E3C11); a.b(0x65, 0x00); a.sta_l(0x7E3C11)          # Jake, as vanilla
    a.b(0xDA, 0x5A)                                                          # phx, phy
    a.lda_l(0x7E2DE6); a.rel(0x30, 'kg_done'); a.b(0xAA)                     # X = last party slot offset
    a.label('kg_slot'); a.b(0xE0); a.w(0); a.rel(0xF0, 'kg_done')            # slot 0 = Jake -> stop
    a.lda_lx(0x7E2DF0); a.imm(0xA0, 0x18)                                    # type of member, Y = $18
    a.label('kg_find'); a.b(0xD9); a.w(0x9683); a.rel(0xF0, 'kg_found'); a.b(0x88, 0x88); a.rel(0x10, 'kg_find'); a.bra('kg_next')
    a.label('kg_found'); a.imm(0xC0, 0); a.rel(0xF0, 'kg_next')              # never touch idx 0
    a.b(0xDA, 0xBB)                                                          # phx; tyx (X = idx*2)
    a.lda_lx(KARMA_X); a.b(0x18, 0x65, 0x00); a.rel(0x90, 'kg_nc'); a.imm(0xA9, 0xFFFF)
    a.label('kg_nc'); a.sta_lx(KARMA_X); a.b(0xFA)                           # plx
    a.label('kg_next'); a.b(0xCA, 0xCA); a.bra('kg_slot')
    a.label('kg_done'); a.b(0x7A, 0xFA, 0x6B)                               # ply, plx, rtl

    # --- Pick: "Use karma" -> who? list (JSL from $80CE8D; never returns: ends with JML $80CE3D like the old BRA) ---
    a.label('pick')
    a.imm(0xA9, 0x70C8); a.sta_l(LIST)                                       # "Exit"
    a.imm(0xA9, 0x7534); a.sta_l(LIST + 2)                                   # "Jake"
    a.imm(0xA9, 0); a.sta_l(MAP + 2); a.sta_l(OBJS + 2)
    a.imm(0xA9, 4); a.sta_l(KOFF)
    a.imm(0xA2, 2)
    a.label('pk_loop'); a.b(0x8A, 0x38); a.b(0xEF); a.l(0x7E2DE6)            # txa; sec; sbc last
    a.rel(0xF0, 'pk_in'); a.rel(0xB0, 'pk_end')
    a.label('pk_in'); a.lda_lx(0x7E2DF0); a.imm(0xA0, 0x18)
    a.label('pk_find'); a.b(0xD9); a.w(0x9683); a.rel(0xF0, 'pk_found'); a.b(0x88, 0x88); a.rel(0x10, 'pk_find'); a.bra('pk_next')
    a.label('pk_found'); a.imm(0xC0, 0); a.rel(0xF0, 'pk_next')
    a.b(0xDA); a.b(0xBD); a.w(0x1FC4); a.b(0x48)                             # phx; lda $1FC4,X (object); pha
    a.b(0x98, 0x48)                                                          # tya; pha (idx*2)
    a.lda_l(KOFF); a.b(0xAA)                                                 # X = list offset
    a.b(0x68); a.sta_lx(MAP); a.b(0xA8); a.b(0xB9); a.w(0x9705); a.sta_lx(LIST)   # map, name text id
    a.b(0x68); a.sta_lx(OBJS)
    a.b(0xE8, 0xE8, 0x8A); a.sta_l(KOFF); a.b(0xFA)                          # K += 2; plx
    a.label('pk_next'); a.b(0xE8, 0xE8); a.bra('pk_loop')
    a.label('pk_end'); a.lda_l(KOFF); a.b(0x4A); a.sta_l(NCNT)               # count = K/2
    a.imm(0xA9, 2); a.b(0x85, 0x00); a.imm(0xA9, 0x11); a.b(0x85, 0x02)       # window x=2 y=17
    a.imm(0xA9, 0x15); a.b(0x85, 0x04); a.lda_l(NCNT); a.b(0x18); a.imm(0x69, 2); a.b(0x85, 0x06)
    a.b(0x64, 0x08); a.call80(0x80F92D); a.b(0xA5, 0x00); a.sta_l(WIN)
    a.label('pk_menu')
    a.lda_l(WIN); a.b(0x85, 0x00); a.call80(0x80FA31)
    a.imm(0xA9, 1); a.b(0x85, 0x02); a.b(0x64, 0x04); a.lda_l(NCNT); a.b(0x85, 0x06)
    a.imm(0xA9, LIST & 0xFFFF); a.b(0x85, 0x08); a.imm(0xA9, LIST >> 16); a.b(0x85, 0x0A)
    a.call80(0x80A654)
    a.b(0xA5, 0x00); a.rel(0xF0, 'pk_exit'); a.rel(0x30, 'pk_exit')
    a.b(0x0A, 0xAA)                                                          # X = 2k
    a.lda_lx(OBJS); a.sta_l(OBJ)
    a.lda_lx(MAP); a.b(0x4A); a.sta_l(SEL); a.rel(0xF0, 'pk_run')           # SEL = idx (0 = Jake)
    a.b(0x3A, 0x0A); a.sta_l(TMP); a.b(0x0A, 0x0A, 0x0A); a.b(0x18); a.adc_l(TMP)   # (idx-1)*18
    a.b(0x18); a.imm(0x69, STATS & 0xFFFF); a.sta_l(BASE)
    a.label('pk_run'); a.call80(0x80EE21); a.bra('pk_menu')
    a.label('pk_exit')
    a.lda_l(WIN); a.b(0x85, 0x00); a.call80(0x80FA08)
    a.imm(0xA9, 0); a.sta_l(SEL)
    a.b(0xE2, 0x20, 0x68, 0x68, 0x68, 0xC2, 0x20)                            # drop the JSL return address
    a.b(0x5C); a.l(0x80CE3D)                                                 # back to the rest menu

    # --- SetF9: karma screen stat pointer for the selected character (JSL from $80EE27) ---
    a.label('setf9')
    a.b(0xDA); a.lda_l(SEL); a.b(0x0A, 0xAA)
    a.lda_lx(0x80969D); a.b(0x85, 0xF9); a.b(0xE2, 0x20); a.lda_lx(0x8096B7); a.b(0x85, 0xFB); a.b(0xC2, 0x20)
    a.b(0xFA, 0x6B)
    # --- GetKarma / SetKarma (JSL from $80EF6D, $80EFDB / $80F010) ---
    a.label('kget')
    a.b(0x08)                                                                # php: caller's SEC must survive
    a.lda_l(SEL); a.rel(0xD0, 'kget_r'); a.lda_l(0x7E3C11); a.b(0x28, 0x6B)
    a.label('kget_r'); a.b(0xDA, 0x0A, 0xAA); a.lda_lx(KARMA_X); a.b(0xFA, 0x28, 0x6B)
    a.label('kset')
    a.b(0xDA, 0x48); a.lda_l(SEL); a.rel(0xF0, 'kset_j')
    a.b(0x0A, 0xAA, 0x68); a.sta_lx(KARMA_X); a.b(0xFA, 0x6B)
    a.label('kset_j'); a.b(0x68); a.sta_l(0x7E3C11); a.b(0xFA, 0x6B)
    # --- stat address for the karma menus (JSL from the six "LDA table,X / STA $0E" sites) ---
    for name, table in (('adr_attr', 0x80EF7C), ('adr_skill', 0x80EF94), ('adr_magic', 0x80EFAC)):
        a.label(name); a.lda_lx(table); a.bra('adr_common')
    a.label('adr_common')
    a.b(0x48); a.lda_l(SEL); a.rel(0xF0, 'adr_j')
    a.b(0x68, 0x38); a.imm(0xE9, 0x3BFB); a.b(0x18); a.adc_l(BASE); a.b(0x85, 0x0E)
    a.imm(0xA9, 0x007F); a.b(0x85, 0x10); a.b(0x6B)
    a.label('adr_j'); a.b(0x68, 0x85, 0x0E); a.imm(0xA9, 0x007E); a.b(0x85, 0x10); a.b(0x6B)
    # --- Body side effect (JSL from $80F155; caller then does BNE: Z=1 -> run Jake's vanilla +10 stamina) ---
    a.label('body')
    a.lda_l(SEL); a.rel(0xD0, 'body_r'); a.b(0xA5, 0x0E); a.imm(0xC9, 0x3BFB); a.b(0x6B)
    a.label('body_r'); a.b(0xA5, 0x0E); a.cmp_l(BASE); a.rel(0xD0, 'body_no')
    a.b(0xDA); a.lda_l(BASE); a.b(0xAA); a.b(0xE2, 0x20)
    a.lda_lx(0x7F0005); a.b(0x18); a.b(0x69, 0x0A); a.rel(0x90, 'body_m'); a.b(0xA9, 0xFF)
    a.label('body_m'); a.sta_lx(0x7F0005); a.sta_l(TMP)                      # new max stamina
    a.b(0xC2, 0x20); a.lda_l(OBJ); a.b(0xAA); a.lda_lx(0x7E13C4); a.b(0xAA)    # X = object record
    a.b(0xE2, 0x20); a.lda_lx(0x7E0002); a.b(0x18); a.b(0x69, 0x0A); a.rel(0xB0, 'body_cap')
    a.cmp_l(TMP); a.rel(0x90, 'body_hp')
    a.label('body_cap'); a.lda_l(TMP)
    a.label('body_hp'); a.sta_lx(0x7E0002); a.b(0xC2, 0x20); a.b(0xFA)
    a.label('body_no'); a.imm(0xA9, 1); a.b(0x6B)                           # Z = 0 -> skip Jake's path

    # ================================================================ COPY EQUIPPING
    # Native #CD (stub at $80CD87 -> JSL here). Replaces native #75 (give) in the armor ($0320) and weapon ($0011)
    # scripts. In: $00 = item object, $02 = target TYPE. Jake's armor/weapon given to a party runner: check Strength,
    # pay the item's price, write the runner's gear record; Jake keeps the item. Otherwise: vanilla give ($809C98).
    a.label('cpgive'); a.bra('cp_go')
    a.label('cp_van'); a.call80(0x809C98); a.b(0x6B)                          # vanilla give
    a.label('cp_go')
    a.b(0xA5, 0x02); a.imm(0xC9, 0x08B2); a.rel(0xF0, 'cp_van')               # giving to Jake -> vanilla
    a.b(0xA4, 0x00); a.b(0xBE); a.w(0x13C4); a.lda_lx(0x7E0003)               # item record owner
    a.imm(0xC9, 0x08B2); a.rel(0xD0, 'cp_van')                                # not Jake's item -> vanilla
    a.b(0xA5, 0x02); a.imm(0xA0, 0x18)
    a.label('cp_tf'); a.b(0xD9); a.w(0x9683); a.rel(0xF0, 'cp_tfound'); a.b(0x88, 0x88); a.rel(0x10, 'cp_tf'); a.brl('cp_van')
    a.label('cp_tfound'); a.imm(0xC0, 0); a.rel(0xF0, 'cp_van')
    a.b(0x98); a.sta_l(CP_IDX2)                                               # idx*2
    a.b(0xAE); a.w(0x026C); a.b(0xBD); a.w(0x026E); a.sta_l(CP_DP)            # thread direct page
    a.b(0xAA); a.lda_lx(0x7E0000)                                             # script base of the caller
    a.imm(0xC9, 0xAD7B); a.rel(0xF0, 'cp_armor')
    a.imm(0xC9, 0xF779); a.rel(0xF0, 'cp_weapon')
    a.brl('cp_van')
    a.label('cp_armor'); a.imm(0xA9, 0); a.sta_l(CP_KIND)
    a.lda_lx(0x7E0016); a.b(0x29); a.w(0xFF); a.sta_l(CP_REQ)                  # requirement = local 3
    a.lda_lx(0x7E0014); a.b(0x29); a.w(0xFF); a.sta_l(CP_S1)                   # protection = local 1
    a.bra('cp_common')
    a.label('cp_weapon'); a.imm(0xA9, 1); a.sta_l(CP_KIND)
    a.lda_lx(0x7E0017); a.b(0x29); a.w(0xFF); a.sta_l(CP_REQ)                  # requirement = local 4
    a.lda_lx(0x7E0014); a.sta_l(CP_S1)                                         # locals 1,2 (s1, s2)
    a.lda_lx(0x7E0016); a.b(0x29); a.w(0xFF); a.sta_l(CP_S3)                   # local 3 (s3)
    a.label('cp_common')
    a.b(0xA4, 0x00); a.b(0xB9); a.w(0x1526); a.sta_l(CP_TYPE)                 # item type
    # Strength check: runner block = STATS + 18*(idx-1)
    a.lda_l(CP_IDX2); a.b(0x3A, 0x3A); a.sta_l(TMP); a.b(0x0A, 0x0A, 0x0A); a.b(0x18); a.adc_l(TMP)  # (2idx-2)*9 = 18(idx-1)
    a.b(0x18); a.imm(0x69, STATS & 0xFFFF); a.b(0xAA)
    a.lda_lx(0x7F0002); a.b(0x29); a.w(0xFF); a.cmp_l(CP_REQ); a.rel(0xB0, 'cp_strong')
    for k, v in ((0x00, 2), (0x02, 21), (0x04, 15), (0x06, 3), (0x08, 0x0800), (0x0A, 20), (0x0C, 240)):
        a.imm(0xA9, v); a.b(0x85, k)
    a.call80(0x80FE8B); a.brl('cp_skip')                                      # "not strong enough"
    a.label('cp_strong')
    # price lookup (table of type,price words; 0-terminated); fallback FALLBACK_PRICE
    a.imm(0xA2, 0)
    a.label('cp_pl'); a.lda_lx(0); a.fix.append(('long', len(a.code) - 3, 'prices'))
    a.rel(0xF0, 'cp_pdef'); a.cmp_l(CP_TYPE); a.rel(0xF0, 'cp_pfound'); a.b(0xE8, 0xE8, 0xE8, 0xE8, 0xE8, 0xE8); a.bra('cp_pl')
    a.label('cp_pfound')                                                      # price = word at the stored ROM address
    a.lda_lx(2); a.fix.append(('long', len(a.code) - 3, 'prices')); a.b(0x85, 0x04)
    a.lda_lx(4); a.fix.append(('long', len(a.code) - 3, 'prices')); a.b(0x85, 0x06)
    a.b(0xA7, 0x04); a.bra('cp_pay')                                           # lda [$04]
    a.label('cp_pdef'); a.lda_l(CP_KIND); a.rel(0xD0, 'cp_pdw')               # armor: price by protection
    a.lda_l(CP_S1); a.imm(0xC9, 9); a.rel(0x90, 'cp_pdi'); a.imm(0xA9, 9)
    a.label('cp_pdi'); a.b(0x0A, 0xAA); a.lda_lx(0); a.fix.append(('long', len(a.code) - 3, 'armor_prices')); a.bra('cp_pay')
    a.label('cp_pdw'); a.imm(0xA9, FALLBACK_PRICE)
    a.label('cp_pay'); a.b(0x85, 0x00); a.call80(0x80CCF0)                     # native #BE pay
    a.b(0xA5, 0x00); a.rel(0xD0, 'cp_paid')
    for k, v in ((0x00, 6), (0x02, 6), (0x04, 16), (0x06, 3), (0x08, 0x0400), (0x0A, 2), (0x0C, 240)):
        a.imm(0xA9, v); a.b(0x85, k)
    a.call80(0x80FE8B); a.brl('cp_skip')                                      # "not enough money"
    a.label('cp_paid')
    a.lda_l(CP_IDX2); a.b(0x0A, 0x0A); a.b(0xAA)                              # X = idx*8 (gear record)
    a.lda_l(CP_KIND); a.rel(0xD0, 'cp_wrec')
    a.lda_l(CP_TYPE); a.sta_lx(0x7E3C2E); a.b(0xE2, 0x20); a.lda_l(CP_S1); a.sta_lx(0x7E3C30); a.b(0xC2, 0x20)
    # live armor value of the runner's object ($7E43D4,obj) if in the party: protection (+2 with dermal armor)
    a.lda_l(CP_S1); a.sta_l(TMPA)
    a.lda_l(CP_IDX2); a.b(0xAA); a.lda_l(DERM); a.b(0x3F); a.l(0); a.fix.append(('long', len(a.code) - 3, 'bits'))
    a.rel(0xF0, 'cp_nod'); a.lda_l(TMPA); a.b(0x18); a.imm(0x69, 2); a.sta_l(TMPA)
    a.label('cp_nod')
    a.lda_l(0x7E2DE6); a.b(0xAA)
    a.label('cp_ls'); a.lda_lx(0x7E2DF0); a.b(0xC5, 0x02); a.rel(0xF0, 'cp_lsf'); a.b(0xCA, 0xCA); a.rel(0x10, 'cp_ls'); a.b(0x6B)
    a.label('cp_lsf'); a.b(0xBD); a.w(0x1FC4); a.b(0xAA); a.lda_l(TMPA); a.sta_lx(0x7E43D4); a.b(0x6B)
    a.label('cp_wrec')
    a.lda_l(CP_TYPE); a.sta_lx(0x7E3C31); a.lda_l(CP_S1); a.sta_lx(0x7E3C33)  # s1,s2 (word)
    a.b(0xE2, 0x20); a.lda_l(CP_S3); a.sta_lx(0x7E3C35); a.b(0xC2, 0x20); a.b(0x6B)
    a.label('cp_skip')                                                         # resume the script at its end
    a.lda_l(CP_DP); a.b(0xAA); a.lda_l(CP_KIND); a.rel(0xD0, 'cp_skw')
    a.imm(0xA9, 0x00F8); a.sta_lx(0x7E0003); a.b(0x6B)
    a.label('cp_skw'); a.imm(0xA9, 0x0100); a.sta_lx(0x7E0003); a.b(0x6B)

    # ================================================================ RUNNER CYBERWARE
    # helper: A = object type -> X = idx*2 (0 = Jake, negative = not a runner/Jake). Uses X only.
    a.label('t2i'); a.imm(0xA2, 0x18)
    a.label('t2i_l'); a.b(0xDF); a.l(0x809683); a.rel(0xF0, 't2i_f'); a.b(0xCA, 0xCA); a.rel(0x10, 't2i_l')
    a.label('t2i_f'); a.b(0x60)
    # --- Dermal armor at map load (JSL from $80A32C, non-Jake party member; X = Y = object) ---
    a.label('derm_spawn')
    a.lda_lx(0x7E1474); a.imm(0x09, 0x0003); a.sta_lx(0x7E1474)              # original: $1474,X |= 3
    a.b(0xDA, 0x5A); a.b(0x8A); a.sta_l(TMPO)
    a.lda_lx(0x7E1526); a.jsr('t2i'); a.imm(0xE0, 0); a.rel(0xF0, 'ds_out'); a.rel(0x30, 'ds_out')
    a.lda_l(DERM); a.b(0x3F); a.l(0); a.fix.append(('long', len(a.code) - 3, 'bits')); a.rel(0xF0, 'ds_out')
    a.lda_l(TMPO); a.b(0xAA); a.lda_lx(0x7E43D4); a.b(0x18); a.imm(0x69, 2); a.sta_lx(0x7E43D4)
    a.label('ds_out'); a.b(0x7A, 0xFA, 0x6B)
    # --- Status screen armor value (JSL from $80E9CA, then BRA $80E9E9). X = idx*8. Returns A, keeps X ---
    a.label('st_armor')
    a.lda_lx(0x7E3C30); a.b(0x29); a.w(0xFF); a.sta_l(TMPA)
    a.imm(0xE0, 0); a.rel(0xD0, 'sa_run')
    a.lda_l(0x7E1F78); a.cmp_l(0x7E0CDE); a.rel(0xD0, 'sa_ret')               # vanilla: Jake's own screen only
    a.lda_l(0x7E3C18); a.b(0x29); a.w(0xFF); a.rel(0xF0, 'sa_ret'); a.bra('sa_plus')
    a.label('sa_run'); a.b(0xDA, 0x8A, 0x4A, 0x4A, 0xAA)
    a.lda_l(DERM); a.b(0x3F); a.l(0); a.fix.append(('long', len(a.code) - 3, 'bits')); a.sta_l(TMPB); a.b(0xFA)
    a.lda_l(TMPB); a.rel(0xF0, 'sa_ret')
    a.label('sa_plus'); a.lda_l(TMPA); a.b(0x18); a.imm(0x69, 2); a.b(0x6B)
    a.label('sa_ret'); a.lda_l(TMPA); a.b(0x6B)
    # --- Wired reflexes: runner AI waits (JSL from $80C3D1 = start of native #9E; must return X=$026C, A=$00) ---
    a.label('wired')
    a.b(0xA5, 0x02); a.imm(0xC9, 20); a.rel(0x90, 'wr_out')                   # only waits of 20+ frames
    a.lda_l(0x7E026C); a.b(0xAA); a.lda_lx(0x7E026E); a.b(0xAA)               # X = thread DP
    a.lda_lx(0x7E0002); a.b(0x29); a.w(0xFF); a.imm(0xC9, 0x9F); a.rel(0xD0, 'wr_out')
    a.lda_lx(0x7E0000)
    for i, c in enumerate(RUNNER_AI):
        a.imm(0xC9, c); a.rel(0xF0, 'wr_ai')
    a.bra('wr_out')
    a.label('wr_ai'); a.lda_lx(0x7E0013); a.b(0x29); a.w(0xFF); a.b(0xAA)    # thread's object
    a.lda_lx(0x7E1526); a.jsr('t2i'); a.imm(0xE0, 0); a.rel(0xF0, 'wr_out'); a.rel(0x30, 'wr_out')
    a.lda_l(WIRED); a.b(0x3F); a.l(0); a.fix.append(('long', len(a.code) - 3, 'bits')); a.rel(0xF0, 'wr_out')
    a.b(0xA5, 0x02); a.imm(0xA2, 0)                                           # frames - frames/3
    a.label('wr_div'); a.b(0x38); a.imm(0xE9, 3); a.rel(0x90, 'wr_dd'); a.b(0xE8); a.bra('wr_div')
    a.label('wr_dd'); a.b(0x8A); a.sta_l(TMPA); a.b(0xA5, 0x02, 0x38); a.b(0xEF); a.l(TMPA); a.b(0x85, 0x02)
    a.label('wr_out'); a.lda_l(0x7E026C); a.b(0xAA); a.b(0xA5, 0x00); a.b(0x6B)
    # --- Street doc: who gets the cyberware? (JSL from $80CCF0 = start of native #BE 'pay') ---
    a.label('docpay')
    a.lda_l(0x7E026C); a.b(0xAA); a.lda_lx(0x7E026E); a.sta_l(DOC_DP); a.b(0xAA)
    a.lda_lx(0x7E0002); a.b(0x29); a.w(0xFF); a.imm(0xC9, DOC_CODE >> 16); a.rel(0xD0, 'dp_van')
    a.lda_lx(0x7E0000); a.imm(0xC9, DOC_CODE & 0xFFFF); a.rel(0xD0, 'dp_van')
    a.lda_lx(0x7E001B)                                                         # item type (local 8)
    a.imm(0xC9, CYB_DERM); a.rel(0xF0, 'dp_derm'); a.imm(0xC9, CYB_WIRED); a.rel(0xF0, 'dp_wired')
    a.label('dp_van'); a.b(0x38); a.lda_l(0x7E3C0D); a.b(0x6B)               # vanilla: SEC; LDA nuyen
    a.label('dp_derm'); a.imm(0xA9, 0); a.bra('dp_go')
    a.label('dp_wired'); a.imm(0xA9, 2)
    a.label('dp_go'); a.sta_l(DOC_KIND); a.b(0xA5, 0x00); a.sta_l(DOC_PRICE)
    # list: Exit, Jake (if he lacks it), party runners lacking it
    a.imm(0xA9, 0x70C8); a.sta_l(LIST); a.imm(0xA9, 2); a.sta_l(KOFF)
    a.lda_l(DOC_KIND); a.rel(0xD0, 'dp_jw')
    a.lda_l(0x7E3C18); a.bra('dp_jt')
    a.label('dp_jw'); a.lda_l(0x7E3C19)
    a.label('dp_jt'); a.b(0x29); a.w(0xFF); a.rel(0xD0, 'dp_party')
    a.imm(0xA9, 0x7534); a.sta_l(LIST + 2); a.imm(0xA9, 0); a.sta_l(MAP + 2); a.imm(0xA9, 4); a.sta_l(KOFF)
    a.label('dp_party')
    a.imm(0xA0, 2)                                                             # Y = party slot offset
    a.label('dp_pl'); a.b(0x98, 0x38); a.b(0xEF); a.l(0x7E2DE6); a.rel(0xF0, 'dp_pin'); a.rel(0x90, 'dp_pin')
    a.brl('dp_pend_n')                                                         # past the last slot
    a.label('dp_pin'); a.b(0xBB); a.lda_lx(0x7E2DF0); a.jsr('t2i')            # tyx; type -> X = idx*2
    a.imm(0xE0, 0); a.rel(0xF0, 'dp_pnext'); a.rel(0x30, 'dp_pnext')
    a.b(0x8A); a.sta_l(TMPB)                                                   # TMPB = idx*2
    a.lda_l(DOC_KIND); a.rel(0xD0, 'dp_mw'); a.lda_l(DERM); a.bra('dp_mt')
    a.label('dp_mw'); a.lda_l(WIRED)
    a.label('dp_mt'); a.b(0x3F); a.l(0); a.fix.append(('long', len(a.code) - 3, 'bits')); a.rel(0xD0, 'dp_pnext')
    a.b(0xBB); a.b(0xBD); a.w(0x1FC4); a.sta_l(TMPO)                          # object of this slot
    a.lda_l(KOFF); a.b(0xAA)
    a.lda_l(TMPB); a.sta_lx(MAP); a.lda_l(TMPO); a.sta_lx(OBJS)
    a.lda_l(TMPB); a.b(0xDA, 0xAA); a.lda_lx(0x809705); a.b(0xFA); a.sta_lx(LIST)   # runner's name
    a.b(0xE8, 0xE8, 0x8A); a.sta_l(KOFF)
    a.label('dp_pnext'); a.b(0xC8, 0xC8); a.bra('dp_pl')
    a.label('dp_pend_n'); a.lda_l(KOFF); a.b(0x4A); a.sta_l(NCNT)
    a.imm(0xA9, 2); a.b(0x85, 0x00); a.imm(0xA9, 0x11); a.b(0x85, 0x02)
    a.imm(0xA9, 0x15); a.b(0x85, 0x04); a.lda_l(NCNT); a.b(0x18); a.imm(0x69, 2); a.b(0x85, 0x06)
    a.b(0x64, 0x08); a.call80(0x80F92D); a.b(0xA5, 0x00); a.sta_l(WIN)
    a.lda_l(WIN); a.b(0x85, 0x00); a.call80(0x80FA31)
    a.imm(0xA9, 1); a.b(0x85, 0x02); a.b(0x64, 0x04); a.lda_l(NCNT); a.b(0x85, 0x06)
    a.imm(0xA9, LIST & 0xFFFF); a.b(0x85, 0x08); a.imm(0xA9, LIST >> 16); a.b(0x85, 0x0A)
    a.call80(0x80A654)
    a.b(0xA5, 0x00); a.sta_l(TMPB)
    a.lda_l(WIN); a.b(0x85, 0x00); a.call80(0x80FA08)                          # close the list
    a.lda_l(TMPB); a.rel(0xF0, 'dp_cnear'); a.rel(0x10, 'dp_sel')
    a.label('dp_cnear'); a.brl('dp_cancel')
    a.label('dp_sel'); a.b(0x0A, 0xAA); a.lda_lx(MAP); a.sta_l(DOC_WHO); a.lda_lx(OBJS); a.sta_l(DOC_OBJ)
    # pay (vanilla routine body after our hook)
    a.lda_l(DOC_PRICE); a.b(0x85, 0x00); a.b(0x38); a.lda_l(0x7E3C0D); a.call80(0x80CCF5)
    a.b(0xA5, 0x00); a.rel(0xD0, 'dp_paid')
    for k, v in ((0x00, 6), (0x02, 6), (0x04, 16), (0x06, 3), (0x08, 0x0400), (0x0A, 2), (0x0C, 240)):
        a.imm(0xA9, v); a.b(0x85, k)
    a.call80(0x80FE8B); a.brl('dp_cancel')                                      # "Not enough money!"
    a.label('dp_paid')
    a.lda_l(DOC_WHO); a.rel(0xD0, 'dp_runner')
    a.b(0xE2, 0x20); a.lda_l(DOC_KIND); a.rel(0xD0, 'dp_jwi')
    a.b(0xA9, 0x01); a.sta_l(0x7E3C18); a.bra('dp_jdone')
    a.label('dp_jwi'); a.b(0xA9, 0xFF); a.sta_l(0x7E3C19)
    a.label('dp_jdone'); a.b(0xC2, 0x20); a.bra('dp_thanks')
    a.label('dp_runner'); a.b(0xAA)                                            # X = idx*2
    a.lda_l(DOC_KIND); a.rel(0xD0, 'dp_rw')
    a.lda_l(DERM); a.b(0x1F); a.l(0); a.fix.append(('long', len(a.code) - 3, 'bits')); a.sta_l(DERM)   # ora bits,X
    a.lda_l(DOC_OBJ); a.b(0xAA); a.lda_lx(0x7E43D4); a.b(0x18); a.imm(0x69, 2); a.sta_lx(0x7E43D4)  # armor now
    a.bra('dp_thanks')
    a.label('dp_rw'); a.lda_l(WIRED); a.b(0x1F); a.l(0); a.fix.append(('long', len(a.code) - 3, 'bits')); a.sta_l(WIRED)
    a.label('dp_thanks')
    for k, v in ((0x00, 13), (0x02, 21), (0x04, 7), (0x06, 3), (0x08, 0x0400), (0x0A, 22), (0x0C, 120)):
        a.imm(0xA9, v); a.b(0x85, k)
    a.call80(0x80FE8B)                                                          # "Thanks!"
    a.label('dp_cancel')                                                       # back to the item's wait loop
    a.lda_l(DOC_DP); a.b(0xAA); a.imm(0xA9, DOC_RESUME); a.sta_lx(0x7E0003)
    a.b(0x64, 0x00)                                                            # result 0
    a.b(0xE2, 0x20, 0x68, 0x68, 0x68, 0xC2, 0x20)                              # drop our JSL return
    a.b(0x5C); a.l(0x80CD86)                                                   # JML to an RTS: leave native #BE
    a.label('bits')
    for i in range(13): a.w(1 << i)
    a.label('prices')
    for t, p in sorted(SHOP_PRICE_AT.items()): a.w(t); a.w(p & 0xFFFF); a.w(p >> 16)
    a.w(0); a.w(0); a.w(0)
    a.label('armor_prices')
    for p in ARMOR_PRICE_BY_PROTECTION: a.w(p)
    code = a.done()
    return code, a.labels

def patch(rom):
    rom = bytearray(rom)
    if len(rom) < 0x200000: rom += b'\x00' * (0x200000 - len(rom))
    code, L = build_code()
    o = lorom(CODE); assert all(b == 0 for b in rom[o:o + len(code)]), 'code area not free'
    rom[o:o + len(code)] = code
    def put(addr, old, new):
        f = lorom(addr); assert rom[f:f + len(old)] == old, (hex(addr), rom[f:f + len(old)].hex()); rom[f:f + len(new)] = new
    jsl = lambda t: bytes([0x22, t & 0xFF, (t >> 8) & 0xFF, t >> 16])
    put(0x808596, b'\x3A', b'\xEA')                                                         # no stay countdown
    put(0x81B141, bytes.fromhex('A2E02DA9030F54707E'), jsl(L['save']) + b'\xEA' * 5)          # save hook
    put(0x81B15B, bytes.fromhex('A0E02DA9030F547E70'), jsl(L['load']) + b'\xEA' * 5)          # load hook
    put(0x809915, bytes.fromhex('A96C718F153C7E'), jsl(L['newgame']) + b'\x60\xEA\xEA')       # new game hook
    for i in range(12):                                                                      # repoint stat blocks
        idx = i + 1
        put(0x80969D + 2 * idx, ROM_PTR[i].to_bytes(2, 'little'), ((STATS + 18 * i) & 0xFFFF).to_bytes(2, 'little'))
        put(0x8096B7 + 2 * idx, b'\x80', b'\x7F')
    # ---------------- stage 2 hooks
    assert rom[lorom(RTL80)] == 0x6B
    put(0x80CD82, bytes.fromhex('18AF113C7E65008F113C7E60'), jsl(L['kgain']) + b'\x60' + b'\xEA' * 7)  # karma gain
    put(0x80CE8D, bytes.fromhex('2021EE80AB'), jsl(L['pick']) + b'\xEA')                    # Use karma -> who?
    put(0x80EE27, bytes.fromhex('AD9D9685F9E220ADB79685FBC220'), jsl(L['setf9']) + b'\xEA' * 10)
    put(0x80EF6D, bytes.fromhex('AF113C7E'), jsl(L['kget']))                                 # karma display
    put(0x80EFDB, bytes.fromhex('AF113C7E'), jsl(L['kget']))                                 # karma cost check
    put(0x80F010, bytes.fromhex('8F113C7E'), jsl(L['kset']))                                 # karma pay
    for addr, tbl, lab in ((0x80F03E, 'EF', 'adr_skill'), (0x80F0AE, 'EF', 'adr_skill'), (0x80F0DD, 'EF', 'adr_attr'),
                           (0x80F14D, 'EF', 'adr_attr'), (0x80F19F, 'EF', 'adr_magic'), (0x80F20F, 'EF', 'adr_magic')):
        lo = {'adr_skill': 0x94, 'adr_attr': 0x7C, 'adr_magic': 0xAC}[lab]
        put(addr, bytes([0xBD, lo, 0xEF, 0x85, 0x0E]), jsl(L[lab]) + b'\xEA')
    put(0x80F155, bytes.fromhex('A50EC9FB3B'), jsl(L['body']) + b'\xEA')                    # Body -> +10 stamina
    # ---------------- copy equipping: native #CD -> stub at $80CD87 (spare bytes after the karma-gain hook)
    put(0x80CD87, b'\xEA' * 5, jsl(L['cpgive']) + b'\x60')
    put(0x82D604 + 2 * 0xCD, bytes.fromhex('EDCF'), bytes.fromhex('87CD'))                 # native table entry
    put(0x82D895 + 0xCD, b'\x00', b'\x02')                                                  # 2 args
    put(0x82D7BA + 0xCD, b'\x02', b'\x00')                                                  # no return value
    put(0x9EADEB, b'\x58\x75', b'\x58\xCD')                                                 # armor script $0320 give
    put(0x9CF7F1, b'\x58\x75', b'\x58\xCD')                                                 # weapon script $0011 give
    # ---------------- runner cyberware
    put(0x80A32C, bytes.fromhex('BD7414090300 9D7414'.replace(' ', '')), jsl(L['derm_spawn']) + b'\xEA' * 5)
    put(0x80E9CA, bytes.fromhex('AD781FCDDE0C'), jsl(L['st_armor']) + b'\x80\x19')          # then BRA $80E9E9
    put(0x80C3D1, bytes.fromhex('AE6C02A500'), jsl(L['wired']) + b'\xEA')                    # native #9E (wait)
    put(0x80CCF0, bytes.fromhex('38AF0D3C7E'), jsl(L['docpay']) + b'\xEA')                   # native #BE (pay)
    rom[0x7FD7] = 0x0B                                                                       # header: 2 MB
    rom[0x7FDC:0x7FE0] = b'\xFF\xFF\x00\x00'; s = sum(rom) & 0xFFFF
    rom[0x7FDC:0x7FDE] = (s ^ 0xFFFF).to_bytes(2, 'little'); rom[0x7FDE:0x7FE0] = s.to_bytes(2, 'little')
    return bytes(rom)

def make_ips(orig, new):
    orig = orig + b'\x00' * (len(new) - len(orig)); recs = []; i = 0
    while i < len(new):
        if new[i] != orig[i]:
            j = i
            while j < len(new) and new[j] != orig[j] and j - i < 0xFFFF: j += 1
            recs.append((i, new[i:j])); i = j
        else: i += 1
    if not recs or recs[-1][0] + len(recs[-1][1]) < len(new):          # force the output size (2 MB)
        recs.append((len(new) - 1, new[-1:]))
    assert all(o != 0x454F46 for o, _ in recs)
    return b'PATCH' + b''.join(o.to_bytes(3, 'big') + len(d).to_bytes(2, 'big') + d for o, d in recs) + b'EOF'

if __name__ == '__main__':
    clean = open(sys.argv[1], 'rb').read(); out = sys.argv[2]
    new = patch(clean)
    open(out + '.sfc', 'wb').write(new); open(out + '.ips', 'wb').write(make_ips(clean, new))
    print('code', len(build_code()[0]), 'bytes; ROM', len(new), 'CRC32 %08X' % zlib.crc32(new))
