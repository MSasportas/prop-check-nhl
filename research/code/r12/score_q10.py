#!/usr/bin/env python3
"""Q10 (HYPOTHESES.md run 12): returners' overs forward. Every data/shadow shots row with ctx.missed_last = true, OVER at the row's
`close` Hard Rock price (last pre-game read), over >= -200, graded on row.result.over (W/L/P). Read-only on data/; writes research/fwd/q10.md.
  python3 -I research/code/r12/score_q10.py [repo_root]"""
import glob, json, os, random, sys
ROOT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "..", ".."))
BAR_N, ALPHA = 300, 0.05 / 25


def dec(a):
    return 1 + a / 100.0 if a > 0 else 1 + 100.0 / -a


bets = []
for f in sorted(glob.glob(os.path.join(ROOT, "data/shadow/2026-*.json"))):
    for r in json.load(open(f))["rows"]:
        if r.get("market") != "shots" or not (r.get("ctx") or {}).get("missed_last"):
            continue
        c = r.get("close") or r.get("open") or {}
        o = c.get("over")
        if o is None or o < -200:
            continue
        res = (r.get("result") or {}).get("over")
        pl = {"W": dec(o) - 1, "L": -1.0, "P": 0.0}.get(res)
        bets.append(dict(date=os.path.basename(f)[:10], game=r["game_id"], name=r["name"], line=r["line"], price=o, res=res, pl=pl))
g = [b for b in bets if b["pl"] is not None]
out = ["# Q10 forward: returners' overs (research/code/r12/score_q10.py). Bar: n >= 300 graded, ROI > 0, p < %.4f." % ALPHA, ""]
if g:
    games = {}
    for b in g:
        games.setdefault(b["game"], []).append(b["pl"])
    keys = list(games); rng = random.Random(11); boots = []
    for _ in range(2000):
        s = [x for k in (rng.choice(keys) for _ in keys) for x in games[k]]
        boots.append(sum(s) / len(s))
    boots.sort()
    roi = sum(b["pl"] for b in g) / len(g); p = sum(x <= 0 for x in boots) / 2000
    out.append("bets %d, graded %d, W %d, ROI %+.1f%%, 90%% CI %+.0f..%+.0f%%, p %.3f, candidate %s" % (
        len(bets), len(g), sum(b["res"] == "W" for b in g), 100 * roi, 100 * boots[100], 100 * boots[1899], p,
        len(g) >= BAR_N and roi > 0 and p < ALPHA))
else:
    out.append("bets %d, graded 0" % len(bets))
open(os.path.join(ROOT, "research/fwd/q10.md"), "w").write("\n".join(out) + "\n")
print("\n".join(out))
