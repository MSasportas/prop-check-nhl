"""Run 6 tests N1, N1b, N2, N3, N4, N5 (registered in HYPOTHESES.md run 6 before testing).
Inputs (scratch, PC_R6_DIR): h/work/shots45_lines.jsonl (hist tgz), add/h2h_rows.jsonl (addon tgz), nhl/*.jsonl (fetch6.py).
Lockbox rows (Mar 1+) are never built or scored. python3 -I n6.py [placebo] -> prints results, writes PC_R6_DIR/n6_out.json"""
import json
import math
import os
import sys
from bisect import bisect_left
from collections import defaultdict
from datetime import datetime

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import rlib  # noqa: E402

D = os.environ["PC_R6_DIR"]
TS = (0.01, 0.02, 0.03)
OUT = {}


def jl(p):
    return [json.loads(l) for l in open(p)]


# ---------------- logs
team_of = {}            # (gid, opp_abbrev_seen_by_other) helper
tg = defaultdict(list)  # team abbrev -> [(date, gid, SF, SA)]
trows = jl(os.path.join(D, "nhl/team_2425.jsonl")) + jl(os.path.join(D, "nhl/team_2526.jsonl"))
by_gid = defaultdict(list)
for t in trows:
    by_gid[t["gameId"]].append(t)
for gid, two in by_gid.items():
    if len(two) != 2:
        continue
    for a, b in ((two[0], two[1]), (two[1], two[0])):
        ab = b["opponentTeamAbbrev"]
        tg[ab].append((a["gameDate"], gid, a["shotsForPerGame"], a["shotsAgainstPerGame"]))
team_sf = {}
for ab, L in tg.items():
    L.sort()
    for d, gid, sf, sa in L:
        team_sf[(gid, ab)] = sf
tdates = {ab: [x[0] for x in L] for ab, L in tg.items()}

sk = defaultdict(list)  # pid -> [(date, gid, team, shots, homeRoad)]
for p in ("nhl/skater_2425.jsonl", "nhl/skater_2526.jsonl"):
    for s in jl(os.path.join(D, p)):
        sk[s["playerId"]].append((s["gameDate"], s["gameId"], s["teamAbbrev"], s["shots"], s["homeRoad"]))
for L in sk.values():
    L.sort()
skd = {p: [x[0] for x in L] for p, L in sk.items()}

gl = defaultdict(list)  # goalie pid -> [(date, gid, team, started, saves, sa)]
starter = {}            # (gid, team) -> goalie pid
for p in ("nhl/goalie_2425.jsonl", "nhl/goalie_2526.jsonl"):
    for g in jl(os.path.join(D, p)):
        gl[g["playerId"]].append((g["gameDate"], g["gameId"], g["teamAbbrev"], g["gamesStarted"], g["saves"] or 0,
                                  g["shotsAgainst"] or 0))
        if g["gamesStarted"] == 1:
            starter[(g["gameId"], g["teamAbbrev"])] = g["playerId"]
for L in gl.values():
    L.sort()
gld = {p: [x[0] for x in L] for p, L in gl.items()}


def prior(lst, dates, d):
    return lst[:bisect_left(dates, d)]


def team_E(team, opp, d):
    a = prior(tg.get(team, []), tdates.get(team, []), d)[-20:]
    b = prior(tg.get(opp, []), tdates.get(opp, []), d)[-20:]
    if len(a) < 5 or len(b) < 5:
        return None
    return 0.5 * (sum(x[2] for x in a) / len(a) + sum(x[3] for x in b) / len(b))


def share(pid, team, d):
    g = [x for x in prior(sk.get(pid, []), skd.get(pid, []), d) if x[2] == team][-20:]
    g = [x for x in g if (x[1], team) in team_sf]
    if len(g) < 5:
        return None
    tot = sum(team_sf[(x[1], team)] for x in g)
    return sum(x[3] for x in g) / tot if tot > 0 else None


def homeroad(pid, d):
    g = prior(sk.get(pid, []), skd.get(pid, []), d)
    h = [x[3] for x in g if x[4] == "H"]
    r = [x[3] for x in g if x[4] == "R"]
    if len(h) < 3 or len(r) < 3:
        return 0.0
    w = len(h) * len(r) / (len(h) + len(r))
    return (sum(h) / len(h) - sum(r) / len(r)) * w / (w + 10.0)


def goalie(gid, team, d):
    """(saves, shots against) over the starter's prior games, backup flag."""
    gp = starter.get((gid, team))
    if gp is None:
        return None
    pr = prior(gl[gp], gld[gp], d)
    sv, sa = sum(x[4] for x in pr), sum(x[5] for x in pr)
    starts = sum(x[3] for x in pr if x[0] >= "2025-07-01" and x[2] == team)
    tgames = sum(1 for x in prior(tg.get(team, []), tdates.get(team, []), d) if x[0] >= "2025-07-01")
    backup = float(tgames >= 5 and starts / tgames < 0.4)
    return sv, sa, backup


def pois_sf(L, m):
    k = int(math.floor(L))
    return 1 - sum(math.exp(-m + j * math.log(m) - math.lgamma(j + 1)) for j in range(k + 1))


def solve_m(L, f):
    lo, hi = 0.01, 20.0
    for _ in range(50):
        mid = (lo + hi) / 2
        if pois_sf(L, mid) < f:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


# ---------------- moneyline
ml = defaultdict(list)
for h in jl(os.path.join(D, "add/h2h_rows.jsonl")):
    if h.get("cons_h") is not None:
        ml[h["gid"]].append((datetime.fromisoformat(h["snap"].replace("Z", "+00:00")), h["cons_h"]))

# ---------------- lines + features
lines = [r for r in jl(os.path.join(D, "h/work/shots45_lines.jsonl"))
         if r["date"] < rlib.LOCKBOX and r["over"] is not None and r["under"] is not None]
for r in lines:
    r["f"] = rlib.fair_prop(r["over"], r["under"])
grp = defaultdict(list)
for r in lines:
    grp[(r["gid"], r["team"])].append(r)
for key, L in grp.items():
    best = {}
    for r in L:
        if r["pid"] not in best or abs(r["f"] - .5) < abs(best[r["pid"]]["f"] - .5):
            best[r["pid"]] = r
    reps = list(best.values())
    for r in reps:
        r["_m"] = solve_m(r["line"], r["f"])
    S = sum(r["_m"] for r in reps)
    k = len(reps)
    d, team, opp = L[0]["date"], L[0]["team"], L[0]["opp"]
    E = team_E(team, opp, d)
    hs = {r["pid"]: share(r["pid"], team, d) for r in reps}
    sub = [r for r in reps if hs[r["pid"]]]          # players with a history share (>= 5 games); the rest dropped
    hsum = sum(hs[r["pid"]] for r in sub)
    Ssub = sum(r["_m"] for r in sub)
    for r in L:
        r["n1"] = [math.log(E) - math.log(S), float(k)] if (E and k >= 4) else None
        h = hs.get(r["pid"])
        r["n1b"] = [math.log((h / hsum) / (best[r["pid"]]["_m"] / Ssub))] if (len(sub) >= 4 and h) else None
for r in lines:
    d = r["date"]
    og = goalie(r["gid"], r["opp"], d)
    mg = goalie(r["gid"], r["team"], d)
    r["n2raw"] = (og, mg) if og and mg else None
    bo, bu = rlib.be(r["over"]), rlib.be(r["under"])
    r["n3"] = [(bo - r["f"]) - (bu - (1 - r["f"])), bo + bu - 1]
    r["n4"] = [homeroad(r["pid"], d) * (1 if r["home"] else -1)]
    at = datetime.fromisoformat(r["at"])
    snaps = [x for x in ml.get(r["gid"], []) if x[0] <= at]
    if snaps:
        ch = max(snaps)[1]
        pw = ch if r["home"] else 1 - ch
        r["n5"] = [0.5 - abs(pw - 0.5)]
    else:
        r["n5"] = None
ROWS = lines


def base(r):
    return [1.0, float(r["line"] == 1.5), float(r["line"] >= 3.5), float(rlib.logit(r["f"]))]


def grade(r, side):
    win = (r["actual"] > r["line"]) == (side == "over")
    return rlib.bet(r["gid"], r["date"], r[side], win, side=side, line=r["line"], pid=r["pid"])


def report(name, bets, quiet=False):
    s2 = rlib.summ([b for b in bets if b["month"] >= "2025-11"])
    if not quiet:
        print("%-10s Nov-Feb %s p1=%s | %s" % (name, rlib.fmt(s2), "%.3f" % s2["p_one"] if s2["n"] else "-",
                                              rlib.by_month(bets)))
        OUT[name] = {"nov_feb": s2, "months": rlib.by_month(bets)}
    return s2


def walk(name, featfn, need, prep=None, shuffle_rng=None, quiet=False):
    data = [r for r in ROWS if need(r) and r["result"] == "OK"]
    res = {T: [] for T in TS}
    weights = []
    for m in rlib.TEST_MONTHS:
        tr = [r for r in data if r["date"][:7] < m]
        te = [r for r in data if r["date"][:7] == m]
        ctx = prep(tr) if prep else {}
        Ftr = np.array([featfn(r, ctx) for r in tr], float)
        Fte = np.array([featfn(r, ctx) for r in te], float)
        if shuffle_rng is not None:   # placebo: shuffle features within date x line
            for F, rows in ((Ftr, tr), (Fte, te)):
                cell = defaultdict(list)
                for i, r in enumerate(rows):
                    cell[(r["date"], r["line"])].append(i)
                for idx in cell.values():
                    F[idx] = F[shuffle_rng.permutation(idx)]
        mu, sd = Ftr.mean(0), Ftr.std(0)
        sd[sd == 0] = 1
        Xtr = np.hstack([np.array([base(r) for r in tr]), (Ftr - mu) / sd])
        Xte = np.hstack([np.array([base(r) for r in te]), (Fte - mu) / sd])
        w = rlib.fit_logit(Xtr, [r["actual"] > r["line"] for r in tr], l2=2.0)
        weights.append((m[5:], np.round(w[4:], 3).tolist()))
        p = rlib.predict(w, Xte)
        for r, q in zip(te, p):
            for T in TS:
                for side, ps in (("over", q), ("under", 1 - q)):
                    if r[side] >= -200 and ps - rlib.be(r[side]) >= T:
                        res[T].append(grade(r, side))
    if not quiet:
        print("%s n rows %d; weights (std units) by fold: %s" % (name, len(data), weights))
    return {T: report("%s T%.2f" % (name, T), res[T], quiet) for T in TS}


def prep2(tr):
    v = [x["n2raw"][0][0] / x["n2raw"][0][1] for x in tr if x["n2raw"][0][1] > 0]
    return {"lg": sum(v) / len(v)}


def f2(r, c):
    (sv, sa, ob), (_, _, mb) = r["n2raw"]
    lg = c["lg"]
    return [(sv + 300 * lg) / (sa + 300) - lg, ob, mb]


TESTS = [
    ("N1", lambda r, c: r["n1"], lambda r: r["n1"] is not None, None),
    ("N1b", lambda r, c: r["n1b"], lambda r: r["n1b"] is not None, None),
    ("N2", f2, lambda r: r["n2raw"] is not None, prep2),
    ("N3", lambda r, c: r["n3"], lambda r: True, None),
    ("N4", lambda r, c: r["n4"], lambda r: True, None),
    ("N5", lambda r, c: r["n5"], lambda r: r["n5"] is not None, None),
]

if __name__ == "__main__":
    print("rows (two-way, pre-lockbox):", len(ROWS))
    cands = []
    for name, ff, need, prep in TESTS:
        s = walk(name, ff, need, prep)
        for T, st in s.items():
            if st["n"] >= 300 and st["roi"] > 0:
                cands.append((name, ff, need, prep, T, st))
    for name, ff, need, prep, T, st in cands:   # placebo only for positive n >= 300 (registered)
        rng = np.random.default_rng(7)
        pl = [walk(name, ff, need, prep, shuffle_rng=rng, quiet=True)[T]["roi"] or 0 for _ in range(200)]
        pl = np.array(pl)
        print("PLACEBO %s T%.2f real %+.1f%% | placebo mean %+.1f%% sd %.1f, share >= real %.3f" % (
            name, T, 100 * st["roi"], 100 * pl.mean(), 100 * pl.std(), (pl >= st["roi"]).mean()))
        OUT["placebo %s T%.2f" % (name, T)] = {"real": st["roi"], "mean": float(pl.mean()), "sd": float(pl.std()),
                                               "share_ge": float((pl >= st["roi"]).mean())}
    json.dump(OUT, open(os.path.join(D, "n6_out.json"), "w"), indent=1, default=float)
