"""Generic walk-forward for 'book + extra features' logistic rules on shots45 lines (Nov-Feb test months)."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rlib  # noqa: E402


def base(r):
    f = rlib.fair_prop(r["over"], r["under"])
    return [1.0, float(r["line"] == 1.5), float(r["line"] >= 3.5), float(rlib.logit(f))]


def run(name, rows, extra, Ts=(0.01, 0.02, 0.03), l2=2.0, verbose=True):
    """extra(r) -> list of floats (raw); standardised on each training set."""
    rows = [r for r in rows if r["ok"] and r["date"] < rlib.LOCKBOX]
    res = {T: [] for T in Ts}
    ll = []
    for m in rlib.TEST_MONTHS:
        tr = [r for r in rows if r["date"][:7] < m and r["result"] == "OK"]
        te = [r for r in rows if r["date"][:7] == m and r["result"] == "OK"]
        E = np.array([extra(r) for r in tr], float)
        mu, sd = E.mean(0), E.std(0)
        sd[sd == 0] = 1
        X = lambda rs: np.array([base(r) + list((np.array(extra(r), float) - mu) / sd) for r in rs])
        w = rlib.fit_logit(X(tr), [r["actual"] > r["line"] for r in tr], l2=l2)
        q = rlib.predict(w, X(te))
        y = np.array([r["actual"] > r["line"] for r in te], float)
        fb = np.array([rlib.fair_prop(r["over"], r["under"]) for r in te])
        ll.append((m, len(y), round(float(-np.mean(y * np.log(q) + (1 - y) * np.log(1 - q))), 4),
                   round(float(-np.mean(y * np.log(fb) + (1 - y) * np.log(1 - fb))), 4)))
        for r, p in zip(te, q):
            for T in res:
                for side, pr, ps in (("over", r["over"], p), ("under", r["under"], 1 - p)):
                    if pr >= -200 and ps - rlib.be(pr) >= T:
                        res[T].append(rlib.bet(r["gid"], r["date"], pr, (r["actual"] > r["line"]) == (side == "over"),
                                               side=side, line=r["line"]))
        if verbose:
            print(name, m, "w", np.round(w, 3).tolist())
    print(name, "log loss (rule vs book):", ll)
    for T, b in res.items():
        print("%s T=%.2f %s | %s" % (name, T, rlib.fmt(rlib.summ(b)), rlib.by_month(b)))
    return res
