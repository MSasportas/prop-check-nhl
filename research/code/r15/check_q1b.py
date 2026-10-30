#!/usr/bin/env python3
"""Run 15: robustness check of forward Q1b (first forward variant to meet its registered bar).
Read-only on data/. Uses research/code/fwd/score_fwd.py definitions unchanged.
  python3 -I research/code/r15/check_q1b.py [repo_root]
"""
import os, sys, random, statistics, importlib.util
ROOT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "..", ".."))
spec = importlib.util.spec_from_file_location("sf", os.path.join(ROOT, "research/code/fwd/score_fwd.py"))
sys.argv = [sys.argv[0], ROOT]
sf = importlib.util.module_from_spec(spec); spec.loader.exec_module(sf)

bets, cand = [], []
for d in sf.dates():
    reads = sf.reads_for(d); res, start = sf.shadow(d)
    bets += sf.score_q1(reads, res, start)["Q1b"]
    seen = set()
    for r in reads:  # placebo pool: first pre-game read of every side with >=1 consensus book, price >= -200
        st = start.get(r["game"])
        if (st and r["at"] >= st) or r["cons"] is None:
            continue
        for side in ("over", "under"):
            k = (r["game"], r["pid"], r["line"], side)
            if k in seen or r[side] < -200:
                continue
            seen.add(k)
            pl = sf.grade(res.get((r["game"], r["pid"], r["line"])), side, r["line"], r[side])
            if pl is not None:
                cand.append(dict(date=d, game=r["game"], pl=pl, key=(r["game"], r["pid"], r["line"]), side=side))
g = [b for b in bets if b["pl"] is not None]
def roi(xs): return sum(x["pl"] for x in xs) / len(xs) if xs else float("nan")
def boot(xs, B=20000, seed=11):
    by = {}
    for b in xs: by.setdefault((b["date"], b["game"]), []).append(b["pl"])
    cl = list(by.values()); rng = random.Random(seed); sims = []
    for _ in range(B):
        s = [cl[rng.randrange(len(cl))] for _ in cl]
        sims.append(sum(map(sum, s)) / sum(map(len, s)))
    sims.sort()
    return sims[int(.05*B)], sims[int(.95*B)-1], sum(1 for x in sims if x <= 0) / B, len(cl)
lo, hi, p, ng = boot(g)
print("Q1b graded %d (games %d) W %d units %+.2f ROI %+.1f%% 90%%CI %+.1f..%+.1f p(20k) %.5f meanEV %+.2f%% meanCLV %+.2f%%" % (
    len(g), ng, sum(b["pl"] > 0 for b in g), sum(b["pl"] for b in g), 100*roi(g), 100*lo, 100*hi, p,
    100*statistics.mean(b["ev"] for b in g), 100*statistics.mean(b["clv"] for b in g if b["clv"] is not None)))
for lab, f in [("night", lambda b: b["date"]), ("pull", lambda b: b["pull"]), ("side", lambda b: b["side"]),
               ("line", lambda b: b["line"]), ("price", lambda b: "fav" if b["price"] < 0 else "dog"),
               ("books", lambda b: "1-3" if b["books"] < 4 else ("4-6" if b["books"] < 7 else "7+"))]:
    by = {}
    for b in g: by.setdefault(f(b), []).append(b)
    print(lab + ": " + "; ".join("%s n%d %+.1f%%" % (k, len(v), 100*roi(v)) for k, v in sorted(by.items(), key=lambda x: str(x[0]))))
nights = sorted({b["date"] for b in g})
print("leave-one-night-out ROI: " + ", ".join("%s %+.1f%%" % (n[5:], 100*roi([b for b in g if b["date"] != n])) for n in nights))
print("product-usable (B/C reads only):", "n%d %+.1f%% p %.4f" % ((lambda x: (len(x), 100*roi(x), boot(x, 5000)[2]))([b for b in g if b["pull"] in "BC"])))
# Placebo 1: same lines, random side (shuffle within date x line), 2000 reps
idx = {(c["key"], c["side"]): c for c in cand}
rng = random.Random(3); act = roi(g); hits = 0; sims = []
for _ in range(2000):
    s = []
    for b in g:
        side = rng.choice(("over", "under")); c = idx.get(((b["game"], b["pid"], b["line"]), side))
        s.append(c["pl"] if c else b["pl"])
    sims.append(sum(s)/len(s)); hits += sims[-1] >= act
print("placebo1 random side on same lines: mean %+.1f%%, share >= actual %.4f" % (100*statistics.mean(sims), hits/2000))
# Placebo 2: random sides from all priced sides (same n)
sims = []; hits = 0
for _ in range(2000):
    s = rng.sample(cand, len(g)); sims.append(roi(s)); hits += sims[-1] >= act
print("placebo2 random %d sides of %d: mean %+.1f%%, share >= actual %.4f" % (len(g), len(cand), 100*statistics.mean(sims), hits/2000))
print("all priced sides ROI (market baseline): n%d %+.1f%%" % (len(cand), 100*roi(cand)))
