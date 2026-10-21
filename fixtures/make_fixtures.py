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


def rules_doc():
    """rules.json for the page: the live config's numbers, same as scripts/run.py writes them."""
    with open(os.path.join(os.path.dirname(HERE), "config", "rules.json")) as f:
        cfg = json.load(f)
    T = cfg["ops"]["gap_guard"]["thresholds"]
    public = {k: T.get(k) for k in ("lines", "price_gate", "max_price", "gap_ev", "books_min", "pin_ev_min", "pull_ev",
                                    "market_weight", "model_weight", "final_ev", "max_per_player", "max_per_game",
                                    "max_per_night")}
    public["live_from"] = cfg["ops"]["gap_guard"].get("live_from")
    public["safety_units"] = cfg["ops"]["safety_pause"]["units"]
    return {"fixture": True, "version": cfg["version"], "updated": cfg["updated"],
            "values": dict(cfg["values"], gap_guard=public), "ui": cfg["ui"]}


RULES = rules_doc()

GAMES = [
    ("g1", "BOS", "BUF", "17:00"), ("g2", "FLA", "TBL", "19:10"), ("g3", "NYR", "NJD", "19:10"),
    ("g4", "TOR", "MTL", "19:10"), ("g5", "COL", "DAL", "20:10"), ("g6", "EDM", "VAN", "22:10"),
    ("g7", "SEA", "SJS", "22:10"),
]
GAME = {g[0]: g for g in GAMES}

# (key, game, player, team, side, line, price, market fair (other books), books, model chance on the side, state,
#  thin, games_used, this_season). Gap = fair x Hard Rock payout - 1; our chance = 0.8 fair + 0.2 model.
PICKS = [
    ("mack", "g5", "N. MacKinnon", "COL", "over", 2.5, -145, 0.625, 6, 0.720, "lineup", False, 61, 4),
    ("maka", "g5", "C. Makar", "COL", "over", 1.5, -190, 0.682, 5, 0.740, "lineup", False, 60, 4),
    ("jhug", "g3", "J. Hughes", "NJD", "over", 2.5, -135, 0.600, 5, 0.660, "lineup", False, 44, 3),
    ("matt", "g4", "A. Matthews", "TOR", "over", 2.5, -120, 0.565, 7, 0.620, "early", False, 52, 4),
    ("rein", "g2", "S. Reinhart", "FLA", "over", 1.5, -170, 0.650, 6, 0.700, "early", False, 58, 3),
    ("kuch", "g2", "N. Kucherov", "TBL", "over", 2.5, 110, 0.500, 5, 0.550, "early", False, 59, 3),
    ("demi", "g4", "I. Demidov", "MTL", "over", 1.5, -130, 0.590, 4, 0.660, "early", True, 14, 4),
    ("ziba", "g3", "M. Zibanejad", "NYR", "under", 2.5, -110, 0.545, 5, 0.580, "early", False, 62, 3),
    ("qhug", "g6", "Q. Hughes", "VAN", "over", 2.5, 100, 0.520, 5, 0.560, "early", False, 57, 4),
    ("past", "g1", "D. Pastrnak", "BOS", "over", 2.5, -125, 0.580, 6, 0.640, "locked", False, 60, 4),
    ("thom", "g1", "T. Thompson", "BUF", "over", 1.5, -150, 0.640, 5, 0.690, "locked_unconfirmed", False, 54, 3),
]
# tonight's board: the night cap is 3, so the usual fixture shows three (two open, one locked); stress fixtures add more
BASE_KEYS = ("mack", "maka", "past")
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


def pick_numbers(price, fair, model):
    """gap %, our chance, break-even: the same arithmetic as the engine."""
    gap = fair * dec(price) - 1
    ours = 0.8 * fair + 0.2 * model
    return round(100 * gap, 1), round(ours, 4), be(price)


def reason_for(p):
    return "%d other books say %.1f%%; Hard Rock's %s only needs %.1f%%. Our model agrees (our blend: %.1f%%)." % (
        p["n_books"], p["market_fair_pct"], ("+%d" % p["price"]) if p["price"] > 0 else str(p["price"]),
        100 * p["breakeven"], 100 * p["p"])


def bet_text(side, line):
    return "%s %g shots on goal" % (side.capitalize(), line)


def make_pick(row, rank):
    key, gid, player, team, side, line, price, fair, nb, model, state, thin, gu, gs = row
    g = GAME[gid]
    home = g[2] == team
    gap, ours, b = pick_numbers(price, fair, model)
    level = "lineup" if state in ("lineup", "locked") else "early"
    hist = [{"at": t("17:31"), "text": STATE_TEXT["early"]}]
    if level == "lineup":
        hist.append({"at": t("18:35"), "text": STATE_TEXT["lineup"]})
    if state.startswith("locked"):
        hist.append({"at": t(g[3]), "text": STATE_TEXT[state]})
    p = {
        "id": "%s:%s:%s" % (D, gid, key), "rank": rank, "tier": "main", "game_id": gid,
        "player": player, "team": team, "opp": g[1] if home else g[2], "home": home, "start": t(g[3]),
        "market": "shots", "line": line, "side": side, "bet": bet_text(side, line),
        "price": price, "price_at": t("17:31"), "first_price": price, "first_price_at": t("17:31"),
        "worst_price": price, "prices": [{"at": t("17:31"), "price": price}],
        "p": ours, "breakeven": b, "p_pct": pct_floor(ours), "breakeven_pct": round(b * 100),
        "gap_pct": gap, "market_fair_pct": round(100 * fair, 1), "n_books": nb,
        "guard": {"verdict": "agrees", "ours_pct": round(100 * ours, 1), "model_pct": round(100 * model, 1)},
        "settled": level, "settled_label": "Lineup confirmed" if level == "lineup" else "Early",
        "reason": None, "graded": None,
        "state": state, "thin": thin, "games_used": gu, "games_this_season": gs,
        "history": hist, "pulled": None,
    }
    p["reason"] = reason_for(p)
    return p


def finish(slate):
    """Recompute every pick's derived numbers and reason, and mark started games."""
    for p in slate["picks"]:
        p["breakeven"] = be(p["price"])
        p["p_pct"], p["breakeven_pct"] = pct_floor(p["p"]), round(p["breakeven"] * 100)
        p["reason"] = reason_for(p)
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


def base_slate():
    rows = [r for r in PICKS if r[0] in BASE_KEYS]
    n = 0
    picks = []
    for r in rows:
        shut = r[10].startswith("locked")
        n += 0 if shut else 1
        picks.append(make_pick(r, None if shut else n))
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
        "parlays": [],
        "parlays_note": "Parlays are not offered: there is no evidence for them yet.",
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
    s["picks"] = []
    s["empty"] = {"code": code, "text": text, "sub": sub}
    for g in s["games"]:
        g["picks"] = 0
    return s


# ---------------- record ----------------
POOL = [
    ("N. MacKinnon", "Over 2.5 shots on goal", "shots"), ("S. Reinhart", "Over 1.5 shots on goal", "shots"),
    ("J. Hughes", "Over 2.5 shots on goal", "shots"), ("A. Matthews", "Over 2.5 shots on goal", "shots"),
    ("C. Makar", "Over 1.5 shots on goal", "shots"), ("N. Kucherov", "Over 2.5 shots on goal", "shots"),
    ("M. Zibanejad", "Under 2.5 shots on goal", "shots"), ("D. Pastrnak", "Over 2.5 shots on goal", "shots"),
    ("K. Kaprizov", "Over 2.5 shots on goal", "shots"), ("J. Eichel", "Over 1.5 shots on goal", "shots"),
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


def night(rng, date, pattern, graded=True, with_pulled=False):
    ents = [single(rng, date, i, r) for i, r in enumerate(pattern)]
    out = list(ents)
    if with_pulled:
        out.append(single(rng, date, 20, "L" if graded else None,
                          {"at": "%sT18:41:00-04:00" % date, "reason": "Scratched from the lineup"}))
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
            row("shots", "Shots on goal", 41, 22, 6.3, 0.61, push=2, void=1),
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
                row("shots", "Shots on goal", 13, 8, 1.9, 0.6, push=1),
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

    # Hard Rock moved the price on one pick and the gap fell under 1.5%: pulled, stays on the page and the Record
    s = base_slate()
    m = find(s, "mack")
    m["pulled"] = {"at": t("17:50"), "reason": "Hard Rock moved it to -160",
                   "if_bet": "Got %s? Still a good bet. Don't bet it at -160." % (("+%d" % m["price"]) if m["price"] > 0 else str(m["price"]))}
    m["history"].append({"at": t("17:50"), "text": "Pulled: Hard Rock moved it to -160"})
    rerank(s)
    out["moved"] = (s, rec)

    # 2026-10-21: the 45-minute read is done for the first game's picks: "Price final"
    s = base_slate()
    for p in s["picks"]:
        if not p["pulled"] and not p["state"].startswith("locked"):
            p["price_final"] = True
            break
    out["final"] = (s, rec)

    s = base_slate()
    find(s, "maka")["pulled"] = {"at": t("18:41"), "reason": "Scratched from the lineup",
                                 "if_bet": "Already bet? It should void and refund (no ice time)."}
    find(s, "maka")["history"].append({"at": t("18:41"), "text": "Pulled: Scratched from the lineup"})
    rerank(s)
    out["pulled"] = (s, rec)

    s = empty_slate("none_qualified", "No picks yet today. 212 lines read, none cleared both checks.",
                    "Next price read at 7:25 PM.")
    s["status"]["lineups_at"] = None
    out["empty"] = (s, rec)

    s = empty_slate("no_games", "No NHL games today.")
    s["games"] = []
    s["fixture_now"], s["generated_at"] = t("10:05"), t("09:52")
    s["status"].update(prices_state="not_yet", prices_at=None, next_price_read_at=None, lineups_at=None, lines_checked=0)
    s["status"]["last_run"]["at"] = t("09:52")
    out["nogames"] = (s, rec)

    s = empty_slate("not_yet", "No picks yet today. The first look at the other books is about 90 minutes before the first puck.")
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

    # every game has started: picks are locked, early games are final and graded
    s = base_slate()
    for p in s["picks"]:
        p["state"] = "locked" if p["state"] in ("lineup", "locked") else "locked_unconfirmed"
        p["rank"] = None
        if not any(h["text"] == STATE_TEXT[p["state"]] for h in p["history"]):
            p["history"].append({"at": p["start"], "text": STATE_TEXT[p["state"]]})
    s["empty"] = {"code": "all_started", "text": "Every game has started. Tonight's picks are under Started.", "sub": None}
    s["fixture_now"], s["generated_at"] = t("22:40"), t("22:32")
    s["status"].update(lineups_at=t("21:40"), next_price_read_at=None)
    s["status"]["last_run"]["at"] = t("22:32")
    find(s, "past")["graded"] = {"result": "W", "actual": "had 5", "units": 0.8}
    find(s, "mack")["graded"] = {"result": "L", "actual": "had 1", "units": -1.0}
    find(s, "maka")["graded"] = {"result": "VOID", "actual": "did not play", "units": 0.0}
    out["allstarted"] = (s, rec)

    # lineup source down: picks stay Early, page says so
    s = base_slate()
    for p in s["picks"]:
        if not p["state"].startswith("locked"):
            p["state"], p["settled"], p["settled_label"] = "early", "early", "Early"
            p["history"] = p["history"][:1]
    s["status"].update(lineups_at=None, lineups_state="failed",
                       lineups_note="Lineups not checked: Daily Faceoff did not answer.")
    s["banners"] = [{"level": "warn", "text": "Lineups couldn't be checked, so picks stay Early."}]
    out["nolineups"] = (s, rec)

    s = base_slate()
    s["generated_at"] = t("15:10")
    s["status"].update(prices_at=t("13:02"), lineups_at=None, next_price_read_at=t("17:40"))
    s["status"]["last_run"]["at"] = t("15:10")
    out["stale"] = (s, rec)

    s = base_slate()
    s["generated_at"] = t("23:42")
    s["fixture_now"] = "2026-10-12T09:15:00-04:00"
    s["status"]["last_run"]["at"] = t("23:42")
    out["expired"] = (s, rec)

    s = base_slate()
    s["banners"] = [{"level": "warn", "text": "Hard Rock prices limited: 3 of 7 games, shots only. Odds keys nearly out."}]
    s["status"].update(prices_state="limited", prices_at=t("17:31"), next_price_read_at=None, lines_checked=64)
    s["status"]["pool"] = {"pulls_left": 9, "keys": 1, "game_days_left": 1, "days_left": 1, "low": True}
    out["limited"] = (s, rec)

    s = base_slate()
    s["fixture_now"], s["generated_at"], s["status_at"] = t("18:10"), t("17:40"), t("18:02")
    s["banners"] = [{"level": "warn", "text": "Part of the last update failed at 6:02 PM (odds pull). Some of what is below may be older."}]
    s["status"].update(next_price_read_at=t("18:16"))
    s["status"]["last_run"] = {"ok": False, "at": t("18:02"), "failed_step": "odds pull"}
    out["failed"] = (s, rec)

    s = base_slate()
    s["banners"] = [{"level": "warn", "text": "Odds pulls are running low: about 2 days left. Fewer price checks until more keys are added."}]
    s["status"]["pool"] = {"pulls_left": 38, "keys": 1, "game_days_left": 2, "days_left": 2, "low": True}
    out["lowpool"] = (s, rec)

    s = base_slate()
    s["picks"] = [p for p in s["picks"] if p["game_id"] != "g5"]
    s["banners"] = [{"level": "warn", "text": "Not covered tonight: DAL, COL (stats behind)."}]
    s["status"]["excluded_teams"] = [{"team": "DAL", "reason": "stats behind"}, {"team": "COL", "reason": "stats behind"}]
    s["status"].update(lineups_state="partial", lineups_note="12 of 14 team line pages are dated today.")
    rerank(s)
    for g in s["games"]:
        if g["id"] == "g5":
            g["excluded_reason"] = "stats behind"
    out["excluded"] = (s, rec)

    # layout stress: 22-character name, +1000 price, a long reason, a state the page does not know, many picks
    s = base_slate()
    for i, r in enumerate(PICKS):
        if r[0] not in BASE_KEYS:
            s["picks"].append(make_pick(r, None))
    m = find(s, "mack")
    m.update(player="J. Vanderbilt-Kowalski", price=1000, first_price=1000, worst_price=1000, breakeven=be(1000),
             market_fair_pct=9.9, gap_pct=8.9, n_books=12)
    r = find(s, "rein")
    r.update(player="A. Konstantinopoulos-Wright", state="warmups", first_price=-135, first_price_at=t("10:31"))
    rerank(s)
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
