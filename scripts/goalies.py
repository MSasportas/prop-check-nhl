"""goalies.py: who starts in goal tonight, and is it confirmed? Source: Daily Faceoff starting-goalies page.

Display only: the game list shows it. No pick depends on it. A scrape, so it can fail; every failure leaves
the last good read in place and the page then says "goalie not checked". Nothing here can stop a run.
State: data/state/goalies.json {date, checked_at, teams: {ABBREV: {name, status}}}.
status: "confirmed" (Daily Faceoff says Confirmed) | "expected" (anything else, e.g. Likely / Unconfirmed).
With PC_LINEUP_FIXTURE_DIR set the page is read from <dir>/starting-goalies.json (pageProps), never the network.
"""
import os

import common
import lineups
import teams

URL = "https://www.dailyfaceoff.com/starting-goalies"
SOURCE = {"ok": 0, "failed": 0}


def path():
    return common.dpath("state", "goalies.json")


def _slug_to_abbrev():
    return {v[1]: ab for ab, v in teams.TEAMS.items() if v[1]}


def fetch_props():
    if lineups.fixture_dir():
        return common.read_json(os.path.join(lineups.fixture_dir(), "starting-goalies.json"))
    if os.environ.get("PC_NOW") or os.environ.get("PC_DATA_DIR"):
        return None                                          # test mode: never the network
    r = common.http_get(URL, timeout=25, retries=1)
    return lineups.next_data(r.text()) if r.ok else None


def parse(props, slate):
    """pageProps -> {ABBREV: {name, status}} for the slate date, or None if it is not a goalie page for today."""
    try:
        rows = props["data"]
    except (KeyError, TypeError):
        return None
    if not isinstance(rows, list):
        return None
    page_date = str(props.get("date") or "")[:10]
    if page_date and page_date != slate:
        return None                                          # yesterday's or tomorrow's page: say nothing
    by_slug, out = _slug_to_abbrev(), {}
    for g in rows:
        if not isinstance(g, dict):
            continue
        for side in ("home", "away"):
            slug = g.get(side + "TeamSlug")
            ab = by_slug.get(slug) if isinstance(slug, str) else None
            name = g.get(side + "GoalieName")
            if not ab or not isinstance(name, str) or not name:
                continue
            confirmed = str(g.get(side + "NewsStrengthName") or "").strip().lower() == "confirmed"
            out[ab] = {"name": str(name), "status": "confirmed" if confirmed else "expected"}
    return out or None


def load(slate):
    st = common.read_json(path(), {})
    if not isinstance(st, dict) or st.get("date") != slate or not isinstance(st.get("teams"), dict):
        return {"date": slate, "teams": {}}
    return st


def check(now, slate, games, started):
    """Read the page every cycle while a game is still ahead (one request). The file is rewritten only when a
    goalie or his status changes, so quiet cycles add no commit. Never raises."""
    try:
        if not any(not started.get(g["id"]) for g in games):
            return {"status": "skipped", "note": "no game ahead"}
        st = load(slate)
        parsed = parse(fetch_props(), slate)
        SOURCE["ok" if parsed else "failed"] += 1
        if not parsed:
            return {"status": "ok", "note": "goalie page not read"}
        if parsed != {k: st["teams"].get(k) for k in parsed}:
            st["teams"].update(parsed)
            st["checked_at"] = common.iso(now)
            common.write_json(path(), st)
        return {"status": "ok", "note": "%d goalies read" % len(parsed)}
    except Exception as e:                                   # display only: never stop a run
        return {"status": "ok", "note": "goalies not checked: %s" % common.short_err(e)}
