#!/usr/bin/env python3
"""Q18a-b (HYPOTHESES.md run 18), nights >= 2026-11-02 only: Q1b bets with side under, line 1.5, at read A (Q18a) vs B/C (Q18b).
Reads research/fwd/scores.json (run score_fwd.py first). Also prints the Q1b A vs B/C split on all nights (descriptive).
Writes research/fwd/q18.md.  python3 -I score_q18.py [repo_root]"""
import json, os, random, sys
ROOT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "..", ".."))
START, BAR_N, ALPHA = "2026-11-02", 300, 0.05 / 36
j = json.load(open(os.path.join(ROOT, "research/fwd/scores.json")))
q1b = j["bets"]["Q1b"]


def stats(bs):
    g = [b for b in bs if b.get("pl") is not None]
    if not g:
        return dict(n=len(bs), graded=0)
    games = {}
    for b in g:
        games.setdefault((b["date"], b["game"]), []).append(b["pl"])
    keys = list(games); rng = random.Random(11); hits = 0; boots = []
    for _ in range(2000):
        s = [x for k in (rng.choice(keys) for _ in keys) for x in games[k]]
        r = sum(s) / len(s); boots.append(r); hits += r <= 0
    boots.sort(); roi = sum(b["pl"] for b in g) / len(g)
    clv = [b["clv"] for b in g if b.get("clv") is not None]; mc = sum(clv) / len(clv) if clv else None; p = hits / 2000
    return dict(n=len(bs), graded=len(g), roi=roi, lo=boots[100], hi=boots[1899], p=p, clv=mc,
                cand=len(g) >= BAR_N and roi > 0 and p < ALPHA and (mc or 0) > 0)


def row(k, bs):
    s = stats(bs)
    if not s["graded"]:
        return "| %s | %d | 0 | - | - | - | - | False |" % (k, s["n"])
    return "| %s | %d | %d | %+.1f%% | %+.0f..%+.0f%% | %.3f | %s | %s |" % (k, s["n"], s["graded"], 100 * s["roi"], 100 * s["lo"],
            100 * s["hi"], s["p"], "-" if s["clv"] is None else "%.4f" % s["clv"], s["cand"])


new = [b for b in q1b if b["date"] >= START and b["side"] == "under" and b["line"] == 1.5]
V = {"Q18a U1.5 at A": [b for b in new if b["pull"] == "A"], "Q18b U1.5 at B/C": [b for b in new if b["pull"] in ("B", "C")]}
hdr = ["| variant | bets | graded | ROI | 90% CI | p | mean CLV | candidate |", "|---|---|---|---|---|---|---|---|"]
out = ["# Q18 forward (research/code/r18/score_q18.py), nights >= %s. Bar: n >= 300, ROI > 0, p < %.4f, CLV > 0." % (START, ALPHA), ""] + hdr
out += [row(k, v) for k, v in V.items()]
out += ["", "Descriptive, all Q1b nights (seen; not a test):", ""] + hdr
out += [row("Q1b read A", [b for b in q1b if b["pull"] == "A"]), row("Q1b reads B/C", [b for b in q1b if b["pull"] in ("B", "C")])]
open(os.path.join(ROOT, "research/fwd/q18.md"), "w").write("\n".join(out) + "\n")
print("\n".join(out))
