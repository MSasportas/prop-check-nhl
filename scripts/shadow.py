"""shadow.py: the shadow log. The model's numbers on EVERY two-way Hard Rock line, graded after the game.

Internal only (TEAM.md section 7 item 17): never on the page, never in the Record, never in Discord. It is the
sample the Data Scientist uses to decide whether the model has an edge (gap bands, de-vig, blend weight).

One file per slate, data/shadow/<slate>.json, one row per (game, market, player, line):
  open     the first read of that line before puck: prices, the book's fair over (fair_over: proportional de-vig;
           fair_over_oh: all hold on the over, rules v2.0), the
           model's own chance of the over (the same Inputs.model the engine uses, before blend and penalties),
           lineup and goalie state at that moment
  close    the last read before puck, same fields
  consensus (in open and close, TEAM.md Q1): when the read also asked other books (fetch "others"), for this exact
           player + line: cons_books (other books with both sides, fresh, sane hold; cons_stale_books = books left out
           because their own last_update was older than stale_min at read time), their proportional fair over
           (cons_fair_over_med / _mean), pin_fair_over (Pinnacle), hr_vs_consensus (Hard Rock's proportional fair
           over minus the median), best other-book price per side (best_over / best_under + _book, one side is
           enough). close also has cons_move (median change since the previous read of this line) and stale = Hard
           Rock's two prices unchanged since the previous read while the consensus median moved >= STALE_MOVE;
           every stale read is kept in the row's stale_events. All None when the read did not ask other books.
  ctx      facts captured with the first read: home, team, opp, position, history, thin, back-to-back, rest,
           recent and season ice time, start time
  result   after the game is OFF: the stat and W / L / PUSH / VOID per side, read from the boxscore exactly as
           scripts/grade.py reads it (read_box; no ice time = VOID)
Snapshot rule: open and close are written only while the game has not started and only from reads made
before puck; after puck only `result` is ever added. Only the timer (run.py) and the one-off backfill
(scripts/shadow_backfill.py) write these files. A failure here never fails a run (run.py wraps it).
"""
import time
from datetime import date, timedelta

import common
import goalies
import grade
import lineups
import model
import nhl
import odds
import sched

VERSION = 1
KEEP_RESULT_DAYS = 3            # results are looked for on this slate and the two before it
RESULT_WAIT_HOURS = 2.5         # a game is looked up only once the schedule says OFF or this long after puck
BUDGET_S = 60                   # the whole step stops starting new work after this many seconds (cycle cap 420 s)
OLD_FETCH_CAP = 4               # boxscore reads per cycle for the two previous slates
FETCH_CAP = 20                  # boxscore reads per cycle for tonight (grade's reads this run are free: shared)
STALE_MOVE = 0.03              # consensus fair over moved this much while Hard Rock's prices stood still = stale
CONS_HOLD = (0.0, 0.15)       # an other book's two-way line counts toward the consensus only with a hold in this range
PINNACLE = "pinnacle"
NOTE = "Internal shadow log (TEAM.md section 7 item 17). Not the Record, not shown anywhere."


def path(slate):
    return common.dpath("shadow", "%s.json" % slate)


def load(slate):
    doc = common.read_json(path(slate))
    if not isinstance(doc, dict) or doc.get("date") != slate or not isinstance(doc.get("rows"), list):
        return {"date": slate, "version": VERSION, "note": NOTE, "rows": []}
    return doc


def serialize(doc):
    """Compact JSON with one row per line, so git stores a day's many small changes as small deltas."""
    head = {k: v for k, v in doc.items() if k != "rows"}
    rows = sorted(doc["rows"], key=lambda r: (r["ctx"]["start"] or "", r["game_id"], r["market"], r["name"] or "",
                                              r["line"], r["pid"]))
    body = ",\n".join(common.dumps(r, False) for r in rows)
    return common.dumps(head, False)[:-1] + ',"rows":[\n' + body + "\n]}\n"


def save(doc):
    common.write_text(path(doc["date"]), serialize(doc))


def key(game_id, market, pid, line):
    return "%s:%s:%s:%s" % (game_id, market, pid, "%g" % line)


def _r(x, n=5):
    return None if x is None else round(x, n)


# ---------------------------------------------------------------- context facts
def team_dates(inp, sched_games, team, slate):
    """Dates this team played before the slate: stats rows plus the schedule (stats can lag a day)."""
    ds = {r["date"] for r in inp.store.teams.get(team, []) if r["date"] < slate}
    for g in (sched_games or {}).values():
        if g.get("date", "") < slate and g.get("sched", "OK") == "OK" and team in (g.get("away"), g.get("home")):
            ds.add(g["date"])
    return ds


def rest_days(inp, sched_games, team, slate):
    """Full days off before tonight (0 = back-to-back). None with no earlier game."""
    ds = team_dates(inp, sched_games, team, slate)
    if not ds:
        return None
    last = max(ds)
    return (date.fromisoformat(slate) - date.fromisoformat(last)).days - 1


def context(inp, sched_games, g, pid, team, market):
    home = team == g["home"]
    opp = g["away"] if home else g["home"]
    t_rest, o_rest = rest_days(inp, sched_games, team, inp.slate), rest_days(inp, sched_games, opp, inp.slate)
    ctx = {"home": home, "team": team, "opp": opp, "start": g.get("start"),
           "team_rest_days": t_rest, "opp_rest_days": o_rest,
           "team_b2b": None if t_rest is None else t_rest == 0, "opp_b2b": None if o_rest is None else o_rest == 0}
    if market == "saves":
        ctx.update(pos="G", n_hist=None, n_season=None, n_team=None, thin=None, sitting=None, missed_last=None,
                   toi_drop=None, toi_last5=None, toi_season=None)
        return ctx
    pv = inp.player(pid, team)
    rows = pv["rows"]
    last5 = [r["toi"] for r in rows[-5:]]
    season = [r["toi"] for r in rows if r["season"] == inp.season]
    ctx.update(pos=pv["pos"], n_hist=pv["n"], n_season=pv["n_season"], n_team=pv["n_team"], thin=pv["thin"],
               sitting=pv["sitting"], missed_last=pv["missed_last"], toi_drop=pv["toi_drop"],
               toi_last5=_r(sum(last5) / 60.0 / len(last5), 2) if last5 else None,
               toi_season=_r(sum(season) / 60.0 / len(season), 2) if season else None)
    return ctx


# ---------------------------------------------------------------- the model on one line
def model_over(inp, market, pid, team, opp, home):
    """Returns (fn(line) -> dict(p_over, mu) or None, note). Skater markets use the engine's own Inputs.model; saves use
    model.goalie_prob with the team-level inputs (it assumes this goalie starts)."""
    if market in model.SK:
        def run(line):
            return inp.model(pid, team, opp, home, market, line)
        return run, None
    if market == "saves":
        lg = inp.league()[0]
        tsa = model.team_factor([r for r in inp.store.teams.get(team, []) if r["date"] < inp.slate], "sa", lg,
                                model.GK["K"])
        osf = model.team_factor([r for r in inp.store.teams.get(opp, []) if r["date"] < inp.slate], "sf", lg,
                                model.GK["K"])

        def run(line):
            gp = model.goalie_prob(line, {"home": home, "league_sf": lg, "team_sa_f": tsa, "opp_sf_f": osf})
            return {"p_over": gp["p"], "mu": gp["mu"]}
        return run, "team-level saves model (assumes this goalie starts)"
    return None, "no model for this market"


# ---------------------------------------------------------------- other books (consensus)
def other_lines(f, market, v):
    """From one read's "others": {(pid, line): {"pairs": {book: (over, under)}, "best": {side: (price, book)}}}.
    Matched players only; a book's market is skipped when its own last_update is stale at read time. None when the
    read did not ask other books."""
    if "others" not in f:
        return None
    at = common.parse_iso(f["at"])
    out = {}
    for book, mks in sorted((f.get("others") or {}).items()):
        mk = (mks or {}).get(market)
        if not mk:
            continue
        if odds.is_stale(mk.get("last_update"), at, v):
            for key_ in pairs_of(mk):
                out.setdefault(key_, {"pairs": {}, "best": {}, "stale": 0})["stale"] += 1
            continue
        for (pid, line), p in pairs_of(mk).items():
            e = out.setdefault((pid, line), {"pairs": {}, "best": {}, "stale": 0})
            for side in ("over", "under"):
                pr = p[side]
                if pr is not None and (side not in e["best"] or odds.decimal(pr) > odds.decimal(e["best"][side][0])):
                    e["best"][side] = (pr, book)
            if p["over"] is not None and p["under"] is not None and \
                    CONS_HOLD[0] <= odds.hold(p["over"], p["under"]) <= CONS_HOLD[1]:
                e["pairs"][book] = (p["over"], p["under"])
    return out


def _median(xs):
    xs = sorted(xs)
    n = len(xs)
    return None if not n else (xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2.0)


def consensus(entry, hr_fair_over, asked):
    """Consensus fields for one line from other_lines()'s entry (None = no other book has this line)."""
    out = {"cons_books": None, "cons_stale_books": None, "cons_fair_over_med": None, "cons_fair_over_mean": None, "pin_fair_over": None,
           "hr_vs_consensus": None, "best_over": None, "best_over_book": None, "best_under": None,
           "best_under_book": None}
    if not asked:
        return out
    entry = entry or {"pairs": {}, "best": {}, "stale": 0}
    fairs = {b: odds.fair_two_sided(o, u) for b, (o, u) in entry["pairs"].items()}
    out["cons_books"] = len(fairs)
    out["cons_stale_books"] = entry["stale"]
    if fairs:
        med = _median(list(fairs.values()))
        out["cons_fair_over_med"] = _r(med)
        out["cons_fair_over_mean"] = _r(sum(fairs.values()) / len(fairs))
        out["hr_vs_consensus"] = _r(hr_fair_over - med)
    if PINNACLE in fairs:
        out["pin_fair_over"] = _r(fairs[PINNACLE])
    for side in ("over", "under"):
        if side in entry["best"]:
            out["best_" + side], out["best_%s_book" % side] = entry["best"][side]
    return out


def stale_vs(prev, snap):
    """(cons_move, stale) for a read against the previous read of the same line. None, None without a consensus
    median on both reads."""
    if not prev or prev.get("cons_fair_over_med") is None or snap.get("cons_fair_over_med") is None:
        return None, None
    move = snap["cons_fair_over_med"] - prev["cons_fair_over_med"]
    still = prev.get("over") == snap["over"] and prev.get("under") == snap["under"]
    return _r(move), bool(still and abs(move) >= STALE_MOVE - 1e-9)


def snapshot(inp, f, market, pair, pid, team, opp, home, thin, model_fn, lineup_state, goalie_state, now,
             historical, cons=None):
    v = inp.v
    over, under = pair["over"], pair["under"]
    fair_over = odds.fair_two_sided(over, under)
    s = {"at": f["at"], "pull": f["pull"], "over": over, "under": under, "fair_over": _r(fair_over),
         "fair_over_oh": _r(odds.devig(over, under, "over", "over_hold")),
         "hold": _r(odds.hold(over, under)), "feed_check": pair.get("why"),
         "model_p_over": None, "mu": None,
         "lineup": None, "lineup_page_today": None, "goalie_own": None, "goalie_opp": None,
         "logged_at": None if historical else common.iso(now), "rules": inp.cfg.get("version")}
    s.update(cons or consensus(None, fair_over, False))
    m = model_fn(pair["line"]) if model_fn else None
    if m is not None:
        s["model_p_over"], s["mu"] = _r(m["p_over"]), _r(m["mu"], 3)
    if not historical:
        if market != "saves":
            s["lineup"] = lineups.player_status(lineup_state, team, pid)
        page = ((lineup_state.get("teams") or {}).get(team) or {}).get("page") or {}
        s["lineup_page_today"] = bool(page.get("today"))
        gt = (goalie_state or {}).get("teams") or {}
        own, oth = gt.get(team) or {}, gt.get(opp) or {}
        s["goalie_own"] = {"name": own.get("name"), "status": own.get("status")} if own else None
        s["goalie_opp"] = {"name": oth.get("name"), "status": oth.get("status")} if oth else None
    return s


def pairs_of(mk):
    out = {}
    for o in mk.get("outcomes", []) or []:
        if o.get("pid") is None or o.get("line") is None:
            continue
        p = out.setdefault((o["pid"], o["line"]), {"over": None, "under": None, "name": o.get("name"),
                                                   "team": o.get("team"), "line": o["line"]})
        p[o["side"]] = o["price"]
    return out


def add_reads(doc, inp, odds_doc, games, sched_games, now, lineup_state=None, goalie_state=None, historical=False,
              deadline=None):
    """Fold every pre-puck read of the slate's odds file into the doc. Returns how many rows changed.
    historical (backfill only): the moment is past, so the 'game has not started yet' test uses the read time
    alone and lineup / goalie state is left empty (not known for the past)."""
    rows = {key(r["game_id"], r["market"], r["pid"], r["line"]): r for r in doc["rows"]}
    by_id = {g["id"]: g for g in games}
    changed = 0
    lineup_state = lineup_state or {}
    for f in sorted((odds_doc or {}).get("fetches", []), key=lambda x: x["at"]):
        if deadline is not None and time.monotonic() > deadline:
            break                                            # out of time: the rest is picked up next cycle
        g = by_id.get(f["game_id"])
        if g is None or not f.get("book"):
            continue
        start, at = common.parse_iso(g["start"]), common.parse_iso(f["at"])
        if at >= start:
            continue                                         # a read after puck is never used
        if not historical and sched.started(g, now):
            continue                                         # snapshot rule: nothing written after puck
        for market, mk in sorted((f.get("markets") or {}).items()):
            oth = other_lines(f, market, inp.v)
            for (pid, line), pair in sorted(pairs_of(mk).items()):
                if pair["over"] is None or pair["under"] is None or pair["team"] not in (g["away"], g["home"]):
                    continue                                 # two-way lines of matched players only
                k = key(g["id"], market, pid, line)
                row = rows.get(k)
                if row is not None and common.parse_iso(row["close"]["at"]) >= at:
                    continue                                 # this read (or a newer one) is already in
                team = pair["team"]
                home = team == g["home"]
                opp = g["away"] if home else g["home"]
                fn, mnote = model_over(inp, market, pid, team, opp, home)
                cons = consensus((oth or {}).get((pid, line)), odds.fair_two_sided(pair["over"], pair["under"]),
                                 oth is not None)
                if row is None:
                    ctx = context(inp, sched_games, g, pid, team, market)
                    snap = snapshot(inp, f, market, pair, pid, team, opp, home, ctx["thin"], fn, lineup_state,
                                    goalie_state, now, historical, cons)
                    snap["cons_move"], snap["stale"] = None, None
                    if fn is not None and snap["model_p_over"] is None and market in model.SK:
                        mnote = "no model (position %s)" % ctx["pos"]
                    row = {"game_id": g["id"], "market": market, "pid": pid, "name": pair["name"], "line": line,
                           "src": "backfill" if historical else "live", "model_note": mnote, "ctx": ctx,
                           "n_reads": 1, "open": snap, "close": snap, "stale_events": [], "result": None}
                    rows[k] = row
                    doc["rows"].append(row)
                else:
                    prev = row["close"]
                    snap = snapshot(inp, f, market, pair, pid, team, opp, home, row["ctx"]["thin"], fn,
                                    lineup_state, goalie_state, now, historical, cons)
                    snap["cons_move"], snap["stale"] = stale_vs(prev, snap)
                    if snap["stale"]:
                        row.setdefault("stale_events", []).append(
                            {"at": snap["at"], "from_at": prev.get("at"), "over": snap["over"], "under": snap["under"],
                             "cons_from": prev["cons_fair_over_med"], "cons_to": snap["cons_fair_over_med"]})
                    row["close"] = snap
                    row["n_reads"] += 1
                changed += 1
    return changed


# ---------------------------------------------------------------- results (boxscore, as grade.py reads it)
def fill_results(doc, now, cfg, sched_games, box_fn=None, deadline=None, budget=None):
    """Add `result` to rows of finished games. Returns (rows graded, notes).
    deadline (time.monotonic) and budget ({"fetch": n}: boxscores not already read this run, decremented in
    place) bound the work per cycle."""
    live_fn = box_fn is None
    box_fn = box_fn or (lambda gid: nhl.boxscore(gid, quick=True))
    by_game = {}
    for r in doc["rows"]:
        if r.get("result") is None:
            by_game.setdefault(r["game_id"], []).append(r)
    n, notes, pbp_cache = 0, [], {}
    for gid, rows in sorted(by_game.items()):
        g = (sched_games or {}).get(str(gid)) or {}
        start = common.parse_iso(g.get("start") or rows[0]["ctx"]["start"])
        if start is None or now < start:
            continue
        postponed = g.get("sched") in ("PPD", "CNCL")
        if not postponed and g.get("state") != "OFF" and now < start + timedelta(hours=RESULT_WAIT_HOURS):
            continue                                         # not final yet: no boxscore call
        if not postponed and not (live_fn and nhl.cached("boxscore", gid)):
            if (deadline is not None and time.monotonic() > deadline) or (budget is not None and budget["fetch"] <= 0):
                notes.append("results wait for the next cycle")
                break
            if budget is not None:
                budget["fetch"] -= 1
        box = None if postponed else box_fn(gid)
        if not postponed and box is None:
            notes.append("boxscore for %s not available" % gid)
            continue
        if box is not None and box.get("gameScheduleState") in ("PPD", "CNCL"):
            postponed = True
        if not postponed and box.get("gameState") != "OFF":
            continue
        parsed = None if postponed else grade.read_box(box)
        if not postponed and parsed is None:
            notes.append("boxscore for %s is missing player stats" % gid)
            continue
        at = common.iso(now)
        for r in rows:
            if postponed:
                r["result"] = {"actual": None, "over": "VOID", "under": "VOID", "note": "game postponed", "at": at}
                n += 1
                continue
            players, teams_ = parsed
            p = players.get(r["pid"])
            if p is None or p.get("toi") in (None, "00:00", "0:00"):
                r["result"] = {"actual": None, "over": "VOID", "under": "VOID", "note": "did not play", "at": at}
                n += 1
                continue
            note = None
            if r["market"] == "shots" and not grade.shots_trusted(gid, p["team"], teams_, pbp_cache):
                if now < start + timedelta(hours=cfg["ops"]["grade_shot_check_hold_hours"]):
                    continue                                 # same wait as grade.py
                note = "team shot total did not match the player rows"
            field = grade.FIELD.get(r["market"])
            actual = p.get(field) if field else None
            if actual is None:
                continue
            r["result"] = {"actual": actual, "over": grade.result_for("over", r["line"], actual),
                           "under": grade.result_for("under", r["line"], actual), "toi": p.get("toi"), "at": at}
            if note:
                r["result"]["note"] = note
            n += 1
    return n, notes


# ---------------------------------------------------------------- the run.py step
def step(now, slate, cfg, inp, sched_cache, games):
    """Called by run.py after odds, engine and grade. Returns a step result dict. Never raises (the caller
    also wraps it)."""
    sched_games = (sched_cache or {}).get("games", {})
    deadline = time.monotonic() + BUDGET_S
    notes = []
    wrote = 0
    doc = load(slate)
    before = serialize(doc)
    odds_doc = common.read_json(odds.odds_path(slate))
    if odds_doc and games and inp is not None:
        added = add_reads(doc, inp, odds_doc, games, sched_games, now, inp.lineup_state or lineups.load(slate),
                          goalies.load(slate), deadline=deadline)
        if added:
            notes.append("%d line read(s) logged" % added)
    graded, bad = fill_results(doc, now, cfg, sched_games, deadline=deadline, budget={"fetch": FETCH_CAP})
    if graded:
        notes.append("%d graded" % graded)
    notes += bad[:2]
    if doc["rows"] and serialize(doc) != before:
        doc["updated_at"] = common.iso(now)
        save(doc)
        wrote += 1
    # results for the last two slates (late games finish after the 5 AM rollover only in theory, but a
    # boxscore that was late or a cycle that failed must still be filled in)
    d = date.fromisoformat(slate)
    old_budget = {"fetch": OLD_FETCH_CAP}
    for back in range(1, KEEP_RESULT_DAYS):
        if old_budget["fetch"] <= 0 or time.monotonic() > deadline:
            break
        old_slate = (d - timedelta(days=back)).isoformat()
        old = common.read_json(path(old_slate))
        if not isinstance(old, dict) or not any(r.get("result") is None for r in old.get("rows", [])):
            continue
        old = load(old_slate)
        g2, bad2 = fill_results(old, now, cfg, sched_games, deadline=deadline, budget=old_budget)
        if g2:
            old["updated_at"] = common.iso(now)
            save(old)
            wrote += 1
            notes.append("%s: %d graded" % (old_slate, g2))
        notes += bad2[:1]
    if not notes:
        return {"status": "skipped", "note": "nothing new"}
    return {"status": "ok", "note": "; ".join(notes)}
