#!/usr/bin/env python3
"""Q6a-c (HYPOTHESES.md run 9): split of Q1a bets, nights >= 2026-10-23 only. Reads research/fwd/scores.json (run score_fwd.py first).
Appends nothing; prints a table and writes research/fwd/q6.md.   python3 -I research/code/r9/score_q6.py [repo_root]"""
import json, os, random, sys
ROOT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "..", ".."))
START, BAR_N, ALPHA = "2026-10-23", 300, 0.05 / 18
j = json.load(open(os.path.join(ROOT, "research/fwd/scores.json")))
q1a = [b for b in j["bets"]["Q1a"] if b["date"] >= START]
V = {"Q6a": lambda b: b["pull"] == "A", "Q6b": lambda b: b["pull"] in ("B", "C"), "Q6c": lambda b: b["side"] == "under"}


def stats(bs):
    g = [b for b in bs if b.get("pl") is not None]
    if not g:
        return dict(n=len(bs), graded=0)
    games = {}
    for b in g:
        games.setdefault(b["game"], []).append(b["pl"])
    keys = list(games); rng = random.Random(11); hits = 0; boots = []
    for _ in range(2000):
        s = [x for k in (rng.choice(keys) for _ in keys) for x in games[k]]
        r = sum(s) / len(s); boots.append(r); hits += r <= 0
    boots.sort()
    roi = sum(b["pl"] for b in g) / len(g)
    clv = [b["clv"] for b in g if b.get("clv") is not None]
    mc = sum(clv) / len(clv) if clv else None
    p = hits / 2000
    return dict(n=len(bs), graded=len(g), roi=roi, lo=boots[100], hi=boots[1899], p=p, clv=mc,
                cand=len(g) >= BAR_N and roi > 0 and p < ALPHA and (mc or 0) > 0)


out = ["# Q6 forward splits (research/code/r9/score_q6.py), nights >= %s. Bar: n >= 300, ROI > 0, p < %.4f, CLV > 0." % (START, ALPHA), "",
       "| variant | bets | graded | ROI | 90% CI | p | mean CLV | candidate |", "|---|---|---|---|---|---|---|---|"]
for k, f in V.items():
    s = stats([b for b in q1a if f(b)])
    if s["graded"]:
        out.append("| %s | %d | %d | %+.1f%% | %+.0f..%+.0f%% | %.3f | %s | %s |" % (k, s["n"], s["graded"], 100 * s["roi"], 100 * s["lo"], 100 * s["hi"],
                   s["p"], "-" if s["clv"] is None else "%.4f" % s["clv"], s["cand"]))
    else:
        out.append("| %s | %d | 0 | - | - | - | - | False |" % (k, s["n"]))
open(os.path.join(ROOT, "research/fwd/q6.md"), "w").write("\n".join(out) + "\n")
print("\n".join(out))
