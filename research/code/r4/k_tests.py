"""Run 4 tests K1-K6, K9 (logistic walk-forward + fixed rules) on R4/feat4.jsonl. Lockbox rows (Mar 1+) are never scored.
python3 -I k_tests.py  -> prints results, writes R4/k_bets.json"""
import json
import math
import os
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import rlib  # noqa: E402

R4 = os.environ.get("PC_R4_DIR", "/tmp/claude-0/-home-claude/ab9b3f07-215a-50c7-96a2-d84b6c4f2d08/scratchpad/r4")
ALL = [json.loads(l) for l in open(os.path.join(R4, "feat4.jsonl"))]
ROWS = [r for r in ALL if r["date"] < rlib.LOCKBOX]
TS = (0.01, 0.02, 0.03)
OUT = {}


def nb_sf(L, m, v):
    """P(X > L) for count X with mean m, variance m*v (NB; Poisson if v <= 1.01)."""
    k = int(math.floor(L))
    if v <= 1.01:
        c = sum(math.exp(-m + j * math.log(m) - math.lgamma(j + 1)) for j in range(k + 1))
    else:
        r = m / (v - 1.0)
        p = r / (r + m)
        c = sum(math.exp(math.lgamma(j + r) - math.lgamma(r) - math.lgamma(j + 1) + r * math.log(p) + j * math.log(1 - p))
                for j in range(k + 1))
    return 1 - c


def solve_m(L, f, v):
    lo, hi = 0.01, 15.0
    for _ in range(40):
        mid = (lo + hi) / 2
        if nb_sf(L, mid, v) < f:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def base(r):
    return [1.0, float(r["line"] == 1.5), float(r["line"] >= 3.5), float(rlib.logit(r["f"]))]


def grade(r, side):
    pr = r[side]
    win = (r["actual"] > r["line"]) == (side == "over")
    return rlib.bet(r["gid"], r["date"], pr, win, side=side, line=r["line"], pid=r["pid"])


def report(name, bets):
    s = rlib.summ(bets)
    nov_feb = [b for b in bets if b["month"] >= "2025-11"]
    s2 = rlib.summ(nov_feb)
    line = "%-10s Nov-Feb %s p1=%s | %s" % (name, rlib.fmt(s2), "%.3f" % s2["p_one"] if s2["n"] else "-", rlib.by_month(bets))
    print(line)
    OUT[name] = {"nov_feb": {k: v for k, v in s2.items()}, "all": {k: v for k, v in s.items()}, "months": rlib.by_month(bets)}
    return s2


def walk(name, featfn, need=lambda r: True, prep=None, placebo=0, cols=None):
    """featfn(r, ctx) -> list of extra terms. prep(train) -> ctx (fold-level constants from training rows only)."""
    data = [r for r in ROWS if need(r)]
    res = {T: [] for T in TS}
    weights = []
    for m in rlib.TEST_MONTHS:
        tr = [r for r in data if r["date"][:7] < m and r["result"] == "OK"]
        te = [r for r in data if r["date"][:7] == m and r["result"] == "OK"]
        ctx = prep(tr) if prep else {}
        Xtr = np.array([base(r) + featfn(r, ctx) for r in tr])
        nb = 4
        mu = Xtr[:, nb:].mean(0)
        sd = Xtr[:, nb:].std(0)
        sd[sd == 0] = 1
        Xtr[:, nb:] = (Xtr[:, nb:] - mu) / sd
        w = rlib.fit_logit(Xtr, [r["actual"] > r["line"] for r in tr], l2=2.0)
        weights.append((m, np.round(w[nb:], 3).tolist()))
        Xte = np.array([base(r) + featfn(r, ctx) for r in te])
        Xte[:, nb:] = (Xte[:, nb:] - mu) / sd
        p = rlib.predict(w, Xte)
        for r, q in zip(te, p):
            for T in TS:
                for side, ps in (("over", q), ("under", 1 - q)):
                    if r[side] < -200:
                        continue
                    if ps - rlib.be(r[side]) >= T:
                        res[T].append(grade(r, side))
    print("%s feature weights (std units) by fold: %s" % (name, weights))
    out = {}
    for T in TS:
        out[T] = report("%s T%.2f" % (name, T), res[T])
    return res, out


def rule(name, pick):
    bets = []
    for r in ROWS:
        if r["result"] != "OK":
            continue
        side = pick(r)
        if side and r[side] >= -200:
            bets.append(grade(r, side))
    report(name, bets)
    return bets


isD = lambda r: float(r["pos"] == "D")
road = lambda r: float(not r["home"])

# ---------------- K1 arena
print("== K1 arena scorekeeper factor")
walk("K1", lambda r, c: [r["logA"], r["logA"] * road(r)])
rule("K1r-over", lambda r: "over" if (not r["home"] and r["arena_top5"] and r["line"] in (1.5, 2.5)) else None)
rule("K1r-under", lambda r: "under" if (not r["home"] and r["arena_bot5"] and r["line"] in (1.5, 2.5)) else None)

# ---------------- K2 moneyline game script
print("== K2 moneyline game script")
walk("K2", lambda r, c: [r["pw"] - .5, (r["pw"] - .5) * isD(r)], need=lambda r: r["pw"] is not None)

# ---------------- K3 player persistent residual
print("== K3 player residual")
walk("K3", lambda r, c: [r["k3"], r["k3"] * isD(r)])

# ---------------- K4 distribution shape
print("== K4 distribution shape")


def vmr(r):
    return r["all_var"] / r["all_mean"] if r.get("all_mean") and r["all_n"] >= 2 else None


def prep4(tr):
    pos = {}
    for P in ("F", "D"):
        v = [vmr(r) for r in tr if (r["pos"] == "D") == (P == "D") and r["all_n"] >= 20 and vmr(r) is not None]
        pos[P] = float(np.mean(v))
    return pos


_k4 = {}


def f4(r, ctx):
    P = "D" if r["pos"] == "D" else "F"
    vp = ctx[P]
    v = vmr(r)
    if v is None:
        return [0.0]
    n = r["all_n"]
    vs = (n * v + 20 * vp) / (n + 20)
    key = (r["line"], round(r["f"], 4), round(vp, 3), round(vs, 3))
    if key not in _k4:
        m = solve_m(r["line"], r["f"], vp)
        ps = min(max(nb_sf(r["line"], m, vs), 1e-4), 1 - 1e-4)
        _k4[key] = float(rlib.logit(ps) - rlib.logit(r["f"]))
    return [_k4[key]]


walk("K4", f4, prep=prep4)

# ---------------- K5 last-game overreaction
print("== K5 last-game overreaction")


def f5(r, c):
    if r["all_n"] < 5 or r.get("earlier_mean") is None:
        z = 0.0
    else:
        z = (r["last_sog"] - r["earlier_mean"]) / math.sqrt(max(r["earlier_mean"], 0.3))
    dl = r["line"] - r["prev_line"] if r.get("prev_line") is not None else 0.0
    return [z, dl]


walk("K5", f5)
rule("K5r-under", lambda r: "under" if (r["all_n"] >= 5 and r["last_sog"] >= r["line"] + 3) else None)
rule("K5r-over", lambda r: "over" if (r["all_n"] >= 5 and r["last_sog"] == 0 and r["all_mean"] >= r["line"]) else None)

# ---------------- K6 price selection
print("== K6 price selection (fixed rules, lines 1.5 + 2.5)")
K6 = {
    "a": lambda r: "over" if r["over"] >= 100 else None,
    "b": lambda r: "over" if r["over"] >= 110 else None,
    "c": lambda r: "over" if r["over"] >= 120 else None,
    "d": lambda r: "under" if r["under"] >= 100 else None,
    "e": lambda r: "under" if r["under"] >= 110 else None,
    "f": lambda r: "over" if (r["line"] == 2.5 and r["over"] >= 110) else None,
}
k6b = {}
for k, fn in K6.items():
    k6b[k] = rule("K6" + k, lambda r, fn=fn: fn(r) if r["line"] in (1.5, 2.5) else None)
sel = []
for m in rlib.TEST_MONTHS:
    best, bk = None, None
    for k, b in k6b.items():
        tr = [x for x in b if x["month"] < m]
        if len(tr) >= 50:
            roi = sum(x["profit"] for x in tr) / len(tr)
            if best is None or roi > best:
                best, bk = roi, k
    print("K6g", m, "selects", bk, "train ROI %+.1f%%" % (100 * best))
    sel += [x for x in k6b[bk] if x["month"] == m]
report("K6g", sel)

# ---------------- K9 attempts surplus
print("== K9 attempts surplus")


def prep9(tr):
    c = {}
    for P in ("F", "D"):
        a = [r for r in tr if (r["pos"] == "D") == (P == "D") and r.get("n20", 0) >= 5]
        c[P] = sum(r["sog20"] for r in a) / sum(r["att20"] for r in a)
    return c


def f9(r, c):
    if r.get("n20", 0) < 5:
        return [0.0]
    P = "D" if r["pos"] == "D" else "F"
    return [r["att20"] * c[P] - r["sog20"]]


walk("K9", f9, prep=prep9)

# descriptive: arena factor persistence 2024-25 vs 2025-26 (free data; no betting outcome)
json.dump(OUT, open(os.path.join(R4, "k_results.json"), "w"), indent=1, default=float)
