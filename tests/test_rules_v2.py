"""Rules v2.0 (Sharp, 2026-10-18; first slate 2026-10-19). The made-up slate runs the CURRENT rules here
(Sim(rules="current")); every other test file runs it under v1.0, which still covers slates through 2026-10-18."""
import json
import os
import unittest

import helpers
import world
from helpers import Sim

import common
import engine
import odds

UPD = "2026-10-11T17:00:00Z"
KEY = "player_shots_on_goal"


def v2_prices(m_over, target, side="over", hold=0.05):
    """(over, under) prices whose v2 edge on `side` is about `target` (0.7 model + 0.3 over-hold fair - break-even)."""
    if side == "over":
        f = m_over - (target + hold) / 0.7                  # fair over (over hold) = 1 - be(under)
        be_o, be_u = f + hold, 1 - f
    else:
        be_u = (1 - m_over) - target / 0.7
        be_o = 1 + hold - be_u
    return world.american_from_prob(be_o), world.american_from_prob(be_u)


class Units(unittest.TestCase):
    def test_rules_by_slate(self):
        cfg = common.load_config()
        self.assertEqual(common.rules_for(cfg, "2026-10-18")["version"], "1.0")
        self.assertEqual(common.rules_for(cfg, "2026-10-18")["values"]["model_weight"], 0.60)
        v2 = common.rules_for(cfg, "2026-10-19")
        self.assertEqual(v2["version"], "2.0")
        v = v2["values"]
        self.assertEqual((v["model_weight"], v["market_weight"], v["edge_cap"], v["devig"]), (0.70, 0.30, 0.05, "over_hold"))
        self.assertEqual((v["uncertainty"], v["under_penalty"], v["thin_over_penalty"], v["min_p"]), (0, 0, 0, 0))
        self.assertEqual((v["margin_confirmed"], v["margin_early"]), (0, 0))
        self.assertIsNone(v["news_gap"]); self.assertIsNone(v["too_good"]); self.assertIsNone(v["drift_pull"])
        self.assertEqual((v["max_per_player"], v["max_per_game"], v["max_picks_night"], v["parlay_cap"]), (1, 2, 8, 0))
        self.assertEqual(v["lines_allowed"], {"shots": [1.5, 2.5]})
        engine.check_config(v2)
        engine.check_config(common.rules_for(cfg, "2026-10-18"))

    def test_over_hold_devig(self):
        be = odds.break_even
        self.assertAlmostEqual(odds.devig(-130, 100, "under", "over_hold"), be(-130))
        self.assertAlmostEqual(odds.devig(100, -130, "over", "over_hold"), 1 - be(-130))
        self.assertAlmostEqual(odds.devig(-130, 100, "under") + odds.devig(100, -130, "over"), 1.0)
        v = common.rules_for(common.load_config(), "2026-10-19")["values"]
        e = engine.edge(0.55, "over", True, -110, -120, v)
        self.assertAlmostEqual(e["fair"], 1 - be(-120))
        self.assertAlmostEqual(e["p"], 0.7 * 0.55 + 0.3 * (1 - be(-120)))         # no penalties, thin or not
        self.assertAlmostEqual(e["margin"], e["p"] - be(-110))

    def test_edge_cap_and_line_filter(self):
        v = common.rules_for(common.load_config(), "2026-10-19")["values"]
        mk = lambda margin: {"b": 0.55, "fair": 0.5, "model": 0.6, "model_adj": 0.6, "gap": 0.3, "p": 0.55 + margin,
                             "margin": margin}
        self.assertEqual(engine.qualifies(mk(0.0), -122, False, v), (True, None))       # 0 qualifies, early too
        self.assertTrue(engine.qualifies(mk(0.049), -122, False, v)[0])                  # a gap of 0.3: no too-good rule
        self.assertEqual(engine.qualifies(mk(0.05), -122, True, v)[0], False)
        self.assertEqual(engine.qualifies(mk(-0.001), -122, True, v)[0], False)
        self.assertTrue(engine.line_allowed("shots", 1.5, v) and engine.line_allowed("shots", 2.5, v))
        self.assertFalse(engine.line_allowed("shots", 3.5, v) or engine.line_allowed("shots", 0.5, v))
        self.assertTrue(engine.line_allowed("saves", 25.5, v))                           # no list: any line


class Day(unittest.TestCase):
    def setUp(self):
        self.s = Sim(pool=20, rules="current")
        self.s.at("09:00")

    def tearDown(self):
        self.s.close()

    def line(self, team, i, ln, target, side="over"):
        over, under = v2_prices(self.s.model_over(team, i, "shots", ln), target, side)
        return (KEY, world.name_of(team, i), ln, over, under)

    def pulled_code(self, team, i):
        pid = world.pid_of(team, i)
        ids = {e["id"] for e in self.s.events() if e["t"] == "shown" and e.get("pick", {}).get("player_id") == pid}
        return next((e["code"] for e in self.s.events() if e["t"] == "pulled" and e["id"] in ids), None)

    def margin_of(self, team, i, ln, side, over, under):
        m = self.s.model_over(team, i, "shots", ln)
        ms = m if side == "over" else 1 - m
        price, other = (over, under) if side == "over" else (under, over)
        return engine.edge(ms, side, False, price, other, helpers.cfg()["values"])["margin"]

    def test_runs_under_v2_and_picks_small_edges_only(self):
        s = self.s
        small, big = self.line("CAR", 1, 2.5, 0.02), self.line("CAR", 4, 2.5, 0.09)
        self.assertTrue(0.0 <= self.margin_of("CAR", 1, 2.5, "over", small[3], small[4]) < 0.05)
        self.assertGreaterEqual(self.margin_of("CAR", 4, 2.5, "over", big[3], big[4]), 0.05)
        s.set_odds("CAR", "PHI", [small, big], UPD)
        sl = s.at("13:02")                                    # lineups not confirmed: same bar (v1 needed 0.03 early)
        ids = {p["player_id"] for p in sl["picks"] if not p["pulled"]}
        self.assertEqual(ids, {world.pid_of("CAR", 1)})
        self.assertEqual(common.read_json(s.path("rules.json"))["version"], "2.0")
        p = s.pick("CAR", 1)
        self.assertEqual(p["state"], "early")
        self.assertIn("-%d needs" % abs(small[3]) if small[3] < 0 else "+%d needs" % small[3], p["reason"])

    def test_three_five_line_never_picked(self):
        s = self.s
        m = s.model_over("CAR", 1, "shots", 3.5)
        over, under = v2_prices(m, 0.02, "under")
        s.set_odds("CAR", "PHI", [(KEY, world.name_of("CAR", 1), 3.5, over, under)], UPD)
        sl = s.at("13:02")
        self.assertEqual([p for p in sl["picks"] if not p["pulled"]], [])

    def test_two_per_game_and_no_parlays(self):
        s = self.s
        s.set_odds("CAR", "PHI", [self.line("CAR", 1, 2.5, 0.02), self.line("CAR", 4, 2.5, 0.03),
                                  self.line("PHI", 1, 2.5, 0.04)], UPD)
        s.set_odds("VAN", "NYR", [self.line("VAN", 1, 2.5, 0.02), self.line("NYR", 4, 2.5, 0.03)], UPD)
        sl = s.at("13:02")
        live = [p for p in sl["picks"] if not p["pulled"]]
        by_game = {}
        for p in live:
            by_game[p["game_id"]] = by_game.get(p["game_id"], 0) + 1
        self.assertEqual(by_game, {2026020901: 2, 2026020902: 2})
        ranked = sorted(live, key=lambda p: p["rank"])
        edges = [p["p"] - p["breakeven"] for p in ranked]
        self.assertEqual(edges, sorted(edges, reverse=True), "ranked by edge")
        self.assertEqual(sl["parlays"], [])
        self.assertFalse(any(e.get("kind") == "parlay" for e in s.events()))

    def test_nightly_cap_counts_every_pick_shown(self):
        s = self.s
        c = helpers.load(os.environ["PC_CONFIG"])
        c["values"]["max_picks_night"] = 3
        world.write(os.environ["PC_CONFIG"], c)
        s.set_odds("CAR", "PHI", [self.line("CAR", 1, 2.5, 0.02), self.line("PHI", 4, 2.5, 0.03)], UPD)
        s.set_odds("VAN", "NYR", [self.line("VAN", 1, 2.5, 0.02), self.line("NYR", 4, 2.5, 0.04)], UPD)
        sl = s.at("13:02")
        self.assertEqual(len([p for p in sl["picks"] if not p["pulled"]]), 3)
        self.assertEqual(sum(1 for e in s.events() if e["t"] == "shown"), 3, "the Record gets only the picks shown")

    def test_pulls_at_a_new_price(self):
        s = self.s
        a, b = self.line("CAR", 1, 2.5, 0.02), self.line("PHI", 1, 2.5, 0.004)
        s.set_odds("CAR", "PHI", [a, b], UPD)
        s.at("13:02")
        self.assertIsNotNone(s.pick("CAR", 1))
        self.assertIsNotNone(s.pick("PHI", 1))
        # CAR 1: the price drifts our way until the edge is 0.07 -> pulled (edge cap). PHI 1: the over lengthens by
        # 4+ points with the lineup unconfirmed (v1.0's drift pull), edge still under the cap: stays in v2.0
        a2 = self.line("CAR", 1, 2.5, 0.07)
        b2 = (KEY, b[1], 2.5, world.american_from_prob(odds.break_even(b[3]) - 0.042), b[4])
        self.assertGreaterEqual(odds.break_even(b[3]) - odds.break_even(b2[3]), 0.04)
        self.assertLess(self.margin_of("PHI", 1, 2.5, "over", b2[3], b2[4]), 0.05)
        s.set_odds("CAR", "PHI", [a2, b2], "2026-10-11T21:30:00Z")
        s.set_lineup("CAR", "2026-10-11T17:00:00-04:00")
        s.set_lineup("PHI", "2026-10-11T17:00:00-04:00")
        sl = s.at("17:31")
        self.assertEqual(self.pulled_code("CAR", 1), "edge_cap")
        self.assertIsNone(self.pulled_code("PHI", 1))
        self.assertIsNone(s.pick("PHI", 1, sl)["pulled"])
        # PHI 1 now below break-even at a new price -> pulled
        m = s.model_over("PHI", 1, "shots", 2.5)
        over, under = v2_prices(m, -0.02, hold=0.10)           # a wider hold keeps the price inside -200
        s.set_odds("CAR", "PHI", [a2, (KEY, world.name_of("PHI", 1), 2.5, over, under)], "2026-10-11T22:16:00Z")
        sl = s.at("18:16")
        self.assertEqual(self.pulled_code("PHI", 1), "margin")

    def test_out_is_pulled(self):
        s = self.s
        s.set_odds("CAR", "PHI", [self.line("CAR", 1, 2.5, 0.02)], UPD)
        s.at("13:02")
        s.set_lineup("CAR", "2026-10-11T17:00:00-04:00", out=(1,))
        sl = s.at("17:00")
        self.assertEqual(self.pulled_code("CAR", 1), "out")


if __name__ == "__main__":
    unittest.main()
