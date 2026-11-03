"""Run 19 tests GG1-GG3 (registered in HYPOTHESES.md run 19, commit f4cbe9d, before testing).
Inputs (scratch, PC_R19_DIR): h/work/shots45_lines.jsonl (hist tgz), add/feat/h2h*.json (h2h addon tgz), nhl/pbp/<gid>.json
(r17/fetch17.py, Feb 28 cut-off), nhl/birth.json + nhl/teams.json (r19/fetch19.py). Lockbox rows (Mar 1+) never built or scored.
python3 -I gg19.py [placebo NAME T]"""
import contextlib, io, json, os, random, statistics, sys
from bisect import bisect_left
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import rlib, wf  # noqa: E402

D = os.environ["PC_R19_DIR"]
P = os.path.join(D, "nhl/pbp")
G = {}
for f in os.listdir(P):
    j = json.load(open(os.path.join(P, f)))
    if j["date"] < rlib.LOCKBOX:
        G[j["gid"]] = j

A = {}  # (gid, team) -> aggregates
for gid, g in G.items():
    side = {g["hid"]: "h", g["aid"]: "a"}; ab = {g["hid"]: g["home"], g["aid"]: g["away"]}
    for t in (g["home"], g["away"]):
        A[(gid, t)] = {"date": g["date"], "ea": defaultdict(int), "eaT": 0, "ot": defaultdict(int), "otT": 0}
    for x in g["plays"]:
        if x["t"] not in ("shot-on-goal", "goal") or x["pt"] == "SO":
            continue
        tid = x["d"].get("eventOwnerTeamId"); t = ab.get(tid)
        if t is None:
            continue
        pid = x["d"].get("shootingPlayerId") or x["d"].get("scoringPlayerId")
        a = A[(gid, t)]
        sc = x.get("sc") or ""
        if len(sc) == 4:
            own_g = sc[3] if side[tid] == "h" else sc[0]
            if own_g == "0":
                a["eaT"] += 1
                if pid:
                    a["ea"][pid] += 1
        if x["pt"] == "OT":
            a["otT"] += 1
            if pid:
                a["ot"][pid] += 1

sched = defaultdict(list)
for (gid, t), a in A.items():
    sched[t].append((a["date"], gid))
for v in sched.values():
    v.sort()
sd = {t: [x[0] for x in v] for t, v in sched.items()}


def prev(t, d, k=None):
    i = bisect_left(sd.get(t, []), d); lo = 0 if k is None else max(0, i - k)
    return [gid for _, gid in sched.get(t, [])[lo:i]]


# moneyline consensus (latest h2h snapshot at or before puck - 45 min)
ab = {t["fullName"]: t["triCode"] for t in json.load(open(os.path.join(D, "nhl/teams.json")))["data"]}
ab.update({"Montréal Canadiens": "MTL", "Montreal Canadiens": "MTL", "St Louis Blues": "STL", "St. Louis Blues": "STL",
           "Utah Mammoth": "UTA", "Utah Hockey Club": "UTA"})
snaps = defaultdict(list)  # (home, commence[:13]) -> [(ts, {abbr: pw})]
FD = os.path.join(D, "add/feat")
for f in sorted(os.listdir(FD)):
    if not f.startswith("h2h"):
        continue
    j = json.load(open(os.path.join(FD, f))); ts = j["timestamp"]
    for e in j["data"]:
        h, a = ab.get(e["home_team"]), ab.get(e["away_team"])
        if not h or not a or e["commence_time"] <= ts:
            continue
        fs = []
        for b in e["bookmakers"]:
            for m in b["markets"]:
                if m["key"] == "h2h":
                    o = {x["name"]: x["price"] for x in m["outcomes"]}
                    if e["home_team"] in o and e["away_team"] in o:
                        fs.append(rlib.fair_prop(o[e["home_team"]], o[e["away_team"]]))
        if fs:
            pw = statistics.median(fs); snaps[(h, e["commence_time"][:13])].append((ts, {h: pw, a: 1 - pw}))


def zt(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


B = json.load(open(os.path.join(D, "nhl/birth.json")))
lines = [json.loads(l) for l in open(os.path.join(D, "h/work/shots45_lines.jsonl"))]
lines = [r for r in lines if r["date"] < rlib.LOCKBOX and r["over"] is not None and r["under"] is not None and r["gid"] in G]
npw = 0
for r in lines:
    d, t, pid, g = r["date"], r["team"], r["pid"], G[r["gid"]]
    cut = zt(g["start"]) - timedelta(minutes=45); pw = 0.5
    c = [s for s in snaps.get((g["home"], g["start"][:13]), []) if zt(s[0]) <= cut]
    if c:
        pw = max(c)[1].get(t, 0.5); npw += 1
    r["pw"] = pw
    pg = prev(t, d, 40); eaT = sum(A[(x, t)]["eaT"] for x in pg)
    r["eash"] = sum(A[(x, t)]["ea"].get(pid, 0) for x in pg) / eaT if eaT >= 10 else 0.0
    r["eatr"] = r["eash"] * (0.5 - pw)
    pg = prev(t, d); otT = sum(A[(x, t)]["otT"] for x in pg)
    r["otsh"] = sum(A[(x, t)]["ot"].get(pid, 0) for x in pg) / otT if otT >= 8 else 0.0
    r["otcl"] = r["otsh"] * (0.5 - abs(pw - 0.5))
    bd = B.get(str(pid))
    r["age"] = (date.fromisoformat(d) - date.fromisoformat(bd)).days / 365.25 if bd else 28.0
    r["b2b"] = float(bool(prev(t, d)) and sd[t][bisect_left(sd[t], d) - 1] == str(date.fromisoformat(d) - timedelta(days=1)))
    r["a28"] = r["age"] - 28; r["b2ba"] = r["b2b"] * r["a28"]

feats = {"GG1": lambda r: [r["eash"], r["eatr"]], "GG2": lambda r: [r["otsh"], r["otcl"]], "GG3": lambda r: [r["b2ba"], r["a28"]]}
KEYS = {"GG1": ["eash", "eatr"], "GG2": ["otsh", "otcl"], "GG3": ["b2ba", "a28"]}


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
    print("games fetched", len(G), "lines", len(lines), "graded Nov-Feb lines", len(te), "lines with pw", npw)
    for k in ["pw", "eash", "otsh", "age", "b2b"]:
        a = np.array([r[k] for r in te], float)
        print("feature %s mean %.4f sd %.4f nonzero %d" % (k, a.mean(), a.std(), int((a != 0).sum())))
    for n in ("GG1", "GG2", "GG3"):
        wf.run(n, lines, feats[n])
    fixed("GG1r OVER when ea share >= .15 and pw <= .40", lambda r: "over" if r["eash"] >= 0.15 and r["pw"] <= 0.40 else None)
    fixed("GG2r OVER when OT share >= .20 and |pw-.5| <= .06", lambda r: "over" if r["otsh"] >= 0.20 and abs(r["pw"] - 0.5) <= 0.06 else None)
    fixed("GG3r UNDER age >= 33 on team B2B", lambda r: "under" if r["age"] >= 33 and r["b2b"] else None)
