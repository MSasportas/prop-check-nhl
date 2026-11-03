#!/usr/bin/env python3
"""Q20a-b (HYPOTHESES.md run 19), nights >= 2026-11-03 only: Q1b bets at read A split by the product's guard (0.8 x consensus fair +
0.2 x (shadow open model_p_over + frozen offset), pass iff EV >= +2%), using the shadow row whose open.pull == "A".
Reads research/fwd/scores.json (run score_fwd.py first) and data/shadow. Also prints the same split on seen nights (descriptive).
Writes research/fwd/q20.md.  python3 -I score_q20.py [repo_root]"""
import json, os, random, sys
ROOT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "..", ".."))
START, BAR_N, ALPHA = "2026-11-03", 300, 0.05 / 38
OFF = {1.5: 0.0179, 2.5: 0.0158, 3.5: 0.017}
q1b = json.load(open(os.path.join(ROOT, "research/fwd/scores.json")))["bets"]["Q1b"]


def dec(a):
    return 1 + a / 100.0 if a > 0 else 1 + 100.0 / -a


SH = {}
for d in sorted({b["date"] for b in q1b}):
    fn = os.path.join(ROOT, "data/shadow/%s.json" % d)
    if not os.path.exists(fn):
        continue
    for r in json.load(open(fn))["rows"]:
        if r.get("market", "shots") == "shots" and (r.get("open") or {}).get("pull") == "A":
            SH[(r["game_id"], r["pid"], float(r["line"]))] = r["open"].get("model_p_over")


def split(bs):
    ok, veto, nomodel = [], [], 0
    for b in bs:
        if b["pull"] != "A":
            continue
        m = SH.get((b["game"], b["pid"], float(b["line"])))
        if m is None or b["line"] not in OFF:
            nomodel += 1; continue
        fair = (b["ev"] + 1) / dec(b["price"])
        mo = m + OFF[b["line"]]; ms = mo if b["side"] == "over" else 1 - mo
        fin = 0.8 * fair + 0.2 * ms
        (ok if fin * dec(b["price"]) - 1 >= 0.02 else veto).append(b)
    return ok, veto, nomodel


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
a, v, nm = split([b for b in q1b if b["date"] >= START])
out = ["# Q20 forward (research/code/r19/score_q20.py), nights >= %s. Bar: n >= 300, ROI > 0, p < %.4f, CLV > 0." % (START, ALPHA), ""] + hdr
out += [row("Q20a A + guard passes", a), row("Q20b A, guard vetoes", v), "", "A bets with no shadow A-open model: %d" % nm]
a, v, nm = split([b for b in q1b if b["date"] < START])
out += ["", "Descriptive, seen nights < %s (not a test):" % START, ""] + hdr + [row("A + guard passes", a), row("A, guard vetoes", v),
        "", "no model: %d" % nm]
open(os.path.join(ROOT, "research/fwd/q20.md"), "w").write("\n".join(out) + "\n")
print("\n".join(out))
