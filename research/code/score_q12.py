"""Q12 forward (HYPOTHESES.md, registered 2026-10-28 after seeing Oct 19-27): shots, 45-min read (C), bet the side
where Hard Rock's price beats Pinnacle's proportional no-vig fair by >= 5% EV, Hard Rock -200..+120. One side per
player per line. Graded from data/shadow results, flat 1u at the C price. Forward nights >= 2026-10-28.
Read-only on data/; writes research/fwd/q12.md.   python3 -I research/code/score_q12.py
"""
import json, glob, os

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
FWD_FROM = '2026-10-28'


def dec(p):
    return 1 + (p / 100 if p > 0 else 100 / -p)


def two(outs, pid, line):
    s = {o['side']: o['price'] for o in outs if o.get('pid') == pid and o.get('line') == line}
    return s if len(s) == 2 else None


res = {}
for f in glob.glob(f'{REPO}/data/shadow/2026-*.json'):
    d = json.load(open(f))
    for r in (d.get('rows') if isinstance(d, dict) else d):
        if r.get('result') and r['market'] == 'shots':
            res[(r['game_id'], r['pid'], r['line'])] = r['result']

out = []
for cut in (0.05, 0.03):
    bets, seen = [], set()
    for f in sorted(glob.glob(f'{REPO}/data/odds/2026-*.json')):
        if f[-15:-5] < FWD_FROM:
            continue
        for x in json.load(open(f))['fetches']:
            pin = ((x.get('others') or {}).get('pinnacle') or {}).get('shots')
            hr = (x.get('markets') or {}).get('shots')
            if x['pull'] != 'C' or not pin or not hr:
                continue
            for pid, line in {(o['pid'], o['line']) for o in hr['outcomes'] if o.get('pid')}:
                h, p = two(hr['outcomes'], pid, line), two(pin['outcomes'], pid, line)
                if not h or not p or (x['game_id'], pid, line) in seen:
                    continue
                a, b = 1 / dec(p['over']), 1 / dec(p['under'])
                fair = {'over': a / (a + b), 'under': b / (a + b)}
                best = max(('over', 'under'), key=lambda s: fair[s] * dec(h[s]))
                ev = fair[best] * dec(h[best]) - 1
                if ev >= cut and -200 <= h[best] <= 120:
                    seen.add((x['game_id'], pid, line))
                    bets.append((x['game_id'], pid, line, best, h[best]))
    w = l = 0; u = 0.0
    for g, pid, line, side, price in bets:
        o = (res.get((g, pid, line)) or {}).get(side)
        if o == 'W':
            w += 1; u += dec(price) - 1
        elif o == 'L':
            l += 1; u -= 1
    n = w + l
    out.append(f"Q12 EV >= {cut*100:.0f}% vs Pinnacle at C, -200..+120: bets {len(bets)}, graded {w}-{l}, {u:+.2f}u"
               + (f", ROI {100*u/n:+.1f}%" if n else ''))
print("\n".join(out))
open(os.path.join(REPO, 'research/fwd/q12.md'), 'w').write(
    f"# Q12 forward (research/code/score_q12.py), nights >= {FWD_FROM}. Bar: n >= 300 + p < .0033 (as Q1). >= 3% is descriptive only.\n\n```\n"
    + "\n".join(out) + "\n```\n")
