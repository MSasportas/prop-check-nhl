"""nhl.py: the two free NHL sources.

  api-web.nhle.com/v1         schedule, rosters, boxscore, play-by-play
  api.nhle.com/stats/rest/en  one row per player per game (and per team per game)

Every function returns None (never raises) when the source does not answer, and notes the
result in SOURCES so status.json can say which sources were reached.
With PC_NHL_FIXTURE_DIR set, nothing here touches the network: responses are read from files.
"""
import json
import os
import time
import urllib.parse

import common

WEB = "https://api-web.nhle.com/v1"
STATS = "https://api.nhle.com/stats/rest/en"
SOURCES = {}          # name -> {"ok": n, "failed": n}
REGULAR = 2           # gameType / gameTypeId of regular-season games


def note(source, ok):
    s = SOURCES.setdefault(source, {"ok": 0, "failed": 0})
    s["ok" if ok else "failed"] += 1


def fixture_dir():
    return os.environ.get("PC_NHL_FIXTURE_DIR")


def _record(name, js):
    """PC_NHL_RECORD_DIR: save every good answer under its fixture name (used to build replay fixtures)."""
    d = os.environ.get("PC_NHL_RECORD_DIR")
    if d and js is not None:
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, name), "w", encoding="utf-8") as f:
            json.dump(js, f)


def _fixture(name):
    path = os.path.join(fixture_dir(), name)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


# ---------------------------------------------------------------- api-web
def web(path):
    """GET api-web path such as 'schedule/2026-10-11'. Returns parsed JSON or None."""
    if fixture_dir():
        js = _fixture(path.replace("/", "_") + ".json")
    else:
        r = common.http_get("%s/%s" % (WEB, path))
        js = r.json() if r.ok else None
        _record(path.replace("/", "_") + ".json", js)
    note("nhl_web", js is not None)
    return js


def schedule_week(date):
    """The 7 days starting at `date`. Returns dict(games=[...], season_start, season_end) or None.
    Each game: id, date (NHL schedule date), season, type, away, home, start (Eastern ISO),
    state (FUT PRE LIVE CRIT FINAL OFF), sched (OK, PPD, CNCL, ...)."""
    js = web("schedule/%s" % date)
    if not js or "gameWeek" not in js:
        return None
    games = []
    try:
        for day in js["gameWeek"]:
            for g in day.get("games", []):
                games.append({
                    "id": g["id"], "date": day["date"], "season": g.get("season"), "type": g.get("gameType"),
                    "away": g["awayTeam"]["abbrev"], "home": g["homeTeam"]["abbrev"],
                    "start": common.iso(common.parse_iso(g["startTimeUTC"])),
                    "state": g.get("gameState"), "sched": g.get("gameScheduleState", "OK"),
                })
    except (KeyError, TypeError, ValueError):
        note("nhl_web", False)
        return None
    return {"games": games, "season_start": js.get("regularSeasonStartDate"),
            "season_end": js.get("regularSeasonEndDate")}


def roster(team):
    """Current roster: list of dict(id, first, last, team, pos 'F'|'D'|'G') or None."""
    js = web("roster/%s/current" % team)
    if not js:
        return None
    out = []
    try:
        for grp, pos in (("forwards", "F"), ("defensemen", "D"), ("goalies", "G")):
            for x in js.get(grp, []):
                out.append({"id": x["id"], "first": x["firstName"]["default"], "last": x["lastName"]["default"],
                            "team": team, "pos": pos})
    except (KeyError, TypeError):
        return None
    return out or None


def boxscore(game_id):
    return web("gamecenter/%s/boxscore" % game_id)


def play_by_play(game_id):
    return web("gamecenter/%s/play-by-play" % game_id)


def goalie_shots(pbp, team):
    """Shots on goal (goals included, shootout excluded) taken by `team`'s GOALIES in one game.
    The team's shot total counts them; the skater rows do not. Returns None if the payload is odd."""
    try:
        tid = next(pbp[s]["id"] for s in ("awayTeam", "homeTeam") if pbp[s]["abbrev"] == team)
        goalies = {r["playerId"] for r in pbp.get("rosterSpots", [])
                   if r.get("teamId") == tid and r.get("positionCode") == "G"}
        n = 0
        for p in pbp.get("plays", []):
            if p.get("typeDescKey") not in ("shot-on-goal", "goal"):
                continue
            if (p.get("periodDescriptor") or {}).get("periodType") == "SO":
                continue
            det = p.get("details") or {}
            if det.get("eventOwnerTeamId") != tid:
                continue
            if (det.get("shootingPlayerId") or det.get("scoringPlayerId")) in goalies:
                n += 1
        return n
    except (KeyError, TypeError, StopIteration):
        return None


# ---------------------------------------------------------------- stats REST (per-game rows)
def stats_url(report, season, d0, d1):
    exp = 'seasonId=%s and gameTypeId=%d and gameDate>="%s" and gameDate<="%s"' % (season, REGULAR, d0, d1)
    q = urllib.parse.urlencode({"isAggregate": "false", "isGame": "true", "limit": -1, "cayenneExp": exp})
    return "%s/%s?%s" % (STATS, report, q)


def stats_report(report, season, d0, d1):
    """All per-game rows of `report` ('skater/summary', 'team/summary') between two dates (7 days or less).
    Returns a list, or None when the source failed OR returned fewer rows than it said it had."""
    if fixture_dir():
        js = _fixture("%s_%s_%s_%s.json" % (report.replace("/", "_"), season, d0, d1))
        if isinstance(js, list):
            js = {"data": js, "total": len(js)}
    else:
        r = common.http_get(stats_url(report, season, d0, d1), timeout=60)
        js = r.json() if r.ok else None
        _record("%s_%s_%s_%s.json" % (report.replace("/", "_"), season, d0, d1), js)
        time.sleep(0.3)                                    # be polite between report pulls
    ok = isinstance(js, dict) and isinstance(js.get("data"), list) and js.get("total", len(js["data"])) == len(js["data"])
    note("nhl_stats", ok)
    return js["data"] if ok else None
