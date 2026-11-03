"""Q19: Matt's Pinnacle-steam rule (2026-11-03). Backtest on the live 2026-27 reads.

Rule (as Matt wrote it):
  - Hard Rock price -200 to +200.
  - Signal: between two back-to-back reads, Pinnacle's proportional no-vig chance moves >= 2 pts toward a side.
  - Other books: their median move toward that side < 2 pts, with >= MIN_BOOKS books quoting the line on both reads.
  - Hard Rock: same line posted on both reads; at the second read its price is at or better than Pinnacle's new fair.
  - One pick per player per market per night (first signal of the night). No game/night cap.
Graded at Hard Rock's second-read price from data/shadow results (reg + OT, void = no ice time). Flat 1u.

Usage: python3 -I research/code/q19_pin_steam.py [MIN_BOOKS=4] [MOVE=0.02] [MAXPRICE=200] [-v] [--md]
--md (default settings only) writes research/fwd/q19.md with all nights and the forward-only nights (>= FWD_FROM).
MIN_BOOKS counts other books (not Hard Rock, not Pinnacle).
"""
import json, glob, collections, sys, os, statistics as st

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
FWD_FROM = '2026-11-03'  # registered after seeing Oct 19-Nov 2: only nights from here count
_a = [x for x in sys.argv[1:] if not x.startswith('-')]
MIN_BOOKS = int(_a[0]) if len(_a) > 0 else 4
MOVE = float(_a[1]) if len(_a) > 1 else 0.02
MAXP = int(_a[2]) if len(_a) > 2 else 200
VERBOSE = '-v' in sys.argv


def dec(p):
    return 1 + (p / 100 if p > 0 else 100 / -p)


def fair_over(po, pu):
    a, b = 1 / dec(po), 1 / dec(pu)
    return a / (a + b)


def two_sided(outs, pid, line):
    s = {o['side']: o['price'] for o in outs if o.get('pid') == pid and o.get('line') == line}
    return s if len(s) == 2 else None


res = {}
for f in glob.glob(f'{REPO}/data/shadow/2026-*.json'):
    d = json.load(open(f))
    for r in (d.get('rows') if isinstance(d, dict) else d):
        if r.get('result'):
            res[(r['game_id'], r['market'], r['pid'], r['line'])] = r['result']

shown = set()
for ln in open(f'{REPO}/data/record/events.jsonl'):
    e = json.loads(ln)
    if e.get('t') == 'shown' and e.get('kind') == 'single':
        p = e['pick']
        shown.add((p['game_id'], p['market'], p['player_id'], p['line'], p['side']))

reads = collections.defaultdict(list)   # (game, market, pid, line) -> reads
lines_by_player = collections.defaultdict(set)
for f in sorted(glob.glob(f'{REPO}/data/odds/2026-*.json')):
    slate = f[-15:-5]
    for x in json.load(open(f))['fetches']:
        oth = x.get('others') or {}
        if 'pinnacle' not in oth:
            continue
        for mkt, mm in (x.get('markets') or {}).items():
            if mkt not in ('shots', 'saves'):
                continue
            hr = mm.get('outcomes', [])
            for pid, line in {(o['pid'], o['line']) for o in hr if o.get('pid')}:
                h = two_sided(hr, pid, line)
                p = two_sided(((oth['pinnacle'].get(mkt) or {}).get('outcomes', [])), pid, line)
                if not h or not p:
                    continue
                books = {}
                for b, bm in oth.items():
                    if b == 'pinnacle':
                        continue
                    s = two_sided(((bm.get(mkt) or {}).get('outcomes', [])), pid, line)
                    if s:
                        hold = 1 / dec(s['over']) + 1 / dec(s['under']) - 1
                        if 0 <= hold <= 0.15:
                            books[b] = fair_over(s['over'], s['under'])
                name = next(o['name'] for o in hr if o.get('pid') == pid)
                reads[(x['game_id'], mkt, pid, line)].append(dict(at=x['at'], pull=x['pull'], slate=slate, hr=h,
                                                                   pin=fair_over(p['over'], p['under']), books=books, name=name))

stats = collections.Counter()
cands = []
for k, rs in reads.items():
    rs.sort(key=lambda r: r['at'])
    for a, b in zip(rs, rs[1:]):
        stats['intervals'] += 1
        dpin = b['pin'] - a['pin']
        if abs(dpin) < MOVE:
            continue
        stats['pin_moved'] += 1
        side = 'over' if dpin > 0 else 'under'
        sgn = 1 if dpin > 0 else -1
        common = set(a['books']) & set(b['books'])
        if len(common) < MIN_BOOKS:
            stats['few_books'] += 1
            continue
        omove = st.median(sgn * (b['books'][x] - a['books'][x]) for x in common)
        if omove >= MOVE:
            stats['books_moved_too'] += 1
            continue
        price = b['hr'][side]
        if price < -200 or price > MAXP:
            stats['price_window'] += 1
            continue
        pfair = b['pin'] if side == 'over' else 1 - b['pin']
        ev = pfair * dec(price) - 1
        if ev < 0:
            stats['hr_worse_than_pin'] += 1
            continue
        stats['signals'] += 1
        cands.append(dict(k=k, side=side, price=price, ev=ev, dpin=dpin, omove=omove, nb=len(common), at=b['at'],
                          slate=b['slate'], pull=f"{a['pull']}->{b['pull']}", name=b['name'],
                          hr_flat=a['hr'] == b['hr']))

# one per player per market per night: first signal of the night
cands.sort(key=lambda c: (c['at'], -c['ev']))
seen, picks = set(), []
for c in cands:
    key = (c['slate'], c['k'][1], c['k'][2])
    if key in seen:
        stats['dupe_player'] += 1
        continue
    seen.add(key)
    picks.append(c)


def grade(c):
    r = res.get(c['k'])
    if not r:
        return 'open'
    o = r.get(c['side'])
    return o if o in ('W', 'L') else 'void'


OUT = []


def summary(label, ps):
    w = sum(1 for c in ps if grade(c) == 'W')
    l = sum(1 for c in ps if grade(c) == 'L')
    u = sum(dec(c['price']) - 1 for c in ps if grade(c) == 'W') - l
    be = st.mean(1 / dec(c['price']) for c in ps if grade(c) in 'WL') if w + l else 0
    ev = st.mean(c['ev'] for c in ps) if ps else 0
    other = len(ps) - w - l
    line = (f"{label:34s} n{len(ps):3d}  {w}-{l}" + (f" (+{other} void/open)" if other else '') +
          (f"  hit {100*w/(w+l):.0f}% vs need {100*be:.0f}%  {u:+.2f}u  ROI {100*u/(w+l):+.1f}%" if w + l else '') +
          f"  avg EV vs Pin {100*ev:+.1f}%")
    print(line); OUT.append(line)


print(f"Rule: Pinnacle move >= {MOVE*100:.0f} pts, others' median < {MOVE*100:.0f} pts, >= {MIN_BOOKS} other books, HR -200..+{MAXP}, HR >= Pin fair")
print('Funnel:', dict(stats))
summary('ALL PICKS', picks)
for m in ('shots', 'saves'):
    sel = [c for c in picks if c['k'][1] == m]
    if sel:
        summary(f'  {m}', sel)
for s in ('over', 'under'):
    summary(f'  {s}', [c for c in picks if c['side'] == s])
for pr in sorted({c['pull'] for c in picks}):
    summary(f'  read {pr}', [c for c in picks if c['pull'] == pr])
summary('  HR price unchanged', [c for c in picks if c['hr_flat']])
summary('  HR price changed', [c for c in picks if not c['hr_flat']])
summary('  also a live Record pick', [c for c in picks if (*c['k'], c['side']) in shown])
summary('  NOT on the Record', [c for c in picks if (*c['k'], c['side']) not in shown])
nights = sorted({c['slate'] for c in picks})
all_nights = sorted({r['slate'] for rs in reads.values() for r in rs})
print(f"Nights with a pick: {len(nights)} of {len(all_nights)} ({all_nights[0]}..{all_nights[-1]})")
if VERBOSE:
    for c in picks:
        print(f"  {c['slate']} {c['pull']} {c['name']:22s} {c['k'][1]} {c['side']} {c['k'][3]} {c['price']:+d} "
              f"pin {100*c['dpin']:+.1f} books {100*c['omove']:+.1f} (n{c['nb']}) EV {100*c['ev']:+.1f}% {grade(c)}")

# Q13 (registered 2026-10-28, forward from 2026-10-28): Pinnacle >= 2 pts, Hard Rock price unchanged, no other filters, HR -200 or better
q13, seen13 = [], set()
for k, rs in reads.items():
    if k[1] != 'shots':
        continue
    for a, b in zip(rs, rs[1:]):
        d = b['pin'] - a['pin']
        if abs(d) < 0.02 or a['hr'] != b['hr'] or b['slate'] < '2026-10-28':
            continue
        side = 'over' if d > 0 else 'under'
        if b['hr'][side] < -200:
            continue
        pf = b['pin'] if d > 0 else 1 - b['pin']
        q13.append(dict(k=k, side=side, price=b['hr'][side], ev=pf * dec(b['hr'][side]) - 1, at=b['at'], slate=b['slate']))
q13.sort(key=lambda c: c['at'])
q13 = [c for c in q13 if not ((c['slate'], c['k'][2]) in seen13 or seen13.add((c['slate'], c['k'][2])))]
if '--md' in sys.argv:
    OUT.clear()
    fwd = [c for c in picks if c['slate'] >= FWD_FROM]
    nights = sorted({r['slate'] for rs in reads.values() for r in rs})
    print('')
    summary('Q19 all nights (seen, not a test)', picks)
    summary(f'Q19 FORWARD (>= {FWD_FROM})', fwd)
    summary('Q13 forward (>= 2026-10-28)', q13)
    md = [f"# Q19 + Q13 forward (research/code/q19_pin_steam.py --md). Nights {nights[0]}..{nights[-1]}. "
          "Bar: n >= 150 graded, units > 0 (Q19); Q13 as HYPOTHESES.md.", "", "```"] + OUT + ["```"]
    open(os.path.join(REPO, 'research/fwd/q19.md'), 'w').write("\n".join(md) + "\n")
