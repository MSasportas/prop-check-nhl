"""engine.py: turns stats + Hard Rock prices + lineups into tonight's picks, and keeps them honest.

The method is the Sharp Standard (FINAL). Every number comes from config/rules.json ("values").

For one side of one line:
    b         break-even of the Hard Rock price
    fair      Hard Rock's own chance with the vig removed (our side's share of the two break-evens)
    model     the model's chance for this side
    gap       model - fair
    model_adj model - uncertainty - under_penalty (unders) - thin_over_penalty (thin overs)
    p         model_weight x model_adj + market_weight x fair            <- "our chance" on the card
A new pick needs: price inside the gate, p >= min_p, p - b >= margin (confirmed or early), gap not
"too good", and a big gap only with the lineup confirmed.

A pick that has been shown is never silently removed. Each run it either stays (with any new price
appended to the Record), is pulled with a reason, or locks at puck drop. What was shown is rebuilt from
the Record's event log, so the page and the Record cannot disagree.
"""
import hashlib
import itertools
import math
from datetime import timedelta

import common
import lineups
import model
import names
import odds
import record
import sched

EPS = 1e-9
STATE_LABEL = {"early": "Early: lineup not confirmed", "lineup": "Lineup confirmed", "locked": "Locked",
               "locked_unconfirmed": "Locked: lineup was not confirmed"}
PULL_TEXT = {
    "out": "Scratched from the lineup",
    "gate": "Price moved past %s",
    "max_price": "Price moved past %s",
    "line_moved": "Hard Rock moved the line to %s",
    "line_gone": "Hard Rock took this line down",
    "market_gone": "Hard Rock took this market down",
    "margin": "The price no longer clears the bar",
    "drift": "The price moved against this side before the lineup was confirmed",
}


class ConfigError(Exception):
    pass


def check_config(cfg):
    v = cfg["values"]
    if abs(v["model_weight"] + v["market_weight"] - 1.0) > 1e-9:
        raise ConfigError("model_weight + market_weight must equal 1")
    for k in ("min_p", "margin_confirmed", "margin_early", "uncertainty", "under_penalty", "thin_over_penalty",
              "news_gap", "too_good", "drift_pull", "parlay_leg_min_p", "parlay_min_p_2", "parlay_min_p_3",
              "parlay_edge", "hold_min", "hold_max"):
        if not (0 <= v[k] <= 1):
            raise ConfigError("%s must be between 0 and 1" % k)
    if v["price_gate"] >= 0 or v["max_price"] < 100:
        raise ConfigError("price_gate must be negative and max_price +100 or longer")


# ---------------------------------------------------------------- the edge rule (pure arithmetic)
def edge(model_side, side, thin, price, other_price, v, fair=None):
    """All the numbers for one side at one price. `fair` may be passed when the other side is missing."""
    b = odds.break_even(price)
    if other_price is not None:
        fair = odds.fair_two_sided(price, other_price)
    adj = model_side - v["uncertainty"]
    if side == "under":
        adj -= v["under_penalty"]
    elif thin:
        adj -= v["thin_over_penalty"]
    p = v["model_weight"] * adj + v["market_weight"] * fair
    return {"b": b, "fair": fair, "model": model_side, "model_adj": adj, "gap": model_side - fair,
            "p": p, "margin": p - b}


def inside_gate(price, v):
    """-200 or better, and no longer than max_price."""
    d = odds.decimal(price)
    return odds.decimal(v["price_gate"]) - EPS <= d <= odds.decimal(v["max_price"]) + EPS


def qualifies(e, price, confirmed, v):
    """Entry test for a NEW pick. Returns (True, None) or (False, why)."""
    if not inside_gate(price, v):
        return False, "price outside the gate"
    if e["gap"] > v["too_good"] + EPS:
        return False, "too good: assume the book knows"
    if e["gap"] > v["news_gap"] + EPS and not confirmed:
        return False, "big gap needs lineup confirmed"
    if e["p"] < v["min_p"] - EPS:
        return False, "chance under the minimum"
    need = v["margin_confirmed"] if confirmed else v["margin_early"]
    if e["margin"] < need - EPS:
        return False, "margin too small"
    return True, None


def rank_key(p, b, confirmed):
    return (-(round(p - b, 6)), -round(p, 6), 0 if confirmed else 1)


# ---------------------------------------------------------------- wording
def fmt_line(line):
    return ("%g" % line)


def bet_text(side, line, market, cfg):
    return "%s %s %s" % ("Over" if side == "over" else "Under", fmt_line(line), cfg["ops"]["markets"][market]["noun"])


def pct_floor(x):
    return int(math.floor(x * 100 + 1e-7))


def pct_round(x):
    return int(math.floor(x * 100 + 0.5))


def pcts(e):
    """The two whole percents the card and the reason sentence both show: chance rounded down,
    break-even rounded to nearest. Computed once from the unrounded numbers and stored with the pick."""
    return pct_floor(e["p"]), pct_round(e["b"])


def reason_text(market, side, line, price, e, mu, etoi, opp, opp_f, thin, n, cfg):
    short = cfg["ops"]["markets"][market]["short"]
    verb = "to clear" if side == "over" else "to stay under"
    s = "%d%% %s %s %s; %s needs %d%%. Projects %.1f %s in %d min." % (
        pcts(e)[0], verb, fmt_line(line), short, common.fmt_price(price), pcts(e)[1],
        mu, short, int(round(etoi / 60.0)))
    x = int(round(abs(opp_f - 1.0) * 100))
    if abs(opp_f - 1.0) >= 0.02:                            # the opponent clause is dropped under 2%
        s += " %s allow %d%% %s %s than average." % (opp, x, "more" if opp_f > 1 else "fewer",
                                                     "shots" if model.SK[market]["opp"] == "sa" else "goals")
    if thin:
        s += " Short history: %d games." % n
    return s


def pick_id(slate, game_id, pid, market, line, side):
    return "%s:%s:%s:%s:%s:%s" % (slate, game_id, pid, market, fmt_line(line), side)


def parlay_id(slate, leg_ids):
    h = hashlib.sha1("|".join(sorted(leg_ids)).encode()).hexdigest()[:10]
    return "%s:P:%s" % (slate, h)


# ---------------------------------------------------------------- model inputs for one player
class Inputs:
    """Everything the engine reads. Built by run.py; tests build it by hand."""

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


# ---------------------------------------------------------------- candidates from the latest prices
def candidates(inp, paused=()):
    """Every side of every usable line with its numbers. Returns (list, counts)."""
    v, out = inp.v, []
    counts = {"checked": 0, "failed": 0}
    for gid, g in inp.games.items():
        gv = inp.view.get(gid) or {}
        for market, mcfg in inp.cfg["ops"]["markets"].items():
            mv = gv.get(market)
            if not mcfg.get("picks") or not mv or mv.get("gone"):
                continue
            counts["checked"] += mv["checked"]
            counts["failed"] += mv["failed"]
            if sched.started(g, inp.now) or market in paused:
                continue
            for (pid, line), pair in mv["pairs"].items():
                if not pair["ok"] or pair["team"] not in (g["away"], g["home"]):
                    continue
                team = pair["team"]
                home = team == g["home"]
                opp = g["away"] if home else g["home"]
                if team in inp.behind:
                    continue
                pv = inp.player(pid, team)
                if pv["n"] < v["min_history"] or pv["sitting"]:
                    continue
                m = inp.model(pid, team, opp, home, market, line)
                if m is None:
                    continue
                status = inp.confirmed(team, pid)
                if status == "out":
                    continue
                conf = status == "in"
                if pv["missed_last"] and not conf:
                    continue
                for side in ("over", "under"):
                    if side == "over" and pv["toi_drop"]:
                        continue
                    price, other = pair[side], pair["under" if side == "over" else "over"]
                    ms = m["p_over"] if side == "over" else 1.0 - m["p_over"]
                    e = edge(ms, side, pv["thin"], price, other, v)
                    ok, why = qualifies(e, price, conf, v)
                    if not ok:
                        continue
                    out.append({"id": pick_id(inp.slate, gid, pid, market, line, side), "game_id": gid, "pid": pid,
                                "team": team, "opp": opp, "home": home, "market": market, "line": line, "side": side,
                                "price": price, "price_at": mv["at"], "e": e, "m": m, "pv": pv, "conf": conf,
                                "name": pair["name"]})
    return out, counts


def explain(inp):
    """Every side of every line the engine looked at, with its numbers and the first rule it failed.
    For people, not for the page: `python scripts/run.py --explain`."""
    v, rows = inp.v, []
    for gid, g in inp.games.items():
        gv = inp.view.get(gid) or {}
        for market, mcfg in inp.cfg["ops"]["markets"].items():
            mv = gv.get(market)
            if not mcfg.get("picks") or not mv or mv.get("gone"):
                continue
            for (pid, line), pair in sorted(mv["pairs"].items(), key=lambda kv: kv[1]["name"]):
                team = pair["team"]
                home = team == g["home"]
                opp = g["away"] if home else g["home"]
                pv = inp.player(pid, team)
                m = inp.model(pid, team, opp, home, market, line)
                status = inp.confirmed(team, pid)
                for side in ("over", "under"):
                    price, other = pair[side], pair["under" if side == "over" else "over"]
                    row = {"player": pair["name"], "team": team, "market": market, "line": line, "side": side,
                           "price": price, "lineup": status, "n": pv["n"], "thin": pv["thin"]}
                    if not pair["ok"]:
                        row["verdict"] = "feed check: %s" % pair["why"]
                    elif team in inp.behind:
                        row["verdict"] = "team excluded: %s" % inp.behind[team]
                    elif m is None:
                        row["verdict"] = "no model (not a skater)"
                    else:
                        ms = m["p_over"] if side == "over" else 1.0 - m["p_over"]
                        e = edge(ms, side, pv["thin"], price, other, v)
                        row.update({k: round(e[k], 4) for k in e})
                        row.update(mu=round(m["mu"], 3), toi_min=round(m["etoi"] / 60.0, 1), opp_f=round(m["opp_f"], 4))
                        ok, why = qualifies(e, price, status == "in", v)
                        if pv["n"] < v["min_history"]:
                            ok, why = False, "under min_history games"
                        elif pv["sitting"]:
                            ok, why = False, "back from an absence"
                        elif status == "out":
                            ok, why = False, "out of the lineup"
                        elif pv["missed_last"] and status != "in":
                            ok, why = False, "missed last game, lineup not confirmed"
                        elif side == "over" and pv["toi_drop"]:
                            ok, why = False, "ice time dropped: no over"
                        elif sched.started(g, inp.now):
                            ok, why = False, "game started"
                        row["verdict"] = "QUALIFIES" if ok else why
                    rows.append(row)
    return rows


def best_per_player(cands, v):
    """One line per player per market (highest p), then at most max_per_player per player (best ranked)."""
    by = {}
    for c in cands:
        k = (c["pid"], c["market"])
        if k not in by or c["e"]["p"] > by[k]["e"]["p"]:
            by[k] = c
    ranked = sorted(by.values(), key=lambda c: rank_key(c["e"]["p"], c["e"]["b"], c["conf"]) + (c["id"],))
    seen, out = {}, []
    for c in ranked:
        if seen.get(c["pid"], 0) >= v["max_per_player"]:
            continue
        seen[c["pid"]] = seen.get(c["pid"], 0) + 1
        out.append(c)
    return out


# ---------------------------------------------------------------- one run of the engine
def evaluate(inp, paused=(), block_new=False):
    """Returns (new_events, state) where state holds what build_slate() needs. Does not write anything.
    block_new: add no new picks this run (stats are behind); picks already shown are still looked after."""
    v, now = inp.v, inp.now
    at = common.iso(now)
    items = record.fold(inp.events)
    today = {i: it for i, it in items.items() if it["slate"] == inp.slate}
    singles = {i: it for i, it in today.items() if it["kind"] == "single"}
    new, live = [], {}                                      # live: id -> current numbers for open singles

    # ---- 1. picks already shown: lock, pull, or carry on with the newest price
    for i, it in singles.items():
        if not record.is_open(it):
            continue
        sh = it["shown"]
        g = inp.games.get(sh["game_id"])
        conf_status = inp.confirmed(sh["team"], sh["player_id"])
        if g is None or sched.started(g, now):
            st = "locked" if it["state"] == "lineup" else "locked_unconfirmed"
            new.append({"t": "locked", "id": i, "at": at, "state": st})
            continue
        if conf_status == "out":
            new.append({"t": "pulled", "id": i, "at": at, "code": "out", "reason": PULL_TEXT["out"]})
            continue
        mv = (inp.view.get(sh["game_id"]) or {}).get(sh["market"])
        last_read = common.parse_iso(it["prices"][-1]["at"])
        price, price_at, other = record.last_price(it), last_read, None
        pair = None if mv is None or mv.get("gone") else mv["pairs"].get((sh["player_id"], sh["line"]))
        bad_pair = pair is not None and pair.get(sh["side"]) is not None and not pair.get("ok")
        if mv is not None and mv["at"] > last_read and bad_pair:
            pass                        # m12: the newest read of this line failed the feed checks: keep the last good price
        elif mv is not None and mv["at"] > last_read:
            if mv.get("gone"):
                new.append({"t": "pulled", "id": i, "at": at, "code": "market_gone", "reason": PULL_TEXT["market_gone"]})
                continue
            if pair is None or pair.get(sh["side"]) is None:
                moved = sorted(l for (pid, l), p in mv["pairs"].items()
                               if pid == sh["player_id"] and l != sh["line"] and p.get(sh["side"]) is not None)
                if moved:
                    new.append({"t": "pulled", "id": i, "at": at, "code": "line_moved",
                                "reason": PULL_TEXT["line_moved"] % fmt_line(moved[0])})
                else:
                    new.append({"t": "pulled", "id": i, "at": at, "code": "line_gone", "reason": PULL_TEXT["line_gone"]})
                continue
            price, price_at = pair[sh["side"]], mv["at"]
            other = pair["under" if sh["side"] == "over" else "over"]
        elif mv is not None and not mv.get("gone"):
            if pair and pair.get("ok"):
                other = pair["under" if sh["side"] == "over" else "over"]
                price_at = max(price_at, mv["at"]) if pair.get(sh["side"]) == price else price_at
        m = inp.model(sh["player_id"], sh["team"], sh["opp"], sh["home"], sh["market"], sh["line"])
        pv = inp.player(sh["player_id"], sh["team"])
        if m is None:
            ms, thin = sh.get("model"), sh.get("thin")
        else:
            ms = m["p_over"] if sh["side"] == "over" else 1.0 - m["p_over"]
            thin = pv["thin"]
        e = edge(ms, sh["side"], thin, price, other, v, fair=it.get("fair") or sh.get("fair"))
        conf = conf_status == "in"
        state = "lineup" if conf else "early"
        # pull rules (Sharp section 8). A price that causes a pull was never shown as a live price.
        code = None
        if odds.decimal(price) < odds.decimal(v["price_gate"]) - EPS:
            code, text = "gate", PULL_TEXT["gate"] % common.fmt_price(v["price_gate"])
        elif odds.decimal(price) > odds.decimal(v["max_price"]) + EPS:
            code, text = "max_price", PULL_TEXT["max_price"] % common.fmt_price(v["max_price"])
        elif e["margin"] < v["pull_margin"] - EPS:
            code, text = "margin", PULL_TEXT["margin"]
        elif not conf and odds.break_even(record.first_price(it)) - e["b"] >= v["drift_pull"] - EPS:
            code, text = "drift", PULL_TEXT["drift"]
        if code:
            new.append({"t": "pulled", "id": i, "at": at, "code": code, "reason": text, "seen_price": price})
            continue
        reason = sh["reason"] if m is None else reason_text(
            sh["market"], sh["side"], sh["line"], price, e, m["mu"], m["etoi"], sh["opp"], m["opp_f"], thin, pv["n"], inp.cfg)
        p_pct, b_pct = pcts(e) if m is not None else (it.get("p_pct"), it.get("breakeven_pct"))
        if price != record.last_price(it):
            new.append({"t": "price", "id": i, "at": at, "price": price, "price_at": common.iso(price_at),
                        "p": round(e["p"], 4), "breakeven": round(e["b"], 4), "fair": round(e["fair"], 4),
                        "p_pct": p_pct, "breakeven_pct": b_pct, "reason": reason})
        elif round(e["p"], 4) != it["p"] or reason != it["reason"] or p_pct != it.get("p_pct"):
            new.append({"t": "update", "id": i, "at": at, "p": round(e["p"], 4), "breakeven": round(e["b"], 4),
                        "fair": round(e["fair"], 4), "p_pct": p_pct, "breakeven_pct": b_pct, "reason": reason})
        if state != it["state"]:
            new.append({"t": "state", "id": i, "at": at, "state": state})
        live[i] = {"p": e["p"], "b": e["b"], "conf": conf, "price": price, "price_at": price_at,
                   "pid": sh["player_id"], "game_id": sh["game_id"]}

    # ---- 2. new picks, inside the caps
    cands, counts = candidates(inp, paused)
    if block_new:
        cands = []
    per_game, per_player = {}, {}
    for x in live.values():
        per_game[x["game_id"]] = per_game.get(x["game_id"], 0) + 1
        per_player[x["pid"]] = per_player.get(x["pid"], 0) + 1
    fresh = []
    for c in best_per_player([c for c in cands if c["id"] not in singles], v):
        if per_player.get(c["pid"], 0) >= v["max_per_player"] or per_game.get(c["game_id"], 0) >= v["max_per_game"]:
            continue
        per_player[c["pid"]] = per_player.get(c["pid"], 0) + 1
        per_game[c["game_id"]] = per_game.get(c["game_id"], 0) + 1
        fresh.append(c)
        live[c["id"]] = {"p": c["e"]["p"], "b": c["e"]["b"], "conf": c["conf"], "price": c["price"],
                         "price_at": c["price_at"], "pid": c["pid"], "game_id": c["game_id"]}
    order = sorted(live, key=lambda i: rank_key(live[i]["p"], live[i]["b"], live[i]["conf"]) + (i,))
    ranks = {i: n + 1 for n, i in enumerate(order)}
    for c in fresh:
        g, e, m, pv = inp.games[c["game_id"]], c["e"], c["m"], c["pv"]
        body = {
            "id": c["id"], "rank": ranks[c["id"]], "tier": "main", "game_id": c["game_id"],
            "player": inp.display_name(c["pid"], c["name"]), "player_id": c["pid"], "team": c["team"],
            "opp": c["opp"], "home": c["home"], "start": g["start"], "market": c["market"], "line": c["line"],
            "side": c["side"], "bet": bet_text(c["side"], c["line"], c["market"], inp.cfg),
            "price": c["price"], "price_at": common.iso(c["price_at"]),
            "p": round(e["p"], 4), "breakeven": round(e["b"], 4), "fair": round(e["fair"], 4),
            "p_pct": pcts(e)[0], "breakeven_pct": pcts(e)[1], "model": round(e["model"], 4),
            "reason": reason_text(c["market"], c["side"], c["line"], c["price"], e, m["mu"], m["etoi"], c["opp"],
                                  m["opp_f"], pv["thin"], pv["n"], inp.cfg),
            "state": "lineup" if c["conf"] else "early", "thin": pv["thin"],
            "games_used": pv["n"], "games_this_season": pv["n_season"],
        }
        new.append({"t": "shown", "kind": "single", "id": c["id"], "at": at, "slate": inp.slate, "pick": body})

    # ---- 3. parlays (built on the picks as they stand after steps 1 and 2)
    items2 = record.fold(inp.events + new)
    new += _parlays(inp, items2, live, at)
    return new, {"counts": counts, "ranks": ranks, "live": live}


def _parlay_numbers(leg_ids, live):
    dec = p = b = 1.0
    for l in leg_ids:
        dec *= odds.decimal(live[l]["price"])
        p *= live[l]["p"]
        b *= live[l]["b"]
    return {"price": odds.american(dec), "p": p, "b": b,
            "legs": {l: live[l]["price"] for l in leg_ids},          # the snapshot this parlay price is made of
            "price_at": max(live[l]["price_at"] for l in leg_ids),   # "from leg prices at": the newest of them
            "state": "lineup" if all(live[l]["conf"] for l in leg_ids) else "early"}


def _parlays(inp, items, live, at):
    v, new = inp.v, []
    today = {i: it for i, it in items.items() if it["slate"] == inp.slate}
    open_parlays, use = [], {}
    for i, it in today.items():
        if it["kind"] != "parlay" or not record.is_open(it):
            continue
        legs = it["shown"]["legs"]
        pulled = [l for l in legs if l in today and today[l]["pulled"]]
        locked = [l for l in legs if l in today and today[l]["locked_at"]]
        if pulled:
            who = today[pulled[0]]["shown"]["player"].split(". ", 1)[-1]
            new.append({"t": "pulled", "id": i, "at": at, "code": "leg", "reason": "%s leg pulled" % who})
            continue
        if locked or any(l not in live for l in legs):
            st = "locked" if it["state"] == "lineup" else "locked_unconfirmed"
            new.append({"t": "locked", "id": i, "at": at, "state": st})
            continue
        n = _parlay_numbers(legs, live)
        # a new snapshot whenever ANY leg's price changed (even if the rounded parlay price did not)
        if n["legs"] != it["prices"][-1].get("legs") or n["price"] != record.last_price(it):
            new.append({"t": "price", "id": i, "at": at, "price": n["price"], "price_at": common.iso(n["price_at"]),
                        "leg_prices": n["legs"], "p": round(n["p"], 4), "breakeven": round(n["b"], 4)})
        elif round(n["p"], 4) != it["p"]:
            new.append({"t": "update", "id": i, "at": at, "p": round(n["p"], 4), "breakeven": round(n["b"], 4)})
        if n["state"] != it["state"]:
            new.append({"t": "state", "id": i, "at": at, "state": n["state"]})
        open_parlays.append(legs)
        for l in legs:
            use[l] = use.get(l, 0) + 1

    # legs that may go in a new parlay
    lo, hi = odds.decimal(v["parlay_leg_min_price"]), odds.decimal(v["parlay_leg_max_price"])
    legs_ok = [i for i, x in live.items() if x["p"] >= v["parlay_leg_min_p"] - EPS
               and lo - EPS <= odds.decimal(x["price"]) <= hi + EPS]
    legs_ok.sort(key=lambda i: rank_key(live[i]["p"], live[i]["b"], live[i]["conf"]) + (i,))
    legs_ok = legs_ok[:12]                                  # keeps the search small; the best legs come first

    def best(size, forbid_shared_with=()):
        top = None
        for combo in itertools.combinations(legs_ok, size):
            if v["parlay_one_per_game"] and len({live[l]["game_id"] for l in combo}) < size:
                continue
            if len({live[l]["pid"] for l in combo}) < size:
                continue
            if any(use.get(l, 0) >= v["parlay_leg_max_use"] for l in combo):
                continue
            if any(set(combo) & set(o) for o in forbid_shared_with):
                continue
            pid_ = parlay_id(inp.slate, combo)
            if pid_ in today:
                continue                                    # shown before (and pulled or locked): never re-shown
            n = _parlay_numbers(combo, live)
            floor = v["parlay_min_p_2"] if size == 2 else v["parlay_min_p_3"]
            if n["p"] < floor - EPS or n["p"] < n["b"] + v["parlay_edge"] - EPS:
                continue
            key = (-(round(n["p"] - n["b"], 6)), -round(n["p"], 6), pid_)
            if top is None or key < top[0]:
                top = (key, combo, n, pid_)
        return top

    def add(found):
        _, combo, n, pid_ = found
        legs = sorted(combo, key=lambda l: rank_key(live[l]["p"], live[l]["b"], live[l]["conf"]) + (l,))
        body = {"id": pid_, "legs": legs, "n": len(legs), "price": n["price"], "price_at": common.iso(n["price_at"]),
                "leg_prices": n["legs"],
                "p": round(n["p"], 4), "breakeven": round(n["b"], 4), "state": n["state"],
                "leg_text": ["%s %s %s" % (today[l]["shown"]["player"], today[l]["shown"]["bet"],
                                           common.fmt_price(live[l]["price"])) for l in legs]}
        new.append({"t": "shown", "kind": "parlay", "id": pid_, "at": at, "slate": inp.slate, "parlay": body})
        open_parlays.append(legs)
        for l in legs:
            use[l] = use.get(l, 0) + 1

    if v["parlay_min_legs"] <= 2:
        while sum(1 for o in open_parlays if len(o) == 2) < 2 and len(open_parlays) < v["parlay_cap"]:
            f = best(2, [o for o in open_parlays if len(o) == 2])
            if not f:
                break
            add(f)
    if v["parlay_max_legs"] >= 3:
        if not any(len(o) == 3 for o in open_parlays) and len(open_parlays) < v["parlay_cap"]:
            f = best(3)
            if f:
                add(f)
    return new


# ---------------------------------------------------------------- paused markets (Sharp section 11)
def paused_markets(events, cfg):
    """A market switches itself off after pause_legs graded picks if it is running pause_gap under its
    average break-even, or is down pause_units. Returns {market: sentence}."""
    v = cfg["values"]
    rec, _ = record.build_views(events, cfg)
    out = {}
    for r in rec["summary"]["rows"]:
        if r["key"] not in cfg["ops"]["markets"] or r["n"] < v["pause_legs"]:
            continue
        if (r["needed"] is not None and r["hit_rate"] <= r["needed"] - v["pause_gap"] + EPS) or r["units"] <= v["pause_units"]:
            out[r["key"]] = "%s picks are paused: results are running too far under the price." % r["label"]
    return out


# ---------------------------------------------------------------- goal watch (top tier only)
def goal_watch(inp):
    v = inp.v
    if not inp.plan or inp.plan.get("tier", 0) < 4:
        return []
    rows = []
    for gid, g in inp.games.items():
        mv = (inp.view.get(gid) or {}).get("goals")
        if not mv or mv.get("gone") or sched.started(g, inp.now):
            continue
        for (pid, line), pair in mv["pairs"].items():
            if pair.get("over") is None or line != 0.5 or pair["team"] not in (g["away"], g["home"]):
                continue
            team = pair["team"]
            if team in inp.behind or inp.confirmed(team, pid) != "in":
                continue
            home = team == g["home"]
            m = inp.model(pid, team, g["away"] if home else g["home"], home, "goals", 0.5)
            if m is None or inp.player(pid, team)["n"] < v["min_history"] or m["p_over"] <= 0:
                continue
            # Goal watch shows only where Hard Rock's price is SHORT of our fair price (pays less than fair).
            # A row where Hard Rock pays more than fair would read like a value bet nobody vetted: never shown.
            if odds.decimal(pair["over"]) >= 1.0 / m["p_over"] - EPS:
                continue
            rows.append({"player": inp.display_name(pid, pair["name"]), "team": team, "price": pair["over"],
                         "fair_price": odds.american(1.0 / m["p_over"]), "p": round(m["p_over"], 4),
                         "text": "%d%% to score; %s needs %d%%. Fair price %s. Not a pick." % (
                             pct_floor(m["p_over"]), common.fmt_price(pair["over"]),
                             pct_round(odds.break_even(pair["over"])),
                             common.fmt_price(odds.american(1.0 / m["p_over"])))})
    rows.sort(key=lambda r: -r["p"])
    return rows[:v["goal_watch_count"]]


# ---------------------------------------------------------------- slate.json
def build_slate(inp, events, extra):
    """The page's file. Built only from the Record log and the same facts status.json gets."""
    v, now, cfg = inp.v, inp.now, inp.cfg
    items = record.fold(events)
    today = {i: it for i, it in items.items() if it["slate"] == inp.slate}
    ranks, live = extra["ranks"], extra["live"]
    picks, parlays = [], []
    for i, it in today.items():
        sh = it["shown"]
        # history = how settled the pick was, and when (the page prints it as is). Prices are listed apart.
        hist = [{"at": s["at"], "text": STATE_LABEL.get(s["state"], s["state"])} for s in it["states"]]
        if it["pulled"]:
            hist.append({"at": it["pulled"]["at"], "text": "Pulled: %s" % it["pulled"]["reason"]})
        hist.sort(key=lambda h: h["at"])
        g = it["graded"]
        base = {"id": i, "price": record.last_price(it), "first_price": record.first_price(it),
                "first_price_at": it["prices"][0]["at"], "worst_price": record.worst_price(it),
                "p": it["p"], "breakeven": it["breakeven"],
                "p_pct": it["p_pct"] if it.get("p_pct") is not None else pct_floor(it["p"]),
                "breakeven_pct": it["breakeven_pct"] if it.get("breakeven_pct") is not None else pct_round(it["breakeven"]),
                "state": it["state"], "history": hist,
                "prices": [{"at": p["at"], "price": p["price"]} for p in it["prices"]],
                "pulled": {"at": it["pulled"]["at"], "reason": it["pulled"]["reason"]} if it["pulled"] else None,
                "graded": {"result": g["result"], "actual": g["actual_text"], "units": g["units"]} if g else None}
        if it["kind"] == "single":
            lv = live.get(i)
            base.update({
                "rank": ranks.get(i) if record.is_open(it) else None, "tier": "main", "game_id": sh["game_id"],
                "player": sh["player"], "player_id": sh["player_id"], "team": sh["team"], "opp": sh["opp"],
                "home": sh["home"], "start": sh["start"], "market": sh["market"], "line": sh["line"],
                "side": sh["side"], "bet": sh["bet"],
                "price_at": common.iso(lv["price_at"]) if lv else it["prices"][-1]["at"],
                "reason": it["reason"], "thin": sh["thin"], "games_used": sh["games_used"],
                "games_this_season": sh["games_this_season"]})
            picks.append(base)
        else:
            open_legs = record.is_open(it) and all(l in live for l in sh["legs"])
            base.update({"legs": sh["legs"], "n": len(sh["legs"]),
                         "price_at": common.iso(max(live[l]["price_at"] for l in sh["legs"])) if open_legs
                         else it["prices"][-1]["at"],
                         "leg_prices": it["prices"][-1].get("legs")})
            parlays.append(base)
    order = {"open": 0, "pulled": 1, "locked": 2}
    bucket = lambda p: "pulled" if p["pulled"] else ("open" if p["state"] in ("early", "lineup") and not p["graded"] else "locked")
    picks.sort(key=lambda p: (order[bucket(p)], p["rank"] or 999, p["start"], p["id"]))
    parlays.sort(key=lambda p: (order[bucket(p)], -(p["p"] - p["breakeven"]), p["id"]))
    open_picks = [p for p in picks if bucket(p) == "open"]

    games = []
    for g in sorted(inp.games.values(), key=lambda x: (x["start"], x["id"])):
        ex = [t for t in (g["away"], g["home"]) if t in inp.behind]
        games.append({"id": g["id"], "away": g["away"], "home": g["home"], "start": g["start"],
                      "started": sched.started(g, now),
                      "picks": sum(1 for p in picks if p["game_id"] == g["id"] and not p["pulled"]),
                      "excluded_reason": inp.behind[ex[0]] if ex else None, "excluded_teams": ex})

    f = inp.facts
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
        "lines_checked": extra["counts"]["checked"], "lines_failed": extra["counts"]["failed"],
        "tier": (inp.plan or {}).get("tier"),
    }
    banners = list(f.get("banners", []))
    if status["excluded_teams"]:
        by = {}
        for x in status["excluded_teams"]:
            by.setdefault(x["reason"], []).append(x["team"])
        for why, ts in sorted(by.items()):
            banners.append({"level": "warn", "text": "Not covered tonight: %s (%s)." % (", ".join(ts), why)})
    if extra["counts"]["failed"]:
        n = extra["counts"]["failed"]
        banners.append({"level": "info", "text": "%d Hard Rock line%s skipped: the two sides did not add up or the price was old."
                                                 % (n, "" if n == 1 else "s")})
    for text in (f.get("paused") or {}).values():
        banners.append({"level": "warn", "text": text})

    empty = None
    if not open_picks:
        empty = _empty(inp, status, picks, games, extra)
    tomorrow5 = (common.parse_iso(inp.slate + "T00:00:00").replace(tzinfo=common.ET) + timedelta(days=1)).replace(
        hour=cfg["ops"]["rollover_hour"])
    gw = goal_watch(inp)
    return {"slate_date": inp.slate, "generated_at": common.iso(now), "status_at": common.iso(now),
            "valid_until": common.iso(tomorrow5),
            "status": status, "banners": banners, "empty": empty, "games": games, "picks": picks,
            "parlays": parlays, "goal_watch": gw,
            "goal_watch_note": "Not picks. Our model is weakest on goals." if gw else None}


def _empty(inp, status, picks, games, extra):
    f = inp.facts
    if not games:
        if f.get("other_games"):
            return {"code": "no_games", "text": "No picks today.", "sub": "Only regular-season games are covered."}
        return {"code": "no_games", "text": "No NHL games today.", "sub": None}
    if f.get("stats_missing") or status["stats_state"] == "behind":
        return {"code": "stats_behind", "text": "Stats are behind, so no picks until they catch up.", "sub": None}
    if all(g["started"] for g in games):
        shown = [p for p in picks if not p["pulled"]]
        return {"code": "all_started", "text": "Every game has started.",
                "sub": "Tonight's picks are under Started." if shown else "No picks were posted tonight."}
    ps = status["prices_state"]
    if ps == "keys_refused":
        text = "No picks tonight. Nothing cleared the bar at Hard Rock's prices." if status["prices_at"] else \
            "No Hard Rock prices today, so no picks."
        return {"code": "keys_refused", "text": text, "sub": odds.KEYS_REFUSED_TEXT}
    if ps == "pool_empty":
        return {"code": "pool_empty", "text": "No Hard Rock prices today, so no picks.", "sub": "The odds pulls ran out."}
    if ps == "feed_down":
        return {"code": "feed_down", "text": "No Hard Rock prices today, so no picks.",
                "sub": "The odds feed did not answer."}
    if ps == "not_yet":
        return {"code": "not_yet", "text": "No prices read yet today.", "sub": f.get("not_yet_sub")}
    if ps == "limited" and not status["prices_at"]:
        return {"code": "pool_low", "text": "No Hard Rock prices today, so no picks.",
                "sub": "Too few odds pulls are left for today's games."}
    sub = None
    if status["prices_at"]:
        n = extra["counts"]["checked"]
        sub = "Checked %d line%s at %s." % (n, "" if n == 1 else "s", common.fmt_time(common.parse_iso(status["prices_at"])))
    return {"code": "none_qualified", "text": "No picks tonight. Nothing cleared the bar at Hard Rock's prices.",
            "sub": sub}
