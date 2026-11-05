#!/usr/bin/env python3
"""Q22a-b (HYPOTHESES.md run 21), nights >= 2026-11-05 only: Q1b bets at read A split by Pinnacle at that same A fetch
(data/odds others.pinnacle, both sides of the same player/line): Q22a EV vs Pinnacle proportional no-vig fair >= 0, Q22b < 0.
Reads research/fwd/scores.json (run score_fwd.py first). Also prints seen nights (descriptive, not a test). Writes research/fwd/q22.md.
python3 -I score_q22.py [repo_root]"""
import json, os, random, sys
ROOT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "..", ".."))
START, BAR_N, ALPHA = "2026-11-05", 300, 0.05 / 42
q1b = json.load(open(os.path.join(ROOT, "research/fwd/scores.json")))["bets"]["Q1b"]


def dec(a):
    return 1 + (a / 100 if a > 0 else 100 / -a)


PIN = {}  # (game, pid, line) -> {side: price} at the A fetch
for d in sorted({b["date"] for b in q1b}):
    fn = os.path.join(ROOT, "data/odds/%s.json" % d)
    if not os.path.exists(fn):
        continue
    for f in json.load(open(fn))["fetches"]:
        if f.get("pull") != "A":
            continue
        pm = ((f.get("others") or {}).get("pinnacle") or {}).get("shots") or {}
        for o in pm.get("outcomes", []):
            PIN.setdefault((f["game_id"], o.get("pid"), o.get("line")), {})[o["side"]] = o["price"]


def split(bs):
    agree, dis, nopin = [], [], 0
    for b in bs:
        if b["pull"] != "A":
            continue
        p = PIN.get((b["game"], b["pid"], b["line"]), {})
        if "over" not in p or "under" not in p:
            nopin += 1; continue
        io, iu = 1 / dec(p["over"]), 1 / dec(p["under"])
        fair = (io if b["side"] == "over" else iu) / (io + iu)
        (agree if fair * dec(b["price"]) - 1 >= 0 else dis).append(b)
    return agree, dis, nopin


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
a, dd, ns = split([b for b in q1b if b["date"] >= START])
out = ["# Q22 forward (research/code/r21/score_q22.py), nights >= %s. Bar: n >= 300, ROI > 0, p < %.5f, CLV > 0." % (START, ALPHA), ""] + hdr
out += [row("Q22a A, Pinnacle agrees", a), row("Q22b A, Pinnacle disagrees", dd), "", "A bets with no two-sided Pinnacle: %d" % ns]
a, dd, ns = split([b for b in q1b if b["date"] < START])
out += ["", "Descriptive, seen nights < %s (not a test):" % START, ""] + hdr + [row("A, Pinnacle agrees", a), row("A, Pinnacle disagrees", dd),
        "", "no Pinnacle: %d" % ns]
open(os.path.join(ROOT, "research/fwd/q22.md"), "w").write("\n".join(out) + "\n")
print("\n".join(out))
