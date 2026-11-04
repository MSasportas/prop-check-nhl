import sys,json,glob,os
sys.path.insert(0,'scripts'); import odds, shadow, common, paper
cfg=json.load(open('config/rules.json')); v=cfg['values']
def evd(p,pr): return p*odds.decimal(pr)-1
# (a) our HR picks: DK vs market fair WITHOUT DK
ev=[json.loads(l) for l in open('data/paper/events.jsonl')]
fl=[e for e in ev if e['t']=='flag' and '2026-10-20'<=e['slate']<='2026-11-02']
a=[]
for e in fl:
    f=next(f for f in json.load(open('data/odds/%s.json'%e['slate']))['fetches'] if f['game_id']==e['game_id'] and f['at']==e['read_at'])
    dk=next((o['price'] for o in f['others'].get('draftkings',{}).get('shots',{}).get('outcomes',[]) if o.get('pid')==e['pid'] and o.get('line')==e['line'] and o.get('side')==e['side']),None)
    if dk is None: continue
    f2=dict(f); f2['others']={b:m for b,m in f['others'].items() if b!='draftkings'}
    ent=(shadow.other_lines(f2,'shots',v) or {}).get((e['pid'],e['line']))
    fair=paper.median([paper.side_fair(odds.fair_two_sided(o,u),e['side']) for o,u in ent['pairs'].values()])
    a.append(evd(fair,dk))
print('(a) HR picks w/ DK:',len(a),'DK beats ex-DK fair:',sum(x>=0 for x in a),'median DK EV %.3f'%sorted(a)[len(a)//2])
# (b) every DK shots line at B/C reads, vs ex-DK fair (>=4 books incl Pinnacle), first read per player-game, best side
rows=[]; seen={}
for fn in sorted(glob.glob('data/odds/*.json')):
    day=os.path.basename(fn)[:10]
    if not('2026-10-20'<=day<='2026-11-02'): continue
    sh=json.load(open('data/shadow/%s.json'%day)); res={}; start={}
    for r in sh['rows']:
        if r['market']!='shots': continue
        start[r['game_id']]=r['ctx']['start']
        rr=r.get('result') or {}
        if rr.get('actual') is not None and rr.get('toi') not in (None,'0:00','00:00'): res[(r['game_id'],r['pid'])]=rr['actual']
    pass
    for f in sorted(json.load(open(fn))['fetches'],key=lambda f:f['at']):
        g=f['game_id']
        if f.get('pull') not in ('B','C') or 'others' not in f or g not in start: continue
        at=common.parse_iso(f['at'])
        if common.parse_iso(start[g])<=at: continue
        mk=f['others'].get('draftkings',{}).get('shots')
        if not mk or odds.is_stale(mk.get('last_update'),at,v): continue
        f2=dict(f); f2['others']={b:m for b,m in f['others'].items() if b!='draftkings'}
        cons=shadow.other_lines(f2,'shots',v) or {}
        for (pid,line),p in shadow.pairs_of(mk).items():
            if line not in (1.5,2.5,3.5) or p['over'] is None or p['under'] is None: continue
            ent=cons.get((pid,line))
            if not ent or len(ent['pairs'])<4 or 'pinnacle' not in ent['pairs']: continue
            for side in ('over','under'):
                pr=p[side]
                if odds.decimal(pr)<odds.decimal(-200): continue
                fair=paper.median([paper.side_fair(odds.fair_two_sided(o,u),side) for o,u in ent['pairs'].values()])
                x=evd(fair,pr); k=(g,pid)
                rows.append((x,day,pid,line,side,pr, k in res))
                for th in (0,0.01,0.02,0.03):
                    kk=(th,k)
                    if x>=th and kk not in seen and k in res:
                        act=res[k]; win=act>line if side=='over' else act<line
                        seen[kk]=(odds.decimal(pr)-1) if win else -1.0
print('(b) DK sides checked',len(rows),'beat ex-DK fair',sum(r[0]>=0 for r in rows))
for th in (0,0.01,0.02,0.03):
    xs=[u for (t,k),u in seen.items() if t==th]
    print('  DK >= +%d%% vs ex-DK fair: %d bets %d-%d %+.2fu'%(th*100,len(xs),sum(u>0 for u in xs),sum(u<0 for u in xs),sum(xs)))
