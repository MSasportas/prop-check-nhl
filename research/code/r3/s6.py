"""S6: schedule spots (B2B, rest) on the moneyline, walk-forward logistic over the consensus price."""
import json, sys, os
from datetime import date
from collections import defaultdict
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from rlib import summ, fmt, be, dec, bet, logit
SCR = "/tmp/claude-0/-home-claude/ab9b3f07-215a-50c7-96a2-d84b6c4f2d08/scratchpad"
games = json.load(open(SCR + "/hist/raw/nhl/games.json"))
played = defaultdict(list)
for g in games:
    for t in (g["home"], g["away"]):
        played[t].append(g["date"])
def rest(t, d):
    prev = [x for x in played[t] if x < d]
    if not prev:
        return 3
    return min(3, (date.fromisoformat(d) - date.fromisoformat(prev[-1])).days - 1)
rows = [json.loads(l) for l in open(SCR + "/r3pull/h2h_rows.jsonl")]
L = [r for r in rows if r["hrs"] <= 6 and r["cons_h"] is not None and r["n_oth"] >= 3 and r["date"] < "2026-03-01"]
FOLDS = ["2025-11", "2025-12", "2026-01", "2026-02"]
def X(rs):
    out = []
    for r in rs:
        rh, ra = rest(r["home"], r["date"]), rest(r["away"], r["date"])
        out.append([1, logit(np.array([r["cons_h"]]))[0], rh == 0, ra == 0, rh - ra])
    return np.array(out, float)
def fit(Xm, y, l2=2.0):
    w = np.zeros(Xm.shape[1]); w[1] = 1
    prior = np.r_[0, 1, 0, 0, 0]
    for _ in range(50):
        p = 1 / (1 + np.exp(-Xm @ w))
        g = Xm.T @ (y - p) - l2 * np.r_[0, (w - prior)[1:]]
        H = -(Xm.T * (p * (1 - p))) @ Xm - l2 * np.diag(np.r_[0, np.ones(4)])
        w = w - np.linalg.solve(H, g)
    return w
print("B2B counts (late, pre-lockbox): home %d, away %d of %d games" % (sum(rest(r['home'], r['date']) == 0 for r in L), sum(rest(r['away'], r['date']) == 0 for r in L), len(L)))
for T in (.01, .02, .03):
    bets = []
    for m in FOLDS:
        tr = [r for r in L if r["date"][:7] < m]; te = [r for r in L if r["date"][:7] == m]
        w = fit(X(tr), np.array([r["home_win"] for r in tr], float))
        if T == .01:
            print("  fold %s w: a %+.3f b %.3f homeB2B %+.3f awayB2B %+.3f restdiff %+.3f" % (m, *w))
        ph = 1 / (1 + np.exp(-X(te) @ w))
        for r, p in zip(te, ph):
            for pr, fa, wn in ((r["hr_h"], p, r["home_win"]), (r["hr_a"], 1 - p, not r["home_win"])):
                if pr >= -200 and fa - be(pr) >= T:
                    bets.append(bet(r["gid"], r["date"], pr, wn))
    fm = defaultdict(list)
    for b in bets: fm[b["month"]].append(b)
    print("S6 T=%.2f %s | %s" % (T, fmt(summ(bets)), " ".join("%s %+.1f%%(n%d)" % (m[5:], 100 * summ(fm[m])["roi"], len(fm[m])) if fm[m] else m[5:] + " n0" for m in FOLDS)))
# descriptive: residual of B2B teams vs consensus (pre-lockbox, all months)
for lab, f in (("home on B2B", lambda r: rest(r["home"], r["date"]) == 0), ("away on B2B", lambda r: rest(r["away"], r["date"]) == 0)):
    s = [r for r in L if f(r)]
    print("  %s: n%d home win %.3f vs consensus %.3f" % (lab, len(s), np.mean([r["home_win"] for r in s]), np.mean([r["cons_h"] for r in s])))
