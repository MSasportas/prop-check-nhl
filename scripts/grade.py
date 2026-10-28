"""grade.py: results, once each game is final.

For every game that has an ungraded pick: read the NHL boxscore. Only gameState "OFF" is final.
  shots -> player `sog`   points -> player `points`   (player fields never include the shootout)
  not in the boxscore, or 00:00 ice time -> Void ("did not play")
  game postponed or cancelled -> Void
  a whole-number tie with the line -> Push
Graded at the worst price shown. A pick is graded once; running this again adds nothing.
"""
from datetime import timedelta

import common
import nhl
import record

FIELD = {"shots": "sog", "points": "points", "goals": "goals", "assists": "assists"}


def result_for(side, line, actual):
    """'W' | 'L' | 'PUSH' for a number against a line."""
    if actual == line:
        return "PUSH"
    over = actual > line
    return "W" if over == (side == "over") else "L"


def read_box(box):
    """boxscore -> ({player_id: stats dict}, {team: dict(sog, skater_sog)}) or None if it is not usable."""
    try:
        players, teams = {}, {}
        for side in ("awayTeam", "homeTeam"):
            ab = box[side]["abbrev"]
            grp = box["playerByGameStats"][side]
            s = 0
            for k in ("forwards", "defense"):
                for p in grp.get(k, []):
                    players[p["playerId"]] = dict(p, team=ab, skater=True)
                    s += p.get("sog") or 0
            for p in grp.get("goalies", []):
                players[p["playerId"]] = dict(p, team=ab, skater=False)
            teams[ab] = {"sog": box[side].get("sog"), "skater_sog": s}
        return players, teams
    except (KeyError, TypeError):
        return None


def shots_trusted(game_id, team, teams, pbp_cache):
    """Skater shots must add up to the team's shots (plus any shot by the team's own goalie)."""
    t = teams.get(team)
    if not t or t["sog"] is None:
        return False
    diff = t["sog"] - t["skater_sog"]
    if diff == 0:
        return True
    if diff < 0 or diff > 2:
        return False
    if game_id not in pbp_cache:
        pbp_cache[game_id] = nhl.play_by_play(game_id)
    pbp = pbp_cache[game_id]
    return bool(pbp) and nhl.goalie_shots(pbp, team) == diff


def grade(events, now, cfg, sched_games):
    """Returns (new events, notes). Appends nothing itself."""
    stake = cfg["values"]["stake"]
    at = common.iso(now)
    items = record.fold(events)
    new, notes = [], []
    by_game = {}
    for it in items.values():
        if it["kind"] == "single" and it["graded"] is None:
            by_game.setdefault(it["shown"]["game_id"], []).append(it)
    pbp_cache = {}
    for gid, its in sorted(by_game.items()):
        g = sched_games.get(str(gid)) or sched_games.get(gid) or {}
        start = common.parse_iso(its[0]["shown"]["start"])
        if now < start and g.get("sched", "OK") == "OK":
            continue                                        # not started: nothing to grade
        postponed = g.get("sched") in ("PPD", "CNCL")
        box = None if postponed else nhl.boxscore(gid)
        if not postponed and box is None:
            notes.append("boxscore for %s not available" % gid)
            continue
        if box is not None and box.get("gameScheduleState") in ("PPD", "CNCL"):
            postponed = True
        if not postponed and box.get("gameState") != "OFF":
            continue                                        # LIVE, CRIT and FINAL are not final
        parsed = None if postponed else read_box(box)
        if not postponed and parsed is None:
            notes.append("boxscore for %s is missing player stats" % gid)
            continue
        for it in sorted(its, key=lambda x: x["id"]):
            sh = it["shown"]
            pre = []
            if record.is_open(it):                          # a pick the engine never got to lock (runs were down)
                pre.append({"t": "locked", "id": it["id"], "at": at,
                            "state": "locked" if it["state"] == "lineup" else "locked_unconfirmed"})
            price = record.worst_price(it)
            if postponed:
                new += pre + [{"t": "graded", "id": it["id"], "at": at, "result": "VOID", "actual": None,
                               "actual_text": "game postponed", "price": price, "units": 0.0}]
                continue
            players, teams = parsed
            p = players.get(sh["player_id"])
            if p is None or p.get("toi") in (None, "00:00", "0:00"):
                new += pre + [{"t": "graded", "id": it["id"], "at": at, "result": "VOID", "actual": None,
                               "actual_text": "did not play", "price": price, "units": 0.0}]
                continue
            note = None
            if sh["market"] == "shots" and not shots_trusted(gid, p["team"], teams, pbp_cache):
                hold = timedelta(hours=cfg["ops"]["grade_shot_check_hold_hours"])
                if now < start + hold:
                    notes.append("shots for %s in %s do not add up yet, waiting" % (p["team"], gid))
                    continue
                note = "team shot total did not match the player rows"
            actual = p.get(FIELD[sh["market"]])
            if actual is None:
                notes.append("no %s for player %s in %s" % (sh["market"], sh["player_id"], gid))
                continue
            res = result_for(sh["side"], sh["line"], actual)
            ev = {"t": "graded", "id": it["id"], "at": at, "result": res, "actual": actual,
                  "actual_text": "had %d" % actual, "price": price,
                  "units": record.single_units(res, price, stake)}
            if note:
                ev["note"] = note
            new += pre + [ev]

    # parlays: graded when every leg is graded
    items = record.fold(events + new)
    for it in sorted(items.values(), key=lambda x: x["id"]):
        if it["kind"] != "parlay" or it["graded"] is not None:
            continue
        legs = [items.get(l) for l in it["shown"]["legs"]]
        if any(l is None or l["graded"] is None for l in legs):
            continue
        # graded at the worst parlay price SHOWN; each leg at its price in that same snapshot, so a void or
        # push leg drops out of a price that was really on the page
        snap = record.parlay_snapshot(it)
        leg_price = lambda l: snap["legs"][l["id"]] if snap and l["id"] in snap["legs"] else l["graded"]["price"]
        res, price, units = record.grade_parlay([(l["graded"]["result"], leg_price(l)) for l in legs], stake)
        hits = sum(1 for l in legs if l["graded"]["result"] == "W")
        counted = sum(1 for l in legs if l["graded"]["result"] in ("W", "L"))
        pre = []
        if record.is_open(it):
            pre.append({"t": "locked", "id": it["id"], "at": at,
                        "state": "locked" if it["state"] == "lineup" else "locked_unconfirmed"})
        new += pre + [{"t": "graded", "id": it["id"], "at": at, "result": res, "actual": hits,
                       "actual_text": "%d of %d legs hit" % (hits, counted) if counted else "no legs counted",
                       "price": price if price is not None else record.last_price(it), "units": units,
                       "legs": [{"id": l["id"], "result": l["graded"]["result"]} for l in legs]}]
    return new, notes
