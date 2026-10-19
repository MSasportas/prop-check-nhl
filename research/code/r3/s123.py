"""S1 / S1e (stale ML vs market), S2 (Florida local bias), S3 (ML calibration). Prints every variant and fold."""
import json, sys, os
from collections import defaultdict
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from rlib import summ, fmt, be, dec, bet, logit
R3 = "/tmp/claude-0/-home-claude/ab9b3f07-215a-50c7-96a2-d84b6c4f2d08/scratchpad/r3pull"
rows = [json.loads(l) for l in open(R3 + "/h2h_rows.jsonl")]
LOCK = "2026-03-01"
FOLDS = ["2025-11", "2025-12", "2026-01", "2026-02"]
pre = [r for r in rows if r["date"] < LOCK]


def sides(r, fair_h):
    """yield (side, price, fair, win)"""
    yield "home", r["hr_h"], fair_h, r["home_win"]
    yield "away", r["hr_a"], 1 - fair_h, not r["home_win"]


def report(name, bets):
    s = summ(bets)
    fm = defaultdict(list)
    for b in bets:
        fm[b["month"]].append(b)
    folds = " ".join("%s %+.1f%%(n%d)" % (m[5:], 100 * summ(fm[m])["roi"], len(fm[m])) if fm[m] else "%s n0" % m[5:] for m in FOLDS)
    nf = sum(b["month"] in FOLDS for b in bets)
    wf = [b for b in bets if b["month"] in FOLDS]
    print("%-34s Oct-Feb %s | Nov-Feb n%d %s | %s | meanEV %+.2f%%" % (name, fmt(s), nf, ("ROI %+.1f%%" % (100 * summ(wf)["roi"])) if wf else "", folds,
          100 * np.mean([b["ev"] for b in bets]) if bets else 0))
    return wf


print("=== S1 / S1e: bet Hard Rock side with EV >= T vs fair (pre-lockbox only) ===")
for hz, lo, hi in (("late", 0.25, 6), ("early", 18, 34)):
    rr = [r for r in pre if lo <= r["hrs"] <= hi]
    for fk in ("cons", "pin"):
        evs = []
        for r in rr:
            f = r["cons_h"] if fk == "cons" else r["pin_h"]
            if f is None or (fk == "cons" and r["n_oth"] < 3):
                continue
            for sd, p, fa, w in sides(r, f):
                evs.append((fa * dec(p) - 1, r, sd, p, w))
        ev = np.array([e[0] for e in evs])
        print("%s/%s sides %d  EV pctiles 50/90/99/max: %+.3f %+.3f %+.3f %+.3f  share EV>=0: %.2f%%" % (
            hz, fk, len(ev), *np.percentile(ev, [50, 90, 99]), ev.max(), 100 * (ev >= 0).mean()))
        for T in (0, .01, .02):
            bets = [bet(r["gid"], r["date"], p, w, ev=e) for e, r, sd, p, w in evs if e >= T and p >= -200]
            report("S1%s %s T=%.2f" % ("" if hz == "late" else "e", fk, T), bets)

print("\n=== S1e timing: Hard Rock early->late move vs consensus early->late move ===")
by = defaultdict(dict)
for r in rows:
    if r["cons_h"] is None or r["n_oth"] < 3:
        continue
    if r["hrs"] <= 6:
        by[r["gid"]]["L"] = r
    elif 18 <= r["hrs"] <= 34:
        by[r["gid"]]["E"] = r
x, y, gap, mv = [], [], [], []
for g, d in by.items():
    if "L" in d and "E" in d:
        E, L = d["E"], d["L"]
        x.append(L["cons_h"] - E["cons_h"]); y.append(L["hr_fair_h"] - E["hr_fair_h"])
        gap.append(E["hr_fair_h"] - E["cons_h"]); mv.append(L["cons_h"] - E["cons_h"])
x, y, gap, mv = map(np.array, (x, y, gap, mv))
print("games with both: %d; slope HR move on consensus move %.2f; corr %.2f" % (len(x), np.polyfit(x, y, 1)[0], np.corrcoef(x, y)[0, 1]))
print("early HR-cons gap predicts later consensus move? slope %.2f (+ = consensus moves toward HR's early price)" % np.polyfit(gap, mv, 1)[0])
L = [d["L"] for d in by.values() if "L" in d]
print("late: |HR fair - cons| mean %.4f, early: %.4f" % (np.mean([abs(r["hr_fair_h"] - r["cons_h"]) for r in L]),
      np.mean([abs(d["E"]["hr_fair_h"] - d["E"]["cons_h"]) for d in by.values() if "E" in d])))

print("\n=== S2 Florida local bias (late, all months incl. lockbox for the DESCRIPTIVE shading only) ===")
late = [r for r in rows if r["hrs"] <= 6 and r["cons_h"] is not None and r["n_oth"] >= 3]
rng = np.random.default_rng(5)
def team_d(team, rs):
    vals = []
    for r in rs:
        if r["home"] == team:
            vals.append(r["hr_fair_h"] - r["cons_h"])
        elif r["away"] == team:
            vals.append(-(r["hr_fair_h"] - r["cons_h"]))
    return np.array(vals)
allteams = sorted({r["home"] for r in late})
tab = []
for t in allteams:
    v = team_d(t, late)
    tab.append((v.mean(), t, len(v)))
tab.sort()
for m, t, n in tab:
    v = team_d(t, late)
    bs = [rng.choice(v, len(v)).mean() for _ in range(2000)]
    if t in ("FLA", "TBL") or t in [x[1] for x in tab[:3]] or t in [x[1] for x in tab[-3:]]:
        print("  %s n%d mean HR-cons fair %+.4f  90%% [%+.4f, %+.4f]" % (t, n, m, np.percentile(bs, 5), np.percentile(bs, 95)))
print("  rank of FLA, TBL among 32 (1 = Hard Rock gives that team the LOWEST fair, i.e. best price on it):",
      [i + 1 for i, x in enumerate(tab) if x[1] in ("FLA", "TBL")])
# vig split: HR overround and how it is split in FL games
def over(r): return be(r["hr_h"]) + be(r["hr_a"]) - 1
fl = [r for r in late if "FLA" in (r["home"], r["away"]) or "TBL" in (r["home"], r["away"])]
nfl = [r for r in late if r not in fl]
print("  HR overround FL games %.4f vs others %.4f" % (np.mean([over(r) for r in fl]), np.mean([over(r) for r in nfl])))
def opp_ev(r):
    loc_home = r["home"] in ("FLA", "TBL")
    if loc_home and r["away"] in ("FLA", "TBL"):
        return None
    if loc_home:
        return "away", r["hr_a"], 1 - r["cons_h"], not r["home_win"]
    return "home", r["hr_h"], r["cons_h"], r["home_win"]
for name, thr in (("S2a all FLA/TBL opponents", -9), ("S2b opponents EV>=-0.01", -0.01)):
    bets = []
    for r in fl:
        if r["date"] >= LOCK:
            continue
        o = opp_ev(r)
        if o is None:
            continue
        sd, p, fa, w = o
        e = fa * dec(p) - 1
        if p >= -200 and e >= thr:
            bets.append(bet(r["gid"], r["date"], p, w, ev=e))
    report(name, bets)
print("  locals' mean EV at HR (late, pre-lockbox):", "%+.2f%%" % (100 * np.mean([((r['cons_h'] if r['home'] in ('FLA','TBL') else 1-r['cons_h']) * dec(r['hr_h'] if r['home'] in ('FLA','TBL') else r['hr_a']) - 1) for r in fl if r['date'] < LOCK])))
print("  others' mean EV both sides (late, pre-lockbox): %+.2f%%" % (100 * np.mean([f * dec(p) - 1 for r in nfl if r['date'] < LOCK for f, p in ((r['cons_h'], r['hr_h']), (1 - r['cons_h'], r['hr_a']))])))

print("\n=== S3 calibration walk-forward (late) ===")
L = [r for r in late if r["date"] < LOCK]
def X(rs): return np.column_stack([np.ones(len(rs)), logit(np.array([r["cons_h"] for r in rs]))])
def fit(Xm, yv, l2=1.0):
    w = np.zeros(Xm.shape[1])
    for _ in range(50):
        p = 1 / (1 + np.exp(-Xm @ w))
        g = Xm.T @ (yv - p) - l2 * np.r_[0, w[1:] - 1]
        Hm = -(Xm.T * (p * (1 - p))) @ Xm - l2 * np.diag(np.r_[0, np.ones(len(w) - 1)])
        w = w - np.linalg.solve(Hm, g)
    return w
for T in (.01, .02, .03):
    bets = []
    for m in FOLDS:
        tr = [r for r in L if r["date"][:7] < m]
        te = [r for r in L if r["date"][:7] == m]
        w = fit(X(tr), np.array([r["home_win"] for r in tr], float))
        p = 1 / (1 + np.exp(-X(te) @ w))
        for r, ph in zip(te, p):
            for sd, pr, fa, wn in (("h", r["hr_h"], ph, r["home_win"]), ("a", r["hr_a"], 1 - ph, not r["home_win"])):
                if pr >= -200 and fa - be(pr) >= T:
                    bets.append(bet(r["gid"], r["date"], pr, wn, ev=fa * dec(pr) - 1))
        if T == .01:
            print("  fold %s weights a %.3f b(logit cons) %.3f" % (m, w[0], w[1]))
    report("S3 T=%.2f" % T, bets)
