"""P4/P5 detail: Nov-Feb aggregate, games, per-game-capped version, shuffle placebo (break saves<->shots link across games)."""
import json, sys, os, random
from collections import defaultdict
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.argv = [sys.argv[0]]
import p16
from rlib import summ, fmt, dec
FOLDS = p16.FOLDS


def build(side, G, S):
    out = []
    for g, gl in S.items():
        for gk in gl:
            if gk["side"] != side:
                continue
            for sk in G.get(g, []):
                if sk["team"] != gk["team"] and sk["side"] == side:
                    out.append((gk, sk))
    return out


def roi(c):
    bets = []
    for a, b in c:
        d = dec(a["price"]) * dec(b["price"])
        w = a["win"] and b["win"]
        bets.append({"gid": a["gid"], "month": a["date"][:7], "profit": d - 1 if w else -1.0, "win": w, "be": 1 / d})
    return bets


for side in ("over", "under"):
    c = build(side, p16.G, p16.S)
    b = roi(c)
    wf = [x for x in b if x["month"] in FOLDS]
    print("P%s: games %d, pairs %d; Oct-Feb %s; Nov-Feb %s" % ("4" if side == "over" else "5", len({x["gid"] for x in b}), len(b), fmt(summ(b)), fmt(summ(wf))))
    # placebo: pair each goalie leg with skater legs from a random OTHER game (same side), same count
    rng = random.Random(7)
    gids = [g for g in p16.G if g in p16.S]
    pl = []
    for k in range(20):
        perm = {g: rng.choice([h for h in gids if h != g]) for g in gids}
        cc = []
        for g in gids:
            for gk in p16.S[g]:
                if gk["side"] != side:
                    continue
                for sk in p16.G[perm[g]]:
                    if sk["side"] == side:
                        cc.append((gk, sk))
        pl.append(summ(roi(cc), B=200)["roi"])
    print("   placebo (goalie leg paired with skaters from a random other game) ROI mean %+.1f%% sd %.1f" % (100 * np.mean(pl), 100 * np.std(pl)))
lock_saves = sum(1 for l in open(os.path.join(p16.W, "saves45_lines.jsonl")) if json.loads(l)["date"] >= p16.LOCK)
print("saves lines in lockbox (Mar+):", lock_saves)
