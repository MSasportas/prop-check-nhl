"""Does DraftKings lag Pinnacle? (2026-11-03, Matt). Between back-to-back reads (A 1 PM -> B 90 min -> C 45 min),
Pinnacle's no-vig chance moves >= MOVE toward a side; bet DraftKings' price on that side at the second read when DK
is at or better than Pinnacle's new fair. Variants: DK price unchanged (lagged) or not. Shots, lines 1.5-3.5, -200 or
better, first signal per player per night, graded from data/shadow actual shots (reg + OT, void = no ice time)."""
import json, glob, collections, os, statistics as st
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
dec = lambda p: 1 + (p / 100 if p > 0 else 100 / -p)
def fo(s): a, b = 1 / dec(s['over']), 1 / dec(s['under']); return a / (a + b)
def ts(mk, pid, line):
    s = {o['side']: o['price'] for o in (mk or {}).get('outcomes', []) if o.get('pid') == pid and o.get('line') == line}
    return s if len(s) == 2 else None
act = {}
for f in glob.glob(REPO + '/data/shadow/2026-*.json'):
    for r in json.load(open(f))['rows']:
        rr = r.get('result') or {}
        if r['market'] == 'shots' and rr.get('actual') is not None:
            act[(r['game_id'], r['pid'])] = None if rr.get('toi') in (None, '0:00', '00:00') else rr['actual']
reads = collections.defaultdict(list)
for f in sorted(glob.glob(REPO + '/data/odds/2026-*.json')):
    slate = f[-15:-5]
    if not ('2026-10-20' <= slate <= '2026-11-02'): continue
    for x in json.load(open(f))['fetches']:
        oth = x.get('others') or {}
        pin, dk = (oth.get('pinnacle') or {}).get('shots'), (oth.get('draftkings') or {}).get('shots')
        if not pin or not dk: continue
        for pid, line in {(o['pid'], o['line']) for o in dk.get('outcomes', []) if o.get('pid')}:
            if line not in (1.5, 2.5, 3.5): continue
            d, p = ts(dk, pid, line), ts(pin, pid, line)
            if d and p:
                reads[(x['game_id'], pid, line)].append(dict(at=x['at'], slate=slate, dk=d, pin=fo(p)))
def run(move, need_flat):
    c = []
    for k, rs in reads.items():
        rs.sort(key=lambda r: r['at'])
        for a, b in zip(rs, rs[1:]):
            dp = b['pin'] - a['pin']
            if abs(dp) < move: continue
            side = 'over' if dp > 0 else 'under'
            pr = b['dk'][side]
            if pr < -200 or (need_flat and a['dk'][side] != pr): continue
            pf = b['pin'] if side == 'over' else 1 - b['pin']
            if pf * dec(pr) - 1 < 0: continue
            c.append(dict(k=k, side=side, price=pr, at=b['at'], slate=b['slate']))
    c.sort(key=lambda x: x['at']); seen = set(); w = l = 0; u = 0.0; n = 0
    for x in c:
        key = (x['slate'], x['k'][1])
        if key in seen: continue
        seen.add(key); n += 1
        a_ = act.get((x['k'][0], x['k'][1]))
        if a_ is None: continue
        win = a_ > x['k'][2] if x['side'] == 'over' else a_ < x['k'][2]
        w += win; l += not win; u += (dec(x['price']) - 1) if win else -1
    return n, w, l, u
ints = sum(len(v) - 1 for v in reads.values())
print('DK+Pinnacle intervals', ints)
for need_flat in (True, False):
    for mv in (0.01, 0.02, 0.03):
        n, w, l, u = run(mv, need_flat)
        print('Pin move >= %d pt, DK %s: %d bets, %d-%d, %+.2fu' % (mv * 100, 'unchanged' if need_flat else 'any', n, w, l, u))
