"""Run 13 tests AA1-AA4 (registered in HYPOTHESES.md run 13, commit 9bc8805, before testing).
Inputs (scratch, PC_R13_DIR): h/work/shots45_lines.jsonl (hist tgz), nhl/skater_2526.jsonl + nhl/goalie_2425|2526.jsonl
(r13/fetch13.py, Feb 28 cut-off). Lockbox rows (Mar 1+) are never built or scored. python3 -I aa13.py [placebo NAME T]"""
import contextlib, io, json, os, random, sys
from bisect import bisect_left
from collections import defaultdict
from datetime import date, timedelta
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import rlib, wf  # noqa: E402

D = os.environ["PC_R13_DIR"]
jl = lambda p: [json.loads(l) for l in open(os.path.join(D, p))]
cut = lambda L: [s for s in L if s["gameDate"][:10] < rlib.LOCKBOX]
S25 = cut(jl("nhl/skater_2526.jsonl"))
G24, G25 = jl("nhl/goalie_2425.jsonl"), cut(jl("nhl/goalie_2526.jsonl"))
dd = lambda s: date.fromisoformat(s)

# skater TOI logs 2025-26
pl = defaultdict(list)
for s in S25:
    pl[s["playerId"]].append((s["gameDate"][:10], (s["timeOnIcePerGame"] or 0) / 60.0))
for v in pl.values():
    v.sort()
pld = {p: [x[0] for x in v] for p, v in pl.items()}

# goalies: per goalie (date, sa, sv); starters per (gameId, team); team game dates 2025-26
gl = defaultdict(list)
for g in G24 + G25:
    gl[g["playerId"]].append((g["gameDate"][:10], g["shotsAgainst"] or 0, g["saves"] or 0))
for v in gl.values():
    v.sort()
gld = {p: [x[0] for x in v] for p, v in gl.items()}
starter = {}
gstarts = defaultdict(list)  # (team) -> [(date, goalie)] 2025-26 starts
for g in G25:
    if g["gamesStarted"] == 1:
        starter[(g["gameId"], g["teamAbbrev"])] = g["playerId"]
        gstarts[g["teamAbbrev"]].append((g["gameDate"][:10], g["playerId"]))
for v in gstarts.values():
    v.sort()
gsd = {t: [x[0] for x in v] for t, v in gstarts.items()}

lines = [json.loads(l) for l in open(os.path.join(D, "h/work/shots45_lines.jsonl"))]
lines = [r for r in lines if r["date"] < rlib.LOCKBOX and r["over"] is not None and r["under"] is not None]

# AA2 board depth at -45 (shots45 = the -45 snapshot)
nT = defaultdict(set); nG = defaultdict(set)
for r in lines:
    nT[(r["gid"], r["team"])].add(r["pid"]); nG[r["gid"]].add(r["pid"])
team_dates = defaultdict(dict)
for (g, t), s in nT.items():
    pass
for r in lines:
    team_dates[r["team"]][r["date"]] = len(nT[(r["gid"], r["team"])])
tdl = {t: sorted(v.items()) for t, v in team_dates.items()}

# league save % mean (training-row convention: Oct 2025 + 2024-25 shots, i.e. never a test month)
sa0 = sum(g["shotsAgainst"] or 0 for g in G24) + sum(g["shotsAgainst"] or 0 for g in G25 if g["gameDate"] < "2025-11-01")
sv0 = sum(g["saves"] or 0 for g in G24) + sum(g["saves"] or 0 for g in G25 if g["gameDate"] < "2025-11-01")
LSV = sv0 / sa0

nostarter = 0
for r in lines:
    r["f"] = rlib.fair_prop(r["over"], r["under"]); r["lf"] = float(rlib.logit(r["f"]))
    d = r["date"]
    # AA1
    v = pl.get(r["pid"], []); i = bisect_left(pld.get(r["pid"], []), d); prior = v[:i]
    r["load"] = r["g4"] = r["lastx"] = 0.0
    if len(prior) >= 5:
        avg = float(np.mean([x[1] for x in prior]))
        lo = (dd(d) - timedelta(days=3)).isoformat()
        rec = [x for x in prior if x[0] >= lo]
        r["g4"] = float(len(rec) >= 2)
        r["load"] = sum(x[1] for x in rec) - len(rec) * avg
        if prior[-1][0] == (dd(d) - timedelta(days=1)).isoformat():
            r["lastx"] = prior[-1][1] - avg
    # AA2
    r["nG"] = float(len(nG[r["gid"]]))
    pr = [n for dt, n in tdl[r["team"]] if dt < d]
    r["rel"] = float(len(nT[(r["gid"], r["team"])]) - np.mean(pr)) if pr else 0.0
    # AA3
    gk = starter.get((r["gid"], r["team"]))
    r["osv"] = r["obk"] = 0.0
    if gk is None:
        nostarter += 1
    else:
        h = gl.get(gk, []); j = bisect_left(gld.get(gk, []), d)
        sa = sum(x[1] for x in h[:j]); sv = sum(x[2] for x in h[:j])
        r["osv"] = (sv / sa - LSV) if sa >= 300 else 0.0
        st = gstarts.get(r["team"], []); k = bisect_left(gsd.get(r["team"], []), d)
        if k >= 10:
            mine = sum(1 for x in st[:k] if x[1] == gk)
            r["obk"] = float(mine / k < 0.40)
    # AA4
    r["isD"] = float(r.get("pos") == "D")
    r["l25"] = float(r["line"] >= 2.5)

feats = {
    "AA1": lambda r: [r["load"], r["g4"], r["lastx"]],
    "AA2": lambda r: [r["nG"], r["rel"], r["rel"] * r["lf"]],
    "AA3": lambda r: [r["osv"], r["obk"]],
    "AA4": lambda r: [r["isD"], r["isD"] * r["lf"], r["isD"] * r["l25"]],
}
KEYS = {"AA1": ["load", "g4", "lastx"], "AA2": ["nG", "rel"], "AA3": ["osv", "obk"], "AA4": ["isD"]}


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
        real = wf.run(name, lines, feats[name], Ts=(T,), verbose=False)[T]
        rr = rlib.summ(real)["roi"]
        rng = random.Random(7); out = []
        grp = defaultdict(list)
        for r in lines:
            grp[(r["date"], r["line"])].append(r)
        ks = KEYS[name]
        orig = {k: [r[k] for r in lines] for k in ks}
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
    print("graded Nov-Feb lines", len(te), "| lines without a starter found", nostarter, "| league sv%", round(LSV, 4))
    for k in ["load", "g4", "lastx", "nG", "rel", "osv", "obk", "isD"]:
        a = np.array([r[k] for r in te], float)
        print("feature %s mean %.3f sd %.3f nonzero %d" % (k, a.mean(), a.std(), int((a != 0).sum())))
    for n in ("AA1", "AA2", "AA3", "AA4"):
        wf.run(n, lines, feats[n])
    fixed("AA1r UNDER 3rd game in 4 nights", lambda r: "under" if r["g4"] else None)
    fixed("AA3r OVER own backup goalie", lambda r: "over" if r["obk"] else None)
