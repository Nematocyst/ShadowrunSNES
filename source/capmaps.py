"""Render whole maps by panning the game's own camera with sprites/HUD layers off and stitching screenshots."""
import os,sys,json
os.environ['SR_ROM']=os.path.abspath('map_tw.sfc'); os.environ['SNES_VARS']='snes9x_layer_5=disabled;snes9x_layer_3=disabled'
sys.path.insert(0,'/home/claude/shadowrun_toolkit')
import snes_retro as sr, numpy as np
from PIL import Image
rom=open('/home/claude/shadowrun.sfc','rb').read()
def L(a): return ((a&0x7F0000)>>1)|(a&0x7FFF)
RWr=lambda a:rom[L(a)]|rom[L(a)+1]<<8
e=sr.make(); e.reset(); START=open('u2s1_tw.state','rb').read()
R=lambda a:int(e._ram[a&0x1FFFF]); W=lambda a:R(a)|R(a+1)<<8
def w16(a,v): e._ram[a&0x1FFFF]=v&0xFF; e._ram[(a+1)&0x1FFFF]=(v>>8)&0xFF
def heal():
    j=W(0x0CDE)
    if j<0x58: r=W(0x13C4+j); e._ram[(r+2)&0x1FFFF]=99
def run(n):
    for _ in range(n): heal(); e.step(sr.action())
def settle(maxf=80):
    last=None; same=0
    for f in range(maxf):
        heal(); e.step(sr.action()); c=(W(0x0CE0),W(0x0CE2))
        same = same+1 if c==last else 0; last=c
        if same>=3: break
    run(2); return last
def capture(loc, out):
    e.em.set_state(START); e.step(sr.action())
    w16(0x7F9990,loc); [e.step(sr.action('START')) for _ in range(3)]; run(160)
    j=W(0x0CDE)
    if j>=0x58: return None
    x0,y0=W(0x0E44+j),W(0x0E9C+j); c0=settle()
    shots={}
    def shoot():
        c=(W(0x0CE0),W(0x0CE2))
        if c not in shots: shots[c]=e.screen().copy()
        return c
    shoot()
    tx=list(range(-6000,6001,760)); ty=list(range(-3000,3001,640))
    for i,cy in enumerate(ty):
        row = tx if i%2==0 else tx[::-1]
        for cx in row:
            dx=int(cy-cx/2); dy=int(cy+cx/2)
            nx,ny=x0+dx,y0+dy
            if not (0<nx<0x3F00 and 0<ny<0x3F00): continue
            w16(0x0E44+j,nx); w16(0x0E9C+j,ny); settle(); shoot()
    if not shots: return None
    xs=[c[0]//4 for c in shots]; ys=[c[1]//4 for c in shots]
    W_=max(xs)-min(xs)+256; H_=max(ys)-min(ys)+224
    canvas=np.zeros((H_,W_,3),np.uint8)
    for (cx,cy),img in sorted(shots.items(), key=lambda kv: kv[0][1]):
        px,py=cx//4-min(xs), cy//4-min(ys)
        m=8   # the PPU leaves a black border; keep only the inner part of each shot
        canvas[py+m:py+224-m,px+m:px+256-m]=img[m:224-m,m:256-m]
    Image.fromarray(canvas).save(out)
    return dict(loc=loc, shots=len(shots), size=[W_,H_], cam_min=[min(xs)*4,min(ys)*4])
if __name__=='__main__':
    os.makedirs('maps',exist_ok=True)
    seen={}; todo=[]
    for loc in range(0x1FC):
        p=RWr(0x8D92AF+9*loc)
        if p in seen: continue
        seen[p]=loc; todo.append(loc)
    only=[int(x,16) for x in sys.argv[1:]] or todo
    res=[]
    for loc in only:
        try: r=capture(loc,'maps/map_%03X.png'%loc)
        except Exception as ex: r=dict(loc=loc,err=str(ex))
        print(hex(loc), r, flush=True); res.append(r)
    json.dump(res,open('maps/capture.json' if len(sys.argv)==1 else 'maps/capture_part.json','w'))
