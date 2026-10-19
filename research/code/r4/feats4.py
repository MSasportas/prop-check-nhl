"""Run 4 features for every Hard Rock shots line (shots45_lines), PRIOR-ONLY: every input for a line dated d comes from
games dated < d (2024-25 is entirely before). Writes R4/feat4.jsonl. python3 -I feats4.py
Inputs (scratch): R4/work/shots45_lines.jsonl (hist tgz), R4/addon/h2h_rows.jsonl (addon tgz), R4/nhl/*.jsonl (fetch_rest.py),
BOX = cached 2025-26 NHL boxscores + games.json (PC_BOX_DIR)."""
import bisect
import json
import math
import os
from collections import defaultdict
from datetime import date as D, datetime

R4 = os.environ.get("PC_R4_DIR", "/tmp/claude-0/-home-claude/ab9b3f07-215a-50c7-96a2-d84b6c4f2d08/scratchpad/r4")
BOX = os.environ.get("PC_BOX_DIR", "/tmp/claude-0/-home-claude/ab9b3f07-215a-50c7-96a2-d84b6c4f2d08/scratchpad/hist/raw/nhl")


def jl(p):
    return [json.loads(l) for l in open(p)]


def be(a):
    return (-a) / (-a + 100.0) if a < 0 else 100.0 / (a + 100.0)


def fair(o, u):
    a, b = be(o), be(u)
    return a / (a + b)


# ---------- team logs (both seasons) -> per-arena home/road totals, per-team SF/SA/date/arena
tl = []   # (date, team, opp, is_home, sf, sa, arena)
for f in ("team_2425", "team_2526"):
    rows = jl(os.path.join(R4, "nhl", f + ".jsonl"))
    byg = defaultdict(list)
    for r in rows:
        byg[r["gameId"]].append(r)
    for gid, rs in byg.items():
        if len(rs) != 2:
            continue
        a, b = rs
        ab = {a["teamId"]: b["opponentTeamAbbrev"], b["teamId"]: a["opponentTeamAbbrev"]}
        for r in rs:
            me = ab[r["teamId"]]
            home = r["homeRoad"] == "H"
            arena = me if home else r["opponentTeamAbbrev"]
            tl.append((r["gameDate"][:10], me, r["opponentTeamAbbrev"], home, r["shotsForPerGame"], r["shotsAgainstPerGame"], arena))
tl.sort()
tdates = [x[0] for x in tl]
team_games = defaultdict(list)   # team -> [(date, sf, sa, arena)]
for d, me, op, home, sf, sa, ar in tl:
    team_games[me].append((d, sf, sa, ar))


def arena_logA(arena, d):
    hs, rs = [], []
    for (dd, sf, sa, ar) in team_games[arena]:
        if dd >= d:
            break
        (hs if ar == arena else rs).append(sf + sa)
    if not hs or not rs:
        return 0.0, 0
    n = len(hs)
    return n / (n + 30.0) * math.log((sum(hs) / n) / (sum(rs) / len(rs))), n


_arena_cache = {}


def arena_all(d):
    if d not in _arena_cache:
        _arena_cache[d] = {t: arena_logA(t, d)[0] for t in team_games}
    return _arena_cache[d]


# ---------- player SOG logs: 2024-25 REST + 2025-26 boxscores
plog = defaultdict(list)   # pid -> [(date, sog, toi_min)]
for r in jl(os.path.join(R4, "nhl", "skater_2425.jsonl")):
    toi = (r.get("timeOnIcePerGame") or 0) / 60.0
    if toi > 0:
        plog[r["playerId"]].append((r["gameDate"][:10], r.get("shots") or 0, toi))
games = {g["id"]: g for g in json.load(open(os.path.join(BOX, "games.json")))}
plog26 = defaultdict(list)
for gid, g in games.items():
    fp = os.path.join(BOX, "box", "%d.json" % gid)
    if gid // 10000 % 100 != 2 or not os.path.exists(fp):
        continue
    b = json.load(open(fp))
    if b.get("gameState") not in ("OFF", "FINAL") or "playerByGameStats" not in b:
        continue
    for side in ("awayTeam", "homeTeam"):
        for grp in ("forwards", "defense"):
            for p in b["playerByGameStats"][side].get(grp, []):
                mm, ss = (p.get("toi") or "0:00").split(":")
                toi = int(mm) + int(ss) / 60
                if toi > 0:
                    plog26[p["playerId"]].append((g["date"], p.get("sog", 0), toi))
for pid, v in plog26.items():
    plog[pid].extend(v)
for d_ in (plog, plog26):
    for k in d_:
        d_[k].sort()

# realtime (attempts) and PP TOI, 2025-26
rt = defaultdict(list)   # pid -> [(date, attempts, sog_from_rt)]
for r in jl(os.path.join(R4, "nhl", "realtime_2526.jsonl")):
    att = r.get("totalShotAttempts") or 0
    sog = att - (r.get("missedShots") or 0) - (r.get("shotAttemptsBlocked") or 0)
    rt[r["playerId"]].append((r["gameDate"][:10], att, sog))
pp = defaultdict(list)
for r in jl(os.path.join(R4, "nhl", "toi_2526.jsonl")):
    pp[r["playerId"]].append((r["gameDate"][:10], (r.get("ppTimeOnIce") or 0) / 60.0))
for d_ in (rt, pp):
    for k in d_:
        d_[k].sort()


def prior(log, d):
    i = bisect.bisect_left([x[0] for x in log], d)
    return log[:i]


# schedule 2025-26 for rest / b2b / travel
sched = defaultdict(list)   # team -> [(date, arena)]
for g in games.values():
    if g["id"] // 10000 % 100 != 2:
        continue
    sched[g["away"]].append((g["date"], g["home"]))
    sched[g["home"]].append((g["date"], g["home"]))
for k in sched:
    sched[k].sort()


def rest(team, d, arena):
    pr = [x for x in sched[team] if x[0] < d]
    if not pr:
        return None, None
    last = pr[-1]
    days = (D.fromisoformat(d) - D.fromisoformat(last[0])).days
    return days, int(last[1] != arena)


# moneyline: latest snapshot at or before the shots snapshot
ml = defaultdict(list)
for h in jl(os.path.join(R4, "addon", "h2h_rows.jsonl")):
    if h.get("cons_h") is not None:
        ml[h["gid"]].append((datetime.fromisoformat(h["snap"].replace("Z", "+00:00")), h["cons_h"]))

lines = jl(os.path.join(R4, "work", "shots45_lines.jsonl"))
lines.sort(key=lambda r: (r["date"], r["gid"]))
hr_hist = defaultdict(list)   # pid -> [(date, res, line)]  (Hard Rock line history, OK results only)
out = open(os.path.join(R4, "feat4.jsonl"), "w")
pending = []
cur = None
for r in lines + [None]:
    if r is None or r["date"] != cur:
        for (pid, d, res, L) in pending:
            hr_hist[pid].append((d, res, L))
        pending = []
        if r is None:
            break
        cur = r["date"]
    d = r["date"]
    arena = r["team"] if r["home"] else r["opp"]
    f = {}
    f["logA"], f["arena_n"] = arena_logA(arena, d)
    al = arena_all(d)
    srt = sorted(al.values())
    f["arena_top5"] = int(f["logA"] >= srt[-5] and f["logA"] >= 0)
    f["arena_bot5"] = int(f["logA"] <= srt[4] and f["logA"] <= 0)
    at = datetime.fromisoformat(r["at"])
    snaps = [x for x in ml.get(r["gid"], []) if x[0] <= at]
    if snaps:
        ch = max(snaps)[1]
        f["pw"] = ch if r["home"] else 1 - ch
    else:
        f["pw"] = None
    hh = hr_hist[r["pid"]]
    f["hr_n"] = len(hh)
    f["k3"] = sum(x[1] for x in hh) / (len(hh) + 10.0)
    f["prev_line"] = hh[-1][2] if hh else None
    pl = prior(plog.get(r["pid"], []), d)
    s = [x[1] for x in pl]
    f["all_n"] = len(s)
    if s:
        m = sum(s) / len(s)
        f["all_mean"] = m
        f["all_var"] = sum((x - m) ** 2 for x in s) / max(1, len(s) - 1)
        f["last_sog"] = s[-1]
        e = s[:-1]
        f["earlier_mean"] = sum(e) / len(e) if e else None
    p6 = prior(plog26.get(r["pid"], []), d)
    s6 = [x[1] for x in p6]
    t6 = [x[2] for x in p6]
    f["n_prior"] = len(s6)
    if s6:
        L = r["line"]
        f["l5"] = sum(s6[-5:]) / len(s6[-5:]) - L
        f["l10"] = sum(s6[-10:]) / len(s6[-10:]) - L
        f["szn"] = sum(s6) / len(s6) - L
        f["toi_tr"] = sum(t6[-5:]) / len(t6[-5:]) - sum(t6) / len(t6)
    pr_rt = prior(rt.get(r["pid"], []), d)[-20:]
    if pr_rt:
        f["att20"] = sum(x[1] for x in pr_rt) / len(pr_rt)
        f["sog20"] = sum(x[2] for x in pr_rt) / len(pr_rt)
        f["n20"] = len(pr_rt)
    pp10 = prior(pp.get(r["pid"], []), d)[-10:]
    f["pp10"] = sum(x[1] for x in pp10) / len(pp10) if pp10 else None
    tg = [x for x in team_games[r["team"]] if x[0] < d and x[0] >= "2025-10-01"][-10:]
    og = [x for x in team_games[r["opp"]] if x[0] < d and x[0] >= "2025-10-01"][-10:]
    f["team_sf10"] = sum(x[1] for x in tg) / len(tg) if tg else None
    f["opp_sa10"] = sum(x[2] for x in og) / len(og) if og else None
    f["rest"], f["travel"] = rest(r["team"], d, arena)
    f["opp_rest"], _ = rest(r["opp"], d, arena)
    f["b2b"] = int(f["rest"] == 1)
    f["opp_b2b"] = int(f["opp_rest"] == 1)
    row = {k: r[k] for k in ("date", "gid", "pid", "name", "team", "opp", "home", "line", "over", "under", "ok", "result",
                            "actual", "pos", "at")}
    row["f"] = fair(r["over"], r["under"])
    row.update(f)
    out.write(json.dumps(row) + "\n")
    if r["result"] == "OK":
        pending.append((r["pid"], d, float(r["actual"] > r["line"]) - row["f"], r["line"]))
out.close()
print("rows", len(lines))
