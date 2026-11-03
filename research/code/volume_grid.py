"""Volume levers for the Gap rule (CEO, 2026-11-03, Matt: "more picks a night, find the best set of rules").
Step-1 lookalike on live reads (no model guard: it vetoed 2 of ~40). For each variant: first read that qualifies makes the
pick at that read's Hard Rock price; one pick per player per night (best EV at that read). Graded from data/shadow.
Descriptive only: every lever here was chosen after seeing these nights.   python3 -I research/code/volume_grid.py
"""
import json, glob, os, collections, statistics as st, random, itertools

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))


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

# every read of every line, with all fair numbers precomputed
R = []
for f in sorted(glob.glob(f'{REPO}/data/odds/2026-*.json')):
    slate = f[-15:-5]
    for x in json.load(open(f))['fetches']:
        oth = x.get('others') or {}
        hr = ((x.get('markets') or {}).get('shots') or {}).get('outcomes', [])
        if not oth or not hr:
            continue
        for pid, line in {(o['pid'], o['line']) for o in hr if o.get('pid')}:
            h = two(hr, pid, line)
            if not h:
                continue
            fairs, pin = [], None
            for b, bm in oth.items():
                s = two(((bm.get('shots') or {}).get('outcomes', [])), pid, line)
                if not s:
                    continue
                a, c = 1 / dec(s['over']), 1 / dec(s['under'])
                if not 0 <= a + c - 1 <= 0.15:
                    continue
                fairs.append(a / (a + c))
                if b == 'pinnacle':
                    pin = a / (a + c)
            if not fairs:
                continue
            med = st.median(fairs)
            for side in ('over', 'under'):
                m = med if side == 'over' else 1 - med
                p = None if pin is None else (pin if side == 'over' else 1 - pin)
                R.append(dict(slate=slate, at=x['at'], pull=x['pull'], k=(x['game_id'], pid, line), pid=pid, side=side,
                              price=h[side], gap=m * dec(h[side]) - 1, nb=len(fairs) - (pin is not None) + (pin is not None),
                              pin_ev=None if p is None else p * dec(h[side]) - 1))
R.sort(key=lambda r: r['at'])
NIGHTS = sorted({r['slate'] for r in R if r['slate'] < '2026-11-03'})


def run(reads='BC', gap=0.03, books=4, pin='req', lo=-200, hi=120):
    picked, out = set(), []
    by_read = collections.defaultdict(list)
    for r in R:
        if r['slate'] >= '2026-11-03' or r['pull'] not in reads:
            continue
        if r['gap'] < gap or r['nb'] < books or not lo <= r['price'] <= hi:
            continue
        if pin == 'req' and (r['pin_ev'] is None or r['pin_ev'] < 0):
            continue
        by_read[(r['slate'], r['at'], r['pid'])].append(r)
    for key in sorted(by_read, key=lambda k: k[1]):
        if (key[0], key[2]) in picked:
            continue
        r = max(by_read[key], key=lambda r: r['gap'])
        picked.add((key[0], key[2]))
        o = (res.get(r['k']) or {}).get(r['side'])
        if o in ('W', 'L'):
            out.append((r, o))
    return out


def line(label, out):
    w = sum(1 for _, o in out if o == 'W'); n = len(out)
    u = sum(dec(r['price']) - 1 if o == 'W' else -1 for r, o in out)
    be = st.mean(1 / dec(r['price']) for r, _ in out) if n else 0
    # game-clustered bootstrap 90% CI on ROI
    g = collections.defaultdict(list)
    for r, o in out:
        g[r['k'][0]].append(dec(r['price']) - 1 if o == 'W' else -1)
    keys = list(g); rnd = random.Random(1); boots = []
    for _ in range(2000):
        s = [g[rnd.choice(keys)] for _ in keys]; flat = [v for x in s for v in x]
        boots.append(sum(flat) / len(flat))
    boots.sort()
    print(f"{label:44s} {n/len(NIGHTS):4.1f}/night  n{n:4d}  {w}-{n-w}  hit {100*w/n:3.0f}% need {100*be:3.0f}%  {u:+6.1f}u  ROI {100*u/n:+5.1f}%  90% CI {100*boots[100]:+.0f}..{100*boots[1899]:+.0f}%")


if __name__ == '__main__':
    print(f"Nights {NIGHTS[0]}..{NIGHTS[-1]} ({len(NIGHTS)}). Step-1 lookalike, no guard, first qualifying read, 1 per player per night.\n")
    line('CURRENT (B/C, gap 3%, 4 books, Pin, <=+120)', run())
    print('-- one lever at a time --')
    line('+ 1 PM read (A/B/C)', run(reads='ABC'))
    line('gap 2%', run(gap=0.02))
    line('gap 1%', run(gap=0.01))
    line('price up to +200', run(hi=200))
    line('3+ books', run(books=3))
    line('Pinnacle not required', run(pin='any'))
    print('-- combinations --')
    line('A/B/C + gap 2%', run(reads='ABC', gap=0.02))
    line('A/B/C + +200', run(reads='ABC', hi=200))
    line('A/B/C + gap 2% + +200', run(reads='ABC', gap=0.02, hi=200))
    line('gap 2% + +200', run(gap=0.02, hi=200))
    line('A/B/C + gap 1% + +200', run(reads='ABC', gap=0.01, hi=200))
    print('-- by read, current thresholds --')
    for rd in 'ABC':
        line(f'read {rd} only', run(reads=rd))
    print('-- by side, current + 1 PM --')
    out = run(reads='ABC')
    for s in ('over', 'under'):
        line(f'  {s}', [x for x in out if x[0]['side'] == s])
