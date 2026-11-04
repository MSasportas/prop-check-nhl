"""The Live tab's data (scripts/live.py -> data/live.json): display only, from the boxscore grade.py already read."""
import os
import shutil
import tempfile
import unittest

import helpers  # noqa: F401  (puts scripts/ on sys.path)
import common
import live
import nhl
import record
import run

SLATE = "2026-10-11"
G1, G2, G3 = 2026020001, 2026020002, 2026020003


def shown(i, game, pid, line=2.5, side="over", market="shots"):
    return {"t": "shown", "kind": "single", "id": i, "at": "2026-10-11T17:31:00-04:00", "slate": SLATE,
            "pick": {"id": i, "game_id": game, "player": "A. Player", "player_id": pid, "team": "CAR", "opp": "PHI",
                     "home": False, "start": "2026-10-11T19:00:00-04:00", "market": market, "line": line, "side": side,
                     "bet": "Over 2.5 shots on goal", "price": -120, "state": "early"}}


def box(state, period, clock, inter, away_score, home_score, players):
    """A small fake NHL boxscore with the fields the real one has (checked on 2025021000)."""
    return {"id": G1, "gameState": state, "gameScheduleState": "OK",
            "periodDescriptor": {"number": period, "periodType": "REG", "maxRegulationPeriods": 3},
            "clock": {"timeRemaining": clock, "secondsRemaining": 0, "running": not inter, "inIntermission": inter},
            "awayTeam": {"id": 12, "abbrev": "CAR", "score": away_score, "sog": 20},
            "homeTeam": {"id": 4, "abbrev": "PHI", "score": home_score, "sog": 17},
            "playerByGameStats": {
                "awayTeam": {"forwards": [{"playerId": pid, "sog": s, "points": 0, "toi": "12:00"} for pid, s in players.items()],
                             "defense": [], "goalies": []},
                "homeTeam": {"forwards": [], "defense": [], "goalies": []}}}


GAMES = [{"id": G1, "away": "CAR", "home": "PHI", "start": "2026-10-11T19:00:00-04:00", "state": "LIVE"},
         {"id": G2, "away": "NYR", "home": "NJD", "start": "2026-10-11T19:00:00-04:00", "state": "LIVE"},
         {"id": G3, "away": "BOS", "home": "BUF", "start": "2026-10-11T22:00:00-04:00", "state": "FUT"}]


class LiveTab(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="pc_live_")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.old_env = os.environ.get("PC_DATA_DIR")
        os.environ["PC_DATA_DIR"] = self.tmp
        self.addCleanup(self.restore)
        nhl.clear_cache()
        self.addCleanup(nhl.clear_cache)
        self.now = common.parse_iso("2026-10-11T20:05:00-04:00")
        self.ev = [shown("a", G1, 1001), shown("b", G1, 1002, line=1.5, side="under"), shown("c", G3, 1003)]

    def restore(self):
        if self.old_env is None:
            os.environ.pop("PC_DATA_DIR", None)
        else:
            os.environ["PC_DATA_DIR"] = self.old_env

    def test_a_live_game_from_this_runs_box(self):
        nhl.CACHE[("boxscore", G1)] = box("LIVE", 2, "08:14", False, 2, 1, {1001: 3})
        out = live.step(self.now, SLATE, GAMES, self.ev)
        self.assertEqual(out["status"], "ok")
        doc = common.read_json(live.path())
        self.assertEqual(doc["slate_date"], SLATE)
        self.assertEqual(len(doc["games"]), 1)                          # G2 has no pick, G3 has not started
        g = doc["games"][0]
        self.assertEqual((g["game_id"], g["state"], g["period"], g["period_type"], g["clock"], g["in_intermission"]),
                         (G1, "LIVE", 2, "REG", "08:14", False))
        self.assertEqual((g["away"], g["home"]), ({"abbrev": "CAR", "score": 2, "sog": 20}, {"abbrev": "PHI", "score": 1, "sog": 17}))
        self.assertEqual(g["updated_at"], common.iso(self.now))
        self.assertEqual(doc["picks"], {"a": {"game_id": G1, "market": "shots", "stat": 3},
                                        "b": {"game_id": G1, "market": "shots", "stat": None}})    # not in the box: null
        # the same box again: nothing to write
        self.assertEqual(live.step(self.now, SLATE, GAMES, self.ev)["status"], "skipped")

    def test_no_call_of_its_own_and_nothing_written_before_puck(self):
        calls = []
        real = nhl.web
        nhl.web = lambda *a, **k: calls.append(a)
        self.addCleanup(setattr, nhl, "web", real)
        early = common.parse_iso("2026-10-11T18:00:00-04:00")
        games = [dict(g, state="FUT") for g in GAMES]
        self.assertEqual(live.step(early, SLATE, games, self.ev)["status"], "skipped")
        self.assertIsNone(common.read_json(live.path()))
        live.step(self.now, SLATE, GAMES, self.ev)                       # started, but no box read this run
        self.assertEqual(calls, [])
        doc = common.read_json(live.path())
        self.assertEqual((doc["games"][0]["state"], doc["games"][0]["updated_at"], doc["picks"]["a"]["stat"]), ("LIVE", None, None))

    def test_final_game_keeps_its_last_line_and_takes_the_graded_number(self):
        nhl.CACHE[("boxscore", G1)] = box("FINAL", 3, "00:00", False, 4, 2, {1001: 2, 1002: 1})
        live.step(self.now, SLATE, GAMES, self.ev)
        nhl.clear_cache()                                                 # next run: grade no longer reads this game
        ev = self.ev + [{"t": "graded", "id": "a", "at": "2026-10-11T22:30:00-04:00", "result": "W", "actual": 3,
                         "actual_text": "had 3", "price": -120, "units": 0.8333}]
        later = common.parse_iso("2026-10-11T22:40:00-04:00")
        live.step(later, SLATE, GAMES, ev)
        doc = common.read_json(live.path())
        g = doc["games"][0]
        self.assertEqual((g["state"], g["away"]["score"], g["updated_at"]), ("FINAL", 4, common.iso(self.now)))
        self.assertEqual((doc["picks"]["a"]["stat"], doc["picks"]["b"]["stat"]), (3, 1))

    def test_a_broken_box_never_fails_the_run_step(self):
        nhl.CACHE[("boxscore", G1)] = {"gameState": "LIVE"}              # no teams, no players
        out = live.step(self.now, SLATE, GAMES, self.ev)
        self.assertIn(out["status"], ("ok", "skipped"))

    def test_wired_as_a_soft_step_after_grade(self):
        self.assertIn("live", run.SOFT)
        self.assertEqual(run.STEPS.index("live"), run.STEPS.index("grade") + 1)
        r = run.Run(helpers.cfg(), self.now)
        real = live.step
        live.step = lambda *a, **k: 1 / 0
        self.addCleanup(setattr, live, "step", real)
        r.games, r.cache, r.events = GAMES, {"games": {}}, self.ev
        r.soft_step("live", r.do_live)
        self.assertEqual(r.steps[-1]["status"], "warn")
        self.assertIsNone(r.failed_step())



class GameChecks(unittest.TestCase):
    """The Games tab's checks per game (engine.game_checks): reads done, the next read, lineup confirmed. Display only."""

    def test_reads_next_read_and_lineups(self):
        import engine
        import types
        tmp = tempfile.mkdtemp(prefix="pc_gc_")
        self.addCleanup(shutil.rmtree, tmp, True)
        old = os.environ.get("PC_DATA_DIR")
        os.environ["PC_DATA_DIR"] = tmp
        self.addCleanup(lambda: os.environ.__setitem__("PC_DATA_DIR", old) if old is not None else os.environ.pop("PC_DATA_DIR", None))
        g = {"id": G1, "away": "CAR", "home": "PHI", "start": "2026-10-11T19:00:00-04:00", "state": "FUT"}
        doc = {"fetches": [
            {"game_id": G1, "pull": "A", "at": "2026-10-11T13:00:05-04:00", "book": "hardrockbet", "markets": {"shots": {}}},
            {"game_id": G1, "pull": "B", "at": "2026-10-11T17:30:04-04:00", "book": "hardrockbet", "markets": {"shots": {}}},
            {"game_id": G1, "pull": "B", "at": "2026-10-11T17:40:04-04:00", "book": "hardrockbet", "markets": {"points": {}}},
            {"game_id": G2, "pull": "C", "at": "2026-10-11T18:15:04-04:00", "book": "hardrockbet", "markets": {"shots": {}}}]}
        inp = types.SimpleNamespace(cfg=helpers.cfg(), now=common.parse_iso("2026-10-11T17:50:00-04:00"), slate=SLATE,
                                    games={G1: g}, odds_doc=doc,
                                    lineup_state={"teams": {"CAR": {"checked_at": "2026-10-11T17:20:00-04:00", "page": {"today": True}}}})
        ck = engine.game_checks(inp, g, {"away": "confirmed", "home": "waiting"}, {})
        self.assertEqual(ck["reads"], [{"pull": "A", "at": "2026-10-11T13:00:05-04:00"}, {"pull": "B", "at": "2026-10-11T17:30:04-04:00"}])
        self.assertEqual(ck["next_read"], {"pull": "C", "at": "2026-10-11T18:15:00-04:00"})
        self.assertEqual(ck["lineups_at"], {"away": "2026-10-11T17:20:00-04:00", "home": None})
        # every read in: no next read; started: no next read either
        self.assertIsNone(engine.game_checks(inp, g, {}, {G1: True})["next_read"])
        inp.now = common.parse_iso("2026-10-11T19:05:00-04:00")
        self.assertIsNone(engine.game_checks(inp, g, {}, {})["next_read"])
        # a broken input never costs the page its slate
        self.assertIsNone(engine.game_checks(types.SimpleNamespace(), g, {}, {}))


class LabConfig(unittest.TestCase):
    """config/lab.json (the page's Lab tab): only active paper tests, each with a summary file the timer writes."""

    def test_entries(self):
        import json
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        doc = json.load(open(os.path.join(root, "config", "lab.json")))
        self.assertTrue(doc["tests"])
        for t in doc["tests"]:
            for k in ("id", "title", "rule", "summary", "stats", "need"):
                self.assertIn(k, t)
            self.assertNotIn("..", t["summary"])
            sm = json.load(open(os.path.join(root, "data", t["summary"])))
            self.assertTrue(sm.get("active"), t["id"])
            self.assertIn(t["stats"], sm)


if __name__ == "__main__":
    unittest.main()
