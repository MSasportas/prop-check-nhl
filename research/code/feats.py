"""Pre-game features for every Hard Rock shots line, built ONLY from 2025-26 NHL boxscores dated strictly before the
game (no leakage). Writes OUT/feat_r3.jsonl. python3 -I feats.py"""
import bisect
import json
import os
from collections import defaultdict

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rlib  # noqa: E402

games = {g["id"]: g for g in json.load(open(os.path.join(rlib.RAW, "nhl", "games.json")))}
plog = defaultdict(list)   # pid -> [(date, sog, toi_min)]
tlog = defaultdict(list)   # team -> [(date, sog_for, sog_against)]
tdates = defaultdict(set)
for gid, g in games.items():
    f = os.path.join(rlib.RAW, "nhl", "box", "%d.json" % gid)
    if not os.path.exists(f):
        continue
    b = json.load(open(f))
    if b.get("gameState") not in ("OFF", "FINAL") or "playerByGameStats" not in b:
        continue
    if gid // 10000 % 100 != 2:   # regular season only
        continue
    a, h = b["awayTeam"], b["homeTeam"]
    tlog[a["abbrev"]].append((g["date"], a.get("sog", 0), h.get("sog", 0)))
    tlog[h["abbrev"]].append((g["date"], h.get("sog", 0), a.get("sog", 0)))
    tdates[a["abbrev"]].add(g["date"]); tdates[h["abbrev"]].add(g["date"])
    for side in ("awayTeam", "homeTeam"):
        for grp in ("forwards", "defense"):
            for p in b["playerByGameStats"][side].get(grp, []):
                t = p.get("toi") or "0:00"
                mm, ss = t.split(":")
                toi = int(mm) + int(ss) / 60
                if toi <= 0:
                    continue
                plog[p["playerId"]].append((g["date"], p.get("sog", 0), toi))
for d in (plog, tlog):
    for k in d:
        d[k].sort()


def prior(log, date):
    i = bisect.bisect_left([x[0] for x in log], date)
    return log[:i]


from datetime import date as D, timedelta
rows = rlib.load("shots45_lines.jsonl")
out = open(os.path.join(rlib.OUT, "feat_r3.jsonl"), "w")
for r in rows:
    pl = prior(plog.get(r["pid"], []), r["date"])
    tl = prior(tlog.get(r["opp"], []), r["date"])
    L = r["line"]
    f = {"n_prior": len(pl)}
    if pl:
        s = [x[1] for x in pl]
        t = [x[2] for x in pl]
        f["l5"] = sum(s[-5:]) / len(s[-5:]) - L
        f["l10"] = sum(s[-10:]) / len(s[-10:]) - L
        f["szn"] = sum(s) / len(s) - L
        f["over10"] = sum(x > L for x in s[-10:]) / len(s[-10:])
        f["toi_tr"] = sum(t[-5:]) / len(t[-5:]) - sum(t) / len(t)
        f["sog_per60_l10"] = 60 * sum(s[-10:]) / max(1, sum(t[-10:]))
    if tl:
        f["opp_sa10"] = sum(x[2] for x in tl[-10:]) / len(tl[-10:])
    yday = (D.fromisoformat(r["date"]) - timedelta(days=1)).isoformat()
    f["b2b"] = int(yday in tdates.get(r["team"], ()))
    f["opp_b2b"] = int(yday in tdates.get(r["opp"], ()))
    r2 = {k: r[k] for k in ("date", "gid", "pid", "name", "team", "opp", "home", "line", "over", "under", "ok", "result",
                            "actual", "p_over", "pos", "missed_last")}
    r2.update(f)
    out.write(json.dumps(r2) + "\n")
out.close()
print("rows", len(rows), "players", len(plog), "teams", len(tlog))
