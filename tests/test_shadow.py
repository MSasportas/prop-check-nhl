"""Shadow log, lineup history, market menu and the every-game closing read (TEAM.md section 7 items 16-17)."""
import json
import os
import subprocess
import tempfile
import unittest

import helpers
import world
from helpers import Sim

import common
import engine
import lineup_backfill
import lineup_history
import lineups
import market_menu
import odds
import run
import shadow
import shadow_backfill

UPD = "2026-10-11T17:00:00Z"
CAR_PHI, VAN_NYR = 2026020901, 2026020902


def rows_of(s, slate=world.SLATE):
    doc = common.read_json(s.path("shadow", "%s.json" % slate))
    return doc["rows"] if doc else []


def row(s, team, i, line, market="shots"):
    pid = world.pid_of(team, i)
    return next((r for r in rows_of(s) if r["pid"] == pid and r["line"] == line and r["market"] == market), None)


class ShadowDay(unittest.TestCase):
    def setUp(self):
        self.s = Sim(pool=12)
        self.s.at("09:00")

    def tearDown(self):
        self.s.close()

    def test_every_two_way_line_logged_with_model_and_context(self):
        s = self.s
        s.set_odds("CAR", "PHI", [s.line("CAR", 1, "shots", 2.5, 0.0), s.line("PHI", 2, "shots", 1.5, 0.05, "under"),
                                  ("player_shots_on_goal", world.name_of("CAR", 3), 3.5, -120, None)], UPD)
        s.at("13:02")
        r = row(s, "CAR", 1, 2.5)
        self.assertIsNotNone(r)
        self.assertIsNone(row(s, "CAR", 3, 3.5), "a one-sided line is not two-way")
        m = s.inputs().model(world.pid_of("CAR", 1), "CAR", "PHI", False, "shots", 2.5)
        self.assertAlmostEqual(r["open"]["model_p_over"], m["p_over"], places=5)       # the engine's own model
        self.assertAlmostEqual(r["open"]["fair_over"], odds.fair_two_sided(r["open"]["over"], r["open"]["under"]), 5)
        e = engine.edge(m["p_over"], "over", False, r["open"]["over"], r["open"]["under"], helpers.cfg()["values"])
        self.assertAlmostEqual(r["open"]["p_over"], e["p"], places=5)
        self.assertEqual(r["open"], r["close"])
        self.assertEqual((r["n_reads"], r["src"], r["result"]), (1, "live", None))
        c = r["ctx"]
        self.assertEqual((c["home"], c["team"], c["opp"], c["pos"]), (False, "CAR", "PHI", "F"))
        self.assertEqual((c["team_b2b"], c["team_rest_days"]), (False, 2))           # CAR last played Oct 8
        self.assertEqual(c["toi_last5"], 19.5)
        self.assertIsInstance(c["n_hist"], int)
        self.assertEqual(r["open"]["lineup"], "unknown")
        self.assertFalse(r["open"]["lineup_page_today"])
        # internal only: never on the page, never in the Record
        self.assertNotIn("shadow", json.dumps(s.slate()))
        self.assertEqual(s.log_bytes(), b"")

    def test_close_is_last_read_before_puck_and_open_never_changes(self):
        s = self.s
        s.set_odds("CAR", "PHI", [("player_shots_on_goal", world.name_of("CAR", 1), 2.5, -120, -110)], UPD)
        s.at("13:02")
        first = row(s, "CAR", 1, 2.5)["open"]
        s.set_odds("CAR", "PHI", [("player_shots_on_goal", world.name_of("CAR", 1), 2.5, -140, 110)], "2026-10-11T22:14:00Z")
        s.at("18:15")                                         # 45 min read (lineups unconfirmed: B fallback + C in one)
        r = row(s, "CAR", 1, 2.5)
        self.assertEqual(r["open"], first)
        self.assertEqual((r["close"]["at"], r["close"]["over"], r["n_reads"]), ("2026-10-11T18:15:00-04:00", -140, 2))
        before = rows_of(s)
        s.set_odds("CAR", "PHI", [("player_shots_on_goal", world.name_of("CAR", 1), 2.5, -170, 130)], "2026-10-11T23:04:00Z")
        s.at("19:05")                                         # after puck: nothing about this game changes
        after = [x for x in rows_of(s) if x["game_id"] == CAR_PHI]
        self.assertEqual(after, [x for x in before if x["game_id"] == CAR_PHI])

    def test_results_after_the_game_is_off(self):
        s = self.s
        s.set_odds("CAR", "PHI", [("player_shots_on_goal", world.name_of("CAR", 1), 2.5, -120, -110),
                                  ("player_shots_on_goal", world.name_of("CAR", 2), 1.5, -120, -110),
                                  ("player_shots_on_goal", world.name_of("PHI", 4), 1.5, -120, -110)], UPD)
        s.at("13:02")
        s.set_box(CAR_PHI, "CAR", "PHI", {world.pid_of("CAR", 1): (4, 0, 0), world.pid_of("CAR", 2): (1, 0, 0)},
                  missing=(world.pid_of("PHI", 4),))
        s.set_states({CAR_PHI: "OFF"})
        s.at("22:30")
        self.assertEqual(row(s, "CAR", 1, 2.5)["result"]["over"], "W")
        self.assertEqual(row(s, "CAR", 1, 2.5)["result"]["under"], "L")
        self.assertEqual(row(s, "CAR", 1, 2.5)["result"]["actual"], 4)
        self.assertEqual(row(s, "CAR", 2, 1.5)["result"]["over"], "L")
        self.assertEqual(row(s, "PHI", 4, 1.5)["result"]["over"], "VOID")
        self.assertNotIn(b"shadow", s.log_bytes())
        shown = row(s, "CAR", 1, 2.5)
        s.at("22:40")
        self.assertEqual(row(s, "CAR", 1, 2.5), shown, "graded once")

    def test_a_failing_shadow_step_never_fails_the_run(self):
        s = self.s
        real = shadow.step
        shadow.step = lambda *a, **k: 1 / 0
        try:
            s.at("13:02")
        finally:
            shadow.step = real
        st = s.status()
        self.assertTrue(st["ok"])
        self.assertIsNone(st["failed_step"])
        step = next(x for x in st["steps"] if x["step"] == "shadow")
        self.assertEqual(step["status"], "warn")
        self.assertIn("ZeroDivisionError", step["note"])
        self.assertIsNotNone(s.slate())


class ShadowBudget(unittest.TestCase):
    def setUp(self):
        self.s = Sim(pool=12)
        self.s.at("09:00")

    def tearDown(self):
        self.s.close()

    def test_grade_and_shadow_read_each_boxscore_once_per_run(self):
        import nhl
        s = self.s
        s.set_odds("CAR", "PHI", [s.line("CAR", 1, "shots", 2.5, 0.14), s.line("PHI", 2, "shots", 1.5, 0.0)], UPD)
        s.at("13:02")
        self.assertTrue(any(e["t"] == "shown" for e in s.events()))
        s.set_box(CAR_PHI, "CAR", "PHI", {})
        s.set_states({CAR_PHI: "OFF"})
        real, paths = nhl.web, []
        nhl.web = lambda path, quick=False: paths.append(path) or real(path, quick)
        try:
            s.at("22:30")
        finally:
            nhl.web = real
        self.assertTrue(any(e["t"] == "graded" for e in s.events()))
        self.assertTrue(row(s, "PHI", 2, 1.5)["result"])
        self.assertEqual(paths.count("gamecenter/%s/boxscore" % CAR_PHI), 1)

    def test_out_of_time_does_nothing_and_never_fails(self):
        s = self.s
        s.set_odds("CAR", "PHI", [("player_shots_on_goal", world.name_of("CAR", 1), 2.5, -120, -110)], UPD)
        real = shadow.BUDGET_S
        shadow.BUDGET_S = -1
        try:
            s.at("13:02")
        finally:
            shadow.BUDGET_S = real
        self.assertEqual(rows_of(s), [])
        self.assertTrue(s.status()["ok"])
        s.at("13:12")                                         # next cycle catches up
        self.assertIsNotNone(row(s, "CAR", 1, 2.5))

    def test_fetch_cap(self):
        mk = lambda gid: {"game_id": gid, "market": "shots", "pid": 1, "line": 1.5,
                          "ctx": {"start": "2026-10-10T19:00:00-04:00"}, "result": None}
        doc = {"rows": [mk(1), mk(2), mk(3)]}
        sg = {str(g): {"start": "2026-10-10T19:00:00-04:00", "state": "OFF", "sched": "OK"} for g in (1, 2, 3)}
        calls, budget = [], {"fetch": 1}
        shadow.fill_results(doc, common.parse_iso("2026-10-11T09:00:00-04:00"), helpers.cfg(), sg,
                            lambda gid: calls.append(gid) or None, budget=budget)
        self.assertEqual((calls, budget["fetch"]), ([1], 0))


class ShadowUnits(unittest.TestCase):
    def setUp(self):
        self.s = Sim(pool=12)
        self.s.at("09:00")
        self.inp = self.s.inputs()
        self.games = list(self.inp.games.values())

    def tearDown(self):
        self.s.close()

    def fetch(self, at, outcomes, market="shots", pull="B"):
        return {"game_id": CAR_PHI, "away": "CAR", "home": "PHI", "pull": pull, "at": at, "book": "hardrockbet",
                "requested": [market], "markets": {market: {"last_update": at, "outcomes": outcomes}}}

    def pair(self, pid, team, line, over, under, name="X"):
        return [{"name": name, "pid": pid, "team": team, "side": "over", "line": line, "price": over},
                {"name": name, "pid": pid, "team": team, "side": "under", "line": line, "price": under}]

    def test_reads_after_puck_and_runs_after_puck_are_ignored(self):
        pid = world.pid_of("CAR", 1)
        doc = {"date": world.SLATE, "rows": []}
        odoc = {"fetches": [self.fetch("2026-10-11T19:00:00-04:00", self.pair(pid, "CAR", 2.5, -120, -110))]}
        now = common.parse_iso("2026-10-11T18:00:00-04:00")
        self.assertEqual(shadow.add_reads(doc, self.inp, odoc, self.games, {}, now), 0)   # read at puck
        odoc = {"fetches": [self.fetch("2026-10-11T18:30:00-04:00", self.pair(pid, "CAR", 2.5, -120, -110))]}
        late = common.parse_iso("2026-10-11T19:01:00-04:00")
        self.assertEqual(shadow.add_reads(doc, self.inp, odoc, self.games, {}, late), 0)  # the run is after puck
        self.assertEqual(shadow.add_reads(doc, self.inp, odoc, self.games, {}, now), 1)
        self.assertEqual(shadow.add_reads(doc, self.inp, odoc, self.games, {}, now), 0)   # same read twice: once

    def test_saves_line_gets_the_goalie_model(self):
        gid = 8489000 + world.TEAM_ID["CAR"]
        doc = {"date": world.SLATE, "rows": []}
        odoc = {"fetches": [self.fetch("2026-10-11T17:30:00-04:00", self.pair(gid, "CAR", 25.5, -115, -105), "saves")]}
        shadow.add_reads(doc, self.inp, odoc, self.games, {}, common.parse_iso("2026-10-11T17:31:00-04:00"),
                         goalie_state={"teams": {"CAR": {"name": "Goalie CAR", "status": "confirmed"}}})
        r = doc["rows"][0]
        self.assertEqual((r["market"], r["ctx"]["pos"]), ("saves", "G"))
        self.assertTrue(0 < r["open"]["model_p_over"] < 1)
        self.assertIn("saves model", r["model_note"])
        self.assertEqual(r["open"]["goalie_own"], {"name": "Goalie CAR", "status": "confirmed"})
        self.assertIsNone(r["open"]["lineup"])

    def test_unknown_market_logged_without_a_model(self):
        doc = {"date": world.SLATE, "rows": []}
        odoc = {"fetches": [self.fetch("2026-10-11T17:30:00-04:00",
                                       self.pair(world.pid_of("CAR", 1), "CAR", 0.5, 150, -190), "blocks")]}
        shadow.add_reads(doc, self.inp, odoc, self.games, {}, common.parse_iso("2026-10-11T17:31:00-04:00"))
        r = doc["rows"][0]
        self.assertIsNone(r["open"]["model_p_over"])
        self.assertEqual(r["model_note"], "no model for this market")
        self.assertIsNotNone(r["open"]["fair_over"])

    def test_fill_results_push_void_and_wait(self):
        pid = world.pid_of("CAR", 1)
        mk = lambda line, market="shots": {"game_id": CAR_PHI, "market": market, "pid": pid, "line": line,
                                           "ctx": {"start": "2026-10-11T19:00:00-04:00"}, "result": None}
        doc = {"rows": [mk(3.0), mk(2.5)]}
        box = world.boxscore(CAR_PHI, "CAR", "PHI", {pid: (3, 0, 0)})
        sg = {str(CAR_PHI): {"start": "2026-10-11T19:00:00-04:00", "state": "LIVE", "sched": "OK"}}
        calls = []
        fn = lambda gid: calls.append(gid) or box
        n, _ = shadow.fill_results(doc, common.parse_iso("2026-10-11T20:30:00-04:00"), helpers.cfg(), sg, fn)
        self.assertEqual((n, calls), (0, []), "not final and too early: no boxscore call")
        sg[str(CAR_PHI)]["state"] = "OFF"
        n, _ = shadow.fill_results(doc, common.parse_iso("2026-10-11T21:45:00-04:00"), helpers.cfg(), sg, fn)
        self.assertEqual(n, 2)
        self.assertEqual((doc["rows"][0]["result"]["over"], doc["rows"][0]["result"]["under"]), ("PUSH", "PUSH"))
        self.assertEqual(doc["rows"][1]["result"]["over"], "W")
        sg[str(CAR_PHI)]["sched"] = "PPD"
        doc = {"rows": [mk(2.5)]}
        shadow.fill_results(doc, common.parse_iso("2026-10-11T21:45:00-04:00"), helpers.cfg(), sg, fn)
        self.assertEqual(doc["rows"][0]["result"]["over"], "VOID")

    def test_file_is_valid_json_one_row_per_line(self):
        pid = world.pid_of("CAR", 1)
        doc = {"date": world.SLATE, "version": 1, "note": shadow.NOTE, "rows": []}
        odoc = {"fetches": [self.fetch("2026-10-11T17:30:00-04:00",
                                       self.pair(pid, "CAR", 2.5, -120, -110) + self.pair(pid, "CAR", 1.5, -200, 150))]}
        shadow.add_reads(doc, self.inp, odoc, self.games, {}, common.parse_iso("2026-10-11T17:31:00-04:00"))
        txt = shadow.serialize(doc)
        self.assertEqual(json.loads(txt)["rows"], sorted(doc["rows"], key=lambda r: r["line"]))
        self.assertEqual(txt.count("\n"), 4)                  # header, 2 rows, closing
        shadow.save(doc)
        self.assertEqual(shadow.load(world.SLATE)["rows"], json.loads(txt)["rows"])
        empty = shadow.serialize({"date": "x", "rows": []})
        self.assertEqual(json.loads(empty)["rows"], [])


class Backfill(unittest.TestCase):
    def setUp(self):
        self.s = Sim(pool=12)
        self.s.at("09:00")

    def tearDown(self):
        self.s.close()

    def test_backfill_matches_the_record_model_value(self):
        s = self.s
        s.set_odds("CAR", "PHI", [s.line("CAR", 1, "shots", 2.5, 0.14)], UPD)
        s.at("13:02")
        self.assertTrue(any(e["t"] == "shown" for e in s.events()), "the setup needs a pick on the Record")
        os.unlink(s.path("shadow", "%s.json" % world.SLATE))
        cache = common.read_json(s.path("state", "schedule.json"))
        store = s.inputs().store
        now = common.parse_iso("2026-10-12T10:00:00-04:00")
        doc, note = shadow_backfill.build(world.SLATE, helpers.cfg(), cache, store, now, box_fn=lambda gid: None)
        self.assertTrue(doc["rows"])
        self.assertTrue(all(r["src"] == "backfill" and r["open"]["lineup"] is None for r in doc["rows"]))
        shadow.save(doc)
        matched, total, problems = shadow_backfill.check([world.SLATE])
        self.assertEqual((matched, total, problems), (1, 1, []))
        # a different model value is reported, not hidden
        for r in doc["rows"]:
            r["open"]["model_p_over"] = 0.5
        shadow.save(doc)
        matched, total, problems = shadow_backfill.check([world.SLATE])
        self.assertEqual((matched, total), (0, 1))
        self.assertIn("vs Record", problems[0])

    def test_backfill_keeps_live_rows(self):
        s = self.s
        s.set_odds("CAR", "PHI", [("player_shots_on_goal", world.name_of("CAR", 1), 2.5, -120, -110)], UPD)
        s.at("13:02")
        live = rows_of(s)
        cache = common.read_json(s.path("state", "schedule.json"))
        doc, _ = shadow_backfill.build(world.SLATE, helpers.cfg(), cache, s.inputs().store,
                                       common.parse_iso("2026-10-11T13:30:00-04:00"), box_fn=lambda gid: None)
        self.assertEqual([r for r in doc["rows"] if r["src"] == "live"], live)


class LineupHistory(unittest.TestCase):
    G = [{"id": 1, "away": "CAR", "home": "PHI", "start": "2026-10-11T19:00:00-04:00", "date": "2026-10-11"}]

    def state(self, today, at, ins=(1, 2)):
        page = {"today": today, "page_date": "2026-10-11" if today else "2026-10-10", "in": list(ins), "unsure": [],
                "out": [], "unmatched": [], "complete": True, "groups": {"f1": list(ins)}}
        return {"date": "2026-10-11", "teams": {"CAR": {"page": page, "checked_at": at}}}

    def test_first_today_and_last_before_puck(self):
        doc = {"date": "2026-10-11", "teams": {}}
        t = lambda h: common.parse_iso("2026-10-11T%s:00-04:00" % h)
        self.assertEqual(lineup_history.fold(doc, t("16:00"), self.G, self.state(False, "2026-10-11T16:00:00-04:00")), 1)
        self.assertIsNone(doc["teams"]["CAR"]["first_today_at"])
        self.assertEqual(lineup_history.fold(doc, t("16:10"), self.G, self.state(False, "2026-10-11T16:10:00-04:00")), 0)
        self.assertEqual(lineup_history.fold(doc, t("17:00"), self.G, self.state(True, "2026-10-11T17:00:00-04:00")), 1)
        self.assertEqual(lineup_history.fold(doc, t("18:00"), self.G,
                                             self.state(True, "2026-10-11T18:00:00-04:00", (1, 3))), 1)
        car = doc["teams"]["CAR"]
        self.assertEqual((car["first_today_at"], car["first_today"]["in"]), ("2026-10-11T17:00:00-04:00", [1, 2]))
        self.assertEqual((car["last_at"], car["last"]["in"], car["changes"]), ("2026-10-11T18:00:00-04:00", [1, 3], 3))
        self.assertEqual(car["last"]["groups"], {"f1": [1, 3]})
        # after puck: frozen
        self.assertEqual(lineup_history.fold(doc, t("19:01"), self.G,
                                             self.state(True, "2026-10-11T19:01:00-04:00", (4,))), 0)
        self.assertEqual(lineup_history.fold(doc, t("18:59"), self.G,
                                             self.state(True, "2026-10-11T19:00:00-04:00", (4,))), 0)
        self.assertNotIn("PHI", doc["teams"])
        # another day's state is ignored
        self.assertEqual(lineup_history.fold(doc, t("18:00"), self.G, dict(self.state(True, "x"), date="2026-10-10")), 0)

    def test_written_by_the_run_only_on_change(self):
        s = Sim(pool=12)
        try:
            s.set_lineup("CAR", "2026-10-11T16:40:00-04:00")
            s.set_lineup("PHI", "2026-10-10T16:40:00-04:00")
            s.at("16:50")
            p = s.path("state", "lineup_history", "%s.json" % world.SLATE)
            doc = common.read_json(p)
            self.assertEqual(doc["teams"]["CAR"]["first_today_at"], "2026-10-11T16:50:00-04:00")
            self.assertIsNone(doc["teams"]["PHI"]["first_today_at"])
            self.assertEqual(doc["teams"]["PHI"]["last"]["page_date"], "2026-10-10")
            self.assertIn("f1", doc["teams"]["CAR"]["last"]["groups"])
            raw = helpers.slurp(p)
            s.at("17:15")                                     # re-read 25 min later, same pages: file unchanged
            self.assertEqual(helpers.slurp(p), raw)
        finally:
            s.close()

    def test_parse_page_keeps_units(self):
        people = world.players("CAR")
        page = lineups.parse_page(world.df_page("CAR", "2026-10-11T16:40:00-04:00"), people, "2026-10-11")
        self.assertEqual(page["groups"]["f1"], sorted(world.pid_of("CAR", i) for i in range(3)))
        self.assertIn("d3", page["groups"])

    def test_backfill_from_git_history(self):
        root = tempfile.mkdtemp(prefix="pc_git_")
        try:
            git = lambda *a, **env: subprocess.run(["git", "-C", root] + list(a), check=True, capture_output=True,
                                                   env=dict(os.environ, **env))
            git("init", "-q")
            os.makedirs(os.path.join(root, "data", "state"))
            p = os.path.join(root, lineup_backfill.REL)
            for when, st in (("2026-10-11T16:00:00-04:00", self.state(False, "2026-10-11T16:00:00-04:00")),
                             ("2026-10-11T17:00:00-04:00", self.state(True, "2026-10-11T17:00:00-04:00")),
                             ("2026-10-11T19:30:00-04:00", self.state(True, "2026-10-11T19:30:00-04:00", (9,)))):
                with open(p, "w") as f:
                    json.dump(st, f)
                git("add", "-A")
                git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "v",
                    GIT_COMMITTER_DATE=when, GIT_AUTHOR_DATE=when)
            vers = lineup_backfill.versions(root)
            self.assertEqual(len(vers), 3)
            cache = {"games": {"1": dict(self.G[0], type=2, state="OFF", sched="OK")}}
            docs = lineup_backfill.rebuild(vers, cache, "2026-10-12")
            car = docs["2026-10-11"]["teams"]["CAR"]
            self.assertEqual(car["first_today_at"], "2026-10-11T17:00:00-04:00")
            self.assertEqual(car["last"]["in"], [1, 2], "the post-puck version is ignored")
            self.assertEqual(lineup_backfill.rebuild(vers, cache, "2026-10-11"), {}, "today is left to the timer")
        finally:
            import shutil
            shutil.rmtree(root, ignore_errors=True)


MENU = {"id": "ev1", "bookmakers": [{"key": "hardrockbet", "markets": [
    {"key": "player_shots_on_goal", "last_update": "2026-10-11T16:00:00Z"},
    {"key": "player_blocked_shots", "last_update": "2026-10-11T16:00:00Z"},
    {"key": "h2h", "last_update": "2026-10-11T16:00:00Z"}]}]}


class MarketMenu(unittest.TestCase):
    def setUp(self):
        self.s = Sim(pool=40)                                 # 10 a game: room for the weekly read
        self.s.at("09:00")

    def tearDown(self):
        self.s.close()

    def menu(self):
        return common.read_json(self.s.path("state", "market_menu.json"))

    def test_weekly_read_counts_one_credit(self):
        s = self.s
        world.write(os.path.join(s.w["odds"], "markets.json"), MENU)
        s.at("12:00")
        self.assertIsNone(self.menu(), "waits for pull A")
        s.at("13:02")
        m = self.menu()
        self.assertEqual(sorted(m["markets"]), ["h2h", "player_blocked_shots", "player_shots_on_goal"])
        self.assertEqual(m["markets"]["h2h"]["first_seen"], world.SLATE)
        wk = market_menu.week_of(world.SLATE)
        self.assertEqual((m["weeks"][wk]["game_id"], m["weeks"][wk]["cost"]), (CAR_PHI, 1))
        led = common.read_json(s.path("state", "credits.json"))
        self.assertEqual([e["cost"] for e in led["spent"] if e["pull"] == "M"], [1])
        s.at("13:32")
        self.assertEqual(len([e for e in common.read_json(s.path("state", "credits.json"))["spent"] if e["pull"] == "M"]), 1,
                         "once per ISO week")
        step = next(x for x in s.status()["steps"] if x["step"] == "market_menu")
        self.assertEqual(step["note"], "read this week")

    def test_no_file_no_spend_and_never_in_a_dry_run(self):
        s = self.s
        s.at("13:02")
        self.assertIsNone(self.menu())
        world.write(os.path.join(s.w["odds"], "markets.json"), MENU)
        games = list(s.inputs().games.values())
        res = market_menu.check(common.parse_iso("2026-10-11T13:40:00-04:00"), world.SLATE, games, {}, helpers.cfg(),
                                dry_run=True)
        self.assertEqual(res["note"], "dry run")
        self.assertIsNone(self.menu())

    def test_low_budget_skips(self):
        s2 = Sim(pool=12)                                     # 3 a game, 6 today: kept for the games
        try:
            world.write(os.path.join(s2.w["odds"], "markets.json"), MENU)
            s2.at("13:02")
            self.assertIsNone(common.read_json(s2.path("state", "market_menu.json")))
        finally:
            s2.close()

    def test_real_client_url_and_ledger(self):
        os.environ.pop("PC_ODDS_FIXTURE_DIR")
        os.environ["ODDS_API_KEYS"] = "zzzzzzzzzzzzzzzz9999"
        real, seen = common.http_get, []

        def get(url, **kw):
            seen.append(url)
            return common.Http(200, {"x-requests-remaining": "77", "x-requests-last": "1"}, json.dumps(MENU).encode())
        common.http_get = get
        try:
            pool = odds.Pool(odds.load_keys(), common.parse_iso("2026-10-11T13:02:00-04:00"))
            client = odds.Client(pool, helpers.cfg())
            js, cost = client.event_markets("ev1", "CAR", "PHI", world.SLATE, CAR_PHI)
        finally:
            common.http_get = real
        self.assertEqual(cost, 1)
        self.assertIn("/events/ev1/markets?", seen[0])
        self.assertIn("regions=us2", seen[0])
        self.assertIn("bookmakers=hardrockbet", seen[0])
        self.assertEqual(pool.spent[-1]["pull"], "M")
        self.assertEqual(market_menu.book_markets(js, ["hardrockbet"])[0][0], "player_shots_on_goal")
        pool.save()
        self.assertNotIn("zzzzzzzzzzzzzzzz9999", helpers.slurp(odds.ledger_path(), "r"))


class ClosingRead(unittest.TestCase):
    def test_pull_c_runs_for_a_game_with_no_pick(self):
        s = Sim(pool=20)                                      # 5 a game: tier 3, budget 10 today
        try:
            s.at("09:00")
            s.set_odds("CAR", "PHI", [("player_total_saves", "Goalie CAR", 25.5, -115, -105)], UPD)
            s.at("13:02")
            s.set_lineup("CAR", "2026-10-11T17:00:00-04:00")
            s.set_lineup("PHI", "2026-10-11T17:00:00-04:00")
            s.at("17:31")                                     # lineups confirmed: B (shots + saves at tier 3)
            s.at("18:15")                                     # C: closing read although no pick is live
            led = common.read_json(s.path("state", "credits.json"))
            pulls = [e["pull"] for e in led["spent"] if e["game_id"] == CAR_PHI]
            self.assertEqual(pulls, ["A", "B", "C"])
            self.assertEqual(s.log_bytes(), b"")
        finally:
            s.close()

    def test_tier_2_has_no_c_without_a_pick(self):
        s = Sim(pool=12)                                      # 3 a game: tier 2
        try:
            s.at("09:00")
            s.at("13:02")
            s.set_lineup("CAR", "2026-10-11T17:00:00-04:00")
            s.set_lineup("PHI", "2026-10-11T17:00:00-04:00")
            s.at("17:31")
            s.at("18:15")
            led = common.read_json(s.path("state", "credits.json"))
            self.assertEqual([e["pull"] for e in led["spent"] if e["game_id"] == CAR_PHI], ["A", "B"])
        finally:
            s.close()


class Steps(unittest.TestCase):
    def test_new_steps_listed_and_soft(self):
        for name in run.SOFT:
            self.assertIn(name, run.STEPS)
        self.assertLess(run.STEPS.index("grade"), run.STEPS.index("shadow"))
        self.assertLess(run.STEPS.index("odds"), run.STEPS.index("shadow"))


if __name__ == "__main__":
    unittest.main()
