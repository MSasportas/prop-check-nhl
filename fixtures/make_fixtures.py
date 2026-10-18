#!/usr/bin/env python3
"""Writes the page's QA fixtures (fixtures/NAME/slate.json, record.json, rules.json).

Test data only: every file carries "fixture": true and the page shows a "Test data" tag.
Open with index.html?fixture=NAME. Each slate carries "fixture_now" so the page's clock
sits at a fixed moment for that fixture (override with ?now=ISO).
Run:  python3 fixtures/make_fixtures.py
"""
import copy
import json
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))
D = "2026-10-11"


def t(hm, day=D):
    return "%sT%s:00-04:00" % (day, hm)


def be(price):
    return round(100.0 / (price + 100.0), 4) if price > 0 else round(-price / (-price + 100.0), 4)


def dec(price):
    return 1 + (price / 100.0 if price > 0 else 100.0 / -price)


def american(d):
    return int(round((d - 1) * 100)) if d >= 2 else int(round(-100 / (d - 1)))


RULES = {
    "fixture": True,
    "version": 1,
    "updated": "2026-10-11",
    "values": {
        "price_gate": -200, "max_price": 120, "min_p": 0.56, "margin_confirmed": 0.02, "margin_early": 0.03,
        "model_weight": 0.60, "market_weight": 0.40, "uncertainty": 0.02, "under_penalty": 0.015,
        "thin_over_penalty": 0.04, "thin_rows": 20, "thin_team_games": 10, "min_history": 10,
        "news_gap": 0.15, "too_good": 0.20, "pull_margin": 0.0, "drift_pull": 0.04,
        "max_per_player": 1, "max_per_game": 3, "parlay_leg_min_p": 0.58, "parlay_min_p_2": 0.34,
        "parlay_min_p_3": 0.20, "parlay_cap": 3, "parlay_min_legs": 2, "parlay_max_legs": 3, "parlay_leg_min_price": -200, "parlay_leg_max_price": 100, "parlay_edge": 0.03, "stake": 1, "min_sample": 30, "pause_legs": 50,
        "change_legs": 150,
    },
    "ui": {"stale_after_min": 75, "refresh_sec": 120, "picks_open": 8},
}

GAMES = [
    ("g1", "BOS", "BUF", "17:00"), ("g2", "FLA", "TBL", "19:10"), ("g3", "NYR", "NJD", "19:10"),
    ("g4", "TOR", "MTL", "19:10"), ("g5", "COL", "DAL", "20:10"), ("g6", "EDM", "VAN", "22:10"),
    ("g7", "SEA", "SJS", "22:10"),
]
GAME = {g[0]: g for g in GAMES}

# (key, game, player, team, market, bet, price, p, state, thin, games_used, this_season, reason tail)
PICKS = [
    ("mack", "g5", "N. MacKinnon", "COL", "shots", "Over 3.5 shots on goal", -145, 0.664, "lineup", False, 61, 4,
     "to clear 3.5 shots", "Projects 4.4 shots in 22 min. DAL allow 6% more shots than average."),
    ("rein", "g2", "S. Reinhart", "FLA", "points", "Over 0.5 points", -160, 0.692, "early", False, 58, 3,
     "to clear 0.5 points", "Projects 1.1 points in 20 min. TBL allow 4% more goals than average."),
    ("jhug", "g3", "J. Hughes", "NJD", "shots", "Over 2.5 shots on goal", -135, 0.631, "lineup", False, 44, 3,
     "to clear 2.5 shots", "Projects 3.5 shots in 21 min. NYR allow 8% more shots than average."),
    ("maka", "g5", "C. Makar", "COL", "points", "Over 0.5 points", -150, 0.652, "lineup", False, 60, 4,
     "to clear 0.5 points", "Projects 1.0 points in 25 min. DAL allow 3% more goals than average."),
    ("matt", "g4", "A. Matthews", "TOR", "shots", "Over 3.5 shots on goal", -120, 0.601, "lineup", False, 52, 4,
     "to clear 3.5 shots", "Projects 4.2 shots in 21 min. MTL allow 9% more shots than average."),
    ("kuch", "g2", "N. Kucherov", "TBL", "points", "Over 0.5 points", -190, 0.701, "early", False, 59, 3,
     "to clear 0.5 points", "Projects 1.3 points in 21 min."),
    ("mcda", "g6", "C. McDavid", "EDM", "points", "Over 0.5 points", -200, 0.712, "early", False, 55, 4,
     "to clear 0.5 points", "Projects 1.4 points in 22 min. VAN allow 5% more goals than average."),
    ("demi", "g4", "I. Demidov", "MTL", "shots", "Over 1.5 shots on goal", -130, 0.611, "early", True, 14, 4,
     "to clear 1.5 shots", "Projects 2.3 shots in 17 min. Short history: 14 games."),
    ("qhug", "g6", "Q. Hughes", "VAN", "shots", "Over 2.5 shots on goal", -115, 0.583, "early", False, 57, 4,
     "to clear 2.5 shots", "Projects 3.1 shots in 25 min. EDM allow 4% more shots than average."),
    ("ziba", "g3", "M. Zibanejad", "NYR", "shots", "Under 2.5 shots on goal", -110, 0.571, "early", False, 62, 3,
     "to stay under 2.5 shots", "Projects 2.1 shots in 19 min. NJD allow 7% fewer shots than average."),
    ("cele", "g7", "M. Celebrini", "SJS", "shots", "Under 3.5 shots on goal", 105, 0.562, "early", False, 49, 4,
     "to stay under 3.5 shots", "Projects 2.9 shots in 20 min. SEA allow 5% fewer shots than average."),
    ("past", "g1", "D. Pastrnak", "BOS", "shots", "Over 3.5 shots on goal", -125, 0.606, "locked", False, 60, 4,
     "to clear 3.5 shots", "Projects 4.1 shots in 20 min. BUF allow 7% more shots than average."),
    ("thom", "g1", "T. Thompson", "BUF", "shots", "Over 2.5 shots on goal", -140, 0.622, "locked_unconfirmed", False, 54, 3,
     "to clear 2.5 shots", "Projects 3.4 shots in 19 min."),
]
# per-game lineup + goalie status for the game list (every combination the page shows)
GAME_LINEUPS = {
    "g1": {"away": "confirmed", "home": "confirmed"}, "g2": {"away": "confirmed", "home": "confirmed"},
    "g3": {"away": "waiting", "home": "confirmed"}, "g4": {"away": "not_checked", "home": "not_checked"},
    "g5": {"away": "confirmed", "home": "waiting"}, "g6": {"away": "not_checked", "home": "not_checked"},
    "g7": {"away": "not_checked", "home": "not_checked"},
}
GAME_GOALIES = {
    "g1": {"away": {"name": "Jeremy Swayman", "status": "confirmed"}, "home": {"name": "Ukko-Pekka Luukkonen", "status": "confirmed"}},
    "g2": {"away": {"name": "Sergei Bobrovsky", "status": "confirmed"}, "home": {"name": "Andrei Vasilevskiy", "status": "expected"}},
    "g3": {"away": {"name": "Igor Shesterkin", "status": "confirmed"}, "home": None},
    "g4": {"away": {"name": "Anthony Stolarz", "status": "expected"}, "home": {"name": "Samuel Montembeault", "status": "expected"}},
    "g5": {"away": {"name": "Mackenzie Blackwood", "status": "expected"}, "home": {"name": "Jake Oettinger", "status": "confirmed"}},
    "g6": {"away": None, "home": None},
    "g7": {"away": {"name": "Joey Daccord", "status": "expected"}, "home": None},
}
STATE_TEXT = {"early": "Early: lineup not confirmed", "lineup": "Lineup confirmed", "locked": "Locked",
              "locked_unconfirmed": "Locked: lineup was not confirmed"}


def pct_floor(p):
    return int(p * 100 + 1e-6)


def reason_for(p, verb, tail):
    price = p["price"]
    return "%d%% %s; %s needs %d%%. %s" % (pct_floor(p["p"]), verb, ("+%d" % price) if price > 0 else str(price),
                                         round(p["breakeven"] * 100), tail)


def make_pick(row, rank):
    key, gid, player, team, market, bet, price, p, state, thin, gu, gs, verb, tail = row
    g = GAME[gid]
    home = g[2] == team
    b = be(price)
    hist = [{"at": t("13:02"), "text": STATE_TEXT["early"]}]
    if state == "lineup":
        hist.append({"at": t("18:35"), "text": STATE_TEXT["lineup"]})
    if state.startswith("locked"):
        hist.append({"at": t(g[3]), "text": STATE_TEXT[state]})
    return {
        "id": "%s:%s:%s" % (D, gid, key), "rank": rank, "tier": "main", "game_id": gid,
        "player": player, "team": team, "opp": g[1] if home else g[2], "home": home, "start": t(g[3]),
        "market": market, "bet": bet,
        "price": price, "price_at": t("17:02"), "first_price": price, "first_price_at": t("13:02"),
        "worst_price": price, "p": p, "breakeven": b, "p_pct": pct_floor(p), "breakeven_pct": round(b * 100),
        "reason": None, "graded": None,
        "state": state, "thin": thin, "games_used": gu, "games_this_season": gs,
        "history": hist, "pulled": None,
        "_verb": verb, "_tail": tail,
    }


def finish(slate):
    """Recompute every pick's reason from its final price and p, and drop helper keys."""
    for p in slate["picks"]:
        p["breakeven"] = be(p["price"])
        p["p_pct"], p["breakeven_pct"] = pct_floor(p["p"]), round(p["breakeven"] * 100)
        p["reason"] = reason_for(p, p.pop("_verb"), p.pop("_tail"))
    for par in slate["parlays"]:
        par["p_pct"], par["breakeven_pct"] = pct_floor(par["p"]), round(par["breakeven"] * 100)
    now = slate.get("fixture_now")
    for g in slate["games"]:                    # the engine marks started games; the game list skips them
        g["started"] = bool(now) and g["start"] <= now
    st = slate["status"]
    if st.get("lineups_at") is None and st.get("lineups_state") == "ok":
        st["lineups_state"], st["lineups_note"] = "not_yet", None
    pool = st.get("pool") or {}
    if pool.get("days_left") is None and pool.get("game_days_left") is not None:
        pool["days_left"] = pool["game_days_left"]
    slate.setdefault("status_at", slate["generated_at"])
    return slate


def make_parlay(n, legs, picks, state):
    by = {p["id"].split(":")[-1]: p for p in picks}
    d = 1.0
    pp = 1.0
    for k in legs:
        d *= dec(by[k]["price"])
        pp *= by[k]["p"]
    return {"id": "%s:parlay:%s" % (D, "+".join(legs)), "legs": [by[k]["id"] for k in legs], "price": american(d),
            "price_at": t("17:02"), "p": round(pp, 4), "breakeven": round(1 / d, 4), "state": state, "pulled": None,
            "graded": None}


def base_slate():
    picks = [make_pick(r, i + 1) for i, r in enumerate(PICKS)]
    counts = {}
    for p in picks:
        counts[p["game_id"]] = counts.get(p["game_id"], 0) + 1
    return {
        "fixture": True,
        "fixture_now": t("18:55"),
        "slate_date": D,
        "generated_at": t("18:52"),
        "status_at": t("18:52"),
        "valid_until": "2026-10-12T05:00:00-04:00",
        "status": {
            "prices_state": "ok", "prices_at": t("17:02"), "next_price_read_at": t("19:25"),
            "stats_built_at": t("09:12"), "stats_through": "2026-10-10", "stats_state": "ok",
            "lineups_at": t("18:35"), "goalies_at": None, "lineups_state": "ok",
            "lineups_note": "14 of 14 team line pages are dated today.",
            "last_run": {"ok": True, "at": t("18:52"), "failed_step": None},
            "pool": {"pulls_left": 412, "keys": 3, "game_days_left": 6, "days_left": 21, "low": False},
            "excluded_teams": [], "lines_checked": 212,
        },
        "banners": [],
        "empty": None,
        "games": [{"id": g[0], "away": g[1], "home": g[2], "start": t(g[3]), "picks": counts.get(g[0], 0),
                   "lineups": GAME_LINEUPS.get(g[0]), "goalies": GAME_GOALIES.get(g[0]),
                   "excluded_reason": None} for g in GAMES],
        "picks": picks,
        "parlays": [make_parlay(1, ["mack", "jhug"], picks, "lineup"),
                    make_parlay(2, ["maka", "matt"], picks, "lineup"),
                    make_parlay(3, ["kuch", "mcda", "demi"], picks, "early")],   # a leg is in 1 parlay only
        "goal_watch": [
            {"player": "A. Matthews", "team": "TOR", "price": 135, "fair_price": 160},
            {"player": "L. Draisaitl", "team": "EDM", "price": 125, "fair_price": 150},
            {"player": "S. Reinhart", "team": "FLA", "price": 170, "fair_price": 195},
        ],
        "goal_watch_note": "Not picks. Our model is weakest on goals.",
    }


def find(slate, key):
    for p in slate["picks"]:
        if p["id"].endswith(":" + key):
            return p
    raise KeyError(key)


def rerank(slate):
    n = 0
    for p in slate["picks"]:
        if not p["pulled"] and not p["state"].startswith("locked"):
            n += 1
            p["rank"] = n
    counts = {}
    for p in slate["picks"]:
        if not p["pulled"]:
            counts[p["game_id"]] = counts.get(p["game_id"], 0) + 1
    for g in slate["games"]:
        g["picks"] = counts.get(g["id"], 0)


def empty_slate(code, text, sub=None):
    s = base_slate()
    s["picks"], s["parlays"], s["goal_watch"] = [], [], []
    s["empty"] = {"code": code, "text": text, "sub": sub}
    s["goal_watch_note"] = None
    for g in s["games"]:
        g["picks"] = 0
    return s


# ---------------- record ----------------
POOL = [
    ("N. MacKinnon", "Over 3.5 shots on goal", "shots"), ("S. Reinhart", "Over 0.5 points", "points"),
    ("J. Hughes", "Over 2.5 shots on goal", "shots"), ("A. Matthews", "Over 3.5 shots on goal", "shots"),
    ("C. Makar", "Over 0.5 points", "points"), ("N. Kucherov", "Over 0.5 points", "points"),
    ("M. Zibanejad", "Under 2.5 shots on goal", "shots"), ("D. Pastrnak", "Over 3.5 shots on goal", "shots"),
    ("K. Kaprizov", "Over 2.5 shots on goal", "shots"), ("J. Eichel", "Over 0.5 points", "points"),
    ("T. Stutzle", "Under 2.5 shots on goal", "shots"), ("B. Point", "Over 2.5 shots on goal", "shots"),
]
PRICES = [-145, -160, -135, -120, -150, -190, -110, -125, 105, -175, -115, 100]


def line_of(bet):
    return float(bet.split()[1])


def single(rng, date, i, result=None, pulled=None):
    player, bet, market = POOL[(i * 5 + int(date[-2:])) % len(POOL)]
    price = PRICES[(i * 3 + int(date[-2:])) % len(PRICES)]
    e = {"id": "%s:r%d" % (date, i), "kind": "single", "player": player, "bet": bet, "price": price,
         "first_price": price + (10 if i % 4 == 0 else 0), "result": result, "actual": None, "units": None,
         "pulled": pulled, "legs": []}
    if result is None:
        return e
    ln = line_of(bet)
    over = bet.startswith("Over")
    if result == "VOID":
        e["actual"], e["units"] = "did not play", 0.0
        return e
    if result == "PUSH":
        e["bet"] = bet.replace(str(ln), str(int(ln + 0.5)))
        e["actual"], e["units"] = "had %d" % int(ln + 0.5), 0.0
        return e
    hit = result == "W"
    if over == hit:
        actual = int(ln + 0.5) + rng.choice([0, 0, 1, 2])
    else:
        actual = max(0, int(ln - 0.5) - rng.choice([0, 0, 1]))
    e["actual"] = "had %d" % actual
    e["units"] = round(dec(price) - 1, 2) if hit else -1.0
    return e


def parlay(date, i, legs, pulled=None):
    graded = all(l["result"] for l in legs)
    live = [l for l in legs if l["result"] in ("W", "L")]
    d = 1.0
    for l in legs:
        d *= dec(l["price"])
    res = None
    u = None
    if graded:
        res = "W" if live and all(l["result"] == "W" for l in live) else "L"
        dl = 1.0
        for l in live:
            dl *= dec(l["price"])
        gp = american(dl)                       # graded price: push/void legs drop out
        u = round(dec(gp) - 1, 2) if res == "W" else -1.0
    ll = []
    for l in legs:
        c = copy.deepcopy(l)
        c["units"] = None
        ll.append(c)
    return {"id": "%s:p%d" % (date, i), "kind": "parlay", "player": None, "bet": None,
            "price": gp if graded else american(d), "first_price": american(d), "result": res, "actual": None, "units": u, "pulled": pulled, "legs": ll}


def night(rng, date, pattern, graded=True, with_pulled=False, with_parlays=True):
    ents = [single(rng, date, i, r) for i, r in enumerate(pattern)]
    out = list(ents)
    if with_pulled:
        out.append(single(rng, date, 20, "L" if graded else None,
                          {"at": "%sT18:41:00-04:00" % date, "reason": "Scratched from the lineup"}))
    if with_parlays and len(ents) >= 2:
        out.append(parlay(date, 1, ents[:2]))
        if len(ents) >= 5:
            out.append(parlay(date, 2, ents[2:5]))
    w = sum(1 for e in ents if e["result"] == "W")
    l = sum(1 for e in ents if e["result"] == "L")
    u = round(sum(e["units"] or 0 for e in ents), 2)
    return {"date": date, "graded": graded, "w": w, "l": l, "units": u, "entries": out}


def tonight_night(slate):
    ents = []
    for p in slate["picks"]:
        ents.append({"id": p["id"], "kind": "single", "player": p["player"], "bet": p["bet"],
                     "price": p["worst_price"], "first_price": p["first_price"], "result": None, "actual": None,
                     "units": None, "pulled": p["pulled"], "legs": []})
    by = {e["id"]: e for e in ents}
    for par in slate["parlays"]:
        ents.append({"id": par["id"], "kind": "parlay", "player": None, "bet": None, "price": par["price"],
                     "first_price": par["price"], "result": None, "actual": None, "units": None,
                     "pulled": par["pulled"], "legs": [copy.deepcopy(by[i]) for i in par["legs"]]})
    return {"date": slate["slate_date"], "graded": False, "w": 0, "l": 0, "units": 0.0, "entries": ents}


def row(key, label, w, l, units, needed, push=0, void=0):
    n = w + l
    return {"key": key, "label": label, "w": w, "l": l, "push": push, "void": void, "units": units,
            "hit_rate": round(w / n, 4) if n else None, "needed": needed, "n": n}


def record60(slate):
    rng = random.Random(60)
    pats = {
        "2026-10-10": ["W", "L", "W", "W", "PUSH", "L", "W", "W", "L"],
        "2026-10-09": ["W", "W", "L", "W", "L", "W"],
        "2026-10-08": ["L", "W", "W", "VOID", "W", "L", "W", "W"],
        "2026-10-07": ["W", "L", "L", "W"],
        "2026-10-06": ["W", "W", "W", "L", "W", "L", "W"],
        "2026-10-05": ["L", "W", "W", "W", "L"],
    }
    nights = [tonight_night(slate)] + [night(rng, d, p, True, with_pulled=(d in ("2026-10-10", "2026-10-08")))
                                        for d, p in pats.items()]
    hd = row("headline", None, 41, 22, 6.3, 0.59, push=2, void=1)
    del hd["key"], hd["label"]
    return {
        "fixture": True, "generated_at": t("18:52"),
        "summary": {"headline": hd, "rows": [
            row("shots", "Shots on goal", 24, 11, 4.9, 0.61, push=2),
            row("points", "Points", 17, 11, 1.4, 0.58, void=1),
            row("parlays", "Parlays", 6, 9, 1.1, 0.36),
            row("pulled", "Pulled (not counted above)", 3, 2, 0.4, 0.6),
        ]},
        "nights": nights,
        "older": ["record/2026-10.json", "record/2026-09.json"],
    }


def older_files():
    rng = random.Random(9)
    oct_ = {"fixture": True, "nights": [
        night(rng, "2026-10-05", ["L", "W", "W", "W", "L"]),          # also in record.json: must not show twice
        night(rng, "2026-10-04", ["W", "L", "W", "W"], with_pulled=True),
        night(rng, "2026-10-03", ["L", "L", "W", "W", "W", "PUSH"]),
    ]}
    sep = {"fixture": True, "nights": [
        night(rng, "2026-09-30", ["W", "W", "L"]),
        night(rng, "2026-09-29", ["L", "W", "W", "L", "W"]),
    ]}
    return {"record/2026-10.json": oct_, "record/2026-09.json": sep}


def record20(slate):
    rng = random.Random(20)
    nights = [tonight_night(slate),
              night(rng, "2026-10-10", ["W", "L", "W", "W", "PUSH", "L", "W", "W"], with_pulled=True),
              night(rng, "2026-10-09", ["W", "W", "L", "W", "L", "W", "L"]),
              night(rng, "2026-10-08", ["L", "W", "W", "W", "L", "W", "L"])]
    hd = row("headline", None, 13, 8, 1.9, 0.59, push=1)
    del hd["key"], hd["label"]
    return {"fixture": True, "generated_at": t("18:52"),
            "summary": {"headline": hd, "rows": [
                row("shots", "Shots on goal", 8, 5, 1.3, 0.6, push=1),
                row("points", "Points", 5, 3, 0.6, 0.58),
                row("parlays", "Parlays", 2, 4, -0.4, 0.36),
                row("pulled", "Pulled (not counted above)", 0, 1, -1.0, 0.6),
            ]},
            "nights": nights, "older": []}


def record0():
    hd = row("headline", None, 0, 0, 0.0, None)
    del hd["key"], hd["label"]
    return {"fixture": True, "generated_at": t("18:52"), "summary": {"headline": hd, "rows": []},
            "nights": [], "older": []}


# ---------------- fixtures ----------------
def build():
    out = {}
    normal = base_slate()
    rec = record60(normal)
    out["normal"] = (normal, rec)
    out["record60"] = (normal, rec)
    out["record20"] = (normal, record20(normal))
    out["record0"] = (normal, record0())

    s = base_slate()
    m = find(s, "mack")
    m.update(first_price=-135, first_price_at=t("10:31"), price=-145, worst_price=-145, breakeven=be(-145))
    m["history"][0]["at"] = t("10:31")
    j = find(s, "jhug")
    j.update(first_price=-150, first_price_at=t("10:31"), price=-135, worst_price=-150, breakeven=be(-135))
    a = find(s, "matt")
    a["pulled"] = {"at": t("17:02"), "reason": "Hard Rock moved the line to 4.5"}
    s["parlays"][1]["pulled"] = {"at": t("17:02"), "reason": "Matthews leg pulled", "legs": [a["id"]]}
    rerank(s)
    out["moved"] = (s, rec)

    s = base_slate()
    find(s, "maka")["pulled"] = {"at": t("18:41"), "reason": "Scratched from the lineup"}
    find(s, "maka")["history"].append({"at": t("18:41"), "text": "Pulled: Scratched from the lineup"})
    s["parlays"][1]["pulled"] = {"at": t("18:41"), "reason": "Makar leg pulled", "legs": [find(s, "maka")["id"]]}
    new = make_pick(("drai", "g6", "L. Draisaitl", "EDM", "points", "Over 0.5 points", -185, 0.695, "early", False, 57, 4,
                     "to clear 0.5 points", "Projects 1.3 points in 21 min. VAN allow 5% more goals than average."), 0)
    new["first_price_at"] = new["price_at"] = t("18:50")
    new["history"] = [{"at": t("18:50"), "text": STATE_TEXT["early"]}]
    s["picks"].insert(5, new)
    rerank(s)
    out["pulled"] = (s, rec)

    s = empty_slate("none_qualified", "No picks tonight. Nothing cleared the bar at Hard Rock's prices.",
                    "Checked 212 lines at 5:02 PM.")
    s["goal_watch"] = base_slate()["goal_watch"]
    s["status"]["lineups_at"] = None
    out["empty"] = (s, rec)

    s = empty_slate("no_games", "No NHL games today.")
    s["games"] = []
    s["fixture_now"], s["generated_at"] = t("10:05"), t("09:52")
    s["status"].update(prices_state="not_yet", prices_at=None, next_price_read_at=None, lineups_at=None, lines_checked=0)
    s["status"]["last_run"]["at"] = t("09:52")
    out["nogames"] = (s, rec)

    s = empty_slate("not_yet", "No prices read yet today. First read is due at 1:00 PM.")
    s["fixture_now"], s["generated_at"] = t("09:40"), t("09:32")
    s["status"].update(prices_state="not_yet", prices_at=None, next_price_read_at=t("13:00"), lineups_at=None, lines_checked=0)
    s["status"]["last_run"]["at"] = t("09:32")
    out["notyet"] = (s, rec)

    s = empty_slate("pool_empty", "No Hard Rock prices today, so no picks. The odds pulls ran out.")
    s["status"].update(prices_state="pool_empty", prices_at=None, next_price_read_at=None, lineups_at=None, lines_checked=0)
    s["status"]["pool"] = {"pulls_left": 0, "keys": 1, "game_days_left": 0, "days_left": 0, "low": True}
    out["poolempty"] = (s, rec)

    s = empty_slate("feed_down", "No Hard Rock prices today, so no picks. The odds feed did not answer.")
    s["status"].update(prices_state="feed_down", prices_at=None, lineups_at=None, lines_checked=0)
    out["feeddown"] = (s, rec)

    refused = "Hard Rock prices are off: the odds keys were refused. New keys are needed."
    s = empty_slate("keys_refused", "No Hard Rock prices today, so no picks.", refused)
    s["status"].update(prices_state="keys_refused", prices_at=None, next_price_read_at=None, lineups_at=None,
                       lines_checked=0)
    s["status"]["pool"] = {"pulls_left": None, "keys": 2, "game_days_left": None, "days_left": None, "low": False}
    s["banners"] = [{"level": "stop", "text": refused}]
    out["keysrefused"] = (s, rec)

    s = empty_slate("stats_behind", "Stats are behind, so no picks until they catch up.")
    s["status"].update(stats_state="behind", stats_through="2026-10-08")
    out["statsbehind"] = (s, rec)

    s = base_slate()
    for p in s["picks"]:
        p["state"] = "locked" if p["state"] in ("lineup", "locked") else "locked_unconfirmed"
        p["history"].append({"at": p["start"], "text": STATE_TEXT[p["state"]]})
    for par in s["parlays"]:
        par["state"] = "locked"
    s["goal_watch"] = []
    s["empty"] = {"code": "all_started", "text": "Every game has started. Tonight's picks are under Started.", "sub": None}
    s["fixture_now"], s["generated_at"] = t("22:40"), t("22:32")
    s["status"].update(lineups_at=t("21:40"), next_price_read_at=None)
    s["status"]["last_run"]["at"] = t("22:32")
    # BOS at BUF (5:00 PM) and FLA at TBL (7:10 PM) are final: those picks carry results
    find(s, "past")["graded"] = {"result": "W", "actual": "had 5", "units": 0.8}
    find(s, "thom")["graded"] = {"result": "L", "actual": "had 1", "units": -1.0}
    find(s, "rein")["graded"] = {"result": "W", "actual": "had 2", "units": 0.63}
    find(s, "kuch")["graded"] = {"result": "VOID", "actual": "did not play", "units": 0.0}
    gp = make_parlay(4, ["past", "rein"], s["picks"], "locked")
    gp["graded"] = {"result": "W", "actual": "2 of 2 legs hit", "units": round(dec(gp["price"]) - 1, 2)}
    s["parlays"].insert(0, gp)
    out["allstarted"] = (s, rec)

    # lineup source down: picks stay Early, page says so
    s = base_slate()
    for p in s["picks"]:
        if not p["state"].startswith("locked"):
            p["state"] = "early"
            p["history"] = p["history"][:1]
    for par in s["parlays"]:
        par["state"] = "early"
    s["status"].update(lineups_at=None, lineups_state="failed",
                       lineups_note="Lineups not checked: Daily Faceoff did not answer.")
    s["banners"] = [{"level": "warn", "text": "Lineups couldn't be checked, so picks stay Early."}]
    out["nolineups"] = (s, rec)

    s = base_slate()
    s["generated_at"] = t("15:10")
    s["status"].update(prices_at=t("13:02"), lineups_at=None, next_price_read_at=t("17:40"))
    s["status"]["last_run"]["at"] = t("15:10")
    for p in s["picks"]:
        p["price_at"] = t("13:02")
        p["state"] = "early"
        p["history"] = p["history"][:1]
    for par in s["parlays"]:
        par["price_at"], par["state"] = t("13:02"), "early"
    out["stale"] = (s, rec)

    s = base_slate()
    s["generated_at"] = t("23:42")
    s["fixture_now"] = "2026-10-12T09:15:00-04:00"
    s["status"]["last_run"]["at"] = t("23:42")
    out["expired"] = (s, rec)

    s = base_slate()
    keep = ("jhug", "matt", "demi", "ziba", "past", "thom")
    s["picks"] = [p for p in s["picks"] if p["id"].split(":")[-1] in keep]
    s["parlays"] = [make_parlay(1, ["jhug", "matt"], s["picks"], "lineup")]
    s["goal_watch"] = []
    s["banners"] = [{"level": "warn", "text": "Hard Rock prices limited: 3 of 7 games, shots only. Odds keys nearly out."}]
    s["status"].update(prices_state="limited", prices_at=t("13:02"), next_price_read_at=None, lines_checked=64)
    s["status"]["pool"] = {"pulls_left": 9, "keys": 1, "game_days_left": 1, "days_left": 1, "low": True}
    for p in s["picks"]:
        p["price_at"] = t("13:02")
    s["parlays"][0]["price_at"] = t("13:02")
    rerank(s)
    out["limited"] = (s, rec)

    s = base_slate()
    s["fixture_now"], s["generated_at"], s["status_at"] = t("16:10"), t("15:10"), t("16:02")
    s["banners"] = [{"level": "warn", "text": "Part of the last update failed at 4:02 PM (odds pull). Some of what is below may be older."}]
    s["status"].update(prices_at=t("13:02"), lineups_at=None, next_price_read_at=t("17:40"))
    s["status"]["last_run"] = {"ok": False, "at": t("16:02"), "failed_step": "odds pull"}
    for p in s["picks"]:
        p["price_at"] = t("13:02")
        p["history"] = p["history"][:1]
        p["state"] = "early"
    for par in s["parlays"]:
        par["price_at"], par["state"] = t("13:02"), "early"
    out["failed"] = (s, rec)

    s = base_slate()
    s["banners"] = [{"level": "warn", "text": "Odds pulls are running low: about 2 days left. Fewer price checks until more keys are added."}]
    s["status"]["pool"] = {"pulls_left": 38, "keys": 1, "game_days_left": 2, "days_left": 2, "low": True}
    out["lowpool"] = (s, rec)

    s = base_slate()
    s["picks"] = [p for p in s["picks"] if p["game_id"] != "g5"]
    s["parlays"] = [make_parlay(1, ["jhug", "matt"], s["picks"], "lineup")]
    s["banners"] = [{"level": "warn", "text": "Not covered tonight: DAL, COL (stats behind)."}]
    s["status"]["excluded_teams"] = [{"team": "DAL", "reason": "stats behind"}, {"team": "COL", "reason": "stats behind"}]
    s["status"].update(lineups_state="partial", lineups_note="12 of 14 team line pages are dated today.")
    rerank(s)
    for g in s["games"]:
        if g["id"] == "g5":
            g["excluded_reason"] = "stats behind"
    out["excluded"] = (s, rec)

    # layout stress: 22-character name, +1000 price, long bet, long reason, unknown state
    s = base_slate()
    m = find(s, "mack")
    m.update(player="J. Vanderbilt-Kowalski", price=1000, first_price=1000, worst_price=1000, breakeven=be(1000))
    r = find(s, "rein")
    r.update(player="A. Konstantinopoulos-Wright", bet="Over 12.5 power play shots on goal in regulation", state="warmups",
             first_price=-135, first_price_at=t("10:31"), _verb="to clear 12.5 power play shots",
             _tail="Projects 13.4 power play shots in 24 min. TBL allow 4% more shots than average.")
    s["goal_watch"][0]["player"] = "J. Vanderbilt-Kowalski"
    s["goal_watch"][0]["price"] = 1000
    s["goal_watch"][0]["fair_price"] = 1250
    out["long"] = (s, rec)
    return out


def write(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f, indent=1, ensure_ascii=False)
        f.write("\n")


def main():
    fx = build()
    older = older_files()
    for name, (slate, rec) in fx.items():
        d = os.path.join(HERE, name)
        if not slate.get("_finished"):
            finish(slate)
            slate["_finished"] = True
        write(os.path.join(d, "slate.json"), {k: v for k, v in slate.items() if k != "_finished"})
        write(os.path.join(d, "record.json"), rec)
        write(os.path.join(d, "rules.json"), RULES)
        for rel in rec.get("older", []):
            write(os.path.join(d, rel), older[rel])
    print("wrote %d fixtures: %s" % (len(fx), ", ".join(sorted(fx))))


if __name__ == "__main__":
    main()
