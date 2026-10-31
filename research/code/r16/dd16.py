"""Run 16 tests DD1-DD4 (registered in HYPOTHESES.md run 16, commit f6efeeb, before testing).
Inputs (scratch, PC_R16_DIR): h/work/shots45_lines.jsonl (hist tgz), add/feat/h2h*.json (h2h addon tgz),
nhl/pbp/<gid>.json (r16/fetch16.py, Feb 28 cut-off), nhl/teams.json. Lockbox rows (Mar 1+) never built or scored.
python3 -I dd16.py [placebo NAME T]"""
import contextlib, io, json, os, random, statistics, sys
from bisect import bisect_left
from collections import defaultdict
from datetime import datetime
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import rlib, wf  # noqa: E402

D = os.environ["PC_R16_DIR"]
P = os.path.join(D, "nhl/pbp")
G = {}
for f in os.listdir(P):
    j = json.load(open(os.path.join(P, f)))
    if j["date"] < rlib.LOCKBOX:
        G[j["gid"]] = j


def secs(t):
    m, s = t.split(":"); return 60 * int(m) + int(s)


# per (gid, team) aggregates
A = {}
for gid, g in G.items():
    ab = {g["hid"]: g["home"], g["aid"]: g["away"]}
    for t in (g["home"], g["away"]):
        A[(gid, t)] = {"date": g["date"], "opp": g["away"] if t == g["home"] else g["home"], "pp": defaultdict(int), "ppT": 0,
                       "tr": defaultdict(int), "trT": 0, "ot": defaultdict(int), "otT": 0, "reb": 0, "pen": 0,
                       "coach": g["hcoach"] if t == g["home"] else g["acoach"]}
    hs = as_ = 0; last = {}; npen = 0
    for x in g["plays"]:
        if x["t"] == "period-start" or x["t"] == "stoppage":
            last = {}; continue
        if x["t"] == "penalty":
            npen += 1; continue
        tid = x["d"].get("eventOwnerTeamId"); t = ab.get(tid)
        if t is None:
            continue
        ts = (x["per"], secs(x["tm"]))
        if x["t"] in ("shot-on-goal", "goal"):
            if x["pt"] == "SO":
                continue
            pid = x["d"].get("shootingPlayerId") or x["d"].get("scoringPlayerId")
            a = A[(gid, t)]
            sc = x.get("sc") or "1551"
            ag, ask, hsk, hg = int(sc[0]), int(sc[1]), int(sc[2]), int(sc[3])
            home = t == g["home"]
            own, opp = (hsk, ask) if home else (ask, hsk)
            if ag == 1 and hg == 1 and own > opp:
                a["pp"][pid] += 1; a["ppT"] += 1
            if x["pt"] == "REG":
                diff = (hs - as_) if home else (as_ - hs)
                if diff < 0:
                    a["tr"][pid] += 1; a["trT"] += 1
                else:
                    a["ot"][pid] += 1; a["otT"] += 1
            lp = last.get(t)
            if lp and lp[0] == ts[0] and 0 <= ts[1] - lp[1] <= 3:
                a["reb"] += 1
        if x["t"] in ("shot-on-goal", "goal", "missed-shot", "blocked-shot"):
            # blocked-shot owner is the blocking team in api-web; the shooting team is the other one
            st = t
            if x["t"] == "blocked-shot":
                st = g["away"] if t == g["home"] else g["home"]
            last[st] = ts
        if x["t"] == "goal":
            hs = x["d"].get("homeScore", hs); as_ = x["d"].get("awayScore", as_)
    for t in (g["home"], g["away"]):
        A[(gid, t)]["pen"] = npen

sched = defaultdict(list)
for (gid, t), a in A.items():
    sched[t].append((a["date"], gid))
for v in sched.values():
    v.sort()
sd = {t: [x[0] for x in v] for t, v in sched.items()}


def prev(t, d, k):
    i = bisect_left(sd.get(t, []), d); return [gid for _, gid in sched.get(t, [])[max(0, i - k):i]]


# referees
gl = sorted((g["date"], gid) for gid, g in G.items())
gdates = [x[0] for x in gl]
refhist = defaultdict(list)
for dte, gid in gl:
    for r in G[gid]["refs"]:
        refhist[r].append((dte, A[(gid, G[gid]["home"])]["pen"]))
cum = np.cumsum([A[(gid, G[gid]["home"])]["pen"] for _, gid in gl])


def lgpen(d):
    i = bisect_left(gdates, d); return cum[i - 1] / i if i else 8.0


def crew(gid, d):
    lm = lgpen(d); vals = []
    for r in G[gid]["refs"]:
        h = [p for dd, p in refhist[r] if dd < d]
        vals.append(sum(h) / len(h) if len(h) >= 5 else lm)
    return (sum(vals) / len(vals) if vals else lm) - lm


# league rebound mean per team-game before d
rl = sorted((a["date"], a["reb"]) for a in A.values()); rd = [x[0] for x in rl]; rc = np.cumsum([x[1] for x in rl])


def lgreb(d):
    i = bisect_left(rd, d); return rc[i - 1] / i if i else 2.0


# h2h consensus win prob
ab = {t["fullName"]: t["triCode"] for t in json.load(open(os.path.join(D, "nhl/teams.json")))["data"]}
ab.update({"Montréal Canadiens": "MTL", "Montreal Canadiens": "MTL", "St Louis Blues": "STL", "St. Louis Blues": "STL", "Utah Mammoth": "UTA", "Utah Hockey Club": "UTA"})
pwin = {}  # (home abbrev, start) -> (ts, {abbrev: pw})
FD = os.path.join(D, "add/feat")
miss = set()
for f in sorted(os.listdir(FD)):
    if not f.startswith("h2h"):
        continue
    j = json.load(open(os.path.join(FD, f))); ts = j["timestamp"]
    for e in j["data"]:
        if e["commence_time"] <= ts:
            continue
        h, a = ab.get(e["home_team"]), ab.get(e["away_team"])
        if not h or not a:
            miss.add(e["home_team"]); continue
        fs = []
        for b in e["bookmakers"]:
            for m in b["markets"]:
                if m["key"] != "h2h":
                    continue
                o = {x["name"]: x["price"] for x in m["outcomes"]}
                if e["home_team"] in o and e["away_team"] in o:
                    fs.append(rlib.fair_prop(o[e["home_team"]], o[e["away_team"]]))
        if fs:
            k = (h, e["commence_time"][:13])
            pw = statistics.median(fs)
            if k not in pwin or pwin[k][0] < ts:
                pwin[k] = (ts, {h: pw, a: 1 - pw})
if miss:
    print("unmapped h2h names", miss)

lines = [json.loads(l) for l in open(os.path.join(D, "h/work/shots45_lines.jsonl"))]
lines = [r for r in lines if r["date"] < rlib.LOCKBOX and r["over"] is not None and r["under"] is not None and r["gid"] in G]
npw = 0
for r in lines:
    d, t, o, pid, gid = r["date"], r["team"], r["opp"], r["pid"], r["gid"]
    g = G[gid]
    # DD1
    r["cdev"] = float(crew(gid, d))
    pg = prev(t, d, 15); ppT = sum(A[(x, t)]["ppT"] for x in pg)
    r["pps"] = sum(A[(x, t)]["pp"].get(pid, 0) for x in pg) / ppT if len(pg) >= 5 and ppT >= 10 else 0.0
    r["cdpp"] = r["cdev"] * r["pps"]
    # DD2
    pg = prev(t, d, 20); trT = sum(A[(x, t)]["trT"] for x in pg); otT = sum(A[(x, t)]["otT"] for x in pg)
    if len(pg) >= 5 and trT >= 15 and otT >= 15:
        r["sens"] = sum(A[(x, t)]["tr"].get(pid, 0) for x in pg) / trT - sum(A[(x, t)]["ot"].get(pid, 0) for x in pg) / otT
    else:
        r["sens"] = 0.0
    k = (g["home"], g["start"][:13]); pw = 0.5
    if k in pwin and pwin[k][0] <= g["start"]:
        pw = pwin[k][1].get(t, 0.5); npw += 1
    r["pw"] = pw; r["senspw"] = r["sens"] * (0.5 - pw)
    # DD3
    lm = lgreb(d)
    po = prev(o, d, 20)
    r["rebo"] = (sum(A[(x, A[(x, o)]["opp"])]["reb"] for x in po) / len(po) - lm) if len(po) >= 5 else 0.0
    pt = prev(t, d, 20)
    r["rebt"] = (sum(A[(x, t)]["reb"] for x in pt) / len(pt) - lm) if len(pt) >= 5 else 0.0
    # DD4
    def newc(team):
        me = A.get((gid, team))
        if not me:
            return 0.0
        return float(any(A[(x, team)]["coach"] != me["coach"] for x in prev(team, d, 10)))
    r["newc"] = newc(t); r["newco"] = newc(o)

feats = {"DD1": lambda r: [r["cdev"], r["cdpp"]], "DD2": lambda r: [r["sens"], r["senspw"]],
         "DD3": lambda r: [r["rebo"], r["rebt"]], "DD4": lambda r: [r["newc"], r["newco"]]}
KEYS = {"DD1": ["cdev", "cdpp"], "DD2": ["sens", "senspw"], "DD3": ["rebo", "rebt"], "DD4": ["newc", "newco"]}


def fixed(name, rule):
    b = []
    for r in lines:
        if r["date"][:7] not in rlib.TEST_MONTHS or r["result"] != "OK" or not r["ok"]:
            continue
        side = rule(r)
        if side is None or r[side] < -200:
            continue
        b.append(rlib.bet(r["gid"], r["date"], r[side], (r["actual"] > r["line"]) == (side == "over"), side=side, line=r["line"]))
    s = rlib.summ(b)
    print("%s %s | %s | p_one %s" % (name, rlib.fmt(s), rlib.by_month(b), s.get("p_one")))
    return b


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "placebo":
        name, T = sys.argv[2], float(sys.argv[3])
        rr = rlib.summ(wf.run(name, lines, feats[name], Ts=(T,), verbose=False)[T])["roi"]
        rng = random.Random(7); out = []; grp = defaultdict(list)
        for r in lines:
            grp[(r["date"], r["line"])].append(r)
        ks = KEYS[name]; orig = {k: [r[k] for r in lines] for k in ks}
        for it in range(200):
            for gg in grp.values():
                idx = list(range(len(gg))); rng.shuffle(idx)
                vals = {k: [gg[j][k] for j in idx] for k in ks}
                for j, r in enumerate(gg):
                    for k in ks:
                        r[k] = vals[k][j]
            with contextlib.redirect_stdout(io.StringIO()):
                b = wf.run(name, lines, feats[name], Ts=(T,), verbose=False)[T]
            out.append(rlib.summ(b)["roi"] or 0.0)
            for k in ks:
                for r, x in zip(lines, orig[k]):
                    r[k] = x
        out = np.array(out)
        print("placebo %s T=%.2f real %+.2f%% shuffled mean %+.2f%% sd %.2f >= real %d/200" % (
            name, T, 100 * rr, 100 * out.mean(), 100 * out.std(), int((out >= rr).sum())))
        sys.exit()
    te = [r for r in lines if r["date"][:7] in rlib.TEST_MONTHS and r["result"] == "OK"]
    print("games fetched", len(G), "lines", len(lines), "graded Nov-Feb lines", len(te), "lines with h2h pw", npw)
    for k in ["cdev", "pps", "sens", "pw", "rebo", "rebt", "newc", "newco"]:
        a = np.array([r[k] for r in te], float)
        print("feature %s mean %.3f sd %.3f nonzero %d" % (k, a.mean(), a.std(), int((a != 0).sum())))
    for n in ("DD1", "DD2", "DD3", "DD4"):
        wf.run(n, lines, feats[n])
    fixed("DD1r OVER when pps >= .20 and crew dev >= +1.0", lambda r: "over" if r["pps"] >= 0.20 and r["cdev"] >= 1.0 else None)
    fixed("DD2r OVER when sens >= +.03 and pw <= .42", lambda r: "over" if r["sens"] >= 0.03 and r["pw"] <= 0.42 else None)
    fixed("DD3r OVER when opp rebound dev >= +0.6", lambda r: "over" if r["rebo"] >= 0.6 else None)
    fixed("DD4r OVER on a team in its first 10 games under a new coach", lambda r: "over" if r["newc"] else None)
