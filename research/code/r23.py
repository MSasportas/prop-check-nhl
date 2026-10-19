"""R2 (book + model stack, calibration refit) and R3 (book + pre-game features), walk-forward Nov-Feb.
Lockbox (Mar 1+) rows are never scored here. python3 -I r23.py"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rlib  # noqa: E402

rows = [r for r in rlib.load("../research/feat_r3.jsonl") if r["ok"] and r["date"] < rlib.LOCKBOX]
FEATS = ["l5", "l10", "szn", "over10", "toi_tr", "sog_per60_l10", "opp_sa10", "b2b", "opp_b2b"]


def base(r):
    f = rlib.fair_prop(r["over"], r["under"])
    return [1.0, float(r["line"] == 1.5), float(r["line"] >= 3.5), float(rlib.logit(f))]


def x_r2(r):
    return base(r) + [float(rlib.logit(r["p_over"]))]


def x_r3(r, mu, sd):
    v = base(r) + [float(r["pos"] == "D"), float(bool(r["home"])), float(r.get("n_prior", 0) < 5)]
    for k in FEATS:
        x = r.get(k)
        v.append(0.0 if x is None or r.get("n_prior", 0) < 5 else (x - mu[k]) / sd[k])
    return v


def run(name, xf, need_model):
    data = [r for r in rows if (r["p_over"] is not None or not need_model)]
    res = {T: [] for T in (0.01, 0.02, 0.03)}
    ll = []
    for m in rlib.TEST_MONTHS:
        tr = [r for r in data if r["date"][:7] < m and r["result"] == "OK"]
        te = [r for r in data if r["date"][:7] == m]
        mu = {k: np.mean([r[k] for r in tr if r.get(k) is not None and r.get("n_prior", 0) >= 5]) for k in FEATS}
        sd = {k: np.std([r[k] for r in tr if r.get(k) is not None and r.get("n_prior", 0) >= 5]) or 1 for k in FEATS}
        f = (lambda r: xf(r, mu, sd)) if name == "R3" else xf
        w = rlib.fit_logit([f(r) for r in tr], [r["actual"] > r["line"] for r in tr], l2=2.0)
        p = rlib.predict(w, [f(r) for r in te])
        okr = [(r, q) for r, q in zip(te, p) if r["result"] == "OK"]
        y = np.array([r["actual"] > r["line"] for r, _ in okr], float)
        q = np.array([q for _, q in okr])
        fb = np.array([rlib.fair_prop(r["over"], r["under"]) for r, _ in okr])
        ll.append((m, len(y), float(-np.mean(y * np.log(q) + (1 - y) * np.log(1 - q))),
                   float(-np.mean(y * np.log(fb) + (1 - y) * np.log(1 - fb)))))
        for r, q in zip(te, p):
            if r["result"] != "OK":
                continue
            for T in res:
                for side, pr, ps in (("over", r["over"], q), ("under", r["under"], 1 - q)):
                    if pr < -200:
                        continue
                    if ps - rlib.be(pr) >= T:
                        win = (r["actual"] > r["line"]) == (side == "over")
                        res[T].append(rlib.bet(r["gid"], r["date"], pr, win, side=side, line=r["line"]))
        print(name, m, "weights", np.round(w, 3).tolist())
    print(name, "log loss by month (model vs proportional book):", [(m, n, round(a, 4), round(b, 4)) for m, n, a, b in ll])
    for T, b in res.items():
        s = rlib.summ(b)
        unders = sum(x["side"] == "under" for x in b)
        print("%s T=%.2f %s | %s | unders %d" % (name, T, rlib.fmt(s), rlib.by_month(b), unders))
    return res


out = {"R2": run("R2", x_r2, True), "R3": run("R3", x_r3, False)}
json.dump({k: {str(T): v for T, v in d.items()} for k, d in out.items()}, open(os.path.join(rlib.OUT, "r23_bets.json"), "w"))
