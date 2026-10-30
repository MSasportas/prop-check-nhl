#!/usr/bin/env python3
"""Q16a-b (HYPOTHESES.md run 15), nights >= 2026-10-30 only. Q16a reads research/fwd/scores.json (run score_fwd.py first);
Q16b re-reads data/odds + data/shadow via score_fwd.py helpers. Writes research/fwd/q16.md.  python3 -I score_q16.py [repo_root]"""
import importlib.util, json, os, random, sys
ROOT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "..", ".."))
START, BAR_N, ALPHA = "2026-10-30", 300, 0.05 / 31
spec = importlib.util.spec_from_file_location("sf", os.path.join(ROOT, "research/code/fwd/score_fwd.py"))
sys.argv = [sys.argv[0], ROOT]; sf = importlib.util.module_from_spec(spec); spec.loader.exec_module(sf)
j = json.load(open(os.path.join(ROOT, "research/fwd/scores.json")))
q1b = [b for b in j["bets"]["Q1b"] if b["date"] >= START]
V = {"Q16a": [b for b in q1b if b["pull"] == "A" and b["side"] == "under"], "Q16b": []}
for d in sorted({b["date"] for b in q1b if b["pull"] == "A"}):
    reads = sf.reads_for(d); res, start = sf.shadow(d)
    firstB = {}
    for r in reads:
        if r["pull"] == "B" and (r["game"], r["pid"], r["line"]) not in firstB:
            st = start.get(r["game"])
            if not st or r["at"] < st:
                firstB[(r["game"], r["pid"], r["line"])] = r
    for b in q1b:
        if b["date"] != d or b["pull"] != "A":
            continue
        r = firstB.get((b["game"], b["pid"], b["line"]))
        if r is None or r[b["side"]] < -200:
            continue
        pr = r[b["side"]]
        V["Q16b"].append(dict(b, pull="B", price=pr, clv=b["clv"],
                              pl=sf.grade(res.get((b["game"], b["pid"], b["line"])), b["side"], b["line"], pr)))


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


out = ["# Q16 forward (research/code/r15/score_q16.py), nights >= %s. Bar: n >= 300, ROI > 0, p < %.4f, CLV > 0. "
       "Q16b CLV = the A-read bet's CLV (not re-priced)." % (START, ALPHA), "",
       "| variant | bets | graded | ROI | 90% CI | p | mean CLV | candidate |", "|---|---|---|---|---|---|---|---|"]
for k, bs in V.items():
    s = stats(bs)
    if s["graded"]:
        out.append("| %s | %d | %d | %+.1f%% | %+.0f..%+.0f%% | %.3f | %s | %s |" % (k, s["n"], s["graded"], 100 * s["roi"], 100 * s["lo"],
                   100 * s["hi"], s["p"], "-" if s["clv"] is None else "%.4f" % s["clv"], s["cand"]))
    else:
        out.append("| %s | %d | 0 | - | - | - | - | False |" % (k, s["n"]))
open(os.path.join(ROOT, "research/fwd/q16.md"), "w").write("\n".join(out) + "\n")
print("\n".join(out))
