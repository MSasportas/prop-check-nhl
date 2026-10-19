"""P1-P6: correlated 2-3 leg parlays at the PRODUCT of Hard Rock prices (-45 snapshot), pre-lockbox only."""
import json, sys, os, itertools
from collections import defaultdict
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from rlib import summ, fmt, be, dec
W = "/tmp/claude-0/-home-claude/ab9b3f07-215a-50c7-96a2-d84b6c4f2d08/scratchpad/r3/work"
LOCK = "2026-03-01"
FOLDS = ["2025-11", "2025-12", "2026-01", "2026-02"]


def legs(fn):
    out = []
    for l in open(os.path.join(W, fn)):
        r = json.loads(l)
        if r["date"] >= LOCK or r.get("result") != "OK" or r.get("actual") is None or not r.get("ok", True):
            continue
        if r.get("over") is None or r.get("under") is None:
            continue
        f = be(r["over"]) / (be(r["over"]) + be(r["under"]))
        for sd in ("over", "under"):
            p = r[sd]
            if p < -200:
                continue
            win = r["actual"] > r["line"] if sd == "over" else r["actual"] < r["line"]
            out.append({"gid": r["gid"], "date": r["date"], "team": r["team"], "pid": r["pid"], "side": sd, "price": p,
                        "fair": f if sd == "over" else 1 - f, "win": win, "pos": r.get("pos")})
    return out


shots = legs("shots45_lines.jsonl")
saves = legs("saves45_lines.jsonl")
# one line per player per game (several lines per player? keep all, but pairs must be different players)
G = defaultdict(list)
for l in shots:
    G[l["gid"]].append(l)
S = defaultdict(list)
for l in saves:
    S[l["gid"]].append(l)


def run(name, combos):
    bets, jf, jo, pm = [], [], [], []
    for c in combos:
        d = np.prod([dec(x["price"]) for x in c])
        win = all(x["win"] for x in c)
        bets.append({"gid": c[0]["gid"], "month": c[0]["date"][:7], "profit": d - 1 if win else -1.0, "win": win, "be": 1 / d})
        jf.append(np.prod([x["fair"] for x in c]))
        jo.append(win)
    s = summ(bets)
    fm = defaultdict(list)
    for b in bets:
        fm[b["month"]].append(b)
    folds = " ".join("%s %+.1f%%" % (m[5:], 100 * summ(fm[m])["roi"]) if fm[m] else m[5:] + " n0" for m in FOLDS)
    jo, jf = np.mean(jo), np.mean(jf)
    print("%-40s %s | joint hit %.3f vs indep-fair %.3f (lift x%.2f) | needed price boost to break even x%.3f | %s" % (
        name, fmt(s), jo, jf, jo / jf, s["be"] / jo, folds))


def pairs(cond, k=2):
    out = []
    for g, ls in G.items():
        for c in itertools.combinations(ls, k):
            if len({x["pid"] for x in c}) < k:
                continue
            if cond(c):
                out.append(c)
    return out

print("legs: shots %d, saves %d (pre-lockbox, priced >= -200)" % (len(shots), len(saves)))
run("baseline single shots overs", [(x,) for x in shots if x["side"] == "over"])
run("baseline single shots unders", [(x,) for x in shots if x["side"] == "under"])
run("P1 same-team OVER pairs", pairs(lambda c: c[0]["team"] == c[1]["team"] and all(x["side"] == "over" for x in c)))
run("P2 same-team UNDER pairs", pairs(lambda c: c[0]["team"] == c[1]["team"] and all(x["side"] == "under" for x in c)))
run("P3 opposing-team OVER pairs", pairs(lambda c: c[0]["team"] != c[1]["team"] and all(x["side"] == "over" for x in c)))
run("  (ref) cross-game OVER pairs, same date", [])  if False else None
p4, p5 = [], []
for g, gl in S.items():
    for gk in gl:
        for sk in G.get(g, []):
            if sk["team"] == gk["team"]:
                continue
            if gk["side"] == "over" and sk["side"] == "over":
                p4.append((gk, sk))
            if gk["side"] == "under" and sk["side"] == "under":
                p5.append((gk, sk))
run("P4 saves OVER + opp skater shots OVER", p4)
run("P5 saves UNDER + opp skater shots UNDER", p5)
run("P6 same-team OVER triples", pairs(lambda c: len({x["team"] for x in c}) == 1 and all(x["side"] == "over" for x in c), 3))
