"""Run 15 tests CC1-CC3 (registered in HYPOTHESES.md run 15, commit 27eda384, before testing).
Inputs (scratch, PC_R14_DIR): h/work/shots45_lines.jsonl (hist tgz), nhl/skater_2526.jsonl (r14/fetch14.py, Feb 28 cut-off).
Lockbox rows (Mar 1+) are never built or scored. python3 -I cc15.py [placebo NAME T]"""
import contextlib, io, json, math, os, random, sys
from bisect import bisect_left
from collections import defaultdict
from datetime import date
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import rlib, wf  # noqa: E402

D = os.environ["PC_R14_DIR"]
S25 = [json.loads(l) for l in open(os.path.join(D, "nhl/skater_2526.jsonl"))]
S25 = [s for s in S25 if s["gameDate"][:10] < rlib.LOCKBOX]
dd = date.fromisoformat

tg = {}
for s in S25:
    k = (s["gameId"], s["teamAbbrev"])
    t = tg.setdefault(k, {"g": 0, "s": 0, "date": s["gameDate"][:10], "opp": s["opponentTeamAbbrev"]})
    t["g"] += s["goals"] or 0; t["s"] += s["shots"] or 0
tsched = defaultdict(list)  # team -> [(date, gid)]
for (gid, team), t in tg.items():
    tsched[team].append((t["date"], gid))
for v in tsched.values():
    v.sort()
tsd = {t: [x[0] for x in v] for t, v in tsched.items()}


def pdo(team, d):
    sch = tsched.get(team, []); i = bisect_left(tsd.get(team, []), d)
    G = S = GA = SA = 0; n = 0
    for _, gid in sch[max(0, i - 20):i]:
        me = tg[(gid, team)]; op = tg.get((gid, me["opp"]))
        if not op:
            continue
        G += me["g"]; S += me["s"]; GA += op["g"]; SA += op["s"]; n += 1
    if n < 5 or S == 0 or SA == 0:
        return 0.0
    return G / S + (1 - GA / SA) - 1


lines = [json.loads(l) for l in open(os.path.join(D, "h/work/shots45_lines.jsonl"))]
lines = [r for r in lines if r["date"] < rlib.LOCKBOX and r["over"] is not None and r["under"] is not None]
for r in lines:
    r["f"] = rlib.fair_prop(r["over"], r["under"]); r["lf"] = float(rlib.logit(r["f"]))

games = defaultdict(set); bydate = defaultdict(list)
for r in lines:
    games[r["date"]].add(r["gid"]); bydate[r["date"]].append(r)
dates = sorted(bydate)
sur, tsur = {}, {}
for i, d in enumerate(dates):
    g = [r for r in bydate[d] if r["result"] == "OK"]
    sur[d] = (np.mean([r["actual"] > r["line"] for r in g]) - np.mean([r["f"] for r in g])) if g else 0.0
    bt = defaultdict(list)
    for r in g:
        bt[r["team"]].append(r)
    tsur[d] = {t: (np.mean([r["actual"] > r["line"] for r in v]) - np.mean([r["f"] for r in v])) for t, v in bt.items() if len(v) >= 3}

for r in lines:
    d = r["date"]
    r["nG"] = float(len(games[d])); r["lnG"] = math.log(r["nG"]); r["lnGf"] = r["lnG"] * r["lf"]
    j = bisect_left(dates, d); r["sur"] = r["tsur"] = 0.0
    if j > 0 and (dd(d) - dd(dates[j - 1])).days <= 3:
        p = dates[j - 1]; r["sur"] = float(sur[p]); r["tsur"] = float(tsur[p].get(r["team"], 0.0))
    r["po"] = pdo(r["team"], d); r["pp"] = pdo(r["opp"], d)

feats = {"CC1": lambda r: [r["lnG"], r["lnGf"]], "CC2": lambda r: [r["sur"], r["tsur"]], "CC3": lambda r: [r["po"], r["pp"]]}
KEYS = {"CC1": ["lnG", "lnGf"], "CC2": ["sur", "tsur"], "CC3": ["po", "pp"]}


def fixed(name, rule):
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
        rr = rlib.summ(wf.run(name, lines, feats[name], Ts=(T,), verbose=False)[T])["roi"]
        rng = random.Random(7); out = []; grp = defaultdict(list)
        for r in lines:
            grp[(r["date"], r["line"])].append(r)
        ks = KEYS[name]; orig = {k: [r[k] for r in lines] for k in ks}
        for it in range(200):
            for g in grp.values():
                idx = list(range(len(g))); rng.shuffle(idx)
                vals = {k: [g[j][k] for j in idx] for k in ks}
                for j, r in enumerate(g):
                    for k in ks:
                        r[k] = vals[k][j]
            with contextlib.redirect_stdout(io.StringIO()):
                b = wf.run(name, lines, feats[name], Ts=(T,), verbose=False)[T]
            out.append(rlib.summ(b)["roi"] or 0.0)
            for k in ks:
                for r, x in zip(lines, orig[k]):
                    r[k] = x
        out = np.array(out)
        print("placebo %s T=%.2f real %+.2f%% shuffled mean %+.2f%% sd %.2f >= real %d/200" % (
            name, T, 100 * rr, 100 * out.mean(), 100 * out.std(), int((out >= rr).sum())))
        sys.exit()
    te = [r for r in lines if r["date"][:7] in rlib.TEST_MONTHS and r["result"] == "OK"]
    print("graded Nov-Feb lines", len(te))
    for k in ["nG", "sur", "tsur", "po", "pp"]:
        a = np.array([r[k] for r in te], float)
        print("feature %s mean %.3f sd %.3f nonzero %d" % (k, a.mean(), a.std(), int((a != 0).sum())))
    for n in ("CC1", "CC2", "CC3"):
        wf.run(n, lines, feats[n])
    fixed("CC1r UNDER on slates with >= 11 games", lambda r: "under" if r["nG"] >= 11 else None)
    fixed("CC2r UNDER when last slate's surprise >= +0.08", lambda r: "under" if r["sur"] >= 0.08 else None)
    fixed("CC3r OVER when own team PDO <= -0.03", lambda r: "over" if r["po"] <= -0.03 else None)
