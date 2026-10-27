"""Run 12 tests Z1-Z4 (registered in HYPOTHESES.md run 12, commit 3100297, before testing).
Inputs (scratch, PC_R12_DIR): h/work/shots45_lines.jsonl (hist tgz), nhl/skater_2425|2526.jsonl + nhl/realtime_2425|2526.jsonl
(r12/fetch12.py, Feb 28 cut-off). Lockbox rows (Mar 1+) are never built or scored. python3 -I z12.py [placebo NAME T]"""
import contextlib, io, json, os, random, sys
from bisect import bisect_left
from collections import defaultdict
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import rlib, wf  # noqa: E402

D = os.environ["PC_R12_DIR"]
jl = lambda p: [json.loads(l) for l in open(os.path.join(D, p))]
cut = lambda L: [s for s in L if s["gameDate"][:10] < rlib.LOCKBOX]
S24, S25 = jl("nhl/skater_2425.jsonl"), cut(jl("nhl/skater_2526.jsonl"))
miss = {}
for s in jl("nhl/realtime_2425.jsonl") + cut(jl("nhl/realtime_2526.jsonl")):
    miss[(s["playerId"], s["gameId"])] = s["missedShots"] or 0

# per player: (date, sog, missed or None, toi_min or None, season)
pl = defaultdict(list)
for season, L in (("24", S24), ("25", S25)):
    for s in L:
        pl[s["playerId"]].append((s["gameDate"][:10], s["shots"] or 0, miss.get((s["playerId"], s["gameId"])),
                                  (s["timeOnIcePerGame"] or 0) / 60.0, season))
for v in pl.values():
    v.sort(key=lambda x: x[0])
pld = {p: [x[0] for x in v] for p, v in pl.items()}

# team games 2025-26
tg = defaultdict(set); sf = defaultdict(lambda: defaultdict(int))
for s in S25:
    tg[s["teamAbbrev"]].add((s["gameDate"][:10], s["gameId"])); sf[s["gameId"]][s["teamAbbrev"]] += s["shots"] or 0
tg = {t: sorted(v) for t, v in tg.items()}; tgd = {t: [x[0] for x in v] for t, v in tg.items()}
gopp = {}
for g, d in sf.items():
    ts = list(d)
    if len(ts) == 2:
        gopp[(g, ts[0])] = ts[1]; gopp[(g, ts[1])] = ts[0]


def team_form(t, d, against):
    L = tg.get(t, []); i = bisect_left(tgd.get(t, []), d)
    if i < 10:
        return 0.0
    vals = []
    for _, g in L[:i]:
        o = gopp.get((g, t))
        if o is None:
            continue
        vals.append(sf[g][o] if against else sf[g][t])
    if len(vals) < 10:
        return 0.0
    return float(np.mean(vals[-5:]) - np.mean(vals))


lines = [json.loads(l) for l in open(os.path.join(D, "h/work/shots45_lines.jsonl"))]
lines = [r for r in lines if r["date"] < rlib.LOCKBOX and r["over"] is not None and r["under"] is not None]
# Z4 prior main lines per player: one per date, f nearest .5
best = {}
for r in lines:
    f = rlib.fair_prop(r["over"], r["under"]); k = (r["pid"], r["date"])
    if k not in best or abs(f - .5) < abs(best[k][0] - .5):
        best[k] = (f, r["line"])
hist = defaultdict(list)
for (p, d), (f, ln) in best.items():
    hist[p].append((d, ln))
for v in hist.values():
    v.sort()
histd = {p: [x[0] for x in v] for p, v in hist.items()}

cvs_oct = []
for r in lines:
    r["f"] = rlib.fair_prop(r["over"], r["under"]); r["lf"] = float(rlib.logit(r["f"]))
    r["tsf5"] = team_form(r["team"], r["date"], False)
    r["osa5"] = team_form(r["opp"], r["date"], True)
    v = pl.get(r["pid"], []); i = bisect_left(pld.get(r["pid"], []), r["date"])
    prior = v[:i]; last = prior[-10:]
    # Z2
    sm = [(x[1], x[2]) for x in last if x[2] is not None]
    allp = [(x[1], x[2]) for x in prior if x[2] is not None]
    s10, m10 = sum(a for a, _ in sm), sum(b for _, b in sm)
    sL, mL = sum(a for a, _ in allp), sum(b for _, b in allp)
    if s10 + m10 >= 10 and sL + mL > 0:
        r["dev"] = s10 / (s10 + m10) - sL / (sL + mL)
        r["luck"] = r["dev"] * (s10 + m10) / len(sm)
    else:
        r["dev"] = r["luck"] = 0.0
    # Z3
    t25 = [x[3] for x in prior if x[4] == "25"][-10:]
    r["cv"] = float(np.std(t25) / np.mean(t25)) if len(t25) >= 5 and np.mean(t25) > 0 else None
    if r["cv"] is not None and r["date"] < "2025-11-01":
        cvs_oct.append(r["cv"])
    # Z4
    h = hist.get(r["pid"], []); j = bisect_left(histd.get(r["pid"], []), r["date"])
    k = 0
    for _, ln in reversed(h[:j]):
        if ln != r["line"]:
            break
        k += 1
    r["k4"] = float(k >= 4)
    r["gap"] = float(np.mean([x[1] for x in last]) - r["line"]) if len(last) >= 5 else 0.0
CV0 = float(np.mean(cvs_oct))  # fill value: Oct 2025 rows only (never a test month)
for r in lines:
    if r["cv"] is None:
        r["cv"] = CV0

feats = {
    "Z1": lambda r: [r["tsf5"], r["osa5"]],
    "Z2": lambda r: [r["luck"], r["dev"]],
    "Z3": lambda r: [r["cv"], r["cv"] * r["lf"]],
    "Z4": lambda r: [r["gap"] * r["k4"], r["k4"], r["gap"]],
}
KEYS = ["tsf5", "osa5", "luck", "dev", "cv", "k4", "gap"]


def fixed(name, rule):
    """rule(r) -> 'over' / 'under' / None"""
    b = []
    for r in lines:
        if r["date"][:7] not in rlib.TEST_MONTHS or r["result"] != "OK" or not r["ok"]:
            continue
        side = rule(r)
        if side is None or r[side] < -200:
            continue
        b.append(rlib.bet(r["gid"], r["date"], r[side], (r["actual"] > r["line"]) == (side == "over"), side=side, line=r["line"]))
    s = rlib.summ(b)
    print("%s %s | %s | p_one %s" % (name, rlib.fmt(s), rlib.by_month(b), s.get("p_one")))
    return b


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "placebo":
        name, T = sys.argv[2], float(sys.argv[3])
        real = wf.run(name, lines, feats[name], Ts=(T,), verbose=False)[T]
        rr = rlib.summ(real)["roi"]
        rng = random.Random(7); out = []
        grp = defaultdict(list)
        for r in lines:
            grp[(r["date"], r["line"])].append(r)
        orig = {k: [r[k] for r in lines] for k in KEYS}
        for it in range(200):
            for g in grp.values():
                idx = list(range(len(g))); rng.shuffle(idx)
                vals = {k: [g[j][k] for j in idx] for k in KEYS}
                for j, r in enumerate(g):
                    for k in KEYS:
                        r[k] = vals[k][j]
            with contextlib.redirect_stdout(io.StringIO()):
                b = wf.run(name, lines, feats[name], Ts=(T,), verbose=False)[T]
            out.append(rlib.summ(b)["roi"] or 0.0)
            for k in KEYS:
                for r, x in zip(lines, orig[k]):
                    r[k] = x
        out = np.array(out)
        print("placebo %s T=%.2f real %+.2f%% shuffled mean %+.2f%% sd %.2f >= real %d/200" % (
            name, T, 100 * rr, 100 * out.mean(), 100 * out.std(), int((out >= rr).sum())))
        sys.exit()
    te = [r for r in lines if r["date"][:7] in rlib.TEST_MONTHS and r["result"] == "OK"]
    print("graded Nov-Feb lines", len(te), "| cv fill (Oct mean)", round(CV0, 3))
    for k in KEYS:
        a = np.array([r[k] for r in te], float)
        print("feature %s mean %.3f sd %.3f nonzero %d" % (k, a.mean(), a.std(), int((a != 0).sum())))
    for n in ("Z1", "Z2", "Z3", "Z4"):
        wf.run(n, lines, feats[n])
    fixed("Z1r OVER tsf5+osa5>=5", lambda r: "over" if r["tsf5"] + r["osa5"] >= 5 else None)
    fixed("Z2r UNDER luck>=0.4", lambda r: "under" if r["luck"] >= 0.4 else None)
    fixed("Z4r stuck k>=4 |gap|>=0.7", lambda r: None if not r["k4"] else ("over" if r["gap"] >= 0.7 else ("under" if r["gap"] <= -0.7 else None)))
