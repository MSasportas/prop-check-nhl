"""Run 4 K7 (LightGBM on market + prior-only features, init_score = logit book fair) and K8 (top-k EV per night).
Walk-forward Nov-Feb, lockbox never scored. python3 -I k7.py [placebo_reps]"""
import json
import math
import os
import sys
from collections import defaultdict

import numpy as np
import lightgbm as lgb

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import rlib  # noqa: E402

R4 = os.environ.get("PC_R4_DIR", "/tmp/claude-0/-home-claude/ab9b3f07-215a-50c7-96a2-d84b6c4f2d08/scratchpad/r4")
ROWS = [r for r in (json.loads(l) for l in open(os.path.join(R4, "feat4.jsonl")))
        if r["date"] < rlib.LOCKBOX and r["result"] == "OK"]
ROWS.sort(key=lambda r: (r["date"], r["gid"]))
NAN = float("nan")
TS = (0.01, 0.02, 0.03, 0.05)
PARAMS = dict(objective="binary", num_leaves=7, min_data_in_leaf=200, learning_rate=0.03, lambda_l2=10.0,
              feature_fraction=0.8, bagging_fraction=1.0, verbose=-1, seed=7, deterministic=True, num_threads=4)


_K4 = {}


def nb_sf(L, m, v):
    k = int(math.floor(L))
    if v <= 1.01:
        c = sum(math.exp(-m + j * math.log(m) - math.lgamma(j + 1)) for j in range(k + 1))
    else:
        r = m / (v - 1.0)
        p = r / (r + m)
        c = sum(math.exp(math.lgamma(j + r) - math.lgamma(r) - math.lgamma(j + 1) + r * math.log(p) + j * math.log(1 - p))
                for j in range(k + 1))
    return 1 - c


def solve_m(L, f, v):
    lo, hi = 0.01, 15.0
    for _ in range(40):
        mid = (lo + hi) / 2
        if nb_sf(L, mid, v) < f:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def g(r, k):
    v = r.get(k)
    return NAN if v is None else float(v)


def feats(r, ctx):
    D = r["pos"] == "D"
    v = (r["all_var"] / r["all_mean"]) if r.get("all_mean") and r["all_n"] >= 2 else None
    vp = ctx["vmr"]["D" if D else "F"]
    k4 = NAN
    if v is not None:
        n = r["all_n"]
        vs = (n * v + 20 * vp) / (n + 20)
        key = (r["line"], round(r["f"], 4), round(vp, 3), round(vs, 3))
        if key not in _K4:
            mm = solve_m(r["line"], r["f"], vp)
            ps = min(max(nb_sf(r["line"], mm, vs), 1e-4), 1 - 1e-4)
            _K4[key] = float(rlib.logit(ps) - rlib.logit(r["f"]))
        k4 = _K4[key]   # K4 shape term exactly as registered
    z = NAN
    if r["all_n"] >= 5 and r.get("earlier_mean") is not None:
        z = (r["last_sog"] - r["earlier_mean"]) / math.sqrt(max(r["earlier_mean"], 0.3))
    dl = r["line"] - r["prev_line"] if r.get("prev_line") is not None else 0.0
    k9 = NAN
    if r.get("n20", 0) >= 5:
        k9 = r["att20"] * ctx["conv"]["D" if D else "F"] - r["sog20"]
    return [float(rlib.logit(r["f"])), r["line"], float(D), float(bool(r["home"])), r["logA"], g(r, "pw"), r["k3"], k4, z, dl,
            g(r, "l5"), g(r, "l10"), g(r, "szn"), g(r, "toi_tr"), g(r, "pp10"), g(r, "team_sf10"), g(r, "opp_sa10"),
            g(r, "rest"), g(r, "opp_rest"), float(r["b2b"]), float(r["opp_b2b"]), g(r, "travel"), k9, float(r["n_prior"])]


NAMES = ["logit_f", "line", "D", "home", "logA", "pw", "k3", "k4", "z", "dl", "l5", "l10", "szn", "toi_tr", "pp10",
         "team_sf10", "opp_sa10", "rest", "opp_rest", "b2b", "opp_b2b", "travel", "k9", "n_prior"]
MARKET = {0, 1}   # columns never shuffled in the placebo


def prep(tr):
    vm, cv = {}, {}
    for P in ("F", "D"):
        a = [r for r in tr if (r["pos"] == "D") == (P == "D")]
        vm[P] = float(np.mean([r["all_var"] / r["all_mean"] for r in a if r["all_n"] >= 20 and r.get("all_mean")]))
        b = [r for r in a if r.get("n20", 0) >= 5]
        cv[P] = sum(r["sog20"] for r in b) / sum(r["att20"] for r in b)
    return {"vmr": vm, "conv": cv}


def sides(rows, p):
    out = []
    for r, q in zip(rows, p):
        for side, ps in (("over", q), ("under", 1 - q)):
            if r[side] < -200:
                continue
            out.append((r, side, ps - rlib.be(r[side]), ps * rlib.dec(r[side]) - 1))
    return out


def grade(r, side):
    return rlib.bet(r["gid"], r["date"], r[side], (r["actual"] > r["line"]) == (side == "over"), side=side, line=r["line"])


def fit_predict(tr, te, ctx, shuffle_rng=None):
    X = np.array([feats(r, ctx) for r in tr])
    Xt = np.array([feats(r, ctx) for r in te])
    if shuffle_rng is not None:
        for A, rows in ((X, tr), (Xt, te)):
            grp = defaultdict(list)
            for i, r in enumerate(rows):
                grp[(r["date"], r["line"])].append(i)
            for idx in grp.values():
                idx = np.array(idx)
                perm = shuffle_rng.permutation(idx)
                for c in range(A.shape[1]):
                    if c not in MARKET:
                        A[idx, c] = A[perm, c]
    y = np.array([float(r["actual"] > r["line"]) for r in tr])
    init = X[:, 0]
    cut = int(len(tr) * 0.75)
    d1 = lgb.Dataset(X[:cut], y[:cut], init_score=init[:cut], free_raw_data=False)
    d2 = lgb.Dataset(X[cut:], y[cut:], init_score=init[cut:], reference=d1)
    b1 = lgb.train(PARAMS, d1, num_boost_round=400, valid_sets=[d2], callbacks=[lgb.early_stopping(40, verbose=False)])
    rounds = max(1, b1.best_iteration or 1)
    pin = 1 / (1 + np.exp(-(b1.predict(X[cut:], num_iteration=rounds, raw_score=True) + init[cut:])))
    inner = sides(tr[cut:], pin)
    bestT, bestroi = 0.03, None
    for T in TS:
        b = [grade(r, s) for r, s, e, ev in inner if e >= T]
        if len(b) >= 30:
            roi = sum(x["profit"] for x in b) / len(b)
            if bestroi is None or roi > bestroi:
                bestT, bestroi = T, roi
    bst = lgb.train(PARAMS, lgb.Dataset(X, y, init_score=init), num_boost_round=rounds)
    p = 1 / (1 + np.exp(-(bst.predict(Xt, raw_score=True) + Xt[:, 0])))
    imp = dict(zip(NAMES, bst.feature_importance("gain").round(1).tolist())) if rounds > 1 else {}
    return p, rounds, bestT, imp


def run(shuffle_seed=None, verbose=True):
    rng = np.random.default_rng(shuffle_seed) if shuffle_seed is not None else None
    res = {("T", T): [] for T in TS}
    res["K7s"] = []
    for k in (1, 3, 5):
        res[("top", k)] = []
    ll = []
    for m in rlib.TEST_MONTHS:
        tr = [r for r in ROWS if r["date"][:7] < m]
        te = [r for r in ROWS if r["date"][:7] == m]
        ctx = prep(tr)
        p, rounds, bestT, imp = fit_predict(tr, te, ctx, rng)
        y = np.array([float(r["actual"] > r["line"]) for r in te])
        fb = np.array([r["f"] for r in te])
        ll.append((m, len(te), rounds, bestT, round(float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))), 5),
                   round(float(-np.mean(y * np.log(fb) + (1 - y) * np.log(1 - fb))), 5)))
        if verbose:
            top = sorted(imp.items(), key=lambda x: -x[1])[:6]
            print("K7", m, "rounds", rounds, "inner T", bestT, "top gain", top)
        sd = sides(te, p)
        for T in TS:
            res[("T", T)] += [grade(r, s) for r, s, e, ev in sd if e >= T]
        res["K7s"] += [grade(r, s) for r, s, e, ev in sd if e >= bestT]
        byd = defaultdict(list)
        for x in sd:
            if x[3] > 0:
                byd[x[0]["date"]].append(x)
        for k in (1, 3, 5):
            for d, xs in byd.items():
                xs.sort(key=lambda x: -x[3])
                res[("top", k)] += [grade(r, s) for r, s, e, ev in xs[:k]]
    return res, ll


if __name__ == "__main__":
    reps = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    res, ll = run()
    print("K7 log loss by month (month, n, rounds, inner T, model, book):", ll)
    out = {}
    for k, b in res.items():
        name = "K7s" if k == "K7s" else ("K7 T%.2f" % k[1] if k[0] == "T" else "K8 top%d" % k[1])
        s = rlib.summ(b)
        out[name] = s
        print("%-10s %s p1=%s | %s" % (name, rlib.fmt(s), "%.3f" % s["p_one"] if s["n"] else "-", rlib.by_month(b)))
    if reps:
        obs = {n: out[n]["roi"] for n in out if out[n]["n"]}
        pl = defaultdict(list)
        for i in range(reps):
            rr, _ = run(shuffle_seed=1000 + i, verbose=False)
            for k, b in rr.items():
                name = "K7s" if k == "K7s" else ("K7 T%.2f" % k[1] if k[0] == "T" else "K8 top%d" % k[1])
                if b:
                    pl[name].append(sum(x["profit"] for x in b) / len(b))
        for n in obs:
            a = np.array(pl[n])
            print("placebo %-10s obs %+.1f%% placebo mean %+.1f%% sd %.1f share >= obs %.2f (reps %d)" % (
                n, 100 * obs[n], 100 * a.mean(), 100 * a.std(), (a >= obs[n]).mean(), len(a)))
    json.dump(out, open(os.path.join(R4, "k7_results.json"), "w"), indent=1, default=float)
