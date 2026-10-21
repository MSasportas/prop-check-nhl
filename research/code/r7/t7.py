"""Run 7 tests T1-T5 (registered in HYPOTHESES.md run 7 before testing).
Inputs (scratch, PC_R7_DIR): h/work/shots45_lines.jsonl (hist tgz), nhl/*.jsonl (research/code/r6/fetch6.py).
Lockbox rows (Mar 1+) are never built or scored. python3 -I t7.py [placebo NAME]"""
import json, math, os, sys
from bisect import bisect_left
from collections import defaultdict, Counter
from datetime import date
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import rlib, wf  # noqa: E402

D = os.environ["PC_R7_DIR"]
LB = len(sys.argv) > 1 and sys.argv[1] == "lockbox"   # LB2 only: frozen T5 T=.01, look #2
if LB:
    rlib.LOCKBOX = "2026-05-01"
    rlib.TEST_MONTHS = ["2026-03", "2026-04"]
EXTRA_T = ["nhl/team_2526_lb.jsonl"] if LB else []
EXTRA_S = ("nhl/skater_2526_lb.jsonl",) if LB else ()
jl = lambda p: [json.loads(l) for l in open(os.path.join(D, p))]

# ---- team games: abbrev -> sorted [(date, gid, homeRoad, opp)]
tg = defaultdict(list); by_gid = defaultdict(list)
for t in jl("nhl/team_2425.jsonl") + jl("nhl/team_2526.jsonl") + sum((jl(x) for x in EXTRA_T), []):
    by_gid[t["gameId"]].append(t)
slate = Counter()
for gid, two in by_gid.items():
    if len(two) != 2:
        continue
    slate[two[0]["gameDate"]] += 1
    for a, b in ((two[0], two[1]), (two[1], two[0])):
        tg[b["opponentTeamAbbrev"]].append((a["gameDate"], gid, a["homeRoad"], a["opponentTeamAbbrev"]))
for L in tg.values():
    L.sort()
tdates = {k: [x[0] for x in L] for k, L in tg.items()}

sk = defaultdict(list)  # pid -> [(date, gid, team, shots, points)]
for p in ("nhl/skater_2425.jsonl", "nhl/skater_2526.jsonl") + EXTRA_S:
    for s in jl(p):
        sk[s["playerId"]].append((s["gameDate"], s["gameId"], s["teamAbbrev"], s["shots"], s["points"]))
for L in sk.values():
    L.sort()
skd = {p: [x[0] for x in L] for p, L in sk.items()}
pts25 = {p: sum(x[4] for x in L if x[0] < "2025-07-01") for p, L in sk.items()}
ranked = sorted(pts25.items(), key=lambda kv: -kv[1])
top25 = {p for p, _ in ranked[:25]}; top50 = {p for p, _ in ranked[:50]}

TZ = {**{t: 0 for t in "BOS BUF DET FLA MTL OTT TBL TOR CAR CBJ NJD NYI NYR PHI PIT WSH".split()},
      **{t: -1 for t in "CHI DAL MIN NSH STL WPG".split()},
      **{t: -2 for t in "COL EDM CGY UTA ARI".split()},
      **{t: -3 for t in "ANA LAK SJS SEA VAN VGK".split()}}


def prior(lst, dates, d):
    return lst[:bisect_left(dates, d)]


def missed(pid, team, d):
    tgs = [x for x in prior(tg.get(team, []), tdates.get(team, []), d) if x[0] >= "2025-07-01"]
    mine = [x for x in prior(sk.get(pid, []), skd.get(pid, []), d) if x[0] >= "2025-07-01" and x[2] == team]
    if not mine or not tgs:
        return 0
    last = mine[-1][0]
    return sum(1 for x in tgs if x[0] > last)


def arena(team, hr, opp):
    return team if hr == "H" else opp


def shift(team, home, opp, d):
    pr = prior(tg.get(team, []), tdates.get(team, []), d)
    if not pr:
        return 0
    pd, _, hr, po = pr[-1]
    if (date.fromisoformat(d) - date.fromisoformat(pd)).days > 2:
        return 0
    now = team if home else opp
    return TZ[now] - TZ[arena(team, hr, po)]


def newteam(pid, team, d):
    L = prior(sk.get(pid, []), skd.get(pid, []), d)
    old = [x for x in L if x[0] < "2025-07-01"]
    if not old:
        return 0.0, 0.0
    new = float(old[-1][2] != team)
    cur = [x for x in L if x[0] >= "2025-07-01" and x[2] == team]
    g = len(cur)
    dn = 0.0
    if new and g >= 3:
        dn = (sum(x[3] for x in cur) / g - sum(x[3] for x in old) / len(old)) * g / (g + 10.0)
    return new * float(g < 20), dn


lines = [json.loads(l) for l in open(os.path.join(D, "h/work/shots45_lines.jsonl"))]
lines = [r for r in lines if r["date"] < rlib.LOCKBOX and r["over"] is not None and r["under"] is not None]
for r in lines:
    d = r["date"]
    r["f"] = rlib.fair_prop(r["over"], r["under"])
    r["missed"] = missed(r["pid"], r["team"], d)
    r["pts"] = pts25.get(r["pid"], 0)
    r["ptsall"] = r["pts"] + sum(x[4] for x in prior(sk.get(r["pid"], []), skd.get(r["pid"], []), d) if x[0] >= "2025-07-01")
    r["shift"] = shift(r["team"], r["home"], r["opp"], d)
    r["big"] = float(slate[d] >= 10)
    r["new"], r["dn"] = newteam(r["pid"], r["team"], d)
ok = [r for r in lines if r["ok"] and r["result"] == "OK"]
test = [r for r in ok if r["date"][:7] >= "2025-11"]


def fixed(name, cond, side="under"):
    b = []
    for r in test:
        if cond(r):
            pr = r[side]
            if pr >= -200:
                b.append(rlib.bet(r["gid"], r["date"], pr, (r["actual"] > r["line"]) == (side == "over")))
    s = rlib.summ(b)
    print("%s %s | %s | p_one %s" % (name, rlib.fmt(s), rlib.by_month(b), s.get("p_one")))
    return b


def logit_test(name, extra):
    res = wf.run(name, lines, extra, verbose=True)
    for T, b in res.items():
        s = rlib.summ(b)
        print("   %s T=%.2f p_one %s" % (name, T, s.get("p_one")))


def main():
    print("rows pre-lockbox", len(lines), "graded Nov-Feb", len(test))
    print("desc missed>=1", sum(r["missed"] >= 1 for r in test), ">=3", sum(r["missed"] >= 3 for r in test),
          "| top25", sum(r["pid"] in top25 for r in test), "top50", sum(r["pid"] in top50 for r in test),
          "| |shift|>=2", sum(abs(r["shift"]) >= 2 for r in test), "east>=2", sum(r["shift"] >= 2 for r in test),
          "| big", sum(r["big"] for r in test), "| new<20", sum(r["new"] for r in test))
    fixed("T1a", lambda r: r["missed"] >= 1)
    fixed("T1b", lambda r: r["missed"] >= 3)
    logit_test("T1c", lambda r: [float(r["missed"] >= 1), math.log1p(r["missed"])])
    fixed("T2a", lambda r: r["pid"] in top25)
    fixed("T2b", lambda r: r["pid"] in top50)
    logit_test("T2c", lambda r: [math.log1p(r["ptsall"])])
    fixed("T3a", lambda r: abs(r["shift"]) >= 2)
    fixed("T3b", lambda r: r["shift"] >= 2)
    logit_test("T3c", lambda r: [abs(r["shift"]), r["shift"]])
    logit_test("T4", lambda r: [r["big"], r["big"] * float(rlib.logit(r["f"]))])
    logit_test("T5", lambda r: [r["new"], r["dn"]])


if len(sys.argv) < 2:
    main()


# ---- placebo for any variant positive Nov-Feb with n >= 300 (registered rule): T5 T=.01
if len(sys.argv) > 2 and sys.argv[1] == "placebo" and sys.argv[2] == "T5":
    import io, contextlib, random
    real = None
    with contextlib.redirect_stdout(io.StringIO()):
        real = rlib.summ(wf.run("T5", lines, lambda r: [r["new"], r["dn"]], Ts=(0.01,), verbose=False)[0.01])
    grp = defaultdict(list)
    for r in lines:
        grp[(r["date"], r["line"])].append(r)
    rng = random.Random(7)
    rois, ns = [], []
    for i in range(200):
        for g in grp.values():
            xs = [(r["new"], r["dn"]) for r in g]
            rng.shuffle(xs)
            for r, x in zip(g, xs):
                r["_x"] = list(x)
        with contextlib.redirect_stdout(io.StringIO()):
            s = rlib.summ(wf.run("P", lines, lambda r: r["_x"], Ts=(0.01,), verbose=False)[0.01], B=1)
        rois.append(s["roi"] if s["n"] else -1.0); ns.append(s["n"])
    rois = np.array(rois)
    print("T5 T=.01 real ROI %+.2f%% n%d | placebo mean %+.2f%% sd %.2f mean n %.0f | share >= real %.3f" % (
        100 * real["roi"], real["n"], 100 * rois.mean(), 100 * rois.std(), np.mean(ns), (rois >= real["roi"]).mean()))


if LB:
    b = wf.run("LB2-T5", lines, lambda r: [r["new"], r["dn"]], Ts=(0.01,), verbose=True)[0.01]
    s_ = rlib.summ(b)
    print("LB2 lockbox T5 T=.01:", rlib.fmt(s_), "| one-sided p %.4f (pass needs < 0.025 and ROI > 0)" % s_["p_one"], "|", rlib.by_month(b))
