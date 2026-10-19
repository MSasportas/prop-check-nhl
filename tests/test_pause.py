"""ops.pause.active: no new picks in any market, the page says why (2026-10-19, TEAM.md item 20)."""
import os
import unittest

import helpers
from helpers import Sim
import common
import test_engine


class Pause(unittest.TestCase):
    def setUp(self):
        os.environ.pop("PC_PAUSE_OFF", None)

    def tearDown(self):
        os.environ["PC_PAUSE_OFF"] = "1"

    def test_live_config_is_paused_with_a_plain_reason(self):
        cfg = common.load_config()
        self.assertTrue(common.picks_paused(cfg))
        p = cfg["ops"]["pause"]
        self.assertIn("no proven edge", p["text"])
        self.assertTrue(p["sub"])

    def test_paused_day_shows_no_picks_and_says_why(self):
        d = test_engine.Day()
        d.s = Sim(pool=12)
        try:
            d.s.at("09:00")
            sl = d.open_day()                                  # lines that qualify when not paused
            self.assertEqual([p for p in sl["picks"] if p["rank"]], [])
            self.assertEqual(sl["parlays"], [])
            self.assertEqual(sl["empty"]["code"], "paused")
            self.assertIn("no proven edge", sl["empty"]["text"])
            self.assertFalse(any(e["t"] == "shown" for e in d.s.events()))
        finally:
            d.s.close()

    def test_env_switch_restores_picks_for_tests(self):
        os.environ["PC_PAUSE_OFF"] = "1"
        self.assertFalse(common.picks_paused(common.load_config()))


if __name__ == "__main__":
    unittest.main()
