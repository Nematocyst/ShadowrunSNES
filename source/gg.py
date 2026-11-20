SUB=dict(zip('DF4709156BC8A23E','0123456789ABCDEF'))
def gg(code):
    h=''.join(SUB[c] for c in code.replace('-','').upper())
    val=int(h[:2],16); bits=bin(int(h[2:],16))[2:].zfill(24)
    pat='ijklqrstopabcduvwxefghmn'
    m=dict(zip(pat,bits)); a=int(''.join(m[c] for c in 'abcdefghijklmnopqrstuvwx'),2)
    return a,val
def lorom_file(a): return ((a&0x7F0000)>>1)|(a&0x7FFF)
if __name__=='__main__':
    import sys
    r=open('shadowrun.sfc','rb').read()
    for c in sys.argv[1:]:
        a,v=gg(c); f=lorom_file(a); print(c, f'${a:06X} file {f:05X} val {v:02X} orig {r[f]:02X}')
