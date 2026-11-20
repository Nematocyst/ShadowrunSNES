"""Tiny 65816 disassembler for poking at any SNES LoROM address.
Usage: python3 dis65816.py ROM SNES_ADDR [count] [--m8] [--x8]
Tracks REP/SEP for M/X width as it goes (starts 16-bit A and X unless --m8/--x8)."""
import sys

# (mnemonic, mode) per opcode
MODES = {
 'imp':0,'acc':0,'imm8':1,'immM':-1,'immX':-2,'dp':1,'dpx':1,'dpy':1,'idp':1,'idpx':1,'idpy':1,'ildp':1,'ildpy':1,
 'sr':1,'isry':1,'abs':2,'absx':2,'absy':2,'iabs':2,'iabsx':2,'ilabs':2,'long':3,'longx':3,'rel':1,'rell':2,'bm':2}
OPS = {}
def _d(s):
    for item in s.split(','):
        o, m, mode = item.split()
        OPS[int(o, 16)] = (m, mode)
_d("00 brk imm8,01 ora idpx,02 cop imm8,03 ora sr,04 tsb dp,05 ora dp,06 asl dp,07 ora ildp,08 php imp,09 ora immM,0A asl acc,0B phd imp,0C tsb abs,0D ora abs,0E asl abs,0F ora long,"
   "10 bpl rel,11 ora idpy,12 ora idp,13 ora isry,14 trb dp,15 ora dpx,16 asl dpx,17 ora ildpy,18 clc imp,19 ora absy,1A inc acc,1B tcs imp,1C trb abs,1D ora absx,1E asl absx,1F ora longx,"
   "20 jsr abs,21 and idpx,22 jsl long,23 and sr,24 bit dp,25 and dp,26 rol dp,27 and ildp,28 plp imp,29 and immM,2A rol acc,2B pld imp,2C bit abs,2D and abs,2E rol abs,2F and long,"
   "30 bmi rel,31 and idpy,32 and idp,33 and isry,34 bit dpx,35 and dpx,36 rol dpx,37 and ildpy,38 sec imp,39 and absy,3A dec acc,3B tsc imp,3C bit absx,3D and absx,3E rol absx,3F and longx,"
   "40 rti imp,41 eor idpx,42 wdm imm8,43 eor sr,44 mvp bm,45 eor dp,46 lsr dp,47 eor ildp,48 pha imp,49 eor immM,4A lsr acc,4B phk imp,4C jmp abs,4D eor abs,4E lsr abs,4F eor long,"
   "50 bvc rel,51 eor idpy,52 eor idp,53 eor isry,54 mvn bm,55 eor dpx,56 lsr dpx,57 eor ildpy,58 cli imp,59 eor absy,5A phy imp,5B tcd imp,5C jml long,5D eor absx,5E lsr absx,5F eor longx,"
   "60 rts imp,61 adc idpx,62 per rell,63 adc sr,64 stz dp,65 adc dp,66 ror dp,67 adc ildp,68 pla imp,69 adc immM,6A ror acc,6B rtl imp,6C jmp iabs,6D adc abs,6E ror abs,6F adc long,"
   "70 bvs rel,71 adc idpy,72 adc idp,73 adc isry,74 stz dpx,75 adc dpx,76 ror dpx,77 adc ildpy,78 sei imp,79 adc absy,7A ply imp,7B tdc imp,7C jmp iabsx,7D adc absx,7E ror absx,7F adc longx,"
   "80 bra rel,81 sta idpx,82 brl rell,83 sta sr,84 sty dp,85 sta dp,86 stx dp,87 sta ildp,88 dey imp,89 bit immM,8A txa imp,8B phb imp,8C sty abs,8D sta abs,8E stx abs,8F sta long,"
   "90 bcc rel,91 sta idpy,92 sta idp,93 sta isry,94 sty dpx,95 sta dpx,96 stx dpy,97 sta ildpy,98 tya imp,99 sta absy,9A txs imp,9B txy imp,9C stz abs,9D sta absx,9E stz absx,9F sta longx,"
   "A0 ldy immX,A1 lda idpx,A2 ldx immX,A3 lda sr,A4 ldy dp,A5 lda dp,A6 ldx dp,A7 lda ildp,A8 tay imp,A9 lda immM,AA tax imp,AB plb imp,AC ldy abs,AD lda abs,AE ldx abs,AF lda long,"
   "B0 bcs rel,B1 lda idpy,B2 lda idp,B3 lda isry,B4 ldy dpx,B5 lda dpx,B6 ldx dpy,B7 lda ildpy,B8 clv imp,B9 lda absy,BA tsx imp,BB tyx imp,BC ldy absx,BD lda absx,BE ldx absy,BF lda longx,"
   "C0 cpy immX,C1 cmp idpx,C2 rep imm8,C3 cmp sr,C4 cpy dp,C5 cmp dp,C6 dec dp,C7 cmp ildp,C8 iny imp,C9 cmp immM,CA dex imp,CB wai imp,CC cpy abs,CD cmp abs,CE dec abs,CF cmp long,"
   "D0 bne rel,D1 cmp idpy,D2 cmp idp,D3 cmp isry,D4 pei dp,D5 cmp dpx,D6 dec dpx,D7 cmp ildpy,D8 cld imp,D9 cmp absy,DA phx imp,DB stp imp,DC jml ilabs,DD cmp absx,DE dec absx,DF cmp longx,"
   "E0 cpx immX,E1 sbc idpx,E2 sep imm8,E3 sbc sr,E4 cpx dp,E5 sbc dp,E6 inc dp,E7 sbc ildp,E8 inx imp,E9 sbc immM,EA nop imp,EB xba imp,EC cpx abs,ED sbc abs,EE inc abs,EF sbc long,"
   "F0 beq rel,F1 sbc idpy,F2 sbc idp,F3 sbc isry,F4 pea abs,F5 sbc dpx,F6 inc dpx,F7 sbc ildpy,F8 sed imp,F9 sbc absy,FA plx imp,FB xce imp,FC jsr iabsx,FD sbc absx,FE inc absx,FF sbc longx")

FMT = {'imp':'','acc':'A','imm8':'#${:02X}','dp':'${:02X}','dpx':'${:02X},X','dpy':'${:02X},Y','idp':'(${:02X})',
       'idpx':'(${:02X},X)','idpy':'(${:02X}),Y','ildp':'[${:02X}]','ildpy':'[${:02X}],Y','sr':'${:02X},S','isry':'(${:02X},S),Y',
       'abs':'${:04X}','absx':'${:04X},X','absy':'${:04X},Y','iabs':'(${:04X})','iabsx':'(${:04X},X)','ilabs':'[${:04X}]',
       'long':'${:06X}','longx':'${:06X},X'}


def lorom(addr):
    return ((addr & 0x7F0000) >> 1) | (addr & 0x7FFF)


def disasm(rom, addr, count=40, m16=True, x16=True, stop_at_return=False):
    out = []
    for _ in range(count):
        f = lorom(addr); op = rom[f]; m, mode = OPS[op]
        n = MODES[mode]
        if n == -1: n = 2 if m16 else 1
        if n == -2: n = 2 if x16 else 1
        raw = rom[f + 1:f + 1 + n]; v = int.from_bytes(raw, 'little')
        if mode == 'rel': arg = '${:04X}'.format((addr + 2 + (v - 256 if v > 127 else v)) & 0xFFFF)
        elif mode == 'rell': arg = '${:04X}'.format((addr + 3 + (v - 65536 if v > 32767 else v)) & 0xFFFF)
        elif mode == 'bm': arg = '${:02X},${:02X}'.format(raw[0], raw[1])
        elif mode in ('immM', 'immX'): arg = ('#${:04X}' if n == 2 else '#${:02X}').format(v)
        else: arg = FMT[mode].format(v)
        out.append('{:06X}  {:<12} {} {}'.format(addr, (bytes([op]) + raw).hex(' '), m, arg))
        if m == 'rep': m16 = m16 or bool(v & 0x20); x16 = x16 or bool(v & 0x10)
        if m == 'sep': m16 = m16 and not (v & 0x20); x16 = x16 and not (v & 0x10)
        addr = (addr & 0xFF0000) | ((addr + 1 + n) & 0xFFFF)
        if stop_at_return and m in ('rts', 'rtl', 'rti', 'jmp', 'jml', 'bra', 'brl'): break
    return out


if __name__ == '__main__':
    rom = open(sys.argv[1], 'rb').read()
    a = int(sys.argv[2].lstrip('$'), 16); n = int(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3].isdigit() else 40
    print('\n'.join(disasm(rom, a, n, '--m8' not in sys.argv, '--x8' not in sys.argv)))
