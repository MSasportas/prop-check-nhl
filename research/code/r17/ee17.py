"""Run 17 tests EE1-EE3 (registered in HYPOTHESES.md run 17, commit 99edae1, before testing).
Inputs (scratch, PC_R17_DIR): h/work/shots45_lines.jsonl (hist tgz), nhl/pbp/<gid>.json (r17/fetch17.py, Feb 28 cut-off).
Lockbox rows (Mar 1+) never built or scored.  python3 -I ee17.py [placebo NAME T]"""
import contextlib, io, json, os, random, sys
from bisect import bisect_left
from collections import defaultdict
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import rlib, wf  # noqa: E402

D = os.environ["PC_R17_DIR"]
P = os.path.join(D, "nhl/pbp")
G = {}
for f in os.listdir(P):
    j = json.load(open(os.path.join(P, f)))
    if j["date"] < rlib.LOCKBOX:
        G[j["gid"]] = j

A = {}  # (gid, team) -> per team-game aggregates
for gid, g in G.items():
    ab = {g["hid"]: g["home"], g["aid"]: g["away"]}
    for t in (g["home"], g["away"]):
        A[(gid, t)] = {"date": g["date"], "opp": g["away"] if t == g["home"] else g["home"], "fow": 0, "fo": 0,
                       "unb": 0, "miss": 0, "att": defaultdict(int)}
    for x in g["plays"]:
        t = ab.get(x["d"].get("eventOwnerTeamId"))
        if t is None:
            continue
        if x["t"] == "faceoff":
            A[(gid, t)]["fow"] += 1
            for u in (g["home"], g["away"]):
                A[(gid, u)]["fo"] += 1
        elif x["t"] in ("shot-on-goal", "goal", "missed-shot") and x["pt"] != "SO":
            a = A[(gid, t)]; a["unb"] += 1; a["miss"] += x["t"] == "missed-shot"
            pid = x["d"].get("shootingPlayerId") or x["d"].get("scoringPlayerId")
            if pid:
                a["att"][pid] += 1

sched = defaultdict(list)
for (gid, t), a in A.items():
    sched[t].append((a["date"], gid))
for v in sched.values():
    v.sort()
sd = {t: [x[0] for x in v] for t, v in sched.items()}


def prev(t, d, k):
    i = bisect_left(sd.get(t, []), d); return [gid for _, gid in sched.get(t, [])[max(0, i - k):i]]


# league miss rate before d (cumulative over team-games)
ml = sorted((a["date"], a["miss"], a["unb"]) for a in A.values()); mdt = [x[0] for x in ml]
cm = np.cumsum([x[1] for x in ml]); cu = np.cumsum([x[2] for x in ml])


def lgmiss(d):
    i = bisect_left(mdt, d); return cm[i - 1] / cu[i - 1] if i else 0.27


allr = [json.loads(l) for l in open(os.path.join(D, "h/work/shots45_lines.jsonl"))]
allr = [r for r in allr if r["date"] < rlib.LOCKBOX and r["over"] is not None and r["under"] is not None]
# residuals by (gid, team) and (gid, opp)
resT = defaultdict(list); resO = defaultdict(list)
for r in allr:
    if r["result"] == "OK":
        x = float(r["actual"] > r["line"]) - rlib.fair_prop(r["over"], r["under"])
        resT[(r["gid"], r["team"])].append(x); resO[(r["gid"], r["opp"])].append(x)

lines = [r for r in allr if r["gid"] in G]
for r in lines:
    d, t, o, pid, gid = r["date"], r["team"], r["opp"], r["pid"], r["gid"]
    # EE1
    def fo(team):
        pg = prev(team, d, 20); n = sum(A[(x, team)]["fo"] for x in pg)
        return sum(A[(x, team)]["fow"] for x in pg) / n - 0.5 if len(pg) >= 5 and n else 0.0
    r["fo"], r["foo"] = fo(t), fo(o)
    # EE2
    v = [x for g in prev(t, d, 10) for x in resT.get((g, t), [])]
    r["tres"] = float(np.mean(v)) if len(v) >= 20 else 0.0
    v = [x for g in prev(o, d, 10) for x in resO.get((g, o), [])]
    r["ores"] = float(np.mean(v)) if len(v) >= 20 else 0.0
    # EE3
    lm = lgmiss(d); po = prev(o, d, 20)
    if len(po) >= 5:
        u = sum(A[(x, A[(x, o)]["opp"])]["unb"] for x in po); m = sum(A[(x, A[(x, o)]["opp"])]["miss"] for x in po)
        r["mdev"] = m / u - lm if u else 0.0
    else:
        r["mdev"] = 0.0
    pt = prev(t, d, 20)
    r["att20"] = sum(A[(x, t)]["att"].get(pid, 0) for x in pt) / 20.0
    r["mdatt"] = r["mdev"] * r["att20"]

feats = {"EE1": lambda r: [r["fo"], r["foo"]], "EE2": lambda r: [r["tres"], r["ores"]], "EE3": lambda r: [r["mdev"], r["mdatt"]]}
KEYS = {"EE1": ["fo", "foo"], "EE2": ["tres", "ores"], "EE3": ["mdev", "mdatt"]}


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
    print("games fetched", len(G), "lines", len(lines), "graded Nov-Feb lines", len(te))
    for k in ["fo", "foo", "tres", "ores", "mdev", "att20"]:
        a = np.array([r[k] for r in te], float)
        print("feature %s mean %.4f sd %.4f nonzero %d" % (k, a.mean(), a.std(), int((a != 0).sum())))
    for n in ("EE1", "EE2", "EE3"):
        wf.run(n, lines, feats[n])
    fixed("EE1r OVER when fo - fo_opp >= +0.04", lambda r: "over" if r["fo"] - r["foo"] >= 0.04 else None)
    fixed("EE2r OVER when ores >= +0.08", lambda r: "over" if r["ores"] >= 0.08 else None)
    fixed("EE3r UNDER when miss dev >= +0.02 and att20 >= 3.5", lambda r: "under" if r["mdev"] >= 0.02 and r["att20"] >= 3.5 else None)
