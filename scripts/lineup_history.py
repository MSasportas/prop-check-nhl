"""lineup_history.py: a daily record of when each team's Daily Faceoff lineup was confirmed, and what it said.

data/state/lineups.json keeps only today's latest read, so this file keeps, per team per slate:
  first_today_at / first_today   when a page dated today was first seen, and what it said then
  last_at / last                 the last page seen before that team's puck (dated today or not)
  changes                        how many different page states were seen before puck
A page is what scripts/lineups.py parsed: in / unsure (injury tag or game-time decision) / out, unmatched
names, and the units (`groups`: f1-f4, d1-d3, pp1/pp2, pk1/pk2, g) when the read had them. Nothing new is
scraped. Written only when something changes, never after the team's puck. Internal (TEAM.md item 4 and 17):
the page does not read it.
"""
import common
import sched

FIELDS = ("page_date", "today", "in", "unsure", "out", "unmatched", "complete", "groups")


def path(slate):
    return common.dpath("state", "lineup_history", "%s.json" % slate)


def load(slate):
    doc = common.read_json(path(slate))
    if not isinstance(doc, dict) or doc.get("date") != slate or not isinstance(doc.get("teams"), dict):
        return {"date": slate, "teams": {}}
    return doc


def compact(page):
    return {k: page.get(k) for k in FIELDS if k in page}


def fold(doc, now, games, state, historical=False):
    """Fold one lineups.json state, as seen at `now`, into the doc. Returns the number of teams changed.
    historical (backfill): the games are long over, so 'started' is judged by the clock alone."""
    teams = (state or {}).get("teams") if isinstance(state, dict) else None
    if not isinstance(teams, dict) or (state.get("date") and state.get("date") != doc["date"]):
        return 0
    n = 0
    for g in games:
        if (now >= common.parse_iso(g["start"])) if historical else sched.started(g, now):
            continue                                        # frozen at puck
        for team in (g["away"], g["home"]):
            rec = teams.get(team)
            page = rec.get("page") if isinstance(rec, dict) else None
            if not isinstance(page, dict):
                continue
            at = rec.get("checked_at") or common.iso(now)
            if common.parse_iso(at) >= common.parse_iso(g["start"]):
                continue
            t = doc["teams"].setdefault(team, {"game_id": g["id"], "start": g["start"], "first_today_at": None,
                                               "first_today": None, "last_at": None, "last": None, "changes": 0})
            cp = compact(page)
            hit = False
            if page.get("today") is True and t["first_today_at"] is None:
                t["first_today_at"], t["first_today"] = at, cp
                hit = True
            if cp != t["last"]:
                t["last_at"], t["last"] = at, cp
                t["changes"] += 1
                hit = True
            n += hit
    return n


def update(now, slate, games, state):
    """The run.py step. Returns a step result dict."""
    doc = load(slate)
    n = fold(doc, now, games, state)
    if not n:
        return {"status": "skipped", "note": "no change"}
    common.write_json(path(slate), doc, pretty=False)
    return {"status": "ok", "note": "%d team(s) changed" % n}
