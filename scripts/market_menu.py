"""market_menu.py: once per ISO week, ask the odds feed which markets Hard Rock lists for one NHL game.

One call to the event-markets endpoint (about 1 credit, counted in the credits ledger as pull "M"), through the
same key pool as every price read. Writes data/state/market_menu.json:
  markets   {feed market key: {first_seen, last_seen, last_update}}   every key Hard Rock has listed
  weeks     {"2026-W42": {at, game_id, away, home, n, cost}}         one read per ISO week
Purpose: tell the team which other Hard Rock markets exist (alt shots, blocks, assists, PP points, periods,
sides/totals) before deciding to log any. Internal only; the page does not read it.
Runs only after pull A's time, with the day's plan made, at tier 1 or higher, and only when today's budget
still covers the rest of the day's games. Never in a dry run. A failure is retried an hour later.
"""
from datetime import date, timedelta

import common
import odds
import sched

RETRY_MIN = 60
MIN_AHEAD_MIN = 30            # the game asked about must be at least this far from puck
RESERVE_PER_GAME = 3          # credits kept back for each game still ahead today (A, B, C at tier 2-3)


def path():
    return common.dpath("state", "market_menu.json")


def week_of(slate):
    y, w, _ = date.fromisoformat(slate).isocalendar()
    return "%04d-W%02d" % (y, w)


def load():
    st = common.read_json(path())
    if not isinstance(st, dict):
        st = {}
    st.setdefault("markets", {})
    st.setdefault("weeks", {})
    st.setdefault("last_try_at", None)
    return st


def book_markets(payload, books):
    """The feed's answer -> [(market key, last_update)] for the first listed book found."""
    for want in books:
        for b in (payload or {}).get("bookmakers", []) or []:
            if isinstance(b, dict) and b.get("key") == want:
                return [(m.get("key"), m.get("last_update")) for m in b.get("markets", []) or []
                        if isinstance(m, dict) and m.get("key")]
    return []


def check(now, slate, games, started, cfg, dry_run=False):
    """The run.py step. Returns a step result dict."""
    st = load()
    wk = week_of(slate)
    if wk in st["weeks"]:
        return {"status": "skipped", "note": "read this week"}
    if dry_run:
        return {"status": "skipped", "note": "dry run"}
    if not games:
        return {"status": "skipped", "note": "no games today"}
    keys = odds.load_keys()
    if not keys and not odds.fixture_dir():
        return {"status": "skipped", "note": "no odds keys"}
    day = odds.load_day(slate)
    plan = day.get("plan")
    if not plan or plan.get("tier", 0) < 1:
        return {"status": "skipped", "note": "odds plan not made or credits too low"}
    if now < odds.pull_times(slate, games, cfg["values"])["A"]:
        return {"status": "skipped", "note": "waits for pull A"}
    last = common.parse_iso(st.get("last_try_at"))
    if last and timedelta(0) <= now - last < timedelta(minutes=RETRY_MIN):
        return {"status": "skipped", "note": "tried in the last hour"}
    ahead = [g for g in games if not started.get(g["id"]) and not sched.started(g, now)]
    cands = [g for g in ahead if (common.parse_iso(g["start"]) - now).total_seconds() / 60.0 >= MIN_AHEAD_MIN
             and day["events"].get(str(g["id"]))]
    if not cands:
        return {"status": "skipped", "note": "no game far enough ahead with a feed event"}
    pool = odds.Pool(keys, now)
    if plan["budget_today"] - pool.spent_on(slate) < 1 + RESERVE_PER_GAME * len(ahead) or pool.total_left() < 1:
        return {"status": "skipped", "note": "budget kept for today's games"}
    g = sorted(cands, key=lambda x: (x["start"], x["id"]))[0]
    client = odds.Client(pool, cfg)
    payload, cost = client.event_markets(day["events"][str(g["id"])], g["away"], g["home"], slate, g["id"])
    if payload is None and not client.errors:
        return {"status": "skipped", "note": "market menu not available"}     # fixture mode without a file
    pool.save()                                            # credits were (or may have been) spent: ledger first
    st["last_try_at"] = common.iso(now)
    found = book_markets(payload, cfg["ops"]["bookmakers"]) if payload is not None else []
    if not found:
        common.write_json(path(), st)
        if payload is None:
            return {"status": "failed", "note": "market menu not read: %s" % client.errors[-1]}
        return {"status": "skipped", "note": "Hard Rock listed no markets for %s at %s" % (g["away"], g["home"])}
    for k, lu in found:
        m = st["markets"].setdefault(k, {"first_seen": slate})
        m["last_seen"] = slate
        m["last_update"] = lu
    st["weeks"][wk] = {"at": common.iso(now), "game_id": g["id"], "away": g["away"], "home": g["home"],
                       "n": len(found), "cost": cost}
    common.write_json(path(), st)
    return {"status": "ok", "note": "%d Hard Rock market(s) listed for %s at %s" % (len(found), g["away"], g["home"])}
