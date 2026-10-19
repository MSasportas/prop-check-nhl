"""R6 game script (team strength), R7 teammate absence. Features from boxscores dated strictly before the game."""
import bisect
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rlib  # noqa: E402
import wf  # noqa: E402

games = {g["id"]: g for g in json.load(open(os.path.join(rlib.RAW, "nhl", "games.json")))}
tg = defaultdict(list)      # team -> [(date, gd, set(pids))]
psog = defaultdict(list)    # pid -> [(date, sog)]
for gid, g in sorted(games.items(), key=lambda x: x[1]["date"]):
    f = os.path.join(rlib.RAW, "nhl", "box", "%d.json" % gid)
    if not os.path.exists(f) or gid // 10000 % 100 != 2:
        continue
    b = json.load(open(f))
    if "playerByGameStats" not in b:
        continue
    a, h = b["awayTeam"], b["homeTeam"]
    for side, me, op in (("awayTeam", a, h), ("homeTeam", h, a)):
        ids = set()
        for grp in ("forwards", "defense"):
            for p in b["playerByGameStats"][side].get(grp, []):
                if (p.get("toi") or "0:00") != "0:00":
                    ids.add(p["playerId"])
                    psog[p["playerId"]].append((g["date"], p.get("sog", 0)))
        tg[me["abbrev"]].append((g["date"], me.get("score", 0) - op.get("score", 0), ids))


def before(log, d):
    return log[:bisect.bisect_left([x[0] for x in log], d)]


def gdpg(team, d):
    x = before(tg[team], d)
    return sum(e[1] for e in x) / len(x) if len(x) >= 5 else 0.0


def avg_sog(pid, d):
    x = before(psog[pid], d)
    return sum(e[1] for e in x) / len(x) if x else 0.0


rows = [r for r in rlib.load("../research/feat_r3.jsonl")]
cache = {}
for r in rows:
    k = (r["team"], r["date"])
    if k not in cache:
        x = before(tg[r["team"]], r["date"])
        last10 = x[-10:]
        cnt = defaultdict(int)
        for e in last10:
            for p in e[2]:
                cnt[p] += 1
        lastg = x[-1][2] if x else set()
        cache[k] = sum(avg_sog(p, r["date"]) for p, c in cnt.items() if c >= 5 and p not in lastg) if x else 0.0
    r["absent_sog"] = cache[k]
    r["sdiff"] = gdpg(r["team"], r["date"]) - gdpg(r["opp"], r["date"])
    own = avg_sog(r["pid"], r["date"])
    r["own"] = own
isD = lambda r: float(r["pos"] == "D")
wf.run("R6", rows, lambda r: [r["sdiff"], r["sdiff"] * isD(r)])
wf.run("R7", rows, lambda r: [r["absent_sog"], r["absent_sog"] * r["own"]])
