import sys
sys.path.insert(0,'/home/claude/shadowrun_toolkit')
from build_runners import Asm
def lorom(a): return ((a&0x7F0000)>>1)|(a&0x7FFF)
p=bytearray(open(sys.argv[1],'rb').read())
if len(p)<0x200000: p+=bytes(0x200000-len(p)); p[0x7FD7]=0x0B
CNT,TMP,LOG=0x7FA8F0,0x7FA8F2,0x7FA900
a=Asm(0xAA9000)
a.b(0x08,0xC2,0x30,0x48,0xDA)
a.lda_l(CNT); a.imm(0xC9,0x1800); a.rel(0xB0,'skip')
a.b(0xA6,0x00)                       # ldx $00 (window)
a.lda_lx(0x7E2020); a.sta_l(TMP); a.lda_lx(0x7E2040); a.sta_l(TMP+2)
a.lda_lx(0x7E20C0); a.b(0x38); a.b(0xFF); a.l(0x7E2060); a.sta_l(TMP+4)   # sbc long,X
a.lda_l(CNT); a.b(0xAA)
a.b(0xA5,0x02); a.sta_lx(LOG); a.lda_l(TMP); a.sta_lx(LOG+2); a.lda_l(TMP+2); a.sta_lx(LOG+4); a.lda_l(TMP+4); a.sta_lx(LOG+6)
a.b(0x8A,0x18); a.imm(0x69,8); a.sta_l(CNT)
a.label('skip'); a.b(0xFA,0x68,0x28)
a.b(0x8B); a.imm(0xA9,0x9DFF); a.b(0x5C); a.l(0x80FE37)
c=a.done(); p[lorom(0xAA9000):lorom(0xAA9000)+len(c)]=c
p[lorom(0x80FE33):lorom(0x80FE37)]=bytes([0x5C,0x00,0x90,0xAA])
open(sys.argv[2],'wb').write(p)
