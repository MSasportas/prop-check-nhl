"""Run 10 tests X1-X3 (registered in HYPOTHESES.md run 10, commit 8077cba, before testing).
Inputs (scratch, PC_R10_DIR): h/work/shots45_lines.jsonl (hist tgz), nhl/skater_2425.jsonl + skater_2526.jsonl (r10/fetch10.py, Feb 28 cut-off).
Lockbox rows (Mar 1+) are never built or scored. python3 -I x10.py [placebo NAME T]"""
import contextlib, io, json, math, os, random, sys
from bisect import bisect_left
from collections import defaultdict
from datetime import date as Date
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import rlib, wf  # noqa: E402

D = os.environ["PC_R10_DIR"]
jl = lambda p: [json.loads(l) for l in open(os.path.join(D, p))]
dd = lambda a, b: (Date.fromisoformat(a) - Date.fromisoformat(b)).days


def pois_sf(m, line):  # P(X > line), line x.5
    k = int(math.floor(line))
    p = term = math.exp(-m)
    for i in range(1, k + 1):
        term *= m / i
        p += term
    return 1 - p


def pois_mean(line, f):
    lo, hi = 1e-4, 30.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if pois_sf(mid, line) < f:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


# ---- skater logs: pid -> season -> [(date, shots)]
s24 = defaultdict(list); s25 = defaultdict(list)
for s in jl("nhl/skater_2425.jsonl"):
    s24[s["playerId"]].append(s["shots"] or 0)
for s in jl("nhl/skater_2526.jsonl"):
    if s["gameDate"][:10] < rlib.LOCKBOX:
        s25[s["playerId"]].append((s["gameDate"][:10], s["shots"] or 0))
for L in s25.values():
    L.sort()
s25d = {p: [x[0] for x in L] for p, L in s25.items()}

lines = [json.loads(l) for l in open(os.path.join(D, "h/work/shots45_lines.jsonl"))]
lines = [r for r in lines if r["date"] < rlib.LOCKBOX and r["over"] is not None and r["under"] is not None]
for r in lines:
    r["f"] = rlib.fair_prop(r["over"], r["under"])
    r["lf"] = float(rlib.logit(r["f"]))
    r["isD"] = float(r["pos"] == "D")

# ---- X1: one representative line per player-game (f nearest 0.5) -> Poisson mean
rep = {}
for r in lines:
    k = (r["pid"], r["date"])
    if k not in rep or abs(r["f"] - 0.5) < abs(rep[k]["f"] - 0.5):
        rep[k] = r
pg = defaultdict(list)
for (pid, d), r in rep.items():
    pg[pid].append((d, pois_mean(r["line"], r["f"]), r))
for L in pg.values():
    L.sort(key=lambda x: x[0])
pgd = {p: [x[0] for x in L] for p, L in pg.items()}
mnow = {(pid, x[0]): x[1] for pid, L in pg.items() for x in L}
X1_MISSING_PREV_RESULT = 0
for r in lines:
    r["x_X1"] = (0.0, 0.0)
    L = pg.get(r["pid"], []); i = bisect_left(pgd.get(r["pid"], []), r["date"])
    if i == 0:
        continue
    pd_, mp, pr = L[i - 1]
    if dd(r["date"], pd_) > 14:
        continue
    if pr["result"] != "OK" or pr["actual"] is None:   # prev game with no SOG (void): no z -> terms 0 (script note)
        X1_MISSING_PREV_RESULT += 1
        continue
    dm = math.log(mnow[(r["pid"], r["date"])] / mp)
    z = (pr["actual"] - mp) / math.sqrt(mp)
    r["x_X1"] = (dm, z)

# ---- X2
for r in lines:
    wd = Date.fromisoformat(r["date"]).weekday()  # Mon 0 .. Sun 6
    r["x_X2"] = (float(wd == 5), float(wd in (4, 6)))

# ---- X3
for r in lines:
    a = s24.get(r["pid"], [])
    P = s25.get(r["pid"], [])[:bisect_left(s25d.get(r["pid"], []), r["date"])]
    if len(a) >= 20 and len(P) >= 3:
        g = len(P)
        r["x_X3"] = ((np.mean(a) - np.mean([x[1] for x in P])) * 20.0 / (20 + g),)
    else:
        r["x_X3"] = (0.0,)

ok = [r for r in lines if r["ok"] and r["result"] == "OK"]
test = [r for r in ok if r["date"][:7] >= "2025-11"]


def fixed(name, cond, side="under"):
    b = []
    for r in test:
        if cond(r) and r[side] >= -200:
            b.append(rlib.bet(r["gid"], r["date"], r[side], (r["actual"] > r["line"]) == (side == "over")))
    s = rlib.summ(b)
    print("%s %s | %s | p_one %s" % (name, rlib.fmt(s), rlib.by_month(b), s.get("p_one")))
    return b


BUILD = {
    "X1": lambda m: (lambda r: [r["x_X1"][0], r["x_X1"][0] * r["x_X1"][1]]),
    "X2": lambda m: (lambda r: [r["x_X2"][0], r["x_X2"][1], r["x_X2"][0] * r["lf"]]),
    "X3": lambda m: (lambda r: [r["x_X3"][0], r["x_X3"][0] * r["isD"]]),
}
SHUF = {"X1": ["x_X1"], "X2": ["x_X2"], "X3": ["x_X3"]}


def per_fold(name, Ts=(0.01, 0.02, 0.03), verbose=True, quiet=False):
    res = {T: [] for T in Ts}
    keep = rlib.TEST_MONTHS
    try:
        for m in keep:
            rlib.TEST_MONTHS = [m]
            ex = BUILD[name](m)
            with contextlib.redirect_stdout(io.StringIO()) as buf:
                rr = wf.run(name, lines, ex, Ts=Ts, verbose=verbose)
            if verbose and not quiet:
                print("\n".join(l for l in buf.getvalue().splitlines() if " w " in l or "log loss" in l))
            for T in Ts:
                res[T] += rr[T]
    finally:
        rlib.TEST_MONTHS = keep
    if not quiet:
        for T, b in res.items():
            s = rlib.summ(b)
            print("%s T=%.2f %s | %s | p_one %s" % (name, T, rlib.fmt(s), rlib.by_month(b), s.get("p_one")))
    return res


def main():
    print("rows pre-lockbox", len(lines), "graded Nov-Feb", len(test))
    print("desc X1 prev", sum(r["x_X1"] != (0.0, 0.0) for r in test), "X1r cond", sum(r["x_X1"][0] >= math.log(1.15) and r["x_X1"][1] >= 1.5 for r in test),
          "prev void", X1_MISSING_PREV_RESULT, "| corr(dm,z) %.3f" % np.corrcoef([r["x_X1"][0] for r in test], [r["x_X1"][1] for r in test])[0, 1],
          "| X2 sat", sum(r["x_X2"][0] for r in test), "fri/sun", sum(r["x_X2"][1] for r in test),
          "| X3 nonzero", sum(r["x_X3"][0] != 0 for r in test), "mean abs %.3f" % np.mean([abs(r["x_X3"][0]) for r in test]))
    per_fold("X1")
    fixed("X1r", lambda r: r["x_X1"][0] >= math.log(1.15) and r["x_X1"][1] >= 1.5)
    per_fold("X2")
    fixed("X2r", lambda r: r["x_X2"][0] == 1.0)
    per_fold("X3")


def placebo(name, T):
    real = rlib.summ(per_fold(name, Ts=(T,), verbose=False, quiet=True)[T])
    grp = defaultdict(list)
    for r in lines:
        grp[(r["date"], r["line"])].append(r)
    rng = random.Random(7); rois = []
    for i in range(200):
        for g in grp.values():
            xs = [[r[k] for k in SHUF[name]] for r in g]; rng.shuffle(xs)
            for r, x in zip(g, xs):
                for k, v in zip(SHUF[name], x):
                    r[k] = v
        s = rlib.summ(per_fold(name, Ts=(T,), verbose=False, quiet=True)[T], B=1)
        rois.append(s["roi"] if s["n"] else -1.0)
    rois = np.array(rois)
    print("%s T=%.2f real %+.2f%% n%d | placebo mean %+.2f%% sd %.2f | share >= real %.3f" % (
        name, T, 100 * real["roi"], real["n"], 100 * rois.mean(), 100 * rois.std(), (rois >= real["roi"]).mean()))


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "placebo":
        placebo(sys.argv[2], float(sys.argv[3]))
    else:
        main()
