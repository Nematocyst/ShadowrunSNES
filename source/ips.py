"""IPS helpers: parse(), apply(), records listing.  python3 ips.py PATCH.ips [ROM]  -> list write ranges"""
import sys
def parse(data):
    assert data[:5]==b'PATCH'; p=5; recs=[]
    while data[p:p+3]!=b'EOF':
        off=int.from_bytes(data[p:p+3],'big'); n=int.from_bytes(data[p+3:p+5],'big'); p+=5
        if n==0:
            rl=int.from_bytes(data[p:p+2],'big'); v=data[p+2]; p+=3; recs.append((off,bytes([v])*rl))
        else: recs.append((off,data[p:p+n])); p+=n
    trunc=int.from_bytes(data[p+3:p+6],'big') if len(data)>=p+6 else None
    return recs,trunc
def apply(rom,data):
    recs,trunc=parse(data); out=bytearray(rom)
    for off,d in recs:
        if off+len(d)>len(out): out.extend(b'\0'*(off+len(d)-len(out)))
        out[off:off+len(d)]=d
    if trunc: del out[trunc:]
    return bytes(out)
if __name__=='__main__':
    recs,_=parse(open(sys.argv[1],'rb').read())
    for o,d in recs: print('%06X len %5d'%(o,len(d)))
