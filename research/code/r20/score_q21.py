#!/usr/bin/env python3
"""Q21a-b (HYPOTHESES.md run 20), nights >= 2026-11-04 only: Q1b bets at read A split by hours from the read to puck
(shadow ctx.start): Q21a >= 6.5 h, Q21b < 6.5 h. Reads research/fwd/scores.json (run score_fwd.py first) and data/shadow.
Also prints the same split on seen nights (descriptive, not a test). Writes research/fwd/q21.md.  python3 -I score_q21.py [repo_root]"""
import json, os, random, sys
from datetime import datetime
ROOT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "..", ".."))
START, BAR_N, ALPHA, CUT = "2026-11-04", 300, 0.05 / 40, 6.5
q1b = json.load(open(os.path.join(ROOT, "research/fwd/scores.json")))["bets"]["Q1b"]


def iso(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


ST = {}
for d in sorted({b["date"] for b in q1b}):
    fn = os.path.join(ROOT, "data/shadow/%s.json" % d)
    if os.path.exists(fn):
        for r in json.load(open(fn))["rows"]:
            st = (r.get("ctx") or {}).get("start")
            if st:
                ST[r["game_id"]] = iso(st)


def split(bs):
    lo, hi, nost = [], [], 0
    for b in bs:
        if b["pull"] != "A":
            continue
        st = ST.get(b["game"])
        if st is None:
            nost += 1; continue
        h = (st - iso(b["at"])).total_seconds() / 3600
        (hi if h >= CUT else lo).append(b)
    return hi, lo, nost


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


hdr = ["| variant | bets | graded | ROI | 90% CI | p | mean CLV | candidate |", "|---|---|---|---|---|---|---|---|"]
hi, lo, ns = split([b for b in q1b if b["date"] >= START])
out = ["# Q21 forward (research/code/r20/score_q21.py), nights >= %s. Bar: n >= 300, ROI > 0, p < %.5f, CLV > 0." % (START, ALPHA), ""] + hdr
out += [row("Q21a A, puck >= 6.5 h", hi), row("Q21b A, puck < 6.5 h", lo), "", "A bets with no shadow start: %d" % ns]
hi, lo, ns = split([b for b in q1b if b["date"] < START])
out += ["", "Descriptive, seen nights < %s (not a test):" % START, ""] + hdr + [row("A, puck >= 6.5 h", hi), row("A, puck < 6.5 h", lo),
        "", "no start: %d" % ns]
open(os.path.join(ROOT, "research/fwd/q21.md"), "w").write("\n".join(out) + "\n")
print("\n".join(out))
