import json, glob, collections, sys, statistics as st

REPO = '/home/claude/prop-check-nhl'
THRESH = float(sys.argv[1]) if len(sys.argv) > 1 else 0.02


def dec(p):
    return 1 + (p / 100 if p > 0 else 100 / -p)


def fair_over(po, pu):
    a, b = 1 / dec(po), 1 / dec(pu)
    return a / (a + b)


def sides(outs, pid, line):
    s = {}
    for o in outs:
        if o.get('pid') == pid and o.get('line') == line:
            s[o['side']] = o['price']
    return s if len(s) == 2 else None


# results from shadow log
res = {}
for f in glob.glob(f'{REPO}/data/shadow/2026-*.json'):
    d = json.load(open(f))
    rows = d.get('rows') if isinstance(d, dict) else d
    for r in rows:
        if r.get('result'):
            res[(r['game_id'], r['market'], r['pid'], r['line'])] = r['result']

# reads per line
reads = collections.defaultdict(list)
for f in sorted(glob.glob(f'{REPO}/data/odds/2026-*.json')):
    d = json.load(open(f))
    for x in d['fetches']:
        pn = (x.get('others') or {}).get('pinnacle') or {}
        for mkt, mm in (x.get('markets') or {}).items():
            if mkt not in ('shots', 'saves'):
                continue
            hr_out = mm.get('outcomes', [])
            pn_out = (pn.get(mkt) or {}).get('outcomes', [])
            keys = {(o['pid'], o['line']) for o in hr_out if o.get('pid')}
            for pid, line in keys:
                h = sides(hr_out, pid, line)
                p = sides(pn_out, pid, line)
                if not h or not p:
                    continue
                reads[(x['game_id'], mkt, pid, line)].append(
                    dict(at=x['at'], pull=x['pull'], hr=h, pin=p, away=x['away'], home=x['home'],
                         name=next(o['name'] for o in hr_out if o.get('pid') == pid)))

intervals = []
for k, rs in reads.items():
    rs.sort(key=lambda r: r['at'])
    for a, b in zip(rs, rs[1:]):
        fa = fair_over(a['pin']['over'], a['pin']['under'])
        fb = fair_over(b['pin']['over'], b['pin']['under'])
        ha = fair_over(a['hr']['over'], a['hr']['under'])
        hb = fair_over(b['hr']['over'], b['hr']['under'])
        intervals.append(dict(k=k, t1=a['pull'], t2=b['pull'], dpin=fb - fa, dhr=hb - ha,
                              hr_same=(a['hr'] == b['hr']), hr_now=b['hr'], pin_now=fb,
                              who=f"{b['name']} {k[1]} {k[3]} ({b['away']}@{b['home']}) {b['at'][5:10]}"))

n = len(intervals)
big = [i for i in intervals if abs(i['dpin']) >= THRESH]
print(f'threshold {THRESH*100:.0f} pts of Pinnacle no-vig chance')
print('lines with Pinnacle+HR two-sided in 2+ reads:', len(reads), '| consecutive-read intervals:', n)
for m in ('shots', 'saves'):
    mi = [i for i in intervals if i['k'][1] == m]
    mb = [i for i in mi if abs(i['dpin']) >= THRESH]
    print(f'  {m}: intervals {len(mi)}, Pinnacle moved >= {THRESH*100:.0f} pts: {len(mb)} ({100*len(mb)/max(1,len(mi)):.1f}%)')
print('  by interval:', {f"{a}->{b}": sum(1 for i in big if (i['t1'], i['t2']) == (a, b)) for a, b in {(i['t1'], i['t2']) for i in intervals}})
print('  of the big Pinnacle moves, Hard Rock prices UNCHANGED:', sum(1 for i in big if i['hr_same']),
      '| HR fair moved < 1 pt:', sum(1 for i in big if abs(i['dhr']) < 0.01),
      '| HR moved same direction >= half:', sum(1 for i in big if i['dhr'] * i['dpin'] > 0 and abs(i['dhr']) >= abs(i['dpin']) / 2))


def grade(i, strict, cap=True):
    side = 'over' if i['dpin'] > 0 else 'under'
    price = i['hr_now'][side]
    if cap and price < -200:
        return None
    r = res.get(i['k'])
    if not r:
        return 'nores', side, price
    o = r.get(side)
    if o in ('VOID', 'PUSH', None):
        return 'push', side, price
    return o, side, price


def report(label, sel, cap=True):
    w = l = p = nr = 0
    units = 0.0
    ev = []
    skipped = 0
    rows = []
    for i in sel:
        g = grade(i, False, cap)
        if g is None:
            skipped += 1
            continue
        o, side, price = g
        pf = i['pin_now'] if side == 'over' else 1 - i['pin_now']
        ev.append(pf * dec(price) - 1)
        if o == 'nores':
            nr += 1
        elif o == 'push':
            p += 1
        elif o == 'W':
            w += 1; units += dec(price) - 1
        else:
            l += 1; units -= 1
        rows.append((i['who'], side, price, round(i['dpin'] * 100, 1), o))
    n = w + l
    print(f'{label}: {len(sel)-skipped} signals ({skipped} worse than -200 skipped) | graded {w}-{l}' + (f' push/void {p}' if p else '') +
          (f' | not yet graded {nr}' if nr else '') + f' | {units:+.2f}u' + (f' ({100*units/n:+.1f}% ROI)' if n else '') +
          (f' | avg EV vs Pinnacle-fair at HR price {100*st.mean(ev):+.1f}%' if ev else ''))
    return rows


print()
A = [i for i in big if i['hr_same']]
B = [i for i in big if not i['hr_same']]
rowsA = report('Pinnacle moved 2+, Hard Rock did NOT change', A)
report('Pinnacle moved 2+, Hard Rock changed too', B)
report('  ...HR changed but moved < 1 pt of fair', [i for i in B if abs(i['dhr']) < 0.01])
report('Pinnacle moved 2+, any HR (no -200 cap)', big, cap=False)
small = [i for i in intervals if abs(i['dpin']) < THRESH and i['hr_same']]
report('Control: Pinnacle flat, HR flat, bet the over?', [], True)
print()
for m in ('shots', 'saves'):
    report(f'{m} only, Pinnacle 2+ & HR flat', [i for i in A if i['k'][1] == m])
for s in ('over', 'under'):
    report(f'{s}-side signals only, Pinnacle 2+ & HR flat', [i for i in A if (i['dpin'] > 0) == (s == 'over')])
for a, b in sorted({(i['t1'], i['t2']) for i in A}):
    report(f'read {a}->{b}', [i for i in A if (i['t1'], i['t2']) == (a, b)])
print()
print('Signals (Pinnacle 2+ & HR flat):')
for r in sorted(rowsA, key=lambda r: r[0][-5:]):
    print('  ', *r)
