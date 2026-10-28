#!/usr/bin/env python3
"""model.py  Prop Check NHL probability-of-over estimator (stdlib only).

One sentence: "his per-minute rate over his last two seasons (recent games count more, pulled toward
the league average for his position), times the ice time he has been getting lately, adjusted for
tonight's opponent, turned into a chance of clearing the number."

Everything here uses ONLY games before the game being predicted. Callers pass prior rows.

Skater row (dict), any order:  season (e.g. 20262027), date "YYYY-MM-DD", gid, toi (seconds),
                               shots, goals, assists, points
Team-game row (dict):          date, gid, sf (shots for), sa (shots against), ga (goals against)

API
  skater_prob(rows, pos, season, market, line, ctx)  -> dict(mu, p_raw, p, n, n_season, thin)
                                                        P(under) = 1 - p
  team_factor(team_rows, key, league_avg, K)         -> shrunk opponent/team multiplier
  naive_last10(rows, market, line)                   -> old tool's hit count / 10 (comparison only)
  break_even(american_price)                         -> probability needed to break even
The self-test lives in tests/test_model.py (ported unchanged from the Data Scientist's file).

PRODUCTION NOTE: this is the Data Scientist's model.py lifted as-is. The only addition is
skater_detail(), which returns the pieces of skater_mu() (expected ice time, opponent factor)
so the engine can write the reason sentence. skater_mu() returns exactly what it always did.
The model's own parameters stay here (they are the fitted model, changed only by a refit);
every betting rule value lives in config/rules.json.
"""
import math

# ---------------------------------------------------------------- parameters (fit on 2024-25, see model_spec.md)
PRIOR_TOI = {"F": 950.0, "D": 1150.0}       # seconds; league mean TOI by position
TOI_H, TOI_K = 5.0, 1.0                      # expected TOI: half-life 5 games, prior weight 1 game
TEAM_H = 25.0                                # team factor half-life (games)
MAX_ROWS = 170                               # history cap (about two seasons)

SK = {  # H: half-life (games); g: weight on prior-season games; K: prior weight in 15-minute games;
        # prior60: league rate per 60 min by position; scale: level correction; r: neg-binomial size
    "shots":   dict(H=40.0, g=0.7, K=5.0,  prior60={"F": 7.37, "D": 4.20}, scale=0.972, opp="sa", oppK=10.0,
                    home=(1.017, 0.983), r=15.7),
    "points":  dict(H=80.0, g=1.0, K=10.0, prior60={"F": 2.06, "D": 1.08}, scale=0.972, opp="ga", oppK=20.0,
                    home=(1.0, 1.0), r=None),
    "assists": dict(H=80.0, g=1.0, K=20.0, prior60={"F": 1.18, "D": 0.85}, scale=0.968, opp="ga", oppK=20.0,
                    home=(1.0, 1.0), r=None),
    "goals":   dict(H=80.0, g=1.0, K=20.0, prior60={"F": 0.88, "D": 0.23}, scale=0.964, opp="ga", oppK=20.0,
                    home=(1.0, 1.0), r=None),
}
# Calibration: p = sigmoid(a + b*logit(p_raw)), fit on 2024-25. Identity (0,1) when not listed.
CALIB = {
    ("shots", 0.5): (-0.103, 1.080), ("shots", 1.5): (0.013, 1.054), ("shots", 2.5): (0.066, 1.051),
    ("shots", 3.5): (0.046, 1.014), ("shots", 4.5): (0.040, 0.998),
    ("points", 0.5): (0.044, 1.092), ("points", 1.5): (0.122, 1.045),
    ("assists", 0.5): (0.138, 1.140), ("goals", 0.5): (0.046, 1.028),
}

# Thin history: backtest shows OVER picks run 1-4 points below the stated chance for these players
# (n<20: -3.6 on 251 legs; <10 games with team: -1.0 and -4.0 on 433 and 119 legs). Flag them; the
# Sharp's rule adds THIN_MARGIN to the required edge. No general early-season penalty is needed.
THIN_ROWS, THIN_TEAM_GAMES, THIN_MARGIN = 20, 10, 0.04

# ---------------------------------------------------------------- distributions
def nb_sf(k, mu, r=None):
    """P(X >= k) for X ~ NegBin(mean mu, size r); Poisson when r is None."""
    if k <= 0:
        return 1.0
    if mu <= 0:
        return 0.0
    cdf, k = 0.0, int(k)
    if r is None:
        term = math.exp(-mu)
        for i in range(k):
            cdf += term
            term *= mu / (i + 1)
    else:
        p = r / (r + mu)
        term = p ** r
        for i in range(k):
            cdf += term
            term *= (i + r) / (i + 1) * (1 - p)
    return min(1.0, max(0.0, 1.0 - cdf))


def _logit(p):
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def calibrate(p_raw, market, line):
    a, b = CALIB.get((market, line), CALIB.get(market, (0.0, 1.0)))
    return 1.0 / (1.0 + math.exp(-(a + b * _logit(p_raw))))


def break_even(american):
    """-200 -> 0.6667, +120 -> 0.4545"""
    return (-american) / (-american + 100.0) if american < 0 else 100.0 / (american + 100.0)

# ---------------------------------------------------------------- team factors
def team_factor(team_rows, key, league_avg, K, H=TEAM_H):
    """Shrunk multiplier for a team's per-game `key` (sa, sf, ga) vs league average.
    team_rows: that team's PRIOR games (any order). 1.0 when no games."""
    rows = sorted(team_rows, key=lambda r: (r["date"], r["gid"]), reverse=True)[:MAX_ROWS]
    w = x = 0.0
    for i, r in enumerate(rows):
        wi = 0.5 ** (i / H)
        w += wi
        x += wi * r[key]
    return (K * league_avg + x) / (K + w) / league_avg

# ---------------------------------------------------------------- skaters
def skater_detail(rows, pos, season, market, ctx=None):
    """Expected count tonight plus its parts. rows: the player's prior games (any team), pos 'F'|'D',
    season: tonight's season id, ctx: {'home': bool, 'opp_sa_f': team_factor(opp rows,'sa',lg,10),
    'opp_ga_f': team_factor(opp rows,'ga',lg,20), 'games_with_team': int (optional, for the thin flag)}.
    Returns dict(mu, etoi (seconds), rate (per second), opp_f, home_f)."""
    c = SK[market]
    ctx = ctx or {}
    rows = [r for r in rows if r["season"] >= season - 10001]          # this season + last season
    rows = sorted(rows, key=lambda r: (r["date"], r["gid"]), reverse=True)[:MAX_ROWS]
    w = t = x = wt = tt = 0.0
    for i, r in enumerate(rows):
        disc = 1.0 if r["season"] == season else c["g"]
        wi = disc * 0.5 ** (i / c["H"])
        w += wi; t += wi * r["toi"]; x += wi * r[market]
        wj = disc * 0.5 ** (i / TOI_H)
        wt += wj; tt += wj * r["toi"]
    prior_rate = c["prior60"][pos] / 3600.0
    rate = (c["K"] * 900.0 * prior_rate + x) / (c["K"] * 900.0 + t)       # per second, shrunk
    etoi = (TOI_K * PRIOR_TOI[pos] + tt) / (TOI_K + wt)                   # expected seconds tonight
    mu = rate * etoi * c["scale"]
    opp_f = ctx.get("opp_sa_f", 1.0) if c["opp"] == "sa" else ctx.get("opp_ga_f", 1.0)
    mu *= opp_f
    home_f = 1.0
    if "home" in ctx:
        home_f = c["home"][0] if ctx["home"] else c["home"][1]
        mu *= home_f
    return dict(mu=mu, etoi=etoi, rate=rate, opp_f=opp_f, home_f=home_f)


def skater_mu(rows, pos, season, market, ctx=None):
    """Expected count tonight (see skater_detail for the arguments)."""
    return skater_detail(rows, pos, season, market, ctx)["mu"]


def skater_prob(rows, pos, season, market, line, ctx=None):
    """Probability the player goes OVER `line` (e.g. 2.5) in `market`."""
    mu = skater_mu(rows, pos, season, market, ctx)
    p_raw = nb_sf(math.floor(line) + 1, mu, SK[market]["r"])
    n = sum(1 for r in rows if r["season"] >= season - 10001)
    n_season = sum(1 for r in rows if r["season"] == season)
    p = calibrate(p_raw, market, line)
    thin = n < THIN_ROWS or (ctx or {}).get("games_with_team", THIN_TEAM_GAMES) < THIN_TEAM_GAMES
    return dict(mu=mu, p_raw=p_raw, p=p, n=n, n_season=n_season, thin=thin)


def naive_last10(rows, market, line):
    """Old tool: share of the last 10 games over the line. None with fewer than 10 games."""
    rows = sorted(rows, key=lambda r: (r["date"], r["gid"]), reverse=True)[:10]
    if len(rows) < 10:
        return None
    return sum(1 for r in rows if r[market] > line) / 10.0

