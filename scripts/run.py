#!/usr/bin/env python3
"""run.py: the one entry point. The timer runs `python scripts/run.py` and this file decides what is due.

    python scripts/run.py                    do whatever is due right now
    python scripts/run.py --only grade       run one step (schedule, stats, odds, lineups, engine, grade, record)
    python scripts/run.py --rebuild-record   rebuild record.json and the month files from the event log, nothing else
    python scripts/run.py --dry-run          run everything against a throwaway copy of data/, spend no credits,
                                             and print what would have changed
    python scripts/run.py --explain          print every line the engine priced, its numbers and why it did or
                                             did not qualify (reads files only; writes nothing)
    python scripts/run.py --build-seed [DIR] build last season's stats file (from saved NHL files in DIR, or the API)

Steps, in order, each allowed to fail without stopping the others:
    rules     data/rules.json from config/rules.json
    schedule  today's games and puck times
    stats     this season's game rows; which teams are complete
    odds      Hard Rock prices, if a pull is due and the budget allows
    lineups   Daily Faceoff, for games close to puck drop
    engine    lock / pull / keep shown picks, add new ones, parlays  -> appends to the Record
    grade     results for games that are final                       -> appends to the Record
    slate     data/slate.json
    record    data/record.json and month files
    status    data/status.json
Safe to run twice in a row: every decision is made from files on disk, and every write is temp + rename.
"""
import os
import shutil
import sys
import tempfile
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import common      # noqa: E402
import engine      # noqa: E402
import grade       # noqa: E402
import lineups     # noqa: E402
import names       # noqa: E402
import nhl         # noqa: E402
import odds        # noqa: E402
import record      # noqa: E402
import sched       # noqa: E402
import stats       # noqa: E402

STEPS = ["rules", "schedule", "stats", "odds", "lineups", "engine", "grade", "slate", "record", "status"]


class Run:
    def __init__(self, cfg, now, only=None, dry_run=False):
        self.cfg, self.now, self.only, self.dry_run = cfg, now, only, dry_run
        self.slate = common.slate_date(now, cfg["ops"]["rollover_hour"])
        self.steps = []
        self.season = None
        self.cache = None            # schedule cache
        self.games = []              # today's regular-season games
        self.other_games = False
        self.started = {}
        self.behind, self.stats_through, self.stats_built_at = {}, None, None
        self.store, self.stats_missing = None, False
        self.people_by_team = {}
        self.odds_res = None
        self.lineup_state = None
        self.events = None
        self.extra = None
        self.inp = None
        self.new_events = 0
        self.wrote_slate = False
        self.paused = {}
        self.odds_doc = None

    # ---- helpers
    def wants(self, step):
        return self.only is None or step in self.only

    def step(self, name, fn):
        if not self.wants(name):
            return
        try:
            out = fn() or {}
            self.steps.append({"step": name, "status": out.get("status", "ok"), "note": out.get("note", "")})
        except Exception as e:                              # one bad step never takes the run down
            self.steps.append({"step": name, "status": "failed", "note": common.short_err(e)})
            common.log("step %s failed: %s" % (name, common.short_err(e)))

    def failed_step(self):
        return next((s["step"] for s in self.steps if s["status"] == "failed"), None)

    # ---- steps
    def do_rules(self):
        out = {"version": self.cfg["version"], "updated": self.cfg["updated"],
               "values": self.cfg["values"], "ui": self.cfg["ui"]}
        if common.read_json(common.dpath("rules.json")) != out:
            common.write_json(common.dpath("rules.json"), out)
            return {"note": "rules.json written"}
        return {"status": "skipped", "note": "unchanged"}

    def load_schedule(self):
        """Use the saved schedule when the schedule step did not run (or failed)."""
        if self.cache is None:
            self.cache = common.read_json(sched.path())
        if self.cache:
            self.season = self.cache.get("season")
            self.games = sched.games_on(self.cache, self.slate)
            self.other_games = bool(sched.games_on(self.cache, self.slate, regular_only=False)) and not self.games
            self.started = {g["id"]: sched.started(g, self.now) for g in self.games}

    def do_schedule(self):
        self.cache, res = sched.update(self.now, self.slate)
        self.load_schedule()
        if self.cache and res["status"] == "ok":
            res["note"] = "%d game(s) today" % len(self.games)
        return res

    def do_stats(self):
        self.load_schedule()
        if not self.cache or not self.season:
            return {"status": "skipped", "note": "no schedule"}
        last = self.season - 10001
        notes = []
        if stats.find_seed(last) is None:
            notes.append(stats.build_seed(last))            # one-time, about 2 minutes, from the NHL API
        res = stats.update_season(self.season, self.cache["season_start"], list(self.cache["games"].values()),
                                  self.now, self.cfg["ops"])
        if notes:
            res["note"] = "; ".join(notes + [res["note"]])
        return res

    def load_stats(self):
        if self.store is not None or not self.cache or not self.season:
            return
        self.store, problems = stats.load(self.season)
        self.stats_missing = bool(problems)
        self.stats_problems = problems
        self.behind, self.stats_through, self.stats_built_at = stats.team_status(
            self.season, list(self.cache["games"].values()), self.slate)

    def people_for(self, team):
        """NHL players for one team: today's roster plus anyone with a game for the team this season."""
        if team in self.people_by_team:
            return self.people_by_team[team]
        path = common.dpath("state", "rosters.json")
        saved = common.read_json(path, {}) or {}
        if saved.get("date") != self.slate:
            saved = {"date": self.slate, "teams": {}}
        ppl = saved["teams"].get(team)
        if ppl is None:
            ppl = nhl.roster(team)
            if ppl:
                saved["teams"][team] = ppl
                common.write_json(path, saved, pretty=False)
        ppl = list(ppl or [])
        self.load_stats()
        have = {p["id"] for p in ppl}
        if self.store:
            for pid, rows in self.store.skaters.items():
                if pid in have or not rows or rows[-1]["team"] != team or rows[-1]["season"] != self.season:
                    continue
                nm = (self.store.players.get(pid) or {}).get("name", "")
                first, _, last = nm.partition(" ")
                if last:
                    ppl.append({"id": pid, "first": first, "last": last, "team": team,
                                "pos": self.store.players[pid]["pos"]})
        self.people_by_team[team] = ppl
        return ppl

    def matcher_for(self, game):
        return names.Matcher(self.people_for(game["away"]) + self.people_for(game["home"]))

    def load_events(self):
        if self.events is None:
            self.events = record.read_events()
        return self.events

    def do_odds(self):
        self.load_schedule()
        if not self.cache:
            return {"status": "skipped", "note": "no schedule"}
        live = {}
        for it in record.fold(self.load_events()).values():
            if it["slate"] == self.slate and it["kind"] == "single" and record.is_open(it):
                live.setdefault(it["shown"]["game_id"], set()).add(it["shown"]["market"])
        left = sched.games_left_this_month(self.cache, self.slate)
        self.odds_res = odds.run_pulls(self.now, self.slate, self.games, left, self.cfg, self.matcher_for,
                                       live, self.started, dry_run=self.dry_run)
        return {"status": self.odds_res["status"], "note": self.odds_res["note"]}

    def do_lineups(self):
        self.load_schedule()
        if not self.games:
            return {"status": "skipped", "note": "no games today"}
        res = lineups.check(self.now, self.slate, self.games, self.started, self.cfg["ops"], self.people_for)
        self.lineup_state = res["state"]
        return {"status": res["status"], "note": res["note"]}

    def build_inputs(self):
        self.load_schedule()
        self.load_stats()
        if self.lineup_state is None:
            self.lineup_state = lineups.load(self.slate)
        doc = common.read_json(odds.odds_path(self.slate))
        view = odds.build_view(doc, self.cfg)
        people = {}
        for g in self.games:
            for t in (g["away"], g["home"]):
                for p in self.people_for(t):
                    people[p["id"]] = p
        day = odds.load_day(self.slate)
        self.odds_doc, self.view = doc, view
        self.inp = engine.Inputs(self.cfg, self.now, self.slate, self.season, self.games,
                                 self.store or stats.Store(), self.behind, view, self.lineup_state, people,
                                 self.load_events(), plan=day.get("plan"), odds_day=day)
        return self.inp

    def do_engine(self):
        self.load_schedule()
        if not self.cache:
            return {"status": "skipped", "note": "no schedule"}
        inp = self.build_inputs()
        self.paused = engine.paused_markets(inp.events, self.cfg)
        # stats missing, or behind for half the slate or more: keep shown picks, add none
        block = self.stats_missing or self.too_far_behind()
        new, self.extra = engine.evaluate(inp, paused=self.paused, block_new=block)
        record.append(new)
        self.events = inp.events + new
        self.new_events += len(new)
        shown = sum(1 for e in new if e["t"] == "shown")
        return {"note": "%d new event(s), %d newly shown" % (len(new), shown) if new else "no change"}

    def too_far_behind(self):
        if not self.games:
            return False
        hit = sum(1 for g in self.games if g["away"] in self.behind or g["home"] in self.behind)
        return hit * 2 >= len(self.games)

    def do_grade(self):
        self.load_schedule()
        new, notes = grade.grade(self.load_events(), self.now, self.cfg, (self.cache or {}).get("games", {}))
        record.append(new)
        self.events = self.events + new
        self.new_events += len(new)
        n = sum(1 for e in new if e["t"] == "graded")
        note = "%d graded" % n if n else "nothing to grade"
        if notes:
            note += "; " + "; ".join(notes[:3])
        return {"status": "ok" if n else "skipped", "note": note}

    # ---- facts shared by slate.json and status.json
    def facts(self, last_run):
        cfg, v, now = self.cfg, self.cfg["values"], self.now
        day = odds.load_day(self.slate)
        plan = day.get("plan")
        doc = getattr(self, "odds_doc", None) or common.read_json(odds.odds_path(self.slate)) or {}
        fetches = [f for f in doc.get("fetches", []) if f.get("book") and f.get("markets")]
        prices_at = max((f["at"] for f in fetches), default=None)
        keys = odds.load_keys()
        led = common.read_json(odds.ledger_path(), {}) or {}
        key_state = led.get("keys", [])
        fixture = bool(odds.fixture_dir())
        no_keys = not keys and not fixture
        pool_known = any(k.get("left") is not None for k in key_state)
        pool_left = sum(k.get("left") or 0 for k in key_state) if pool_known else None
        left_games, sched_days = sched.games_left_this_month(self.cache, self.slate) if self.cache else (0, [])
        banners, sub = [], None
        open_games = [g for g in self.games if not self.started.get(g["id"])]
        times = odds.pull_times(self.slate, self.games, v) if self.games else None
        priced = {f["game_id"] for f in fetches}

        # prices_state
        if fetches:
            ps = "limited" if (plan and plan["tier"] <= 1) or day.get("skipped") else "ok"
        elif no_keys:
            ps = "not_yet"
        elif pool_known and (pool_left == 0 or (plan and plan["budget_today"] == 0)):
            ps = "pool_empty"
        elif day.get("last_fail_at") and times and now >= times["A"]:
            ps = "feed_down"
        else:
            ps = "not_yet"

        # the pool banner (Sharp standard section 2 table)
        if self.games:
            n_all = len(self.games)
            a_time = common.fmt_time(common.parse_iso(prices_at)) if prices_at else common.fmt_time(times["A"])
            if no_keys:
                banners.append({"level": "warn", "text": "Hard Rock prices are not connected: no odds keys are set."})
                sub = "No odds keys are set, so prices cannot be read."
            elif plan is None:
                sub = "Waiting to reach the odds feed."
            elif plan["tier"] == 0:
                n = len(priced) if fetches else min(plan["budget_today"], n_all)
                if plan["budget_today"] == 0 and not fetches:
                    banners.append({"level": "stop", "text": "No Hard Rock prices today, odds keys are used up. No picks."})
                else:
                    banners.append({"level": "warn", "text": "Hard Rock prices limited: %d of %d games, shots only. "
                                                              "Odds keys nearly out." % (n, n_all)})
            elif plan["tier"] == 1:
                banners.append({"level": "warn", "text": "Shots only today. One price check at %s. Odds keys low." % a_time})
            elif plan["tier"] == 2:
                verb = "Prices checked at" if prices_at else "Prices are checked at"
                banners.append({"level": "info", "text": "%s %s, and again before each game for live picks." % (verb, a_time)})
            if sub is None and not fetches and times:
                if now < times["A"]:
                    sub = "First read is due at %s." % common.fmt_time(times["A"])
                elif open_games:
                    sub = "The first read is running late."
        if ps == "feed_down":
            banners.append({"level": "warn", "text": "The odds feed did not answer at %s. Trying again on the next update."
                                                     % common.fmt_time(common.parse_iso(day["last_fail_at"]))})
        fetched = odds.fetched_map(day)
        budget_ok = bool(plan) and plan["budget_today"] - sum(e["cost"] for e in led.get("spent", [])
                                                              if e["date"] == self.slate) > 0
        nxt = odds.next_read_at(now, self.games, plan["tier"], v, fetched, self.started, budget_ok) if plan else None

        # lineups
        ls = self.lineup_state or lineups.load(self.slate)
        lineups_at = ls.get("last_ok_at")
        lineup_note = None
        if ls.get("last_try_at") and not lineups_at:
            lineup_note = "Lineups not checked: Daily Faceoff did not answer."
        elif lineups_at:
            today_pages = sum(1 for t in ls["teams"].values() if (t.get("page") or {}).get("today"))
            lineup_note = "%d of %d team line pages are dated today." % (today_pages, len(ls["teams"]))

        if not last_run["ok"]:
            banners.insert(0, {"level": "warn", "text": "Part of the last update failed at %s (%s). Some of what is below may be older."
                                                        % (common.fmt_time(now), last_run["failed_step"])})
        unmatched = sorted({n for f in doc.get("fetches", []) for n in f.get("unmatched", [])})
        return {
            "prices_state": ps, "prices_at": prices_at, "next_price_read_at": common.iso(nxt) if nxt else None,
            "stats_built_at": self.stats_built_at, "stats_through": self.stats_through,
            "stats_state": "behind" if (self.stats_missing or self.too_far_behind()) else "ok",
            "stats_missing": self.stats_missing, "lineups_at": lineups_at, "lineups_note": lineup_note,
            "last_run": last_run, "pool": odds.pool_summary(pool_left, len(key_state), plan, sched_days, cfg),
            "banners": banners, "not_yet_sub": sub, "other_games": self.other_games,
            "paused": getattr(self, "paused", {}),
            # for status.json only
            "_keys": [{"n": k["n"], "left": k.get("left")} for k in key_state], "_plan": plan,
            "_spent_today": sum(e["cost"] for e in led.get("spent", []) if e["date"] == self.slate),
            "_unmatched": unmatched, "_unknown_teams": day.get("unknown_teams", []),
            "_lineup_unmatched": sorted({n for t in ls.get("teams", {}).values()
                                         for n in (t.get("page") or {}).get("unmatched", [])}),
        }

    def do_slate(self, facts):
        if self.inp is None or self.extra is None:
            return {"status": "skipped", "note": "engine did not run"}
        self.inp.facts = facts
        new = engine.build_slate(self.inp, self.events, self.extra)
        path = common.dpath("slate.json")
        old = common.read_json(path)
        if old and _essence(old) == _essence(new) and not self._heartbeat_due(old.get("generated_at")):
            self.wrote_slate = True                         # the file on disk already says exactly this
            return {"status": "skipped", "note": "unchanged"}
        common.write_json(path, new)
        self.wrote_slate = True
        return {"note": "%d open pick(s)" % sum(1 for p in new["picks"] if p["rank"])}

    def _heartbeat_due(self, stamp):
        last = common.parse_iso(stamp) if stamp else None
        return last is None or self.now < last or \
            self.now - last >= timedelta(minutes=self.cfg["ops"]["heartbeat_min"])

    def do_record(self):
        changed = record.write_views(self.cfg, self.load_events())
        return {"status": "ok" if changed else "skipped", "note": ", ".join(changed) or "unchanged"}

    def write_status(self, facts, started_at):
        failed = self.failed_step()
        path = common.dpath("status.json")
        old = common.read_json(path) or {}
        src = dict(nhl.SOURCES)
        src["odds"] = dict(odds.SOURCE)
        src["dailyfaceoff"] = dict(lineups.SOURCE)
        # each source's most recent result: one not needed this run keeps what it said last time
        reached = dict((old.get("sources") or {}))
        for k, s in src.items():
            if s["ok"] or s["failed"]:
                reached[k] = "ok" if not s["failed"] else "failed" if not s["ok"] else "partly"
        for k in ("nhl_web", "nhl_stats", "odds", "dailyfaceoff"):
            reached.setdefault(k, "not tried")
        plan = facts.get("_plan") or {}
        st = {
            "ok": failed is None, "slate_date": self.slate, "started_at": common.iso(started_at),
            "finished_at": common.iso(common.now() if not os.environ.get("PC_NOW") else self.now),
            "last_ok_at": common.iso(self.now) if failed is None else old.get("last_ok_at"),
            "failed_step": failed, "steps": self.steps, "sources": reached,
            "keys": facts.get("_keys", []), "pool_total": facts["pool"]["pulls_left"],
            "allowance": plan.get("allowance"), "tier": plan.get("tier"), "budget_today": plan.get("budget_today"),
            "budget_used_today": facts.get("_spent_today", 0),
            "prices_state": facts["prices_state"], "prices_at": facts["prices_at"],
            "next_price_read_at": facts["next_price_read_at"],
            "unmatched_names": facts.get("_unmatched", []), "unknown_teams": facts.get("_unknown_teams", []),
            "lineup_unmatched_names": facts.get("_lineup_unmatched", []),
            "excluded_teams": [{"team": t, "reason": r} for t, r in sorted(self.behind.items())
                               if any(t in (g["away"], g["home"]) for g in self.games)],
            "stats_through": self.stats_through, "lineups_at": facts["lineups_at"], "lineups_note": facts["lineups_note"],
            "games_today": len(self.games), "record_events": len(self.events) if self.events is not None else None,
            "odds_notes": sorted(set((self.odds_res or {}).get("errors", [])))[:6],
        }
        if old and _essence(old) == _essence(st) and not self._heartbeat_due(old.get("finished_at")):
            return
        common.write_json(path, st)


def _essence(doc):
    """A file with its clock stamps removed: used to tell 'something changed' from 'only time passed'."""
    d = common.dumps(doc, False)
    import json
    d = json.loads(d)
    for k in ("generated_at", "started_at", "finished_at", "last_ok_at"):
        d.pop(k, None)
    if isinstance(d.get("steps"), list):                    # a step that merely had nothing to do is not news
        d["steps"] = [(s["step"], s["note"]) for s in d["steps"] if s["status"] == "failed"]
    if isinstance(d.get("sources"), dict):                  # ... and neither is a source nobody needed this run
        d["sources"] = sorted(k for k, v in d["sources"].items() if v in ("failed", "partly"))
    if isinstance(d.get("status"), dict):
        lr = d["status"].get("last_run")
        if isinstance(lr, dict):
            lr.pop("at", None)
    return d


def run(only=None, dry_run=False):
    cfg = common.load_config()
    engine.check_config(cfg)
    now = common.now()
    started_at = now
    odds.load_keys()                                        # registers the keys so nothing can print them
    nhl.SOURCES.clear()
    for src in (odds.SOURCE, lineups.SOURCE):
        src.update(ok=0, failed=0)
    r = Run(cfg, now, only, dry_run)
    r.step("rules", r.do_rules)
    r.step("schedule", r.do_schedule)
    r.step("stats", r.do_stats)
    r.step("odds", r.do_odds)
    r.step("lineups", r.do_lineups)
    r.step("engine", r.do_engine)
    r.step("grade", r.do_grade)
    failed = r.failed_step()
    last_run = {"ok": failed is None, "at": common.iso(now), "failed_step": failed}
    facts = None
    try:
        r.load_schedule()
        r.load_stats()
        facts = r.facts(last_run)
    except Exception as e:
        r.steps.append({"step": "facts", "status": "failed", "note": common.short_err(e)})
    if facts is not None:
        r.step("slate", lambda: r.do_slate(facts))
    if not r.wrote_slate and r.failed_step() and r.wants("slate"):
        _mark_slate_failed(now, r.failed_step())            # old slate stays, with the truth on top
    r.step("record", r.do_record)
    if facts is None:
        facts = {"pool": {"pulls_left": None}, "prices_state": None, "prices_at": None, "next_price_read_at": None,
                 "lineups_at": None, "lineups_note": None}
    try:
        r.write_status(facts, started_at)
    except Exception as e:
        common.log("status write failed: %s" % common.short_err(e))
        raise
    for s in r.steps:
        common.log("%-9s %-8s %s" % (s["step"], s["status"], s["note"]))
    return r


def _mark_slate_failed(now, step):
    """The slate could not be rebuilt: keep the old one but tell the page the truth."""
    path = common.dpath("slate.json")
    sl = common.read_json(path)
    if not isinstance(sl, dict) or "status" not in sl:
        return
    mark = "The last update failed"
    sl["status"]["last_run"] = {"ok": False, "at": common.iso(now), "failed_step": step}
    shown = common.fmt_time(common.parse_iso(sl["generated_at"])) if sl.get("generated_at") else "earlier"
    sl["banners"] = [{"level": "stop", "text": "%s at %s (%s). Showing %s data." % (mark, common.fmt_time(now), step, shown)}] + \
                    [b for b in sl.get("banners", []) if not str(b.get("text", "")).startswith(mark)]
    common.write_json(path, sl)


def dry_run_main():
    """Copy data/ to a throwaway folder, run there with paid calls switched off, report, clean up."""
    src = common.data_dir()
    tmp = tempfile.mkdtemp(prefix="pc_dry_")
    try:
        dst = os.path.join(tmp, "data")
        if os.path.isdir(src):
            shutil.copytree(src, dst)
        else:
            os.makedirs(dst)
        os.environ["PC_DATA_DIR"] = dst
        r = run(dry_run=True)                               # dry_run: the odds step makes no paid call
        print("DRY RUN (nothing in %s was changed, no odds credits spent)" % src)
        print("  new Record events: %d" % r.new_events)
        sl = common.read_json(os.path.join(dst, "slate.json")) or {}
        for p in sl.get("picks", []):
            print("  %s %s %s %s  chance %s needs %s  [%s]" % (
                p.get("rank") or "-", p["player"], p["bet"], common.fmt_price(p["price"]), p["p"], p["breakeven"],
                "pulled" if p["pulled"] else p["state"]))
        if sl.get("empty"):
            print("  empty: %s %s" % (sl["empty"]["text"], sl["empty"].get("sub") or ""))
        for b in sl.get("banners", []):
            print("  banner: %s" % b["text"])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return 0


def main(argv):
    common.install_scrubbers()
    if "--rebuild-record" in argv:
        changed = record.write_views(common.load_config())
        print("record rebuilt from the log: %s" % (", ".join(changed) or "no file changed"))
        return 0
    if "--build-seed" in argv:
        i = argv.index("--build-seed")
        cache_dir = argv[i + 1] if len(argv) > i + 1 and not argv[i + 1].startswith("--") else None
        wk = nhl.schedule_week(common.slate_date(common.now()))
        season = next((g["season"] for g in (wk or {}).get("games", [])), None)
        if not season:
            print("could not read the current season from the NHL schedule")
            return 1
        print(stats.build_seed(season - 10001, cache_dir))
        return 0
    if "--dry-run" in argv:
        return dry_run_main()
    if "--explain" in argv:
        r = Run(common.load_config(), common.now())
        rows = engine.explain(r.build_inputs())
        print("%-22s %-4s %-6s %4s %-5s %6s | %6s %6s %6s %6s %6s %7s %7s | %-7s %s" % (
            "player", "team", "market", "line", "side", "price", "model", "adj", "fair", "p", "b", "margin", "gap",
            "lineup", "verdict"))
        for x in sorted(rows, key=lambda x: -(x.get("margin", -9))):
            print("%-22s %-4s %-6s %4s %-5s %6s | %6s %6s %6s %6s %6s %7s %7s | %-7s %s" % (
                x["player"][:22], x["team"], x["market"], x["line"], x["side"], common.fmt_price(x["price"]),
                x.get("model", ""), x.get("model_adj", ""), x.get("fair", ""), x.get("p", ""), x.get("b", ""),
                x.get("margin", ""), x.get("gap", ""), x["lineup"], x["verdict"]))
        return 0
    only = None
    if "--only" in argv:
        only = set()
        for i, a in enumerate(argv):
            if a == "--only" and i + 1 < len(argv):
                only |= set(argv[i + 1].split(","))
        bad = only - set(STEPS)
        if bad:
            print("unknown step(s): %s. Steps: %s" % (", ".join(sorted(bad)), ", ".join(STEPS)))
            return 2
        only |= {"status"}
    run(only=only)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
