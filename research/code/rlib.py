"""Shared helpers for research scripts (numpy). Data paths point at private session scratch (PC_HIST_DIR)."""
import json
import os
import random
from collections import defaultdict

import numpy as np

SCR = "/tmp/claude-0/-home-claude/ab9b3f07-215a-50c7-96a2-d84b6c4f2d08/scratchpad"
H = os.environ.get("PC_HIST_DIR", os.path.join(SCR, "hist"))
WORK = os.path.join(H, "work")
RAW = os.path.join(H, "raw")
OUT = os.path.join(H, "research")
os.makedirs(OUT, exist_ok=True)
LOCKBOX = "2026-03-01"
TEST_MONTHS = ["2025-11", "2025-12", "2026-01", "2026-02"]


def be(a):
    return (-a) / (-a + 100.0) if a < 0 else 100.0 / (a + 100.0)


def dec(a):
    return 1.0 + (100.0 / -a if a < 0 else a / 100.0)


def fair_prop(o, u):
    a, b = be(o), be(u)
    return a / (a + b)


def logit(p):
    p = np.clip(p, 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p))


def load(name):
    return [json.loads(l) for l in open(os.path.join(WORK, name))]


def bet(gid, date, price, win, **kw):
    d = {"gid": gid, "date": date, "month": date[:7], "price": price, "win": bool(win),
         "profit": dec(price) - 1.0 if win else -1.0, "be": be(price)}
    d.update(kw)
    return d


def summ(bets, B=2000, seed=11):
    n = len(bets)
    if n == 0:
        return {"n": 0, "roi": None, "lo90": None, "hi90": None, "lo95": None, "hit": None, "be": None}
    units = sum(b["profit"] for b in bets)
    by = defaultdict(list)
    for b in bets:
        by[b["gid"]].append(b["profit"])
    g = list(by.values())
    sums = np.array([sum(x) for x in g])
    cnts = np.array([len(x) for x in g])
    rng = np.random.default_rng(seed)
    rois = []
    for _ in range(B):
        idx = rng.integers(0, len(g), len(g))
        rois.append(sums[idx].sum() / cnts[idx].sum())
    rois = np.sort(rois)
    return {"n": n, "hit": sum(b["win"] for b in bets) / n, "be": sum(b["be"] for b in bets) / n, "units": units,
            "roi": units / n, "lo90": rois[int(.05 * B)], "hi90": rois[int(.95 * B)], "lo95": rois[int(.025 * B)],
            "p_one": float((rois <= 0).mean())}


def fmt(s):
    if not s["n"]:
        return "n 0"
    return "n %d hit %.1f%% BE %.1f%% ROI %+.1f%% 90%% [%+.1f, %+.1f]" % (
        s["n"], 100 * s["hit"], 100 * s["be"], 100 * s["roi"], 100 * s["lo90"], 100 * s["hi90"])


def by_month(bets):
    m = defaultdict(list)
    for b in bets:
        m[b["month"]].append(b)
    return " / ".join("%s %+.1f%% (n%d)" % (k[5:], 100 * sum(x["profit"] for x in v) / len(v), len(v)) for k, v in sorted(m.items()))


def fit_logit(X, y, l2=1.0, iters=50):
    """L2 logistic regression by Newton; intercept is column 0 and not penalised."""
    X = np.asarray(X, float)
    y = np.asarray(y, float)
    w = np.zeros(X.shape[1])
    P = np.eye(X.shape[1]) * l2
    P[0, 0] = 0
    for _ in range(iters):
        z = X @ w
        p = 1 / (1 + np.exp(-z))
        g = X.T @ (p - y) + P @ w
        Hs = (X * (p * (1 - p))[:, None]).T @ X + P
        step = np.linalg.solve(Hs, g)
        w -= step
        if np.abs(step).max() < 1e-8:
            break
    return w


def predict(w, X):
    return 1 / (1 + np.exp(-(np.asarray(X, float) @ w)))
