"""Run 11 tests Y1-Y4 (registered in HYPOTHESES.md run 11, commit 55727c6, before testing).
Inputs (scratch, PC_R11_DIR): h/work/shots45_lines.jsonl (hist tgz), nhl/skater_2425.jsonl + skater_2526.jsonl (r11/fetch11.py, Feb 28 cut-off).
Lockbox rows (Mar 1+) are never built or scored. python3 -I y11.py [placebo NAME T]"""
import contextlib, io, json, os, random, sys
from bisect import bisect_left
from collections import defaultdict
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import rlib, wf  # noqa: E402

D = os.environ["PC_R11_DIR"]
jl = lambda p: [json.loads(l) for l in open(os.path.join(D, p))]

L24 = jl("nhl/skater_2425.jsonl")
L25 = [s for s in jl("nhl/skater_2526.jsonl") if s["gameDate"][:10] < rlib.LOCKBOX]

# ---- per-player game lists (date, sog, opp, season)
pl = defaultdict(list)
for s in L24:
    pl[s["playerId"]].append((s["gameDate"][:10], s["shots"] or 0, None))
for s in L25:
    pl[s["playerId"]].append((s["gameDate"][:10], s["shots"] or 0, s["opponentTeamAbbrev"]))
for v in pl.values():
    v.sort(key=lambda x: x[0])
pld = {p: [x[0] for x in v] for p, v in pl.items()}

# ---- 2025-26 team games, team shots for per game, skater appearances per team game
tg = defaultdict(set)                      # team -> {(date, gid)}
sf = defaultdict(lambda: defaultdict(int))  # gid -> team -> SOG
app = defaultdict(set)                     # (team, gid) -> {pid}
pinfo = {}                                 # pid -> (pos, [(date, team, toi)])
toi_hist = defaultdict(list)
for s in L25:
    t, g, d = s["teamAbbrev"], s["gameId"], s["gameDate"][:10]
    tg[t].add((d, g)); sf[g][t] += s["shots"] or 0; app[(t, g)].add(s["playerId"])
    toi_hist[s["playerId"]].append((d, t, (s["timeOnIcePerGame"] or 0) / 60.0))
    pinfo[s["playerId"]] = "D" if s["positionCode"] == "D" else "F"
tg = {t: sorted(v) for t, v in tg.items()}
tgd = {t: [x[0] for x in v] for t, v in tg.items()}
gopp = {}
for g, d in sf.items():
    ts = list(d)
    if len(ts) == 2:
        gopp[(g, ts[0])] = ts[1]; gopp[(g, ts[1])] = ts[0]

_oc = {}
def oppf_all(d):
    """team -> SA/g over its 2025-26 games before d divided by league mean; 1.0 if < 5 games"""
    if d in _oc:
        return _oc[d]
    sa, n = defaultdict(float), defaultdict(int)
    for t, L in tg.items():
        for dt, g in L[:bisect_left(tgd[t], d)]:
            o = gopp.get((g, t))
            if o is None:
                continue
            sa[t] += sf[g][o]; n[t] += 1
    tot = sum(sa.values()); cnt = sum(n.values())
    lg = tot / cnt if cnt else 1.0
    out = {t: (sa[t] / n[t]) / lg if n[t] >= 5 else 1.0 for t in tg}
    _oc[d] = out
    return out


def miss(team, d):
    L = tg.get(team, []); i = bisect_left(tgd.get(team, []), d)
    if i < 1:
        return 0.0, 0.0
    last10 = L[max(0, i - 10):i]; lastg = L[i - 1][1]
    cnt = defaultdict(int)
    for dt, g in last10:
        for p in app[(team, g)]:
            cnt[p] += 1
    mD = mF = 0.0
    for p, c in cnt.items():
        if c >= 5 and p not in app[(team, lastg)]:
            ts = [x[2] for x in toi_hist[p] if x[1] == team and x[0] < d]
            m = sum(ts) / len(ts) if ts else 0.0
            if pinfo[p] == "D":
                mD += m
            else:
                mF += m
    return mD, mF


lines = [json.loads(l) for l in open(os.path.join(D, "h/work/shots45_lines.jsonl"))]
lines = [r for r in lines if r["date"] < rlib.LOCKBOX and r["over"] is not None and r["under"] is not None]
first_dates = defaultdict(set)
for r in lines:
    first_dates[r["pid"]].add(r["date"])
first_dates = {p: sorted(v) for p, v in first_dates.items()}
for r in lines:
    r["f"] = rlib.fair_prop(r["over"], r["under"]); r["lf"] = float(rlib.logit(r["f"]))
    r["isD"] = float(r["pos"] == "D")
    r["missD"], r["missF"] = miss(r["opp"], r["date"])
    # Y2
    v = pl.get(r["pid"], []); i = bisect_left(pld.get(r["pid"], []), r["date"])
    last = v[max(0, i - 10):i]
    if len(last) >= 5:
        of = oppf_all(r["date"])
        adjm = np.mean([s / max(of.get(o, 1.0), 0.3) if o else s for _, s, o in last])
        r["adj"] = float(adjm - np.mean([s for _, s, _ in last]))
    else:
        r["adj"] = 0.0
    # Y3
    r["nHR"] = bisect_left(first_dates[r["pid"]], r["date"])

feats = {
    "Y1": lambda r: [r["missD"], r["missF"]],
    "Y2": lambda r: [r["adj"], r["adj"] * r["isD"]],
    "Y3": lambda r: [float(r["nHR"] == 0), float(1 <= r["nHR"] <= 4)],
    "Y4": lambda r: [float(r["line"] == 1.5) * r["lf"], float(r["line"] >= 3.5) * r["lf"], r["lf"] ** 2],
}


def fixed(name, cond, side):
    b = []
    for r in lines:
        if r["date"][:7] not in rlib.TEST_MONTHS or r["result"] != "OK" or not r["ok"] or not cond(r):
            continue
        pr = r[side]
        if pr < -200:
            continue
        b.append(rlib.bet(r["gid"], r["date"], pr, (r["actual"] > r["line"]) == (side == "over"), side=side, line=r["line"]))
    s = rlib.summ(b)
    print("%s %s | %s | p_one %s" % (name, rlib.fmt(s), rlib.by_month(b), s.get("p_one")))
    return b


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "placebo":
        name, T = sys.argv[2], float(sys.argv[3])
        real = wf.run(name, lines, feats[name], Ts=(T,), verbose=False)[T]
        rr = rlib.summ(real)["roi"]
        keys = ["missD", "missF", "adj", "nHR"]
        rng = random.Random(7); out = []
        grp = defaultdict(list)
        for r in lines:
            grp[(r["date"], r["line"])].append(r)
        orig = {k: [r[k] for r in lines] for k in keys}
        for it in range(200):
            for g in grp.values():
                idx = list(range(len(g))); rng.shuffle(idx)
                vals = {k: [g[j][k] for j in idx] for k in keys}
                for j, r in enumerate(g):
                    for k in keys:
                        r[k] = vals[k][j]
            with contextlib.redirect_stdout(io.StringIO()):
                b = wf.run(name, lines, feats[name], Ts=(T,), verbose=False)[T]
            out.append(rlib.summ(b)["roi"] or 0.0)
            for k in keys:
                for r, x in zip(lines, orig[k]):
                    r[k] = x
        out = np.array(out)
        print("placebo %s T=%.2f real %+.2f%% shuffled mean %+.2f%% sd %.2f >= real %d/200" % (
            name, T, 100 * rr, 100 * out.mean(), 100 * out.std(), int((out >= rr).sum())))
        sys.exit()
    te = [r for r in lines if r["date"][:7] in rlib.TEST_MONTHS and r["result"] == "OK"]
    print("graded Nov-Feb lines", len(te))
    for k in ("missD", "missF", "adj", "nHR"):
        a = np.array([r[k] for r in te], float)
        print("feature %s mean %.3f sd %.3f nonzero %d" % (k, a.mean(), a.std(), int((a != 0).sum())))
    print("Y3 first-postings in test months:", sum(r["nHR"] == 0 for r in te))
    for n in ("Y1", "Y2", "Y3", "Y4"):
        wf.run(n, lines, feats[n])
    fixed("Y1r OVER missD>=20", lambda r: r["missD"] >= 20, "over")
    fixed("Y3r UNDER first HR line", lambda r: r["nHR"] == 0, "under")
