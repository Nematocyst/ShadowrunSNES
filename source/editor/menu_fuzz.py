import os,sys,json,random
os.environ['SR_ROM']=os.path.abspath(os.environ.get('FZROM','log.sfc'))
sys.path.insert(0,'/home/claude/shadowrun_toolkit')
import snes_retro as sr
state, seed, frames = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
rnd=random.Random(seed)
e=sr.make(); e.reset()
if state!='boot.state': e.em.set_state(open(state,'rb').read())
e.step(sr.action())
R=lambda a:e._ram[a]|e._ram[a+1]<<8
out={}
def harvest():
    n=R(0x1A8F0)
    for o in range(0,n,8):
        a=0x1A900+o; t,w,h,c=R(a),R(a+2),R(a+4),R(a+6)
        k='%04X'%t; v='%d,%d,%d'%(w,h,c)
        out.setdefault(k,{}); out[k][v]=out[k].get(v,0)+1
    e._ram[0x1A8F0]=0; e._ram[0x1A8F1]=0
e._ram[0x1A8F0]=0; e._ram[0x1A8F1]=0
btns=(['A']*20+['B']*15+['START']*10+['Y']*8+['SELECT']*4+['X']*5+['UP']*10+['DOWN']*10+['LEFT']*9+['RIGHT']*9) if not os.environ.get('MENU') else (['A']*25+['B']*8+['START']*12+['UP']*15+['DOWN']*20+['LEFT']*10+['RIGHT']*10)
f=0
while f<frames:
    b=rnd.choice(btns); hold=rnd.randint(1,8)
    for _ in range(hold): e.step(sr.action(b)); f+=1
    for _ in range(rnd.randint(2,20)): e.step(sr.action()); f+=1
    if f%600<30: harvest()
harvest()
json.dump(out,open('fz_%s_%s_%d.json'%(os.path.basename(os.environ.get('FZROM','log'))[:-4],os.path.basename(state)[:-6],seed),'w'))
print(state,seed,len(out),'texts')
