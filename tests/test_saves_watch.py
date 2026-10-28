"""2026-10-25 (Matt): goalie saves "behind the scenes". The saves watch track runs the exact Gap + Guard maths of shots on Hard
Rock's saves lines into data/paper_watch/saves/ (shown on the page's Behind the scenes tab). It is never a pick, never in the
Record, never in Discord, and only a CONFIRMED starter can be flagged. Offline: the made-up league (Sim)."""
import json
import os
import unittest

import helpers  # noqa: F401  (puts scripts/ on sys.path)
import common
import odds
import paper
import shadow
import world
from helpers import Sim, BOOKS

SAVES = {"id": "saves", "market": "saves", "label": "Goalie saves", "from_slate": "2026-10-01", "lines": "any",
         "offsets": {"*": 0.0}}


class Pure(unittest.TestCase):
    def test_goalie_starts_needs_confirmed_and_the_same_goalie(self):
        gs = {"teams": {"CAR": {"name": "Frederik Andersen", "status": "confirmed"},
                        "PHI": {"name": "Samuel Ersson", "status": "expected"}}}
        self.assertTrue(paper.goalie_starts(gs, "CAR", "Frederik Andersen"))
        self.assertTrue(paper.goalie_starts(gs, "CAR", "F. Andersen"))
        self.assertFalse(paper.goalie_starts(gs, "CAR", "Pyotr Kochetkov"))          # backup
        self.assertFalse(paper.goalie_starts(gs, "PHI", "Samuel Ersson"))            # only expected
        self.assertFalse(paper.goalie_starts(gs, "NYR", "Igor Shesterkin"))          # not posted
        self.assertFalse(paper.goalie_starts({}, "CAR", "Frederik Andersen"))

    def test_any_line_and_the_star_offset(self):
        T = {"lines": "any", "offsets": {"*": 0.0}}
        self.assertTrue(paper.line_ok(24.5, T))
        self.assertEqual(paper.calibrated_over(0.5, 24.5, T), 0.5)
        self.assertFalse(paper.line_ok(24.5, {"lines": [1.5, 2.5]}))
        self.assertIsNone(paper.calibrated_over(0.5, 24.5, {"offsets": {"1.5": 0.01}}))

    def test_paper_markets_adds_saves_only_while_the_track_is_on(self):
        c = json.loads(helpers.slurp(common.CONFIG_PATH, "r"))
        c["ops"]["gap_guard"]["watch"] = [dict(SAVES, from_slate="2026-10-25")]
        self.assertEqual(odds.paper_markets(c, "2026-10-25"), ["shots", "saves"])
        self.assertEqual(odds.paper_markets(c, "2026-10-24"), ["shots"])
        c["ops"]["gap_guard"]["watch"] = []
        self.assertEqual(odds.paper_markets(c, "2026-10-25"), ["shots"])
        c["ops"]["gap_guard"]["active"] = False
        self.assertFalse(odds.paper_markets(c, "2026-10-25"))

    def test_saves_are_asked_at_b_and_c_only_at_tier_3_plus(self):
        pm = ["shots", "saves"]
        self.assertEqual(odds.markets_for(4, "B", paper=pm), pm)
        self.assertEqual(odds.markets_for(3, "B", paper=pm), pm)
        self.assertEqual(odds.markets_for(2, "B", paper=pm), ["shots"])
        self.assertEqual(odds.markets_for(3, "C", c_every_game=True, paper=pm), pm)
        self.assertEqual(odds.markets_for(3, "C", c_every_game=False, live_markets={"shots"}, paper=pm), ["shots"])
        self.assertEqual(odds.markets_for(4, "A", paper=pm), ["shots"])               # the 1 PM baseline stays shots only
        self.assertEqual(odds.markets_for(4, "B", paper=True), ["shots"])             # no watch market: unchanged

    def test_the_live_config_has_the_points_track_and_saves_is_off(self):
        # 2026-10-28 (Matt): saves stopped, points research track in its place. The saves machinery above stays tested
        # with a made-up track, so it can be switched on again by config.
        cfg = common.load_config()
        watch = common.gap_guard(cfg)["watch"]
        tr = [t for t in watch if t.get("id") == "points"]
        self.assertEqual(len(tr), 1)
        self.assertEqual((tr[0]["market"], tr[0]["lines"]), ("points", "any"))
        self.assertFalse([t for t in watch if t.get("market") == "saves"])
        self.assertEqual(odds.paper_markets(cfg, "2026-10-28"), ["shots", "points"])
        self.assertEqual(odds.paper_markets(cfg, "2026-10-27"), ["shots"])           # before from_slate


class EndToEnd(unittest.TestCase):
    def setUp(self):
        self.s = Sim(pool=400)
        c = json.load(open(os.environ["PC_CONFIG"]))
        c["ops"]["gap_guard"]["watch"] = [dict(SAVES)]
        json.dump(c, open(os.environ["PC_CONFIG"], "w"))
        self.s.at("09:00")
        self.s.read("13:02")
        self.s.clock("17:00")
        self.wdir = os.path.join(os.environ["PC_DATA_DIR"], "paper_watch", "saves")

    def tearDown(self):
        self.s.close()

    def goalies(self, car_status="confirmed", car_name=None):
        common.write_json(os.path.join(os.environ["PC_DATA_DIR"], "state", "goalies.json"),
                          {"date": world.SLATE, "checked_at": "2026-10-11T16:00:00-04:00",
                           "teams": {"CAR": {"name": car_name or "Goalie CAR", "status": car_status},
                                     "PHI": {"name": "Goalie PHI", "status": "confirmed"}}})

    def saves_lines(self, line=24.5, ev=0.06):
        """(Hard Rock saves line, {book: line}) for CAR's goalie: the books agree with the model, Hard Rock pays +ev on the over."""
        inp = self.s.inputs()
        fn, _ = shadow.model_over(inp, "saves", 8489000 + world.TEAM_ID["CAR"], "CAR", "PHI", False)
        F = min(0.62, max(0.48, fn(line)["p_over"]))
        b = F / (1.0 + ev)
        hr = ("player_total_saves", "Goalie CAR", line, world.american_from_prob(b), world.american_from_prob(1.05 - b))
        oth = {}
        for bk in BOOKS:
            o, u = world.two_sided(F, 0.05)
            oth[bk] = ("player_total_saves", "Goalie CAR", line, o, u)
        return hr, oth

    def wevents(self):
        p = os.path.join(self.wdir, "events.jsonl")
        return [json.loads(x) for x in open(p).read().split("\n") if x] if os.path.exists(p) else []

    def test_a_confirmed_starter_with_a_gap_is_logged_behind_the_scenes_and_never_a_pick(self):
        self.goalies()
        sl = self.s.read("17:31", cp=[self.saves_lines()])
        self.assertEqual(sl["picks"], [])                          # not on the page as a pick
        self.assertEqual(self.s.events(), [])                      # nothing in the Record
        ev = [e for e in self.wevents() if e["t"] in ("flag", "veto")]
        self.assertEqual([(e["market"], e["line"], e["side"]) for e in ev], [("saves", 24.5, "over")])
        self.assertEqual(ev[0]["settled"], "Goalie confirmed")
        summ = common.read_json(os.path.join(self.wdir, "summary.json"))
        self.assertEqual(summ["market"], "saves")
        self.assertIn("research only", summ["note"])
        live = os.path.join(os.environ["PC_DATA_DIR"], "paper", "events.jsonl")
        if os.path.exists(live):
            self.assertNotIn('"saves"', open(live).read())         # the live research log never sees saves

    def test_an_unconfirmed_goalie_is_never_flagged(self):
        self.goalies(car_status="expected")
        self.s.read("17:31", cp=[self.saves_lines()])
        self.assertEqual([e for e in self.wevents() if e["t"] in ("flag", "veto")], [])

    def test_a_backup_start_pulls_the_saves_flag(self):
        self.goalies()
        hr, oth = self.saves_lines()
        self.s.read("17:31", cp=[(hr, oth)])
        if not [e for e in self.wevents() if e["t"] == "flag"]:
            self.skipTest("the made-up model vetoed this line")
        self.goalies(car_name="Backup CAR")
        self.s.read("18:00", cp=[(hr, oth)])
        pulls = [e for e in self.wevents() if e["t"] == "pull"]
        self.assertEqual([p["reason"] for p in pulls], ["not the starter"])


if __name__ == "__main__":
    unittest.main()
