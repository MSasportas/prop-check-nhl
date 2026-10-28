#!/usr/bin/env python3
"""Q11a-b (HYPOTHESES.md run 13): Q1c bets split by goalie status at read time. Needs a full (unshallow) clone: reads the git history of
data/state/goalies.json. Reads research/fwd/scores.json (run score_fwd.py first) and data/odds/<date>.json (game teams).
Writes research/fwd/q11.md.   python3 -I research/code/r13/score_q11.py [repo_root]"""
import json, os, random, subprocess, sys
from datetime import datetime
ROOT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "..", ".."))
BAR_N, ALPHA = 300, 0.05 / 27
iso = lambda s: datetime.fromisoformat(s.replace("Z", "+00:00"))
git = lambda *a: subprocess.run(["git", "-C", ROOT] + list(a), capture_output=True, text=True, check=True).stdout

# goalies.json versions: (commit time, doc)
vers = []
for line in git("log", "--format=%H %cI", "--", "data/state/goalies.json").split("\n"):
    if not line.strip():
        continue
    h, t = line.split()
    try:
        doc = json.loads(git("show", "%s:data/state/goalies.json" % h))
    except Exception:
        continue
    vers.append((iso(t), doc))
vers.sort(key=lambda x: x[0])

teams = {}
for fn in os.listdir(os.path.join(ROOT, "data/odds")):
    if fn.endswith(".json"):
        for f in json.load(open(os.path.join(ROOT, "data/odds", fn))).get("fetches", []):
            teams[f["game_id"]] = (f["away"], f["home"])


def both_confirmed(b):
    at = iso(b["at"]); doc = None
    for t, d in vers:
        if t <= at and d.get("date") == b["date"]:
            doc = d
        elif t > at:
            break
    if doc is None or b["game"] not in teams:
        return False
    st = doc.get("teams", {})
    return all((st.get(x) or {}).get("status") == "confirmed" for x in teams[b["game"]])


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


q1c = json.load(open(os.path.join(ROOT, "research/fwd/scores.json")))["bets"]["Q1c"]
for b in q1c:
    b["gc"] = both_confirmed(b)
out = ["# Q11 forward splits (Q1c by goalie status at read time) (research/code/r13/score_q11.py), all nights. Bar: n >= 300, ROI > 0, "
       "p < %.5f, CLV > 0. goalies.json versions read: %d." % (ALPHA, len(vers)), "",
       "| variant | bets | graded | ROI | 90% CI | p | mean CLV | candidate |", "|---|---|---|---|---|---|---|---|"]
for k, f in (("Q11a both confirmed", lambda b: b["gc"]), ("Q11b not both", lambda b: not b["gc"])):
    s = stats([b for b in q1c if f(b)])
    if s["graded"]:
        out.append("| %s | %d | %d | %+.1f%% | %+.0f..%+.0f%% | %.3f | %s | %s |" % (k, s["n"], s["graded"], 100 * s["roi"], 100 * s["lo"],
                   100 * s["hi"], s["p"], "-" if s["clv"] is None else "%.4f" % s["clv"], s["cand"]))
    else:
        out.append("| %s | %d | 0 | - | - | - | - | False |" % (k, s["n"]))
by = {}
for b in q1c:
    by.setdefault((b["pull"], b["gc"]), 0); by[(b["pull"], b["gc"])] += 1
out += ["", "Bets by pull x both-confirmed: " + ", ".join("%s/%s %d" % (p, g, n) for (p, g), n in sorted(by.items()))]
open(os.path.join(ROOT, "research/fwd/q11.md"), "w").write("\n".join(out) + "\n")
print("\n".join(out))
