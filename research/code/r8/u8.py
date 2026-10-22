"""Run 8 tests U1-U5 (registered in HYPOTHESES.md run 8, commit 902c4a0, before testing).
Inputs (scratch, PC_R8_DIR): h/work/shots45_lines.jsonl (hist tgz), nhl/*.jsonl (research/code/r6/fetch6.py).
Lockbox rows (Mar 1+) are never built or scored. python3 -I u8.py [placebo NAME]"""
import contextlib, io, json, os, random, sys
from bisect import bisect_left
from collections import defaultdict, Counter
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import rlib, wf  # noqa: E402

D = os.environ["PC_R8_DIR"]
jl = lambda p: [json.loads(l) for l in open(os.path.join(D, p))]
ET = ZoneInfo("America/New_York")
DIV = {}
for dv, ts in (("A", "BOS BUF DET FLA MTL OTT TBL TOR"), ("M", "CAR CBJ NJD NYI NYR PHI PIT WSH"),
               ("C", "CHI COL DAL MIN NSH STL UTA WPG"), ("P", "ANA CGY EDM LAK SEA SJS VAN VGK")):
    for t in ts.split():
        DIV[t] = dv

sk = defaultdict(list)          # pid -> [(date, gid, team, opp, shots)]
opp_games = defaultdict(lambda: defaultdict(lambda: [None, 0, 0]))  # O -> gid -> [date, Dshots, allshots] (shots BY O's opponents)
for p in ("nhl/skater_2425.jsonl", "nhl/skater_2526.jsonl"):
    for s in jl(p):
        if s["gameDate"] >= rlib.LOCKBOX:
            continue
        sk[s["playerId"]].append((s["gameDate"], s["gameId"], s["teamAbbrev"], s["opponentTeamAbbrev"], s["shots"]))
        g = opp_games[s["opponentTeamAbbrev"]][s["gameId"]]
        g[0] = s["gameDate"]; g[2] += s["shots"]; g[1] += s["shots"] * (s["positionCode"] == "D")
for L in sk.values():
    L.sort()
skd = {p: [x[0] for x in L] for p, L in sk.items()}
og = {O: sorted(v.values()) for O, v in opp_games.items()}
ogd = {O: [x[0] for x in L] for O, L in og.items()}


def prior(lst, dates, d):
    return lst[:bisect_left(dates, d)]


def dshare(O, d):
    L = prior(og.get(O, []), ogd.get(O, []), d)[-20:]
    if len(L) < 5:
        return None
    a = sum(x[2] for x in L)
    return sum(x[1] for x in L) / a if a else None


def vsopp(pid, opp, d):
    L = prior(sk.get(pid, []), skd.get(pid, []), d)
    if not L:
        return 0.0, 0
    m = sum(x[4] for x in L) / len(L)
    v = [x[4] for x in L if x[3] == opp]
    k = len(v)
    if not k:
        return 0.0, 0
    return (sum(v) / k - m) * k / (k + 5.0), k


lines = [json.loads(l) for l in open(os.path.join(D, "h/work/shots45_lines.jsonl"))]
lines = [r for r in lines if r["date"] < rlib.LOCKBOX and r["over"] is not None and r["under"] is not None]
for r in lines:
    d = r["date"]
    r["f"] = rlib.fair_prop(r["over"], r["under"])
    h = datetime.fromisoformat(r["start"].replace("Z", "+00:00")).astimezone(ET).hour
    r["matinee"], r["late"] = float(h < 17), float(h >= 21)
    r["div"] = float(DIV.get(r["team"]) is not None and DIV.get(r["team"]) == DIV.get(r["opp"]))
    r["isD"] = float(r["pos"] == "D")
    r["dsh"] = dshare(r["opp"], d)
    r["vdev"], r["vk"] = vsopp(r["pid"], r["opp"], d)
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


def per_fold(name, extra_for_month, Ts=(0.01, 0.02, 0.03), verbose=True):
    """wf.run one test month at a time so the feature can depend on that fold's training set."""
    res = {T: [] for T in Ts}
    keep = rlib.TEST_MONTHS
    try:
        for m in keep:
            rlib.TEST_MONTHS = [m]
            ex = extra_for_month(m)
            with contextlib.redirect_stdout(io.StringIO()) as buf:
                rr = wf.run(name, lines, ex, Ts=Ts, verbose=verbose)
            if verbose:
                print("\n".join(l for l in buf.getvalue().splitlines() if " w " in l or "log loss" in l))
            for T in Ts:
                res[T] += rr[T]
    finally:
        rlib.TEST_MONTHS = keep
    for T, b in res.items():
        s = rlib.summ(b)
        print("%s T=%.2f %s | %s | p_one %s" % (name, T, rlib.fmt(s), rlib.by_month(b), s.get("p_one")))
    return res


def logit_test(name, extra):
    res = wf.run(name, lines, extra, verbose=True)
    for T, b in res.items():
        print("   %s T=%.2f p_one %s" % (name, T, rlib.summ(b).get("p_one")))
    return res


def tmpl_extra(m):
    tr = [r for r in lines if r["ok"] and r["result"] == "OK" and r["date"][:7] < m]
    c = defaultdict(Counter)
    for r in tr:
        c[r["line"]][(r["over"], r["under"])] += 1
    top = {ln: {k for k, _ in cc.most_common(3)} for ln, cc in c.items()}
    def ex(r):
        t = float((r["over"], r["under"]) in top.get(r["line"], set()))
        return [t, t * float(rlib.logit(r["f"]))]
    ex.top = top
    return ex


def u3_extra(m):
    tr = [r for r in lines if r["ok"] and r["result"] == "OK" and r["date"][:7] < m and r["dsh"] is not None]
    mu = float(np.mean([r["dsh"] for r in tr]))
    def ex(r):
        dev = (r["dsh"] if r["dsh"] is not None else mu) - mu
        return [dev * r["isD"], dev * (1 - r["isD"])]
    return ex


def main():
    print("rows pre-lockbox", len(lines), "graded Nov-Feb", len(test))
    print("desc matinee", sum(r["matinee"] for r in test), "late", sum(r["late"] for r in test), "div", sum(r["div"] for r in test),
          "dsh None", sum(r["dsh"] is None for r in test), "vk>=1", sum(r["vk"] >= 1 for r in test), "vdev>=1", sum(r["vdev"] >= 1 for r in test))
    for m in rlib.TEST_MONTHS:
        ex = tmpl_extra(m)
        te = [r for r in test if r["date"][:7] == m]
        print("U1 desc", m, "top triples", {k: sorted(v) for k, v in ex.top.items() if k in (1.5, 2.5, 3.5)},
              "tmpl share %.2f" % np.mean([ex(r)[0] for r in te]))
    per_fold("U1", tmpl_extra)
    logit_test("U2", lambda r: [r["matinee"], r["late"]])
    fixed("U2r", lambda r: r["matinee"] == 1)
    per_fold("U3", u3_extra)
    logit_test("U4", lambda r: [r["div"], r["div"] * r["isD"]])
    logit_test("U5", lambda r: [r["vdev"], float(r["vk"] >= 3)])
    fixed("U5r", lambda r: r["vdev"] >= 1.0)


def placebo(name, T):
    feats = {"U2": ("matinee", "late"), "U4": ("div", "isD"), "U5": ("vdev", "vk")}
    exs = {"U2": lambda r: [r["_x"][0], r["_x"][1]], "U4": lambda r: [r["_x"][0], r["_x"][0] * r["_x"][1]],
           "U5": lambda r: [r["_x"][0], float(r["_x"][1] >= 3)]}
    for r in lines:
        r["_x"] = [r[k] for k in feats[name]]
    with contextlib.redirect_stdout(io.StringIO()):
        real = rlib.summ(wf.run(name, lines, exs[name], Ts=(T,), verbose=False)[T])
    grp = defaultdict(list)
    for r in lines:
        grp[(r["date"], r["line"])].append(r)
    rng = random.Random(7); rois = []
    for i in range(200):
        for g in grp.values():
            xs = [[r[k] for k in feats[name]] for r in g]; rng.shuffle(xs)
            for r, x in zip(g, xs):
                r["_x"] = x
        with contextlib.redirect_stdout(io.StringIO()):
            s = rlib.summ(wf.run("P", lines, exs[name], Ts=(T,), verbose=False)[T], B=1)
        rois.append(s["roi"] if s["n"] else -1.0)
    rois = np.array(rois)
    print("%s T=%.2f real %+.2f%% n%d | placebo mean %+.2f%% sd %.2f | share >= real %.3f" % (
        name, T, 100 * real["roi"], real["n"], 100 * rois.mean(), 100 * rois.std(), (rois >= real["roi"]).mean()))


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "placebo":
        placebo(sys.argv[2], float(sys.argv[3]))
    else:
        main()
