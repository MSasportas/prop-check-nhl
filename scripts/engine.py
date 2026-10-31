"""engine.py: turns the Gap + Guard flags into the page's picks and the Record, and keeps them honest.

THERE IS ONE RULE SET: Gap + Guard (config ops.gap_guard, TEAM.md section 4). paper.py decides what qualifies (step 1 the gap
against the other books, step 2 the model guard); this file never re-does that maths. It only
  - shows a pick for every flag (price FROZEN at the flag's read; this is the price shown and graded),
  - pulls a shown pick when the Gap + Guard log pulls its flag or Daily Faceoff lists the player out,
  - locks a pick at puck drop,
  - builds slate.json for the page.
A pick that has been shown is never silently removed: it stays, is pulled with a reason, or locks at puck drop. What was
shown is rebuilt from the Record's event log, so the page and the Record cannot disagree. Nothing is ever shown for a slate
before ops.gap_guard.live_from (2026-10-20). Parlays are not offered.
"""
import math
from datetime import datetime, timedelta

import common
import goalies
import lineups
import model
import names
import odds
import paper
import record
import sched

EPS = 1e-9
STATE_LABEL = {"early": "Early: lineup not confirmed", "lineup": "Lineup confirmed", "locked": "Locked",
               "locked_unconfirmed": "Locked: lineup was not confirmed"}
SETTLED = {"Early": "early", "Lineup confirmed": "lineup", "Goalie confirmed": "goalie"}
# the Gap + Guard log's pull reasons in plain words, with a short code for the Record
PULL_TEXT = {
    "out": ("out", "Scratched from the lineup"),
    "out per daily faceoff": ("out", "Scratched from the lineup"),
    "price moved, gap gone": ("gap_gone", "Hard Rock moved the price and the gap is gone"),
    "line removed": ("line_gone", "Hard Rock took this line down"),
    "pinnacle gone": ("pinnacle_gone", "Pinnacle stopped quoting this line"),
    "pinnacle disagrees": ("pinnacle_flip", "Pinnacle no longer agrees with the price"),
    "model guard fails": ("guard_fails", "The edge fell under our bar"),
}
# what to do if you already bet it (Hard Rock bets cannot be taken back)
OUT_IF_BET = "Already bet? It should void and refund (no ice time)."


def advice(code, pull, shown_price, bar):
    """(what happened, what it means if you already bet at the shown price). pull = the Gap + Guard log's pull event,
    which carries Hard Rock's price now and the final EV at the SHOWN price on that read (paper.at_your_price)."""
    fp = common.fmt_price
    now, yev = pull.get("now_price"), pull.get("yours_ev")
    moved = now is not None and shown_price is not None and now != shown_price
    if code == "line_gone":
        return "Hard Rock took the line down", "Got %s? Your bet still stands." % fp(shown_price)
    if code in ("books_low", "pinnacle_gone"):
        what = "Too few other books to check it against" if code == "books_low" else "Pinnacle stopped quoting it"
        return what, "Got %s? Nothing says it got worse. Haven't bet? Skip it." % fp(shown_price)
    if moved:
        what = "Hard Rock moved it to %s" % fp(now)
    elif code == "pinnacle_flip":
        what = "Pinnacle moved against it"
    else:
        what = "The other books moved against it"
    if code == "pinnacle_flip" and pull.get("yours_pin_ev") is not None and pull["yours_pin_ev"] < -EPS:
        return what, "Pinnacle, the sharpest book, leans against it even at %s. Haven't bet? Skip it." % fp(shown_price)
    if yev is None:
        return what, None
    if yev >= bar - EPS:
        tail = (" Don't bet it at %s." % fp(now)) if moved else ""
        return what, "Got %s? Still a good bet.%s" % (fp(shown_price), tail)
    if yev >= -EPS:
        return what, "Got %s? Still a small plus. Too thin to bet now." % fp(shown_price)
    return what, "Edge is gone even at %s. Haven't bet? Skip it." % fp(shown_price)


class ConfigError(Exception):
    pass


def check_config(cfg):
    g = common.gap_guard(cfg)
    T = g.get("thresholds") or {}
    need = ("lines", "price_gate", "max_price", "gap_ev", "books_min", "pin_ev_min", "pull_ev", "market_weight", "model_weight",
            "offsets", "final_ev", "flag_pulls", "close_min", "move_min", "max_per_player", "max_per_game", "max_per_night",
            "min_history")
    miss = [k for k in need if k not in T]
    if miss:
        raise ConfigError("ops.gap_guard.thresholds is missing: %s" % ", ".join(miss))
    if abs(T["market_weight"] + T["model_weight"] - 1.0) > 1e-9:
        raise ConfigError("market_weight + model_weight must equal 1")
    if T["price_gate"] >= 0 or T["max_price"] < 100:
        raise ConfigError("price_gate must be negative and max_price +100 or longer")
    for line in T["lines"]:
        if ("%g" % line) not in (T["offsets"] or {}):
            raise ConfigError("no frozen offset for the %g line" % line)
    if not g.get("live_from"):
        raise ConfigError("ops.gap_guard.live_from is missing")
    sp = (cfg.get("ops") or {}).get("safety_pause") or {}
    if not isinstance(sp.get("units"), (int, float)) or sp["units"] >= 0:
        raise ConfigError("ops.safety_pause.units must be a negative number")


# ---------------------------------------------------------------- wording
def fmt_line(line):
    return "%g" % line


def bet_text(side, line, market, cfg):
    return "%s %s %s" % ("Over" if side == "over" else "Under", fmt_line(line), cfg["ops"]["markets"][market]["noun"])


def pct_floor(x):
    return int(math.floor(x * 100 + 1e-7))


def pct_round(x):
    return int(math.floor(x * 100 + 0.5))


def pick_id(slate, game_id, pid, market, line, side):
    return "%s:%s:%s:%s:%s:%s" % (slate, game_id, pid, market, fmt_line(line), side)


def reason_text(fl):
    """One or two short sentences: what the other books say against Hard Rock's price, and what our model says."""
    need = odds.break_even(fl["price"])
    s = "%d other books say %.1f%%; Hard Rock's %s only needs %.1f%%." % (
        fl["n_books"], 100 * fl["market_fair"], common.fmt_price(fl["price"]), 100 * need)
    s += " Our model agrees (our blend: %.1f%%)." % (100 * fl["final"])
    return s


# ---------------------------------------------------------------- model inputs for one player
class Inputs:
    """Everything the engine and the Gap + Guard step read. Built by run.py; tests build it by hand."""

    def __init__(self, cfg, now, slate, season, games, store, behind, view, lineup_state, people,
                 events, plan=None, odds_day=None, facts=None):
        self.cfg, self.v, self.now, self.slate, self.season = cfg, cfg["values"], now, slate, season
        self.games = {g["id"]: g for g in games}
        self.store, self.behind, self.view, self.lineup_state = store, behind or {}, view or {}, lineup_state or {}
        self.people = people or {}                          # pid -> dict(first, last, team, pos)
        self.events, self.plan, self.odds_day = events, plan, odds_day or {}
        self.facts = facts or {}                            # status facts gathered by run.py
        self._lg = None
        self._tf = {}
        self._pv = {}

    def league(self):
        if self._lg is None:
            n = sf = ga = 0
            for rows in self.store.teams.values():
                for r in rows:
                    if r["date"] < self.slate and r["season"] >= self.season - 10001:
                        n += 1; sf += r["sf"]; ga += r["ga"]
            self._lg = (sf / n if n else 28.0, ga / n if n else 3.0)
        return self._lg

    def opp_factor(self, opp, market):
        key, K = model.SK[market]["opp"], model.SK[market]["oppK"]
        if (opp, key, K) not in self._tf:
            lg = self.league()[0] if key == "sa" else self.league()[1]
            rows = [r for r in self.store.teams.get(opp, []) if r["date"] < self.slate]
            self._tf[(opp, key, K)] = model.team_factor(rows, key, lg, K)
        return self._tf[(opp, key, K)]

    def player(self, pid, team):
        """History facts for one player on tonight's team (cached)."""
        if (pid, team) in self._pv:
            return self._pv[(pid, team)]
        v = self.v
        rows = [r for r in self.store.skaters.get(pid, [])
                if r["date"] < self.slate and r["season"] >= self.season - 10001]
        n_team = 0
        for r in reversed(rows):
            if r["team"] != team:
                break
            n_team += 1
        team_games = [r["gid"] for r in self.store.teams.get(team, [])
                      if r["season"] == self.season and r["date"] < self.slate]
        played = {r["gid"] for r in rows}
        flags = [g in played for g in team_games]
        miss = 0
        while miss < len(flags) and not flags[-1 - miss]:
            miss += 1
        back = 0                                            # games played since the last absence
        while miss == 0 and back < len(flags) and flags[-1 - back]:
            back += 1
        gap_before = 0
        while miss == 0 and back + gap_before < len(flags) and not flags[-1 - back - gap_before]:
            gap_before += 1
        sitting = miss >= v["absence_games"] or (gap_before >= v["absence_games"] and back < v["absence_sitout"])
        recent = [r["toi"] for r in reversed(rows)][:10]
        toi_drop = len(recent) >= 3 and (sum(recent) / len(recent)) - (sum(recent[:2]) / 2.0) >= v["toi_drop_sec"]
        pp = self.people.get(pid) or {}
        pos = pp.get("pos") or (self.store.players.get(pid) or {}).get("pos")
        out = {"rows": rows, "n": len(rows), "n_season": sum(1 for r in rows if r["season"] == self.season),
               "n_team": n_team, "missed_last": miss >= 1, "sitting": sitting, "toi_drop": toi_drop, "pos": pos,
               "thin": len(rows) < v["thin_rows"] or n_team < v["thin_team_games"]}
        self._pv[(pid, team)] = out
        return out

    def model(self, pid, team, opp, home, market, line):
        """dict(p_over, mu, etoi, opp_f) or None when the model cannot run for this player."""
        pv = self.player(pid, team)
        if pv["pos"] not in ("F", "D"):
            return None
        ctx = {"home": home, "opp_sa_f": self.opp_factor(opp, "shots"), "opp_ga_f": self.opp_factor(opp, "points"),
               "games_with_team": pv["n_team"]}
        pr = model.skater_prob(pv["rows"], pv["pos"], self.season, market, line, ctx)
        det = model.skater_detail(pv["rows"], pv["pos"], self.season, market, ctx)
        return {"p_over": pr["p"], "mu": det["mu"], "etoi": det["etoi"], "opp_f": det["opp_f"]}

    def display_name(self, pid, feed_name):
        pp = self.people.get(pid)
        if pp:
            return names.display(pp["first"], pp["last"])
        parts = (feed_name or "").split()
        return names.display(parts[0], " ".join(parts[1:])) if len(parts) > 1 else (feed_name or str(pid))

    def confirmed(self, team, pid):
        return lineups.player_status(self.lineup_state, team, pid)


# ---------------------------------------------------------------- the safety pause
def safety_pause(events, cfg):
    """The automatic safeguard: when the Record's graded singles are down `ops.safety_pause.units` or more, no NEW picks are
    added (shown picks are still looked after). Returns {"text", "sub"} or None."""
    sp = (cfg.get("ops") or {}).get("safety_pause") or {}
    if not sp:
        return None
    rec, _ = record.build_views(events, cfg)
    u = rec["summary"]["headline"].get("units")
    if u is not None and u <= sp["units"] + EPS:
        return {"text": sp.get("text") or "New picks are stopped.", "sub": sp.get("sub")}
    return None


# ---------------------------------------------------------------- one run of the engine
def settled_of(inp, team, opp, pid, goalie_state=None):
    """Early | Lineup confirmed | Goalie confirmed, from lineups.json and goalies.json."""
    gs = goalie_state if goalie_state is not None else goalies.load(inp.slate)
    return paper.settled_level(inp.lineup_state, gs, team, opp, pid)


def evaluate(inp, gg_events=(), block_new=False):
    """Returns (new_events, state) where state holds what build_slate() needs. Does not write anything.
    gg_events: the Gap + Guard log (paper.read_events()). block_new: add no new picks this run (stats behind or the safety
    pause); picks already shown are still looked after."""
    now = inp.now
    at = common.iso(now)
    items = record.fold(inp.events)
    today = {i: it for i, it in items.items() if it["slate"] == inp.slate}
    singles = {i: it for i, it in today.items() if it["kind"] == "single"}
    gg = paper.fold(list(gg_events))
    new, live = [], {}                                      # live: id -> current numbers for open singles

    # ---- 1. picks already shown: lock, pull, or carry on (the price never changes: it is frozen at the flag)
    for i, it in singles.items():
        if not record.is_open(it):
            continue
        sh = it["shown"]
        g = inp.games.get(sh["game_id"])
        if g is None or sched.started(g, now):
            st = "locked" if it["state"] == "lineup" else "locked_unconfirmed"
            new.append({"t": "locked", "id": i, "at": at, "state": st})
            continue
        status = inp.confirmed(sh["team"], sh["player_id"])
        if status == "out":
            code, text = PULL_TEXT["out"]
            new.append({"t": "pulled", "id": i, "at": at, "code": code, "reason": text, "if_bet": OUT_IF_BET})
            continue
        pull = (gg.get(sh.get("gg_id")) or {}).get("pull")
        if pull:
            new.append(_pulled_event(i, at, pull, sh.get("price"), inp.cfg))
            continue
        state = "lineup" if status == "in" else "early"
        if state != it["state"]:
            new.append({"t": "state", "id": i, "at": at, "state": state})
        live[i] = {"final_ev": sh.get("final_ev") or 0.0, "price": record.last_price(it), "game_id": sh["game_id"],
                   "pid": sh["player_id"], "final": _is_final(gg.get(sh.get("gg_id")), sh.get("start"), inp.cfg)}

    # ---- 2. new picks: every Gap + Guard flag of tonight not shown yet (paper.py already applied the caps)
    fresh = []
    if not block_new and common.gap_guard_active(inp.cfg, inp.slate):
        flags = [it["flag"] for it in gg.values() if it.get("flag") and it["flag"].get("slate") == inp.slate]
        for fl in sorted(flags, key=lambda f: (f["read_at"], -f["final_ev"], f["id"])):
            rid = pick_id(inp.slate, fl["game_id"], fl["pid"], fl["market"], fl["line"], fl["side"])
            g = inp.games.get(fl["game_id"])
            if rid in singles or g is None or sched.started(g, now):
                continue
            fresh.append((rid, fl, g))
            if not (gg.get(fl["id"]) or {}).get("pull"):
                live[rid] = {"final_ev": round(fl["final_ev"], 4), "price": fl["price"], "game_id": fl["game_id"], "pid": fl["pid"],
                             "final": _is_final(gg.get(fl["id"]), g["start"], inp.cfg)}
    order = sorted(live, key=lambda i: (-round(live[i]["final_ev"], 4), i))
    ranks = {i: n + 1 for n, i in enumerate(order)}
    for rid, fl, g in fresh:
        pv = inp.player(fl["pid"], fl["team"])
        status = inp.confirmed(fl["team"], fl["pid"])
        raw_side = fl["model_raw_over"] if fl["side"] == "over" else 1.0 - fl["model_raw_over"]
        be = odds.break_even(fl["price"])
        body = {
            "id": rid, "gg_id": fl["id"], "rank": ranks.get(rid), "tier": "main", "game_id": fl["game_id"],
            "player": fl["player"], "player_id": fl["pid"], "team": fl["team"], "opp": fl["opp"], "home": fl["home"],
            "start": g["start"], "market": fl["market"], "line": fl["line"], "side": fl["side"],
            "bet": bet_text(fl["side"], fl["line"], fl["market"], inp.cfg),
            "price": fl["price"], "price_at": fl["read_at"], "read_pull": fl["read_pull"],
            "p": round(fl["final"], 4), "breakeven": round(be, 4), "fair": round(fl["market_fair"], 4),
            "p_pct": pct_floor(fl["final"]), "breakeven_pct": pct_round(be),
            "gap_ev": round(fl["gap_ev"], 4), "gap_pct": round(100 * fl["gap_ev"], 1),
            "market_fair_pct": round(100 * fl["market_fair"], 1), "n_books": fl["n_books"],
            "final_ev": round(fl["final_ev"], 4), "final_ev_pct": round(100 * fl["final_ev"], 1),
            "guard": "agrees", "model": round(raw_side, 4), "model_side_cal": round(fl["model_side"], 4),
            "reason": reason_text(fl), "link": fl.get("link"),
            "state": "lineup" if status == "in" else "early", "thin": pv["thin"],
            "games_used": pv["n"], "games_this_season": pv["n_season"],
        }
        new.append({"t": "shown", "kind": "single", "id": rid, "at": at, "slate": inp.slate, "pick": body})
        pull = (gg.get(fl["id"]) or {}).get("pull")
        if pull:                                            # flagged and pulled before this run saw it: stays, marked pulled
            new.append(_pulled_event(rid, at, pull, fl["price"], inp.cfg))
    return new, {"ranks": ranks, "live": live}


def _is_final(gg_item, start, cfg):
    """The last price check is done: the Gap + Guard close came from a read taken at or inside the 45-minute mark. A 90-minute
    read that slipped to 45-46 minutes counts as the close in the research log but the 45-minute read still runs after it, so
    it does not make a pick final (no chip rather than a false one)."""
    c = (gg_item or {}).get("close")
    if not c or (gg_item or {}).get("pull") or not c.get("read_at") or not start:
        return False
    mins = (common.parse_iso(start) - common.parse_iso(c["read_at"])).total_seconds() / 60.0
    return mins <= (common.gap_guard(cfg).get("thresholds") or {}).get("close_min", 45) + EPS


def _pulled_event(i, at, pull, shown_price, cfg):
    code, text = _pull_words(pull)
    if code == "out":
        return {"t": "pulled", "id": i, "at": at, "code": code, "reason": text, "if_bet": OUT_IF_BET}
    bar = (common.gap_guard(cfg).get("thresholds") or {}).get("final_ev", 0.02)
    if "yours_ev" not in pull and "now_price" not in pull:
        return {"t": "pulled", "id": i, "at": at, "code": code, "reason": text}     # an older pull event: no advice
    what, if_bet = advice(code, pull, shown_price, bar)
    e = {"t": "pulled", "id": i, "at": at, "code": code, "reason": what}
    if if_bet:
        e["if_bet"] = if_bet
    return e


def _pull_words(pull):
    key = str(pull.get("reason") or "")
    if key.startswith("fewer than"):
        return "books_low", "Other books stopped quoting this line"
    return PULL_TEXT.get(key.lower()) or ("pulled", key[:1].upper() + key[1:])


# ---------------------------------------------------------------- slate.json
def build_slate(inp, events, extra):
    """The page's file. Built only from the Record log and the same facts status.json gets."""
    now, cfg = inp.now, inp.cfg
    items = record.fold(events)
    today = {i: it for i, it in items.items() if it["slate"] == inp.slate}
    ranks, live = extra["ranks"], extra["live"]
    goalie_state = goalies.load(inp.slate)
    picks = []
    for i, it in today.items():
        if it["kind"] != "single":
            continue                                        # parlays are not offered (an old shape is never shown)
        sh = it["shown"]
        # history = how settled the pick was, and when (the page prints it as is)
        hist = [{"at": s["at"], "text": STATE_LABEL.get(s["state"], s["state"])} for s in it["states"]]
        if it["pulled"]:
            hist.append({"at": it["pulled"]["at"], "text": "Pulled: %s" % it["pulled"]["reason"]})
        hist.sort(key=lambda h: h["at"])
        g = it["graded"]
        settled = settled_of(inp, sh["team"], sh["opp"], sh["player_id"], goalie_state)
        picks.append({
            "id": i, "price": record.last_price(it), "first_price": record.first_price(it),
            "first_price_at": it["prices"][0]["at"], "worst_price": record.worst_price(it),
            "p": it["p"], "breakeven": it["breakeven"],
            "p_pct": it["p_pct"] if it.get("p_pct") is not None else pct_floor(it["p"]),
            "breakeven_pct": it["breakeven_pct"] if it.get("breakeven_pct") is not None else pct_round(it["breakeven"]),
            "state": it["state"], "history": hist,
            "prices": [{"at": p["at"], "price": p["price"]} for p in it["prices"]],
            "pulled": {"at": it["pulled"]["at"], "reason": it["pulled"]["reason"], "if_bet": it["pulled"].get("if_bet")}
            if it["pulled"] else None,
            # the last price read (45 min before puck) is done: from here only a scratch can pull it
            "price_final": bool((live.get(i) or {}).get("final")) if record.is_open(it) else False,
            "graded": {"result": g["result"], "actual": g["actual_text"], "units": g["units"]} if g else None,
            "rank": ranks.get(i) if record.is_open(it) else None, "tier": "main", "game_id": sh["game_id"],
            "player": sh["player"], "player_id": sh["player_id"], "team": sh["team"], "opp": sh["opp"],
            "home": sh["home"], "start": sh["start"], "market": sh["market"], "line": sh["line"],
            "side": sh["side"], "bet": sh["bet"], "price_at": it["prices"][-1]["at"],
            "gap_pct": sh.get("gap_pct"), "market_fair_pct": sh.get("market_fair_pct"), "n_books": sh.get("n_books"),
            "guard": {"verdict": sh.get("guard", "agrees"), "ours_pct": round(100 * it["p"], 1) if it["p"] is not None else None,
                      "model_pct": round(100 * sh["model"], 1) if sh.get("model") is not None else None},
            "settled": SETTLED.get(settled, "early"), "settled_label": settled,
            "reason": it["reason"], "link": sh.get("link"), "thin": sh.get("thin"), "games_used": sh.get("games_used"),
            "games_this_season": sh.get("games_this_season")})
    order = {"open": 0, "pulled": 1, "locked": 2}
    bucket = lambda p: "pulled" if p["pulled"] else ("open" if p["state"] in ("early", "lineup") and not p["graded"] else "locked")
    picks.sort(key=lambda p: (order[bucket(p)], p["rank"] or 999, p["start"], p["id"]))
    open_picks = [p for p in picks if bucket(p) == "open"]

    games = []
    for g in sorted(inp.games.values(), key=lambda x: (x["start"], x["id"])):
        ex = [t for t in (g["away"], g["home"]) if t in inp.behind]
        lx, gx = {}, {}
        for side in ("away", "home"):
            rec = (inp.lineup_state.get("teams") or {}).get(g[side]) or {}
            pg = rec.get("page")
            lx[side] = "confirmed" if pg and pg.get("today") else ("waiting" if rec.get("checked_at") else "not_checked")
            gx[side] = (goalie_state.get("teams") or {}).get(g[side])
        games.append({"id": g["id"], "away": g["away"], "home": g["home"], "start": g["start"],
                      "lineups": lx, "goalies": gx,
                      "started": sched.started(g, now),
                      "picks": sum(1 for p in picks if p["game_id"] == g["id"] and not p["pulled"]),
                      "excluded_reason": inp.behind[ex[0]] if ex else None, "excluded_teams": ex})

    f = inp.facts
    reads = f.get("flag_reads") or {"games": 0, "lines": 0}
    status = {
        "prices_state": f.get("prices_state", "not_yet"), "prices_at": f.get("prices_at"),
        "next_price_read_at": f.get("next_price_read_at"), "stats_built_at": f.get("stats_built_at"),
        "stats_through": f.get("stats_through"), "lineups_at": f.get("lineups_at"), "goalies_at": None,
        "lineups_note": f.get("lineups_note"), "lineups_state": f.get("lineups_state", "not_yet"),
        "stats_state": f.get("stats_state", "ok"),
        "last_run": f.get("last_run", {"ok": True, "at": common.iso(now), "failed_step": None}),
        "pool": f.get("pool", {"pulls_left": None, "keys": 0, "game_days_left": None, "low": False}),
        "excluded_teams": [{"team": t, "reason": inp.behind[t]} for t in sorted(
            {t for g in inp.games.values() for t in (g["away"], g["home"]) if t in inp.behind})],
        "lines_checked": reads["lines"], "flag_reads": reads["games"],
        "tier": (inp.plan or {}).get("tier"),
    }
    banners = list(f.get("banners", []))
    if status["excluded_teams"]:
        by = {}
        for x in status["excluded_teams"]:
            by.setdefault(x["reason"], []).append(x["team"])
        for why, ts in sorted(by.items()):
            banners.append({"level": "warn", "text": "Not covered tonight: %s (%s)." % (", ".join(ts), why)})
    sp = f.get("safety_pause")
    if sp:
        banners.append({"level": "warn", "text": sp["text"]})

    empty = None
    if not open_picks:
        empty = _empty(inp, status, picks, games, extra)
    tomorrow5 = (common.parse_iso(inp.slate + "T00:00:00").replace(tzinfo=common.ET) + timedelta(days=1)).replace(
        hour=cfg["ops"]["rollover_hour"])
    return {"slate_date": inp.slate, "generated_at": common.iso(now), "status_at": common.iso(now),
            "valid_until": common.iso(tomorrow5),
            "status": status, "banners": banners, "empty": empty, "games": games, "picks": picks,
            "parlays": [], "parlays_note": "Parlays are not offered: there is no evidence for them yet."}


def _fmt_day(iso_date):
    try:
        d = datetime.strptime(iso_date, "%Y-%m-%d")
        return "%s %d" % (d.strftime("%b"), d.day)
    except (TypeError, ValueError):
        return str(iso_date)


def _empty(inp, status, picks, games, extra):
    f = inp.facts
    if not games:
        if f.get("other_games"):
            return {"code": "no_games", "text": "No picks today.", "sub": "Only regular-season games are covered."}
        return {"code": "no_games", "text": "No NHL games today.", "sub": None}
    cfg = getattr(inp, "cfg", None) or {}
    if not common.gap_guard_active(cfg, inp.slate):
        return {"code": "not_live", "text": "No picks today.",
                "sub": "Picks start %s. Nothing is shown before then." % _fmt_day(common.gap_guard(cfg).get("live_from"))}
    sp = f.get("safety_pause")
    if sp:
        return {"code": "safety_pause", "text": sp["text"], "sub": sp.get("sub")}
    if f.get("stats_missing") or status["stats_state"] == "behind":
        return {"code": "stats_behind", "text": "Stats are behind, so no picks until they catch up.", "sub": None}
    if all(g["started"] for g in games):
        shown = [p for p in picks if not p["pulled"]]
        if shown:
            return {"code": "all_started", "text": "Every game has started.",
                    "sub": "Tonight's picks are under Started."}
        if picks:
            n = len(picks)
            return {"code": "all_started", "text": "Every game has started.",
                    "sub": ("Tonight's pick was pulled; see Pulled today." if n == 1
                            else "Tonight's %d picks were pulled; see Pulled today." % n)}
        parts = ["No picks were posted tonight."]
        reads = f.get("flag_reads") or {"games": 0, "lines": 0}
        if reads["games"]:
            n, k = reads["lines"], reads["games"]
            parts.append("%d line%s read across %d game%s, none cleared both checks."
                         % (n, "" if n == 1 else "s", k, "" if k == 1 else "s"))
            if f.get("gg_vetoes"):
                v = f["gg_vetoes"]
                parts.append("%d had a gap but our model said no." % v if v != 1 else "1 had a gap but our model said no.")
        return {"code": "all_started", "text": "Every game has started.", "sub": " ".join(parts)}
    ps = status["prices_state"]
    if ps == "keys_refused":
        text = "No picks yet today" if status["prices_at"] else "No Hard Rock prices today, so no picks."
        return {"code": "keys_refused", "text": text, "sub": odds.KEYS_REFUSED_TEXT}
    if ps == "pool_empty":
        return {"code": "pool_empty", "text": "No Hard Rock prices today, so no picks.", "sub": "The odds pulls ran out."}
    if ps == "feed_down":
        return {"code": "feed_down", "text": "No Hard Rock prices today, so no picks.",
                "sub": "The odds feed did not answer."}
    if ps == "not_yet":
        return {"code": "not_yet", "text": "No picks yet today", "sub": f.get("not_yet_sub")}
    if ps == "limited" and not status["prices_at"]:
        return {"code": "pool_low", "text": "No Hard Rock prices today, so no picks.",
                "sub": "Too few odds pulls are left for today's games."}
    parts = []
    reads = f.get("flag_reads") or {"games": 0, "lines": 0}
    nxt = None
    if status.get("next_price_read_at"):
        try:
            nxt = common.parse_iso(status["next_price_read_at"])
        except (TypeError, ValueError):
            nxt = None
        if nxt is not None and nxt <= inp.now:
            nxt = None
    if reads["games"]:
        n = reads["lines"]
        parts.append("%d line%s read, none cleared both checks." % (n, "" if n == 1 else "s"))
        if f.get("gg_vetoes"):
            k = f["gg_vetoes"]
            parts.append("%d had a gap but our model said no." % k if k != 1 else "1 had a gap but our model said no.")
    else:
        parts.append("Picks come from the price read 90 minutes before each game.")
    started_ids = {g["id"] for g in games if g["started"]}
    shown_started = [p for p in picks if not p["pulled"] and p["game_id"] in started_ids]
    if shown_started:
        parts.append("Today's earlier pick is under Started." if len(shown_started) == 1
                     else "Today's earlier picks are under Started.")
    if nxt:
        parts.append("Next read at %s." % common.fmt_time(nxt))
    waiting = nxt is not None or shown_started or any(not g["started"] for g in games)
    return {"code": "none_qualified", "text": "No picks yet today" if waiting else "No picks today",
            "sub": " ".join(parts) or None}
