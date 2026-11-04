"""live.py: data/live.json, the page's Live tab. Display only: never a pick, a price, a grade or a Record event.

For every game of tonight's slate that has started and has a pick on the Record, from the NHL boxscore that grade.py
already read this run (nhl.CACHE: no extra calls):
  games[]  game_id, state (LIVE CRIT FINAL OFF ...), period, period_type (REG OT SO), clock (time left, "08:14"),
           in_intermission, running, away/home {abbrev, score, sog}, updated_at (when that box was read)
  picks{}  pick id -> {game_id, market, stat}: the player's number so far for the pick's market (shots = box "sog"),
           null when he is not in the box (yet)
A game whose box was not read this run (grade.py stops reading a game once its picks are graded) keeps its last entry
from the previous live.json of the same slate; a graded pick's stat comes from the Record's grade. Nothing is written
when no slate game with a pick has started, or when nothing changed. A soft step: a failure never fails a run.
"""
import common
import grade
import nhl
import record
import sched


def path():
    return common.dpath("live.json")


def _int(v):
    return v if isinstance(v, int) and not isinstance(v, bool) else None


def game_entry(gid, box, at):
    """One game's line from a boxscore; None if the box is not usable."""
    try:
        pd = box.get("periodDescriptor") or {}
        ck = box.get("clock") or {}
        side = lambda k: {"abbrev": box[k]["abbrev"], "score": _int(box[k].get("score")), "sog": _int(box[k].get("sog"))}
        return {"game_id": gid, "state": box.get("gameState"), "schedule_state": box.get("gameScheduleState"),
                "period": _int(pd.get("number")), "period_type": pd.get("periodType"),
                "clock": ck.get("timeRemaining") if isinstance(ck.get("timeRemaining"), str) else None,
                "in_intermission": bool(ck.get("inIntermission")), "running": bool(ck.get("running")),
                "away": side("awayTeam"), "home": side("homeTeam"), "updated_at": at}
    except (KeyError, TypeError, AttributeError):
        return None


def build(now, slate, games, events, old=None):
    """-> the live.json doc, or None when there is nothing to show."""
    at = common.iso(now)
    items = record.fold(events)
    by_game = {}
    for it in items.values():
        if it["kind"] == "single" and it["slate"] == slate:
            by_game.setdefault(it["shown"]["game_id"], []).append(it)
    old = old if isinstance(old, dict) and old.get("slate_date") == slate else {}
    old_games = {g.get("game_id"): g for g in old.get("games") or [] if isinstance(g, dict)}
    old_picks = old.get("picks") if isinstance(old.get("picks"), dict) else {}
    out_games, out_picks = [], {}
    for g in sorted(games, key=lambda x: (x["start"], x["id"])):
        its = by_game.get(g["id"])
        if not its or not sched.started(g, now):
            continue
        box = nhl.boxscore(g["id"]) if nhl.cached("boxscore", g["id"]) else None    # this run's read only
        ent = game_entry(g["id"], box, at) if box is not None else None
        players = None
        if ent is not None:
            parsed = grade.read_box(box)
            players = parsed[0] if parsed else {}
        else:
            ent = old_games.get(g["id"]) or {
                "game_id": g["id"], "state": g.get("state"), "schedule_state": g.get("sched"), "period": None,
                "period_type": None, "clock": None, "in_intermission": False, "running": False,
                "away": {"abbrev": g["away"], "score": None, "sog": None},
                "home": {"abbrev": g["home"], "score": None, "sog": None}, "updated_at": None}
        out_games.append(ent)
        for it in sorted(its, key=lambda x: x["id"]):
            sh = it["shown"]
            field = grade.FIELD.get(sh.get("market"))
            stat = None
            if players is not None:
                p = players.get(sh.get("player_id"))
                stat = _int((p or {}).get(field)) if field else None
            else:
                stat = _int((old_picks.get(it["id"]) or {}).get("stat"))
            gr = it["graded"]
            if gr and _int(gr.get("actual")) is not None and gr.get("result") in ("W", "L", "PUSH"):
                stat = gr["actual"]                         # the Record's own number once graded
            out_picks[it["id"]] = {"game_id": g["id"], "market": sh.get("market"), "stat": stat}
    if not out_games:
        return None
    return {"slate_date": slate, "generated_at": at, "games": out_games, "picks": out_picks}


def step(now, slate, games, events):
    """The run.py step. Returns a step result dict."""
    old = common.read_json(path())
    doc = build(now, slate, games or [], events or [], old)
    if doc is None:
        return {"status": "skipped", "note": "no started game with a pick"}
    same = isinstance(old, dict) and {k: v for k, v in old.items() if k != "generated_at"} == \
        {k: v for k, v in doc.items() if k != "generated_at"}
    if same:
        return {"status": "skipped", "note": "no change"}
    common.write_json(path(), doc)
    fresh = sum(1 for g in doc["games"] if g.get("updated_at") == doc["generated_at"])
    return {"status": "ok", "note": "%d game(s), %d read this run" % (len(doc["games"]), fresh)}
