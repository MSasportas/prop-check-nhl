"""Run 9 tests W1-W5 (registered in HYPOTHESES.md run 9, commit fa577da, before testing).
Inputs (scratch, PC_R9_DIR): h/work/shots45_lines.jsonl (hist tgz), nhl/*.jsonl (research/code/r9/fetch9.py, Feb 28 cut-off).
Lockbox rows (Mar 1+) are never built or scored. python3 -I w9.py [placebo NAME T]"""
import contextlib, io, json, os, random, sys
from bisect import bisect_left
from collections import defaultdict
from datetime import date as Date
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import rlib, wf  # noqa: E402

D = os.environ["PC_R9_DIR"]
jl = lambda p: [json.loads(l) for l in open(os.path.join(D, p))]
DIV = {}
for dv, ts in (("A", "BOS BUF DET FLA MTL OTT TBL TOR"), ("M", "CAR CBJ NJD NYI NYR PHI PIT WSH"),
               ("C", "CHI COL DAL MIN NSH STL UTA WPG"), ("P", "ANA CGY EDM LAK SEA SJS VAN VGK")):
    for t in ts.split():
        DIV[t] = dv
dd = lambda a, b: (Date.fromisoformat(a) - Date.fromisoformat(b)).days


def prior(lst, dates, d):
    return lst[:bisect_left(dates, d)]


# ---- skater logs (both seasons): pid -> [(date, gid, team, opp, shots, goals)]
sk = defaultdict(list)
in2425 = set()
for p in ("nhl/skater_2425.jsonl", "nhl/skater_2526.jsonl"):
    for s in jl(p):
        if s["gameDate"] >= rlib.LOCKBOX:
            continue
        sk[s["playerId"]].append((s["gameDate"][:10], s["gameId"], s["teamAbbrev"], s["opponentTeamAbbrev"], s["shots"] or 0, s["goals"] or 0))
        if p.endswith("2425.jsonl"):
            in2425.add(s["playerId"])
for L in sk.values():
    L.sort()
skd = {p: [x[0] for x in L] for p, L in sk.items()}
skg = {p: {x[1]: x for x in L} for p, L in sk.items()}

# ---- team powerplay (both seasons): abbrev from the other row of the same game
tpp = defaultdict(list)
for p in ("nhl/teampp_2425.jsonl", "nhl/teampp_2526.jsonl"):
    rows = [r for r in jl(p) if r["gameDate"][:10] < rlib.LOCKBOX]
    byg = defaultdict(list)
    for r in rows:
        byg[r["gameId"]].append(r)
    for g, rs in byg.items():
        if len(rs) != 2:
            continue
        for a, b in ((rs[0], rs[1]), (rs[1], rs[0])):
            tpp[g, b["opponentTeamAbbrev"]] = (a["gameDate"][:10], a["opponentTeamAbbrev"], a["ppOpportunities"] or 0,
                                               (a.get("ppTimeOnIcePerGame") or 0.0))
team_log = defaultdict(list)   # team -> [(date, gid, opp, own_pp_opps, opp_pp_opps, own_pp_toi_sec)]
for (g, t), (dt, opp, ppo, ppt) in tpp.items():
    o = tpp.get((g, opp))
    team_log[t].append((dt, g, opp, ppo, o[2] if o else None, ppt))
for L in team_log.values():
    L.sort()
tld = {t: [x[0] for x in L] for t, L in team_log.items()}

# ---- player PP TOI 2025-26
ppl = defaultdict(list)
for r in jl("nhl/toi_2526.jsonl"):
    if r["gameDate"][:10] < rlib.LOCKBOX:
        ppl[r["playerId"]].append((r["gameDate"][:10], (r.get("ppTimeOnIce") or 0)))
for L in ppl.values():
    L.sort()
ppd = {p: [x[0] for x in L] for p, L in ppl.items()}

# ---- realtime 2025-26 (K9)
rt = defaultdict(list)
for r in jl("nhl/realtime_2526.jsonl"):
    if r["gameDate"][:10] >= rlib.LOCKBOX:
        continue
    att = r.get("totalShotAttempts") or 0
    sog = att - (r.get("missedShots") or 0) - (r.get("shotAttemptsBlocked") or 0)
    rt[r["playerId"]].append((r["gameDate"][:10], att, sog))
for L in rt.values():
    L.sort()
rtd = {p: [x[0] for x in L] for p, L in rt.items()}


def w1_raw(r):
    d = r["date"]
    L = prior(ppl.get(r["pid"], []), ppd.get(r["pid"], []), d)[-10:]
    T = prior(team_log.get(r["team"], []), tld.get(r["team"], []), d)
    t10 = [x for x in T if x[0] >= "2025-10-01"][-10:]
    tp = np.mean([x[5] for x in t10]) if t10 else 0.0
    pps = (np.mean([x[1] for x in L]) / tp) if (len(L) >= 3 and tp > 0) else 0.0
    T20 = T[-20:]
    own = np.mean([x[3] for x in T20]) if len(T20) >= 5 else None
    O = prior(team_log.get(r["opp"], []), tld.get(r["opp"], []), d)[-20:]
    O = [x for x in O if x[4] is not None]
    give = np.mean([x[4] for x in O]) if len(O) >= 5 else None
    return (float(pps), give, own)


def w2_raw(r):
    L = prior(sk.get(r["pid"], []), skd.get(r["pid"], []), r["date"])
    g5 = sum(x[5] for x in L[-5:])
    g3 = sum(x[5] for x in L[-3:])
    s10 = sum(x[4] for x in L[-10:])
    if len(L) < 5 or s10 == 0:
        luck = 0.0
    else:
        luck = sum(x[5] for x in L[-10:]) / s10 - (sum(x[5] for x in L) + 10.0) / (sum(x[4] for x in L) + 100.0)
    return (float(g5), float(luck), g3)


def w3_raw(r):
    rook = float(r["pid"] not in in2425)
    L = prior(sk.get(r["pid"], []), skd.get(r["pid"], []), r["date"])
    g = sum(1 for x in L if x[0] >= "2025-10-01")
    return (rook, float(g < 20))


def w4_raw(r):
    T = prior(team_log.get(r["team"], []), tld.get(r["team"], []), r["date"])
    if not T:
        return (0.0, 0.0, None)
    pdt, pg, popp = T[-1][0], T[-1][1], T[-1][2]
    if popp != r["opp"] or not (1 <= dd(r["date"], pdt) <= 3):
        return (0.0, 0.0, None)
    x = skg.get(r["pid"], {}).get(pg)
    if x is None:
        return (1.0, 0.0, None)
    L = prior(sk[r["pid"]], skd[r["pid"]], pdt)
    m = np.mean([y[4] for y in L]) if L else x[4]
    return (1.0, float(x[4] - m), x[4])


def k9_raw(r):
    L = prior(rt.get(r["pid"], []), rtd.get(r["pid"], []), r["date"])[-20:]
    if len(L) < 5:
        return (0, 0.0, 0.0)
    return (len(L), float(np.mean([x[1] for x in L])), float(np.mean([x[2] for x in L])))


lines = [json.loads(l) for l in open(os.path.join(D, "h/work/shots45_lines.jsonl"))]
lines = [r for r in lines if r["date"] < rlib.LOCKBOX and r["over"] is not None and r["under"] is not None]
for r in lines:
    r["f"] = rlib.fair_prop(r["over"], r["under"])
    r["lf"] = float(rlib.logit(r["f"]))
    r["isD"] = float(r["pos"] == "D")
    bo, bu = rlib.be(r["over"]), rlib.be(r["under"])
    r["hold"] = bo + bu - 1
    r["skew"] = (bo - r["f"]) - (bu - (1 - r["f"]))
    r["div"] = float(DIV.get(r["team"]) is not None and DIV.get(r["team"]) == DIV.get(r["opp"]))
    r["x_W1"] = w1_raw(r)
    r["x_W2"] = w2_raw(r)
    r["x_W3"] = w3_raw(r)
    r["x_W4"] = w4_raw(r)
    r["x_K9"] = k9_raw(r)
ok = [r for r in lines if r["ok"] and r["result"] == "OK"]
test = [r for r in ok if r["date"][:7] >= "2025-11"]


def fixed(name, cond, side="under"):
    b = []
    for r in test:
        if cond(r) and r[side] >= -200:
            b.append(rlib.bet(r["gid"], r["date"], r[side], (r["actual"] > r["line"]) == (side == "over")))
    s = rlib.summ(b)
    print("%s %s | %s | p_one %s" % (name, rlib.fmt(s), rlib.by_month(b), s.get("p_one")))
    return b


# ---- extra builders: m -> (r -> list). Training-dependent centring done per fold.
def w1_extra(m):
    tr = [r for r in lines if r["ok"] and r["result"] == "OK" and r["date"][:7] < m]
    mg = float(np.mean([r["x_W1"][1] for r in tr if r["x_W1"][1] is not None]))
    mo = float(np.mean([r["x_W1"][2] for r in tr if r["x_W1"][2] is not None]))
    def ex(r):
        pps, give, own = r["x_W1"]
        return [pps * ((give if give is not None else mg) - mg), pps * ((own if own is not None else mo) - mo)]
    return ex


def w2_extra(m):
    return lambda r: [r["x_W2"][0], r["x_W2"][1]]


def w3_extra(m):
    return lambda r: [r["x_W3"][0], r["x_W3"][0] * r["x_W3"][1], r["x_W3"][0] * r["lf"]]


def w4_extra(m):
    return lambda r: [r["x_W4"][0], r["x_W4"][0] * r["x_W4"][1]]


def w5_extra(m):
    tr = [r for r in lines if r["ok"] and r["result"] == "OK" and r["date"][:7] < m]
    c = {}
    for P in (0.0, 1.0):
        a = [r for r in tr if r["isD"] == P and r["x_K9"][0] >= 5]
        c[P] = sum(r["x_K9"][2] for r in a) / sum(r["x_K9"][1] for r in a)
    def ex(r):
        n, att, sog = r["x_K9"]
        k9 = att * c[r["isD"]] - sog if n >= 5 else 0.0
        return [r["skew"], r["hold"], r["div"], r["div"] * r["isD"], k9]
    return ex


BUILD = {"W1": w1_extra, "W2": w2_extra, "W3": w3_extra, "W4": w4_extra, "W5": w5_extra}
SHUF = {"W1": ["x_W1"], "W2": ["x_W2"], "W3": ["x_W3"], "W4": ["x_W4"], "W5": ["skew", "hold", "div", "x_K9"]}


def per_fold(name, Ts=(0.01, 0.02, 0.03), verbose=True, quiet=False):
    res = {T: [] for T in Ts}
    keep = rlib.TEST_MONTHS
    try:
        for m in keep:
            rlib.TEST_MONTHS = [m]
            ex = BUILD[name](m)
            with contextlib.redirect_stdout(io.StringIO()) as buf:
                rr = wf.run(name, lines, ex, Ts=Ts, verbose=verbose)
            if verbose and not quiet:
                print("\n".join(l for l in buf.getvalue().splitlines() if " w " in l or "log loss" in l))
            for T in Ts:
                res[T] += rr[T]
    finally:
        rlib.TEST_MONTHS = keep
    if not quiet:
        for T, b in res.items():
            s = rlib.summ(b)
            print("%s T=%.2f %s | %s | p_one %s" % (name, T, rlib.fmt(s), rlib.by_month(b), s.get("p_one")))
    return res


def main():
    print("rows pre-lockbox", len(lines), "graded Nov-Feb", len(test))
    print("desc W1 pps>0.3", sum(r["x_W1"][0] > 0.3 for r in test), "give None", sum(r["x_W1"][1] is None for r in test),
          "| W2 g5 mean %.2f" % np.mean([r["x_W2"][0] for r in test]), "g3>=3", sum(r["x_W2"][2] >= 3 for r in test),
          "| W3 rook", sum(r["x_W3"][0] for r in test), "| W4 rem", sum(r["x_W4"][0] for r in test),
          "| K9 n>=5", sum(r["x_K9"][0] >= 5 for r in test))
    per_fold("W1")
    per_fold("W2")
    fixed("W2r", lambda r: r["x_W2"][2] >= 3)
    per_fold("W3")
    per_fold("W4")
    fixed("W4r", lambda r: r["x_W4"][2] is not None and r["x_W4"][2] >= r["line"] + 2)
    per_fold("W5")


def placebo(name, T):
    real = rlib.summ(per_fold(name, Ts=(T,), verbose=False, quiet=True)[T])
    grp = defaultdict(list)
    for r in lines:
        grp[(r["date"], r["line"])].append(r)
    rng = random.Random(7); rois = []
    for i in range(200):
        for g in grp.values():
            xs = [[r[k] for k in SHUF[name]] for r in g]; rng.shuffle(xs)
            for r, x in zip(g, xs):
                for k, v in zip(SHUF[name], x):
                    r[k] = v
        s = rlib.summ(per_fold(name, Ts=(T,), verbose=False, quiet=True)[T], B=1)
        rois.append(s["roi"] if s["n"] else -1.0)
    rois = np.array(rois)
    print("%s T=%.2f real %+.2f%% n%d | placebo mean %+.2f%% sd %.2f | share >= real %.3f" % (
        name, T, 100 * real["roi"], real["n"], 100 * rois.mean(), 100 * rois.std(), (rois >= real["roi"]).mean()))


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "placebo":
        placebo(sys.argv[2], float(sys.argv[3]))
    else:
        main()
