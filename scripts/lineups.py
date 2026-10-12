"""lineups.py: is the player in tonight's lineup? Source: Daily Faceoff line-combination pages.

A team's page counts only if it is dated today (Eastern). On a page dated today:
  listed on a line, pair or special-teams unit, no injury tag  -> in the lineup ("Lineup confirmed")
  listed with an injury tag or as a game-time decision         -> not sure (stays "Early")
  listed only under injuries, or not listed at all             -> out
If a name on the page cannot be matched to an NHL player we no longer trust "not listed" for that team
(a pick is never pulled because of a name we could not read).

This is a scrape and it can fail (the site blocks some networks). Every failure degrades to "lineups
not checked": picks stay Early and the page says so. Nothing here can stop a run.
State: data/state/lineups.json. With PC_LINEUP_FIXTURE_DIR set, pages are read from <dir>/<slug>.json
(the page's pageProps) or <dir>/<slug>.html, never the network.
"""
import time
import json
import os
import re
from datetime import timedelta

import common
import names
import teams

URL = "https://www.dailyfaceoff.com/teams/%s/line-combinations"
SOURCE = {"ok": 0, "failed": 0}


def path():
    return common.dpath("state", "lineups.json")


def fixture_dir():
    return os.environ.get("PC_LINEUP_FIXTURE_DIR")


def next_data(html):
    """The page's embedded JSON (pageProps), or None."""
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html or "", re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(1))["props"]["pageProps"]
    except (ValueError, KeyError, TypeError):
        return None


def fetch_page(slug):
    """pageProps for one team, or None."""
    if fixture_dir():
        base = os.path.join(fixture_dir(), slug)
        props = common.read_json(base + ".json")
        if props is None and os.path.exists(base + ".html"):
            with open(base + ".html", "r", encoding="utf-8") as f:
                props = next_data(f.read())
    else:
        r = common.http_get(URL % slug, timeout=25, retries=1)
        props = next_data(r.text()) if r.ok else None
    SOURCE["ok" if props else "failed"] += 1
    return props


def parse_page(props, people, slate):
    """pageProps + the team's NHL players -> dict(today, page_date, in, unsure, out, unmatched, complete).
    Returns None if the page does not look like a line-combination page."""
    try:
        comb = props["combinations"]
        players = comb["players"]
        updated = common.parse_iso(comb["updatedAt"])
    except (KeyError, TypeError, ValueError):
        return None
    if not isinstance(players, list) or updated is None:
        return None
    matcher = names.Matcher(people)
    active, unsure, injured, unmatched = set(), set(), set(), []
    skaters_listed = 0
    for p in players:
        nm = p.get("name") or ""
        grp, cat = p.get("groupIdentifier") or "", p.get("categoryIdentifier") or ""
        is_injury_list = grp == "ir" or cat == "oi"
        hit = matcher.find(nm)
        if hit is None:
            if not is_injury_list and nm not in unmatched:
                unmatched.append(nm)
            continue
        if is_injury_list:
            injured.add(hit["id"])
            continue
        if cat == "ev" and grp[:1] in ("f", "d"):
            skaters_listed += 1
        if p.get("injuryStatus") or p.get("gameTimeDecision"):
            unsure.add(hit["id"])
        else:
            active.add(hit["id"])
    if skaters_listed < 15:
        return None                                         # not a full lineup: do not trust it
    active -= unsure
    page_date = updated.astimezone(common.ET).date().isoformat()
    return {"today": page_date == slate, "page_date": page_date,
            "in": sorted(active), "unsure": sorted(unsure), "out": sorted(injured - active - unsure),
            "unmatched": unmatched, "complete": not unmatched}


def check(now, slate, games, started, ops, people_for):
    """Check the teams whose game is close. people_for(team) -> list of NHL players (dicts) or None.
    Returns dict(status, note, teams {abbrev: parsed}, last_ok_at)."""
    st = common.read_json(path(), {}) or {}
    if st.get("date") != slate:
        st = {"date": slate, "teams": {}, "last_ok_at": None, "last_try_at": None}
    st.setdefault("teams", {})
    tried = okn = recent = 0
    t0 = time.monotonic()
    cap = ops.get("lineup_cycle_cap_s", 90)
    for g in games:
        if started.get(g["id"]):
            continue
        mins = (common.parse_iso(g["start"]) - now).total_seconds() / 60.0
        if mins > ops["lineup_window_min"] or mins < 0:
            continue
        for team in (g["away"], g["home"]):
            rec = st["teams"].get(team) or {}
            last = common.parse_iso(rec.get("tried_at"))
            if last and timedelta(0) <= now - last < timedelta(minutes=ops["lineup_recheck_min"]):
                recent += 1
                continue
            tried += 1
            rec["tried_at"] = common.iso(now)
            if time.monotonic() - t0 > cap:                # cycle time cap: do not starve the odds step
                rec["last_error"] = "not reached (time cap)"
                st["teams"][team] = rec
                continue
            slug = teams.df_slug(team)
            people = people_for(team)
            props = fetch_page(slug) if slug and people else None
            parsed = parse_page(props, people, slate) if props else None
            if parsed is None:
                rec["last_error"] = "page not read" if people else "roster not available"
                st["teams"][team] = rec
                continue
            okn += 1
            rec.pop("last_error", None)
            # never downgrade: a today-dated page already saved is replaced only by another today-dated page
            if parsed["today"] or not (rec.get("page") or {}).get("today"):
                rec["page"] = parsed
            rec["checked_at"] = common.iso(now)
            st["teams"][team] = rec
            st["last_ok_at"] = common.iso(now)
    if tried:
        st["last_try_at"] = common.iso(now)
        common.write_json(path(), st)
    if not tried:
        res = {"status": "skipped", "note": "checked in the last %d minutes" % ops["lineup_recheck_min"] if recent
               else "no game close enough"}
    elif okn == 0:
        res = {"status": "ok", "note": "Daily Faceoff did not answer: lineups not checked", "degraded": True}
    else:
        res = {"status": "ok", "note": "%d of %d team pages read" % (okn, tried)}
    res["state"] = st
    return res


def load(slate):
    st = common.read_json(path(), {}) or {}
    return st if st.get("date") == slate else {"date": slate, "teams": {}, "last_ok_at": None}


def player_status(st, team, pid):
    """'in' | 'out' | 'unknown' for one player from the saved state."""
    page = ((st.get("teams") or {}).get(team) or {}).get("page")
    if not page or not page.get("today"):
        return "unknown"
    if pid in page["in"]:
        return "in"
    if pid in page["unsure"]:
        return "unknown"
    if pid in page["out"]:
        return "out"
    return "out" if page.get("complete") else "unknown"
