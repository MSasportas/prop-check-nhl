"""book_probe.py: ONE-TIME discovery of every book the odds feed has for NHL player shots (TEAM.md section 7 item 24, rung 4).

Why: ops.consensus_books is a hand-picked list asked on every read (max 9 so the read is one billed region). Matt wants the
market we compare against to be the best SHARP books, chosen from evidence rather than guesses, so this asks the event-odds
endpoint with NO bookmakers= filter across the regions in ops.book_probe.regions and records what every book actually returns.

Cost: one call, markets (1) x regions (5) = about 5 credits, once (up to 3 tries if the first answers nothing). Counted in the
credits ledger as pull "P". Runs only after pull A, with the day's plan made, when today's budget still covers the games
ahead, for the soonest game that is 35-120 minutes from puck (props are posted by then). Never in a dry run.

Writes (research only: no pick, page, Record or Discord reads them):
  data/state/book_probe.json         per book: pairs, players, lines (1.5 / 2.5 / 3.5), mean hold, freshness, and how it tracks
                                     Pinnacle (shared pairs, mean abs / signed gap in fair over chance), plus the call's cost
  data/state/book_probe_pairs.json.gz  every (book, player, line, over, under) so the team can re-slice it offline
"""
import gzip
import json
from datetime import timedelta

import common
import odds
import sched

RETRY_MIN = 60
MAX_TRIES = 3
MIN_AHEAD_MIN = 35
MAX_AHEAD_MIN = 120
RESERVE_PER_GAME = 3
MARKET = "player_shots_on_goal"
PINNACLE = "pinnacle"
LINES = (1.5, 2.5, 3.5)


def path():
    return common.dpath("state", "book_probe.json")


def pairs_path():
    return common.dpath("state", "book_probe_pairs.json.gz")


def load():
    st = common.read_json(path())
    if not isinstance(st, dict):
        st = {}
    st.setdefault("done", None)
    st.setdefault("tries", 0)
    st.setdefault("last_try_at", None)
    return st


def regions(cfg):
    r = ((cfg.get("ops") or {}).get("book_probe") or {}).get("regions") or ["us", "us2", "us_ex", "eu", "uk"]
    return list(r)


def collect(payload):
    """The feed's answer -> {book key: {"title", "last_update", "pairs": {(player, point): [over, under]}}} for the shots market."""
    out = {}
    for b in (payload or {}).get("bookmakers", []) or []:
        if not isinstance(b, dict) or not b.get("key"):
            continue
        for m in b.get("markets", []) or []:
            if not isinstance(m, dict) or m.get("key") != MARKET:
                continue
            rec = out.setdefault(b["key"], {"title": b.get("title"), "last_update": m.get("last_update"), "pairs": {}})
            for o in m.get("outcomes", []) or []:
                who, pt, side, price = o.get("description"), o.get("point"), (o.get("name") or "").lower(), o.get("price")
                if who is None or pt is None or side not in ("over", "under") or not isinstance(price, (int, float)):
                    continue
                rec["pairs"].setdefault((who, float(pt)), [None, None])[0 if side == "over" else 1] = price
    return out


def _hold(o, u):
    return 1.0 / odds.decimal(o) + 1.0 / odds.decimal(u) - 1.0


def summarize(books, now):
    """Per book numbers (pure). Two-sided pairs only. gap_* compare the book's de-vigged fair over with Pinnacle's on the same
    (player, line): sharp books sit close to Pinnacle (small mean abs gap) and carry low hold."""
    full = {k: {pl: v for pl, v in rec["pairs"].items() if v[0] is not None and v[1] is not None} for k, rec in books.items()}
    pin = full.get(PINNACLE) or {}
    pin_fair = {pl: odds.fair_two_sided(v[0], v[1]) for pl, v in pin.items()}
    rows = {}
    for k, rec in books.items():
        pr = full[k]
        if not pr:
            continue
        holds = [_hold(v[0], v[1]) for v in pr.values()]
        shared = [(odds.fair_two_sided(v[0], v[1]) - pin_fair[pl]) for pl, v in pr.items() if pl in pin_fair]
        lu = common.parse_iso(rec.get("last_update")) if rec.get("last_update") else None
        rows[k] = {"title": rec.get("title"), "pairs": len(pr), "players": len({pl[0] for pl in pr}),
                   "by_line": {("%g" % ln): sum(1 for pl in pr if pl[1] == ln) for ln in LINES},
                   "other_lines": sum(1 for pl in pr if pl[1] not in LINES),
                   "hold_mean": round(sum(holds) / len(holds), 4), "hold_min": round(min(holds), 4), "hold_max": round(max(holds), 4),
                   "age_min": None if lu is None else round((now - lu).total_seconds() / 60.0, 1),
                   "shared_with_pinnacle": len(shared),
                   "gap_abs": None if not shared else round(sum(abs(x) for x in shared) / len(shared), 4),
                   "gap_signed": None if not shared else round(sum(shared) / len(shared), 4)}
    return rows


def check(now, slate, games, started, cfg, dry_run=False):
    """The run.py step. Returns a step result dict."""
    st = load()
    if st["done"]:
        return {"status": "skipped", "note": "done"}
    if dry_run:
        return {"status": "skipped", "note": "dry run"}
    if st["tries"] >= MAX_TRIES:
        return {"status": "skipped", "note": "gave up after %d tries" % MAX_TRIES}
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
    last = common.parse_iso(st.get("last_try_at")) if st.get("last_try_at") else None
    if last and timedelta(0) <= now - last < timedelta(minutes=RETRY_MIN):
        return {"status": "skipped", "note": "tried in the last hour"}
    ahead = [g for g in games if not started.get(g["id"]) and not sched.started(g, now)]
    mins = lambda g: (common.parse_iso(g["start"]) - now).total_seconds() / 60.0
    cands = [g for g in ahead if MIN_AHEAD_MIN <= mins(g) <= MAX_AHEAD_MIN and day["events"].get(str(g["id"]))]
    if not cands:
        return {"status": "skipped", "note": "no game 35-120 minutes from puck with a feed event"}
    reg = regions(cfg)
    pool = odds.Pool(keys, now)
    if plan["budget_today"] - pool.spent_on(slate) < len(reg) + RESERVE_PER_GAME * len(ahead) or pool.total_left() < len(reg):
        return {"status": "skipped", "note": "budget kept for today's games"}
    g = sorted(cands, key=lambda x: (x["start"], x["id"]))[0]
    client = odds.Client(pool, cfg)
    payload, cost = client.event_all_books(day["events"][str(g["id"])], g["away"], g["home"], reg, slate, g["id"])
    if payload is None and not client.errors:
        return {"status": "skipped", "note": "all-books read not available"}      # fixture mode without a file
    pool.save()                                            # credits were (or may have been) spent: ledger first
    st["last_try_at"] = common.iso(now)
    st["tries"] += 1
    books = collect(payload) if payload else {}
    if not books:
        common.write_json(path(), st)
        if payload is None:
            return {"status": "failed", "note": "all-books read failed: %s" % client.errors[-1]}
        return {"status": "skipped", "note": "no book returned shots for %s at %s" % (g["away"], g["home"])}
    rows = summarize(books, now)
    pairs = [[k, who, pt, v[0], v[1]] for k, rec in sorted(books.items()) for (who, pt), v in sorted(rec["pairs"].items())]
    common.write_bytes(pairs_path(), gzip.compress(json.dumps(pairs, separators=(",", ":")).encode("utf-8"), mtime=0))
    st["done"] = {"at": common.iso(now), "game_id": g["id"], "away": g["away"], "home": g["home"], "minutes_to_puck": round(mins(g)),
                  "regions": reg, "cost": cost}
    st["books"] = rows
    common.write_json(path(), st)
    return {"status": "ok", "note": "%d book(s) returned shots for %s at %s (%s credits)" % (len(rows), g["away"], g["home"], cost)}
