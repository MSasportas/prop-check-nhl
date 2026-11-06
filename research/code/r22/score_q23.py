#!/usr/bin/env python3
"""Q23a-b (HYPOTHESES.md run 22), nights >= 2026-11-06 only: OVER on forwards whose team dresses 11F/7D per data/state/lineup_history
as known at the shadow row's `close` read (last page if last_at <= close.at, else first_today if first_today_at <= close.at, else skip).
Q23a: ctx.toi_last5 >= 16.0; Q23b: every forward. OVER at the close Hard Rock price (>= -200), graded on result.over.
Also prints seen nights (descriptive, not a test). Read-only on data/; writes research/fwd/q23.md.  python3 -I score_q23.py [repo_root]"""
import glob, json, os, random, sys
from datetime import datetime
ROOT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "..", ".."))
START, BAR_N, ALPHA = "2026-11-06", 300, 0.05 / 44


def dec(a):
    return 1 + a / 100.0 if a > 0 else 1 + 100.0 / -a


def ts(x):
    return datetime.fromisoformat(x) if x else None


def shape(groups, pid):
    fw = [p for k in ("f1", "f2", "f3", "f4") for p in groups.get(k, [])]
    dd = [p for k in ("d1", "d2", "d3", "d4") for p in groups.get(k, [])]
    return len(fw) == 11 and len(dd) == 7 and pid in fw


bets = {"Q23a": [], "Q23b": []}
for f in sorted(glob.glob(os.path.join(ROOT, "data/shadow/2026-*.json"))):
    day = os.path.basename(f)[:10]
    lh = os.path.join(ROOT, "data/state/lineup_history/%s.json" % day)
    if not os.path.exists(lh):
        continue
    teams = json.load(open(lh)).get("teams", {})
    for r in json.load(open(f))["rows"]:
        ctx = r.get("ctx") or {}
        c = r.get("close") or {}
        if r.get("market") != "shots" or ctx.get("pos") != "F" or c.get("over") is None or c["over"] < -200:
            continue
        t = teams.get(ctx.get("team")) or {}
        if t.get("game_id") not in (None, r["game_id"]):
            continue
        at = ts(c.get("at"))
        page = None
        if t.get("last_at") and ts(t["last_at"]) <= at:
            page = t.get("last")
        elif t.get("first_today_at") and ts(t["first_today_at"]) <= at:
            page = t.get("first_today")
        if not page or not shape(page.get("groups") or {}, r["pid"]):
            continue
        res = (r.get("result") or {}).get("over")
        b = dict(date=day, game=r["game_id"], name=r["name"], line=r["line"], price=c["over"], res=res,
                 pl={"W": dec(c["over"]) - 1, "L": -1.0, "P": 0.0}.get(res))
        bets["Q23b"].append(b)
        if (ctx.get("toi_last5") or 0) >= 16.0:
            bets["Q23a"].append(b)


def stats(bs):
    g = [b for b in bs if b["pl"] is not None]
    if not g:
        return "bets %d, graded 0" % len(bs)
    games = {}
    for b in g:
        games.setdefault(b["game"], []).append(b["pl"])
    keys = list(games); rng = random.Random(11); boots = []
    for _ in range(2000):
        s = [x for k in (rng.choice(keys) for _ in keys) for x in games[k]]
        boots.append(sum(s) / len(s))
    boots.sort(); roi = sum(b["pl"] for b in g) / len(g); p = sum(x <= 0 for x in boots) / 2000
    return "bets %d, graded %d, W %d, ROI %+.1f%%, 90%% CI %+.0f..%+.0f%%, p %.3f, candidate %s" % (
        len(bs), len(g), sum(b["res"] == "W" for b in g), 100 * roi, 100 * boots[100], 100 * boots[1899], p,
        len(g) >= BAR_N and roi > 0 and p < ALPHA)


out = ["# Q23 forward (research/code/r22/score_q23.py), nights >= %s. Bar: n >= 300 graded, ROI > 0, p < %.5f." % (START, ALPHA), ""]
for k, bs in bets.items():
    out.append("- %s: %s" % (k, stats([b for b in bs if b["date"] >= START])))
out += ["", "Descriptive, seen nights < %s (not a test):" % START]
for k, bs in bets.items():
    out.append("- %s: %s" % (k, stats([b for b in bs if b["date"] < START])))
open(os.path.join(ROOT, "research/fwd/q23.md"), "w").write("\n".join(out) + "\n")
print("\n".join(out))
