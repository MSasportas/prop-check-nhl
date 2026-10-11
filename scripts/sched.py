"""sched.py: the season schedule cache (data/state/schedule.json).

Every run re-reads the week that starts today (live game states, puck times). Once per slate day it
also re-reads last week (final states) and the weeks up to the 1st of next month (needed to work out
how many games the odds keys must cover).
"""
from datetime import date, timedelta

import common
import nhl


def path():
    return common.dpath("state", "schedule.json")


def _merge(cache, wk, now):
    for g in wk["games"]:
        cache["games"][str(g["id"])] = g
    if wk.get("season_start"):
        cache["season_start"] = wk["season_start"][:10]
    if wk.get("season_end"):
        cache["season_end"] = wk["season_end"][:10]


def update(now, slate):
    """Refresh the cache. Returns (cache, status dict). cache is None only if we have never had one
    and the NHL did not answer."""
    cache = common.read_json(path()) or {"games": {}}
    cache.setdefault("games", {})
    today = date.fromisoformat(slate)
    wk = nhl.schedule_week(slate)
    if wk is None:
        if not cache["games"]:
            return None, {"status": "failed", "note": "NHL schedule did not answer"}
        return cache, {"status": "failed", "note": "NHL schedule did not answer, using the saved copy"}
    before = common.dumps(cache, False)
    _merge(cache, wk, now)
    season = next((g["season"] for g in wk["games"] if g["date"] == slate), None) or \
        next((g["season"] for g in wk["games"]), cache.get("season"))
    cache["season"] = season

    notes = []
    stale_recent = any(g["date"] < slate and g["date"] >= (today - timedelta(days=2)).isoformat()
                       and g.get("sched") == "OK" and g.get("state") != "OFF" for g in cache["games"].values())
    if cache.get("full_day") != slate or stale_recent:
        want = [(today - timedelta(days=7)).isoformat()]
        # forward: through the end of this month
        nxt = (today.replace(day=1) + timedelta(days=32)).replace(day=1)
        d = today + timedelta(days=7)
        while d < nxt:
            want.append(d.isoformat())
            d += timedelta(days=7)
        # backward: any week of this season we have never read (first run, or a lost cache)
        start = cache.get("season_start")
        if start and cache.get("history_done") != season:
            d = today - timedelta(days=14)
            first = date.fromisoformat(start)
            while d > first - timedelta(days=7):
                want.append(d.isoformat())
                d -= timedelta(days=7)
        ok = True
        for w in want:
            if cache.get("full_day") == slate and w != want[0]:
                continue                                    # stale_recent refresh: last week only
            more = nhl.schedule_week(w)
            if more is None:
                ok = False
                continue
            _merge(cache, more, now)
        if ok:
            cache["full_day"] = slate
            cache["history_done"] = season
        else:
            notes.append("part of the schedule did not load")
    # keep the cache to this season and the last few weeks of noise out
    cache["games"] = {k: g for k, g in cache["games"].items() if g.get("season") == season or g["date"] >= slate}
    cache.pop("weeks", None)
    if common.dumps(cache, False) != before:                # written only when something changed
        common.write_json(path(), cache, pretty=False)
    return cache, {"status": "ok", "note": "; ".join(notes) or "schedule read"}


def games_on(cache, slate, regular_only=True):
    out = [g for g in cache["games"].values() if g["date"] == slate
           and (g.get("type") == nhl.REGULAR or not regular_only)]
    return sorted(out, key=lambda g: (g["start"], g["id"]))


def games_left_this_month(cache, slate):
    """Regular-season games from today to the last day of the month (the odds keys reset on the 1st).
    Returns (games, game_days as a list of (date, n))."""
    today = date.fromisoformat(slate)
    nxt = (today.replace(day=1) + timedelta(days=32)).replace(day=1).isoformat()
    per = {}
    for g in cache["games"].values():
        if slate <= g["date"] < nxt and g.get("type") == nhl.REGULAR and g.get("sched") == "OK":
            per[g["date"]] = per.get(g["date"], 0) + 1
    return sum(per.values()), sorted(per.items())


def started(game, now):
    """Puck has dropped: the schedule's start time has passed, or the NHL says the game is under way."""
    if game.get("state") in ("LIVE", "CRIT", "FINAL", "OFF"):
        return True
    return now >= common.parse_iso(game["start"])
