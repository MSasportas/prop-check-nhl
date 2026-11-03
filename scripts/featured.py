"""featured.py: sides and totals, TRACKED ONLY (Matt, 2026-11-03: "track sides and totals from all the same books").

Never a pick, never the Record, the page, Discord or status.json picks. Research data for the team, like data/shadow.
Each time a shots price read (pull A, B or C) lands for a game that has not started, one bulk call asks the feed for
moneyline (h2h), puck line (spreads) and totals for EVERY game on the slate, from the same books as the shots reads
(Hard Rock + ops.consensus_books, one billed region). Cost: markets returned x 1 region = about 3 credits per call,
whatever the number of games (ledger pull "F"). Games starting together share one call.
Writes data/featured/<slate>.json:
  done    ["<game_id>:<pull>", ...]   which shots reads already have a sides/totals snapshot
  snaps   [{at, pulls: ["<game_id>:<pull>"], cost, games: {game_id: {away, home, start, books: {book: {market:
           {last_update, outcomes: [{name, price, point?}]}}}}}}]
Only games not yet started are kept in a snapshot (prices after puck are live odds). Grading: final scores come from
the NHL API (free) when the team analyses it. Soft step: a failure is a "warn" and never touches picks.
Runs only when today's budget (the odds plan, else the pool) still covers the shots reads left today, never at tier 0.
"""
from datetime import timedelta

import common
import odds
import sched

RETRY_MIN = 10
RESERVE_PER_GAME = 3          # credits kept back for each game still ahead today (shots A, B, C)
MARKETS = ("h2h", "spreads", "totals")
PULLS = ("A", "B", "C")


def path(slate):
    return common.dpath("featured", "%s.json" % slate)


def load(slate):
    st = common.read_json(path(slate))
    if not isinstance(st, dict):
        st = {"date": slate, "version": 1}
    st.setdefault("done", [])
    st.setdefault("snaps", [])
    st.setdefault("last_try_at", None)
    return st


def due_reads(day, games, now, started, done):
    """'<game_id>:<pull>' for every shots read (A/B/C) already taken for a game that has not started and has no snapshot."""
    ahead = {str(g["id"]) for g in games if not started.get(g["id"]) and not sched.started(g, now)}
    out = []
    for f in (day or {}).get("fetches", []) or []:
        gid = str(f.get("game_id"))
        k = "%s:%s" % (gid, f.get("pull"))
        if f.get("pull") in PULLS and gid in ahead and "shots" in (f.get("markets") or {}) and \
                common.parse_iso(f["at"]) <= now and k not in done and k not in out:
            out.append(k)
    return out


def snapshot(payload, games, day, now, started):
    """The feed's bulk answer -> {game_id: {...}} for the slate's games that have not started."""
    by_event = {v: k for k, v in ((day or {}).get("events") or {}).items()}
    matched, _ = odds.match_events(payload if isinstance(payload, list) else [], games, 6)
    by_event.update({v: k for k, v in matched.items()})
    gmap = {str(g["id"]): g for g in games}
    out = {}
    for e in payload if isinstance(payload, list) else []:
        gid = by_event.get(e.get("id"))
        g = gmap.get(gid)
        if not g or started.get(g["id"]) or sched.started(g, now):
            continue
        books = {}
        for b in e.get("bookmakers", []) or []:
            mk = {}
            for m in b.get("markets", []) or []:
                if m.get("key") in MARKETS:
                    mk[m["key"]] = {"last_update": m.get("last_update"),
                                    "outcomes": [{k: o[k] for k in ("name", "price", "point") if k in o}
                                                 for o in m.get("outcomes", []) or []]}
            if mk:
                books[b.get("key")] = mk
        if books:
            out[gid] = {"away": g["away"], "home": g["home"], "start": g["start"], "books": books}
    return out


def check(now, slate, games, started, cfg, dry_run=False):
    """The run.py step. Returns a step result dict."""
    if dry_run:
        return {"status": "skipped", "note": "dry run"}
    if not games:
        return {"status": "skipped", "note": "no games today"}
    st = load(slate)
    day = odds.load_day(slate)                             # plan + feed event ids
    reads = common.read_json(odds.odds_path(slate), {}) or {}   # the day's shots reads (fetches)
    due = due_reads(reads, games, now, started, set(st["done"]))
    if not due:
        return {"status": "skipped", "note": "no new shots read to match"}
    keys = odds.load_keys()
    if not keys and not odds.fixture_dir():
        return {"status": "skipped", "note": "no odds keys"}
    plan = day.get("plan")
    if plan and plan.get("tier", 0) < 1:
        return {"status": "skipped", "note": "credits too low"}
    last = common.parse_iso(st.get("last_try_at"))
    if last and timedelta(0) <= now - last < timedelta(minutes=RETRY_MIN):
        return {"status": "skipped", "note": "tried in the last %d minutes" % RETRY_MIN}
    ahead = [g for g in games if not started.get(g["id"]) and not sched.started(g, now)]
    pool = odds.Pool(keys, now)
    keep = len(MARKETS) + RESERVE_PER_GAME * len(ahead)
    room = (plan["budget_today"] - pool.spent_on(slate)) if plan and plan.get("budget_today") is not None else pool.total_left()
    if room < keep or pool.total_left() < keep:
        return {"status": "skipped", "note": "budget kept for today's shots reads"}
    client = odds.Client(pool, cfg)
    payload, cost = client.featured_odds(MARKETS, slate)
    if payload is None and not client.errors:
        return {"status": "skipped", "note": "sides/totals not available"}   # fixture mode without a file
    pool.save()                                            # credits were (or may have been) spent: ledger first
    st["last_try_at"] = common.iso(now)
    if payload is None:
        common.write_json(path(slate), st, pretty=False)
        return {"status": "failed", "note": "sides/totals not read: %s" % client.errors[-1]}
    games_out = snapshot(payload, games, day, now, started)
    missing = [k for k in due if k.split(":")[0] not in games_out]   # no book priced it: never asked again for this read
    st["snaps"].append({"at": common.iso(now), "pulls": due, "missing": missing, "cost": cost, "games": games_out})
    st["done"] = st["done"] + due
    common.write_json(path(slate), st, pretty=False)
    return {"status": "ok", "note": "sides/totals for %d game(s), %d book(s) max, %d credit(s)" %
            (len(games_out), max([len(v["books"]) for v in games_out.values()] or [0]), cost)}
