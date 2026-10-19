"""Negative-binomial tail model conditional on the main line's proportional fair: for each line, mu solves
P(X > line) = c(fair) under NB(mu, r); r and a calibration slope/intercept are fitted by max likelihood on given rows."""
import math
import numpy as np
from scipy import optimize, stats  # noqa


def nb_sf(k, mu, r):
    """P(X >= k)."""
    p = r / (r + mu)
    return float(stats.nbinom.sf(k - 1, r, p))


def mu_for(line, q, r):
    k = int(line + 0.5)
    lo, hi = 0.01, 20.0
    for _ in range(50):
        m = (lo + hi) / 2
        if nb_sf(k, m, r) < q:
            lo = m
        else:
            hi = m
    return (lo + hi) / 2


def fit_r(rows, grid=(2, 3, 4, 6, 8, 12, 20, 50, 200)):
    """rows: (line, fair, actual). Picks r with best log-likelihood of the actual count (mu from fair)."""
    best = None
    for r in grid:
        ll = 0.0
        cache = {}
        for line, f, a in rows:
            key = (line, round(f, 3))
            if key not in cache:
                cache[key] = mu_for(line, f, r)
            mu = cache[key]
            ll += stats.nbinom.logpmf(a, r, r / (r + mu))
        if best is None or ll > best[1]:
            best = (r, ll)
    return best
