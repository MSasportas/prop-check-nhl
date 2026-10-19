"""Run 4 own ideas K10 (PP TOI change), K11 (opponent shot-blocking rate), K12 (shift-chart linemate quality).
Same logistic walk-forward as k_tests.py (Nov-Feb folds, T .01/.02/.03, lockbox never scored). Every input is from games dated
< the line's date. Optional placebo: python3 -I k_own.py [reps] shuffles the feature terms within date x line (train + test).
Inputs: R4/feat4.jsonl (feats4.py), R4/nhl/{toi_2526,realtime_2526,skater_2425,shared_2526}.jsonl, BOX boxscores."""
import bisect
import json
import os
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import rlib  # noqa: E402

R4 = os.environ.get("PC_R4_DIR", "/tmp/claude-0/-home-claude/ab9b3f07-215a-50c7-96a2-d84b6c4f2d08/scratchpad/r4")
BOX = os.environ.get("PC_BOX_DIR", "/tmp/claude-0/-home-claude/ab9b3f07-215a-50c7-96a2-d84b6c4f2d08/scratchpad/hist/raw/nhl")
NHL = os.path.join(R4, "nhl")
ROWS = [r for r in (json.loads(l) for l in open(os.path.join(R4, "feat4.jsonl"))) if r["date"] < rlib.LOCKBOX]
TS = (0.01, 0.02, 0.03)


def jl(fn):
    return [json.loads(l) for l in open(os.path.join(NHL, fn))]


def before(log, d):
    return log[:bisect.bisect_left([x[0] for x in log], d)]


# ---------- K10 PP TOI per game
pp = defaultdict(list)
for r in jl("toi_2526.jsonl"):
    pp[r["playerId"]].append((r["gameDate"][:10], (r.get("ppTimeOnIce") or 0) / 60.0))
for k in pp:
    pp[k].sort()


def k10(r):
    h = [x[1] for x in before(pp.get(r["pid"], []), r["date"])]
    base = h[-20:-3]
    if len(h) < 3 or len(base) < 5:
        return 0.0
    return float(np.mean(h[-3:]) - np.mean(base))


# ---------- K11 opponent shot-blocking rate
rt = jl("realtime_2526.jsonl")
blk = defaultdict(float)   # (gid, team) -> blocks by team
att = defaultdict(float)   # (gid, team) -> attempts by team
gdate = {}
for x in rt:
    blk[(x["gameId"], x["teamAbbrev"])] += x.get("blockedShots") or 0
    att[(x["gameId"], x["teamAbbrev"])] += x.get("totalShotAttempts") or 0
    gdate[(x["gameId"], x["teamAbbrev"])] = (x["gameDate"][:10], x["opponentTeamAbbrev"])
tg = defaultdict(list)   # team -> [(date, blocks, attempts faced)]
for (gid, t), (d, o) in gdate.items():
    if (gid, o) in att:
        tg[t].append((d, blk[(gid, t)], att[(gid, o)]))
for k in tg:
    tg[k].sort()


def opp_blk(r):
    h = before(tg.get(r["opp"], []), r["date"])[-20:]
    if len(h) < 5:
        return None
    return sum(x[1] for x in h) / sum(x[2] for x in h)


# ---------- K12 linemate quality
plog = defaultdict(list)   # pid -> [(date, sog, toi_min)]
for x in jl("skater_2425.jsonl"):
    toi = (x.get("timeOnIcePerGame") or 0) / 60.0
    if toi > 0:
        plog[x["playerId"]].append((x["gameDate"][:10], x.get("shots") or 0, toi))
games = {g["id"]: g for g in json.load(open(os.path.join(BOX, "games.json")))}
for gid, g in games.items():
    fp = os.path.join(BOX, "box", "%d.json" % gid)
    if gid // 10000 % 100 != 2 or not os.path.exists(fp):
        continue
    b = json.load(open(fp))
    if b.get("gameState") not in ("OFF", "FINAL") or "playerByGameStats" not in b:
        continue
    for side in ("awayTeam", "homeTeam"):
        for grp in ("forwards", "defense"):
            for p in b["playerByGameStats"][side].get(grp, []):
                mm, ss = (p.get("toi") or "0:00").split(":")
                toi = int(mm) + int(ss) / 60
                if toi > 0:
                    plog[p["playerId"]].append((g["date"], p.get("sog", 0), toi))
for k in plog:
    plog[k].sort()
_rate = {}


def rate(pid, d):
    key = (pid, d)
    if key not in _rate:
        h = before(plog.get(pid, []), d)[-40:]
        _rate[key] = (60.0 * sum(x[1] for x in h) / sum(x[2] for x in h)) if len(h) >= 5 and sum(x[2] for x in h) > 0 else None
    return _rate[key]


shared = defaultdict(list)   # pid -> [(date, {mate: secs})]
for g in jl("shared_2526.jsonl"):
    if len(g["skaters"]) > 40:   # one corrupt game (2025020565, 72 skaters) dropped
        continue
    m = defaultdict(dict)
    for a, b, s in g["pairs"]:
        m[a][b] = s
        m[b][a] = s
    for p, mates in m.items():
        shared[p].append((g["date"], mates))
for k in shared:
    shared[k].sort(key=lambda x: x[0])


def lq(mates, d):
    num = den = 0.0
    for j, s in mates.items():
        rj = rate(j, d)
        if rj is not None:
            num += s * rj
            den += s
    return num / den if den else None


def k12(r):
    h = before(shared.get(r["pid"], []), r["date"])
    if len(h) < 4:
        return 0.0
    last = lq(h[-1][1], r["date"])
    prev = [v for v in (lq(x[1], r["date"]) for x in h[-11:-1]) if v is not None]
    if last is None or len(prev) < 3:
        return 0.0
    return float(last - np.mean(prev))


# ---------- walk-forward (same as k_tests.walk, with placebo shuffle)
def base(r):
    return [1.0, float(r["line"] == 1.5), float(r["line"] >= 3.5), float(rlib.logit(r["f"]))]


def grade(r, side):
    return rlib.bet(r["gid"], r["date"], r[side], (r["actual"] > r["line"]) == (side == "over"), side=side, line=r["line"])


def walk(raw, prep=None, rng=None):
    """raw(r) -> list of raw values; prep(train) -> fn(values, r) -> terms (fold constants from training rows only)."""
    data = [r for r in ROWS if r["result"] == "OK"]
    vals = [raw(r) for r in data]
    if rng is not None:
        grp = defaultdict(list)
        for i, r in enumerate(data):
            grp[(r["date"], r["line"])].append(i)
        nv = list(vals)
        for idx in grp.values():
            perm = rng.permutation(idx)
            for a, b in zip(idx, perm):
                nv[a] = vals[b]
        vals = nv
    res = {T: [] for T in TS}
    weights = []
    for m in rlib.TEST_MONTHS:
        tri = [i for i, r in enumerate(data) if r["date"][:7] < m]
        tei = [i for i, r in enumerate(data) if r["date"][:7] == m]
        term = prep([data[i] for i in tri], [vals[i] for i in tri]) if prep else (lambda v, r: v)
        Xtr = np.array([base(data[i]) + term(vals[i], data[i]) for i in tri])
        mu, sd = Xtr[:, 4:].mean(0), Xtr[:, 4:].std(0)
        sd[sd == 0] = 1
        Xtr[:, 4:] = (Xtr[:, 4:] - mu) / sd
        w = rlib.fit_logit(Xtr, [data[i]["actual"] > data[i]["line"] for i in tri], l2=2.0)
        weights.append((m, np.round(w[4:], 3).tolist()))
        Xte = np.array([base(data[i]) + term(vals[i], data[i]) for i in tei])
        Xte[:, 4:] = (Xte[:, 4:] - mu) / sd
        for i, q in zip(tei, rlib.predict(w, Xte)):
            r = data[i]
            for side, ps in (("over", q), ("under", 1 - q)):
                if r[side] >= -200:
                    for T in TS:
                        if ps - rlib.be(r[side]) >= T:
                            res[T].append(grade(r, side))
    return res, weights


isD = lambda r: float(r["pos"] == "D")


def raw10(r):
    return k10(r)


def term10(v, r):
    return [v, v * isD(r)]


def raw11(r):
    a = r["att20"] if r.get("n20", 0) >= 5 else None
    return (a, opp_blk(r))


def prep11(tr, vals):
    lg = float(np.mean([v[1] for v in vals if v[1] is not None]))

    def t(v, r):
        a, ob = v
        x = 0.0 if a is None else a * (lg - (ob if ob is not None else lg))
        return [x, x * isD(r)]
    return t


def raw12(r):
    return k12(r)


IDEAS = [("K10", raw10, lambda tr, vals: term10), ("K11", raw11, prep11), ("K12", raw12, lambda tr, vals: term10)]

if __name__ == "__main__":
    reps = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    out = {}
    for name, raw, prep in IDEAS:
        vv = [raw(r) for r in ROWS if r["result"] == "OK"]
        nz = sum(1 for v in vv if (v != 0.0 if not isinstance(v, tuple) else v[0] is not None and v[1] is not None))
        res, wts = walk(raw, prep)
        print("%s feature coverage %d / %d; weights (std units) by fold %s" % (name, nz, len(vv), wts))
        for T in TS:
            b = res[T]
            s = rlib.summ(b)
            out["%s T%.2f" % (name, T)] = {"s": s, "months": rlib.by_month(b)}
            print("%-10s %s p1=%s | %s" % ("%s T%.2f" % (name, T), rlib.fmt(s), "%.3f" % s["p_one"] if s["n"] else "-",
                                          rlib.by_month(b)))
            if reps and s["n"] >= 300 and s["roi"] > 0:
                pl = []
                for k in range(reps):
                    rr, _ = walk(raw, prep, np.random.default_rng(5000 + k))
                    if rr[T]:
                        pl.append(sum(x["profit"] for x in rr[T]) / len(rr[T]))
                pl = np.array(pl)
                print("  placebo obs %+.1f%% mean %+.1f%% sd %.1f share >= obs %.3f (reps %d)" % (
                    100 * s["roi"], 100 * pl.mean(), 100 * pl.std(), (pl >= s["roi"]).mean(), len(pl)))
    json.dump(out, open(os.path.join(R4, "k_own_results.json"), "w"), indent=1, default=float)
