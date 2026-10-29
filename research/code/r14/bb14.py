"""Run 14 tests BB1-BB3 (registered in HYPOTHESES.md run 14, commit 399b42c, before testing).
Inputs (scratch, PC_R14_DIR): h/work/shots45_lines.jsonl (hist tgz), nhl/skater_2526.jsonl (r14/fetch14.py, Feb 28 cut-off).
Lockbox rows (Mar 1+) are never built or scored. python3 -I bb14.py [placebo NAME T]"""
import contextlib, io, json, os, random, sys
from bisect import bisect_left
from collections import defaultdict
from datetime import date, timedelta
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import rlib, wf  # noqa: E402

D = os.environ["PC_R14_DIR"]
S25 = [json.loads(l) for l in open(os.path.join(D, "nhl/skater_2526.jsonl"))]
S25 = [s for s in S25 if s["gameDate"][:10] < rlib.LOCKBOX]
dd = date.fromisoformat

# team game table: (gid, team) -> goals, sog, home, date, opp
tg = {}
for s in S25:
    k = (s["gameId"], s["teamAbbrev"])
    t = tg.setdefault(k, {"g": 0, "s": 0, "home": s["homeRoad"] == "H", "date": s["gameDate"][:10], "opp": s["opponentTeamAbbrev"]})
    t["g"] += s["goals"] or 0; t["s"] += s["shots"] or 0
tsched = defaultdict(list)  # team -> [(date, gid, home)]
for (gid, team), t in tg.items():
    tsched[team].append((t["date"], gid, t["home"]))
for v in tsched.values():
    v.sort()
tsd = {t: [x[0] for x in v] for t, v in tsched.items()}

lines = [json.loads(l) for l in open(os.path.join(D, "h/work/shots45_lines.jsonl"))]
lines = [r for r in lines if r["date"] < rlib.LOCKBOX and r["over"] is not None and r["under"] is not None]
for r in lines:
    r["f"] = rlib.fair_prop(r["over"], r["under"]); r["lf"] = float(rlib.logit(r["f"]))

# BB2: per player, one line per date (f nearest .5), graded outcome
hist = defaultdict(dict)
for r in lines:
    if r["result"] != "OK":
        continue
    cur = hist[r["pid"]].get(r["date"])
    if cur is None or abs(r["f"] - 0.5) < abs(cur["f"] - 0.5):
        hist[r["pid"]][r["date"]] = r
hseq = {p: sorted((d, 1 if x["actual"] > x["line"] else -1) for d, x in v.items()) for p, v in hist.items()}
hsd = {p: [x[0] for x in v] for p, v in hseq.items()}

miss_team = 0
for r in lines:
    d = r["date"]
    # BB1
    r["gd"] = r["sdf"] = r["L3"] = 0.0
    sch = tsched.get(r["team"], []); i = bisect_left(tsd.get(r["team"], []), d)
    if i > 0:
        pd, pgid, _ = sch[i - 1]
        if (dd(d) - dd(pd)).days <= 4:
            me = tg[(pgid, r["team"])]; op = tg.get((pgid, me["opp"]))
            if op:
                gd = me["g"] - op["g"]
                r["gd"] = float(max(-5, min(5, gd))); r["sdf"] = float(max(-25, min(25, me["s"] - op["s"]))); r["L3"] = float(gd <= -3)
    elif not sch:
        miss_team += 1
    # BB3 (prior games' home/road + tonight's location)
    prev = [h for _, _, h in sch[:i]]
    if not r["home"]:
        k = 0
        for h in reversed(prev):
            if h:
                break
            k += 1
        r["rt"] = float(k + 1)
    else:
        r["rt"] = 0.0
    r["hc"] = float(bool(r["home"]) and len(prev) >= 3 and not any(prev[-3:]))
    r["rt1"] = float(r["rt"] == 1)
    r["rt6"] = min(r["rt"], 6.0)
    # BB2
    q = hseq.get(r["pid"], []); j = bisect_left(hsd.get(r["pid"], []), d)
    s = 0
    if j > 0:
        last = q[j - 1][1]
        for x in reversed(q[:j]):
            if x[1] != last:
                break
            s += 1
        s = min(s, 6) * last
    r["s"] = float(s); r["s3"] = float(np.sign(s) * (abs(s) >= 3))

feats = {
    "BB1": lambda r: [r["gd"], r["sdf"], r["L3"]],
    "BB2": lambda r: [r["s"], r["s3"]],
    "BB3": lambda r: [r["rt6"], r["hc"], r["rt1"]],
}
KEYS = {"BB1": ["gd", "sdf", "L3"], "BB2": ["s", "s3"], "BB3": ["rt6", "hc", "rt1"]}


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
        real = wf.run(name, lines, feats[name], Ts=(T,), verbose=False)[T]
        rr = rlib.summ(real)["roi"]
        rng = random.Random(7); out = []
        grp = defaultdict(list)
        for r in lines:
            grp[(r["date"], r["line"])].append(r)
        ks = KEYS[name]; orig = {k: [r[k] for r in lines] for k in ks}
        for it in range(200):
            for g in grp.values():
                idx = list(range(len(g))); rng.shuffle(idx)
                vals = {k: [g[j][k] for j in idx] for k in ks}
                for j, r in enumerate(g):
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
    print("graded Nov-Feb lines", len(te), "| lines with no team schedule", miss_team)
    for k in ["gd", "sdf", "L3", "s", "s3", "rt", "hc", "rt1"]:
        a = np.array([r[k] for r in te], float)
        print("feature %s mean %.3f sd %.3f nonzero %d" % (k, a.mean(), a.std(), int((a != 0).sum())))
    for n in ("BB1", "BB2", "BB3"):
        wf.run(n, lines, feats[n])
    fixed("BB1r OVER after losing last game by 3+", lambda r: "over" if r["L3"] else None)
    fixed("BB2r UNDER after 3+ straight overs vs his line", lambda r: "under" if r["s"] >= 3 else None)
    fixed("BB3r UNDER on 4th+ straight road game", lambda r: "under" if r["rt"] >= 4 else None)
