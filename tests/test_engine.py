"""The betting method: edge arithmetic, entry rules, caps, pull rules, lock, parlays.
Hand-computed numbers are worked in the comments so a reader can check them with a calculator."""
import unittest

import helpers
from helpers import Sim
import common
import engine
import odds
import record
import world

CFG = helpers.cfg()
V = CFG["values"]
UPD = "2026-10-11T17:00:00Z"          # feed last_update used for the 1:02 PM pull
UPD_C = "2026-10-11T22:10:00Z"        # ... and for the 6:16 PM re-price


class EdgeArithmetic(unittest.TestCase):
    """Price -125 on our side, -105 on the other.
       b     = 125/225            = 0.555556
       other = 105/205            = 0.512195
       fair  = 0.555556/1.067751  = 0.520305"""

    def test_over(self):
        e = engine.edge(0.66, "over", False, -125, -105, V)
        self.assertAlmostEqual(e["b"], 0.555556, places=6)
        self.assertAlmostEqual(e["fair"], 0.520305, places=6)
        self.assertAlmostEqual(e["gap"], 0.139695, places=6)
        self.assertAlmostEqual(e["model_adj"], 0.64)                 # 0.66 - 0.02
        self.assertAlmostEqual(e["p"], 0.592122, places=6)           # 0.6 x 0.64 + 0.4 x 0.520305
        self.assertAlmostEqual(e["margin"], 0.036566, places=6)
        self.assertEqual(engine.qualifies(e, -125, False, V), (True, None))     # early needs 0.03

    def test_under_gets_the_under_penalty(self):
        e = engine.edge(0.66, "under", False, -125, -105, V)
        self.assertAlmostEqual(e["model_adj"], 0.625)                # 0.66 - 0.02 - 0.015
        self.assertAlmostEqual(e["p"], 0.583122, places=6)           # 0.375 + 0.208122
        self.assertAlmostEqual(e["margin"], 0.027566, places=6)
        self.assertEqual(engine.qualifies(e, -125, False, V), (False, "margin too small"))   # early: 0.03
        self.assertEqual(engine.qualifies(e, -125, True, V), (True, None))                    # confirmed: 0.02

    def test_thin_over_gets_the_thin_penalty_and_thin_under_does_not(self):
        e = engine.edge(0.66, "over", True, -125, -105, V)
        self.assertAlmostEqual(e["model_adj"], 0.60)                 # 0.66 - 0.02 - 0.04
        self.assertAlmostEqual(e["p"], 0.568122, places=6)
        self.assertEqual(engine.qualifies(e, -125, True, V), (False, "margin too small"))    # 0.0126 < 0.02
        u = engine.edge(0.66, "under", True, -125, -105, V)
        self.assertAlmostEqual(u["model_adj"], 0.625)

    def test_min_p(self):
        # +100 / -120: b 0.5, fair 0.5/1.045455 = 0.478261, p = 0.6 x 0.58 + 0.4 x 0.478261 = 0.539304
        e = engine.edge(0.60, "over", False, 100, -120, V)
        self.assertAlmostEqual(e["p"], 0.539304, places=6)
        self.assertGreater(e["margin"], V["margin_early"])           # the margin is fine ...
        self.assertEqual(engine.qualifies(e, 100, True, V), (False, "chance under the minimum"))  # ... the chance is not

    def test_news_gap_and_too_good(self):
        e = engine.edge(0.68, "over", False, -125, -105, V)           # gap 0.1597 > 0.15
        self.assertEqual(engine.qualifies(e, -125, False, V), (False, "big gap needs lineup confirmed"))
        self.assertEqual(engine.qualifies(e, -125, True, V), (True, None))
        e = engine.edge(0.75, "over", False, -125, -105, V)           # gap 0.2297 > 0.20
        self.assertEqual(engine.qualifies(e, -125, True, V), (False, "too good: assume the book knows"))

    def test_price_gate(self):
        for price, ok in ((-200, True), (-201, False), (-205, False), (-150, True), (100, True), (120, True),
                          (121, False), (125, False)):
            self.assertEqual(engine.inside_gate(price, V), ok, price)
        e = engine.edge(0.80, "over", False, -210, 160, V)
        self.assertEqual(engine.qualifies(e, -210, True, V)[1], "price outside the gate")

    def test_one_side_missing_uses_the_last_fair(self):
        e = engine.edge(0.66, "over", False, -125, None, V, fair=0.52)
        self.assertAlmostEqual(e["p"], 0.6 * 0.64 + 0.4 * 0.52)

    def test_config_is_checked(self):
        bad = helpers.cfg()
        bad["values"]["market_weight"] = 0.5
        with self.assertRaises(engine.ConfigError):
            engine.check_config(bad)
        engine.check_config(helpers.cfg())


class Wording(unittest.TestCase):
    def test_bet_and_reason(self):
        self.assertEqual(engine.bet_text("over", 2.5, "shots", CFG), "Over 2.5 shots on goal")
        self.assertEqual(engine.bet_text("under", 0.5, "points", CFG), "Under 0.5 points")
        e = engine.edge(0.66, "over", False, -125, -105, V)
        s = engine.reason_text("shots", "over", 2.5, -125, e, 3.44, 1195.0, "PHI", 1.061, False, 61, CFG)
        self.assertEqual(s, "59% to clear 2.5 shots; -125 needs 56%. Projects 3.4 shots in 20 min. "
                            "PHI allow 6% more shots than average.")
        e = engine.edge(0.66, "under", True, -125, -105, V)
        s = engine.reason_text("points", "under", 0.5, -125, e, 0.41, 840.0, "CAR", 0.985, True, 14, CFG)
        self.assertEqual(s, "58% to stay under 0.5 points; -125 needs 56%. Projects 0.4 points in 14 min. "
                            "Short history: 14 games.")          # opponent clause dropped under 2%
        s = engine.reason_text("points", "over", 0.5, 110, e, 0.9, 1200.0, "CAR", 0.93, False, 80, CFG)
        self.assertTrue(s.endswith("CAR allow 7% fewer goals than average."))

    def test_ids_are_stable(self):
        self.assertEqual(engine.pick_id("2026-10-11", 2026020086, 8478427, "shots", 2.5, "over"),
                         "2026-10-11:2026020086:8478427:shots:2.5:over")
        a = engine.parlay_id("2026-10-11", ["x", "y"])
        self.assertEqual(a, engine.parlay_id("2026-10-11", ["y", "x"]))


class Caps(unittest.TestCase):
    def cand(self, pid, market, line, p, b, game=1, conf=False):
        return {"id": "%s:%s:%s" % (pid, market, line), "pid": pid, "market": market, "line": line, "game_id": game,
                "conf": conf, "e": {"p": p, "b": b}}

    def test_one_line_per_market_and_one_pick_per_player(self):
        c = [self.cand(1, "shots", 2.5, 0.60, 0.55), self.cand(1, "shots", 3.5, 0.62, 0.60),
             self.cand(1, "points", 0.5, 0.61, 0.52), self.cand(2, "shots", 1.5, 0.59, 0.55)]
        out = engine.best_per_player(c, V)
        # player 1: shots keeps the higher p (3.5, margin 0.02); points has margin 0.09 and wins the player slot
        self.assertEqual([x["id"] for x in out], ["1:points:0.5", "2:shots:1.5"])

    def test_rank_order(self):
        rows = [("a", 0.60, 0.55, False), ("b", 0.62, 0.55, False), ("c", 0.60, 0.55, True), ("d", 0.65, 0.60, False)]
        got = sorted(rows, key=lambda r: engine.rank_key(r[1], r[2], r[3]))
        self.assertEqual([r[0] for r in got], ["b", "d", "c", "a"])    # margin, then chance, then confirmed first


class Day(unittest.TestCase):
    """Whole-engine behaviour on the made-up league. Pool 12 over 4 games = 3.0 a game = tier 2 (A and C)."""

    def setUp(self):
        self.s = Sim(pool=12)
        self.s.at("09:00")

    def tearDown(self):
        self.s.close()

    def shots(self, team, i=1, gap=0.14, line=2.5, side="over", hold=0.07):
        return self.s.line(team, i, "shots", line, gap, side, hold)

    def open_day(self, extra_cp=(), extra_vn=()):
        """1:02 PM pull with one qualifying over in each team's game."""
        s = self.s
        s.set_odds("CAR", "PHI", [self.shots("CAR"), self.shots("PHI")] + list(extra_cp), UPD)
        s.set_odds("VAN", "NYR", [self.shots("VAN"), self.shots("NYR")] + list(extra_vn), UPD)
        return s.at("13:02")

    def reprice(self, lines, hhmm="18:16"):
        self.s.set_odds("CAR", "PHI", lines, UPD_C)
        return self.s.at(hhmm)

    def moved(self, team, over, under, line=2.5, i=1):
        return ("player_shots_on_goal", world.name_of(team, i), line, over, under)

    # ---- entry
    def test_picks_shown_ranked_and_recorded_in_the_same_run(self):
        sl = self.open_day()
        open_picks = [p for p in sl["picks"] if p["rank"]]
        self.assertEqual(len(open_picks), 4)
        self.assertEqual([p["rank"] for p in open_picks], [1, 2, 3, 4])
        margins = [p["p"] - p["breakeven"] for p in open_picks]
        self.assertEqual(margins, sorted(margins, reverse=True))
        shown = [e for e in self.s.events() if e["t"] == "shown" and e["kind"] == "single"]
        self.assertEqual({e["id"] for e in shown}, {p["id"] for p in open_picks})
        for p in open_picks:
            self.assertEqual(p["state"], "early")
            self.assertEqual(p["tier"], "main")
            self.assertGreaterEqual(p["p"], V["min_p"])
            self.assertGreaterEqual(p["p"] - p["breakeven"], V["margin_early"] - 1e-9)
            self.assertTrue(engine.inside_gate(p["price"], V))
            self.assertEqual(p["bet"], "Over 2.5 shots on goal")
            self.assertRegex(p["reason"], r"^\d+% to clear 2\.5 shots; [+-]\d+ needs \d+%\. Projects \d\.\d shots in \d+ min\.")
            ev = next(e for e in shown if e["id"] == p["id"])["pick"]
            for k in ("bet", "price", "p", "breakeven", "reason", "state", "rank", "player"):
                self.assertEqual(ev[k], p[k], k)
        self.assertIsNone(sl["empty"])
        self.assertEqual(sl["status"]["lines_checked"], 6)      # 4 real lines + the 2 filler lines

    def test_too_good_and_news_gap_are_not_picked_early(self):
        s = self.s
        s.set_odds("CAR", "PHI", [self.shots("CAR", gap=0.25), self.shots("PHI", gap=0.17)], UPD)
        sl = s.at("13:02")
        self.assertEqual(sl["picks"], [])
        self.assertEqual(sl["empty"]["code"], "none_qualified")
        self.assertEqual(sl["empty"]["text"], "No picks tonight. Nothing cleared the bar at Hard Rock's prices.")
        self.assertEqual(sl["empty"]["sub"], "Checked 4 lines at 1:02 PM.")
        # 6:20 PM: lineups confirm -> the 0.17 gap becomes a pick ("Lineup confirmed"); the 0.25 gap never does
        s.set_lineup("CAR", "2026-10-11T21:00:00Z")
        s.set_lineup("PHI", "2026-10-11T21:00:00Z")
        sl = s.at("18:20")
        self.assertEqual([(p["team"], p["state"]) for p in sl["picks"]], [("PHI", "lineup")])

    def test_caps_three_per_game(self):
        s = self.s
        lines = [self.shots("CAR"), self.shots("PHI"),
                 self.shots("CAR", 7, 0.145, side="under", hold=0.04), self.shots("PHI", 7, 0.145, side="under", hold=0.04)]
        s.set_odds("CAR", "PHI", lines, UPD)
        sl = s.at("13:02")
        rows = [r for r in engine.explain(s.inputs()) if r["verdict"] == "QUALIFIES"]
        self.assertEqual(len(rows), 4, "the test needs four qualifying sides in one game")
        self.assertEqual(len(sl["picks"]), V["max_per_game"])
        best = sorted(rows, key=lambda r: -r["margin"])[:3]
        self.assertEqual({p["player"].split(". ")[1] for p in sl["picks"]}, {r["player"].split(" ")[1] for r in best})
        # the fourth does not sneak in on the next run
        sl = s.at("13:12")
        self.assertEqual(len(sl["picks"]), 3)

    def test_missed_last_game_needs_lineup(self):
        s2 = Sim(pool=12, skip_this_season={("CAR", 2): [1]})      # CAR player 1 sat out CAR's last game
        try:
            s2.at("09:00")
            s2.set_odds("CAR", "PHI", [s2.line("CAR", 1, "shots", 2.5, 0.14), s2.line("PHI", 1, "shots", 2.5, 0.14)], UPD)
            sl = s2.at("13:02")
            self.assertEqual([p["team"] for p in sl["picks"]], ["PHI"])
            s2.set_lineup("CAR", "2026-10-11T21:00:00Z")
            sl = s2.at("18:20")
            self.assertEqual(sorted(p["team"] for p in sl["picks"]), ["CAR", "PHI"])
        finally:
            s2.close()

    def test_long_absence_sits_out_two_games(self):
        s2 = Sim(pool=12, skip_this_season={("CAR", 0): [1], ("CAR", 1): [1], ("CAR", 2): [1]})
        try:
            s2.at("09:00")
            s2.set_lineup("CAR", "2026-10-11T21:00:00Z")
            s2.set_odds("CAR", "PHI", [s2.line("CAR", 1, "shots", 2.5, 0.14)], UPD)
            s2.at("13:02")
            sl = s2.at("18:20")
            self.assertEqual(sl["picks"], [])                      # missed 3 straight: no pick even when confirmed
            row = [r for r in engine.explain(s2.inputs()) if r["side"] == "over"][0]
            self.assertEqual(row["verdict"], "back from an absence")
        finally:
            s2.close()

    # ---- staying, pulling, locking
    def test_small_worse_price_stays_and_is_recorded(self):
        sl = self.open_day()
        p0 = self.s.pick("CAR", 1, sl)
        worse = p0["price"] - 10                                    # e.g. -123 -> -133: margin shrinks but stays >= 0
        sl = self.reprice([self.moved("CAR", worse, 102), self.shots("PHI")])
        p1 = self.s.pick("CAR", 1, sl)
        self.assertIsNone(p1["pulled"])
        self.assertEqual((p1["price"], p1["first_price"], p1["worst_price"]), (worse, p0["price"], worse))
        self.assertLess(p1["p"] - p1["breakeven"], V["margin_early"])       # under the entry bar, over the pull bar
        self.assertGreaterEqual(p1["p"] - p1["breakeven"], V["pull_margin"])
        ev = [e for e in self.s.events() if e["id"] == p0["id"] and e["t"] == "price"]
        self.assertEqual([(e["price"], e["at"][11:16]) for e in ev], [(worse, "18:16")])
        self.assertEqual([(x["price"], x["at"][11:16]) for x in p1["prices"]], [(p0["price"], "13:02"), (worse, "18:16")])
        self.assertEqual(p1["history"], [{"at": "2026-10-11T13:02:00-04:00", "text": "Early: lineup not confirmed"}])

    def test_pull_price_past_the_gate(self):
        sl = self.open_day()
        p0 = self.s.pick("CAR", 1, sl)
        sl = self.reprice([self.moved("CAR", -210, 165), self.shots("PHI")])
        p1 = self.s.pick("CAR", 1, sl)
        self.assertEqual(p1["pulled"]["reason"], "Price moved past -200")
        self.assertIsNone(p1["rank"])
        self.assertEqual(p1["price"], p0["price"], "the price that caused the pull was never a live price")
        self.assertEqual(p1["worst_price"], p0["price"])
        self.assertEqual(p1["bet"], p0["bet"])
        self.assertEqual([h["text"] for h in p1["history"]], ["Early: lineup not confirmed", "Pulled: Price moved past -200"])

    def test_pull_margin_gone(self):
        self.open_day()
        # -190 / +150: b 0.6552, fair 0.6209; chance about 0.63 -> under the price's break-even
        sl = self.reprice([self.moved("CAR", -190, 150), self.shots("PHI")])
        self.assertEqual(self.s.pick("CAR", 1, sl)["pulled"]["reason"], "The price no longer clears the bar")

    def test_pull_drift_only_when_not_confirmed(self):
        sl = self.open_day()
        p0 = self.s.pick("CAR", 1, sl)
        longer = 105                                                # break-even falls from about 0.55 to 0.488
        self.assertGreaterEqual(odds.break_even(p0["price"]) - odds.break_even(longer), V["drift_pull"])
        sl = self.reprice([self.moved("CAR", longer, -135), self.shots("PHI")])
        self.assertEqual(self.s.pick("CAR", 1, sl)["pulled"]["reason"],
                         "The price moved against this side before the lineup was confirmed")
        self.assertIsNone(self.s.pick("PHI", 1, sl)["pulled"])

    def test_no_drift_pull_once_lineup_is_confirmed(self):
        self.open_day()
        self.s.set_lineup("CAR", "2026-10-11T21:00:00Z")
        sl = self.reprice([self.moved("CAR", 105, -135), self.shots("PHI")])
        p = self.s.pick("CAR", 1, sl)
        self.assertIsNone(p["pulled"])
        self.assertEqual((p["state"], p["price"]), ("lineup", 105))

    def test_pull_line_moved_and_new_line_is_a_new_pick(self):
        sl = self.open_day()
        old = self.s.pick("CAR", 1, sl)
        sl = self.reprice([self.shots("CAR", line=3.5), self.shots("PHI")])
        picks = [p for p in sl["picks"] if p["player_id"] == world.pid_of("CAR", 1)]
        was = next(p for p in picks if p["id"] == old["id"])
        self.assertEqual(was["pulled"]["reason"], "Hard Rock moved the line to 3.5")
        # the 3.5 line is a different pick id: it would be judged from scratch (here it does not qualify)
        row = [r for r in engine.explain(self.s.inputs()) if r["line"] == 3.5 and r["side"] == "over"][0]
        self.assertNotEqual(row["verdict"], "QUALIFIES")
        self.assertEqual(len(picks), 1)

    def test_pull_line_gone(self):
        sl = self.open_day()
        sl = self.reprice([self.shots("PHI")])                      # CAR player no longer listed
        self.assertEqual(self.s.pick("CAR", 1, sl)["pulled"]["reason"], "Hard Rock took this line down")
        self.assertIsNone(self.s.pick("PHI", 1, sl)["pulled"])

    def test_pull_market_gone(self):
        self.open_day()
        # the 6:16 PM re-price asks for shots; the book answers with a points market only
        world.write(self.s.path("..", "odds", "odds_car_phi.json"),
                    world.odds_payload("CAR", "PHI", [("player_points", world.name_of("PHI", 0), 0.5, 120, -150)], UPD_C))
        sl = self.s.at("18:16")
        self.assertEqual(self.s.pick("PHI", 1, sl)["pulled"]["reason"], "Hard Rock took this market down")
        self.assertEqual(self.s.pick("CAR", 1, sl)["pulled"]["reason"], "Hard Rock took this market down")
        self.assertIsNone(self.s.pick("VAN", 1, sl)["pulled"])

    def test_book_missing_is_a_feed_problem_not_a_pull(self):
        self.open_day()
        world.write(self.s.path("..", "odds", "odds_car_phi.json"), {"id": "x", "bookmakers": []})
        sl = self.s.at("18:16")
        self.assertEqual([p["pulled"] for p in sl["picks"]], [None] * 4)

    def test_pull_out_of_lineup(self):
        self.open_day()
        self.s.set_lineup("CAR", "2026-10-11T21:00:00Z", out=[1])
        self.s.set_lineup("PHI", "2026-10-11T21:00:00Z", missing=[1])       # complete page, player not listed
        sl = self.s.at("16:30")
        self.assertEqual(self.s.pick("CAR", 1, sl)["pulled"]["reason"], "Scratched from the lineup")
        self.assertEqual(self.s.pick("PHI", 1, sl)["pulled"]["reason"], "Scratched from the lineup")
        self.assertEqual(sl["status"]["lineups_at"][11:16], "16:30")

    def test_yesterdays_page_and_game_time_decisions_do_not_confirm_or_pull(self):
        self.open_day()
        self.s.set_lineup("CAR", "2026-10-10T21:00:00Z", out=[1])           # dated yesterday: ignored
        self.s.set_lineup("PHI", "2026-10-11T21:00:00Z", gtd=[1])           # today, but a game-time decision
        sl = self.s.at("16:30")
        self.assertEqual([(p["state"], p["pulled"]) for p in sl["picks"]], [("early", None)] * 4)

    def test_lineups_not_checked_far_from_puck_and_at_most_every_20_minutes(self):
        self.open_day()
        self.s.set_lineup("CAR", "2026-10-11T15:00:00Z")
        sl = self.s.at("15:30")                                      # 3.5 hours before the puck: not yet
        self.assertIsNone(sl["status"]["lineups_at"])
        sl = self.s.at("16:05")
        self.assertEqual(sl["status"]["lineups_at"][11:16], "16:05")
        self.s.set_lineup("CAR", "2026-10-11T20:10:00Z", out=[1])
        sl = self.s.at("16:15")                                      # 10 minutes later: not re-read
        self.assertIsNone(self.s.pick("CAR", 1, sl)["pulled"])
        sl = self.s.at("16:26")
        self.assertIsNotNone(self.s.pick("CAR", 1, sl)["pulled"])

    def test_pulled_pick_never_comes_back_and_nothing_is_silently_removed(self):
        sl = self.open_day()
        ids = {p["id"] for p in sl["picks"]}
        sl = self.reprice([self.moved("CAR", -210, 165), self.shots("PHI")])
        sl = self.reprice([self.shots("CAR"), self.shots("PHI")], "18:48")      # price is back
        p = self.s.pick("CAR", 1, sl)
        self.assertIsNotNone(p["pulled"])
        self.assertEqual(ids, {p["id"] for p in sl["picks"]})
        sl = self.s.at("23:30")
        self.assertEqual(ids, {p["id"] for p in sl["picks"]})

    def test_lock_at_puck_drop(self):
        self.open_day()
        self.s.set_lineup("PHI", "2026-10-11T21:00:00Z")
        self.s.at("18:20")
        sl = self.s.at("19:00")                                       # CAR at PHI puck time from the schedule
        self.assertEqual(self.s.pick("CAR", 1, sl)["state"], "locked_unconfirmed")
        self.assertEqual(self.s.pick("PHI", 1, sl)["state"], "locked")
        self.assertEqual(self.s.pick("VAN", 1, sl)["state"], "early")
        self.assertEqual([g["started"] for g in sl["games"]], [True, False])
        self.assertIsNone(self.s.pick("CAR", 1, sl)["rank"])
        self.assertEqual([p["rank"] for p in sl["picks"] if p["rank"]], [1, 2])
        # a locked pick is never pulled afterwards
        self.s.set_lineup("CAR", "2026-10-11T23:05:00Z", out=[1])
        sl = self.s.at("19:30")
        self.assertIsNone(self.s.pick("CAR", 1, sl)["pulled"])

    def test_live_game_state_locks_before_the_clock(self):
        self.open_day()
        self.s.set_states({2026020902: "LIVE"})                        # NHL says live although the clock says 6:50 PM
        sl = self.s.at("18:50")
        self.assertEqual(self.s.pick("VAN", 1, sl)["state"], "locked_unconfirmed")
        self.assertEqual(self.s.pick("CAR", 1, sl)["state"], "early")

    def test_all_started_and_no_games_wording(self):
        self.open_day()
        sl = self.s.at("20:05")
        self.assertEqual(sl["empty"], {"code": "all_started", "text": "Every game has started.",
                                       "sub": "Tonight's picks are under Started."})
        sl = self.s.at("09:00", day="2026-10-12")                      # no games on the 12th in this league
        self.assertEqual(sl["slate_date"], "2026-10-12")
        self.assertEqual(sl["empty"]["text"], "No NHL games today.")
        self.assertEqual(sl["picks"], [])
        self.assertEqual(sl["valid_until"], "2026-10-13T05:00:00-04:00")

    def test_slate_rolls_over_at_5_am(self):
        self.open_day()
        self.assertEqual(self.s.at("04:59", day="2026-10-12")["slate_date"], "2026-10-11")
        self.assertEqual(self.s.at("05:00", day="2026-10-12")["slate_date"], "2026-10-12")

    # ---- parlays
    def test_parlay_rules(self):
        sl = self.open_day()
        picks = {p["id"]: p for p in sl["picks"]}
        par = sl["parlays"]
        self.assertTrue(1 <= len(par) <= V["parlay_cap"])
        use = {}
        for q in par:
            legs = [picks[l] for l in q["legs"]]
            self.assertIn(len(legs), (2, 3))
            self.assertEqual(len({l["game_id"] for l in legs}), len(legs), "one leg per game")
            dec = pp = bb = 1.0
            for l in legs:
                self.assertGreaterEqual(l["p"], V["parlay_leg_min_p"])
                self.assertTrue(-200 <= l["price"] <= 100 and l["price"] < 0 or l["price"] == 100)
                dec *= odds.decimal(l["price"]); pp *= l["p"]; bb *= l["breakeven"]
                use[l["id"]] = use.get(l["id"], 0) + 1
            self.assertEqual(q["price"], odds.american(dec))
            self.assertAlmostEqual(q["p"], pp, places=3)
            self.assertGreaterEqual(q["p"], V["parlay_min_p_2"] if len(legs) == 2 else V["parlay_min_p_3"])
            self.assertGreaterEqual(q["p"], q["breakeven"] + V["parlay_edge"] - 1e-3)
            self.assertEqual(q["state"], "early")
        self.assertLessEqual(max(use.values()), V["parlay_leg_max_use"])
        two = [set(q["legs"]) for q in par if len(q["legs"]) == 2]
        self.assertEqual(len(two), 2)
        self.assertFalse(two[0] & two[1], "the two 2-leg parlays share no leg")
        self.assertEqual(sum(1 for q in par if len(q["legs"]) == 3), 0)     # only two games tonight: no 3-leg
        shown = [e for e in self.s.events() if e["t"] == "shown" and e["kind"] == "parlay"]
        self.assertEqual({e["id"] for e in shown}, {q["id"] for q in par})

    def test_parlay_pulled_with_its_leg_and_locked_with_first_puck(self):
        sl = self.open_day()
        car = self.s.pick("CAR", 1, sl)["id"]
        hit = [q["id"] for q in sl["parlays"] if car in q["legs"]]
        other = [q["id"] for q in sl["parlays"] if car not in q["legs"]]
        self.assertEqual((len(hit), len(other)), (1, 1))
        sl = self.reprice([self.moved("CAR", -210, 165), self.shots("PHI")])
        q = {x["id"]: x for x in sl["parlays"]}
        self.assertEqual(q[hit[0]]["pulled"]["reason"], "Car01 leg pulled")
        self.assertIsNone(q[other[0]]["pulled"])
        sl = self.s.at("19:01")
        q = {x["id"]: x for x in sl["parlays"]}
        self.assertEqual(q[other[0]]["state"], "locked_unconfirmed")       # its PHI leg has started
        self.assertEqual(len(sl["parlays"]), 2, "a pulled parlay stays on the page")

    def test_no_parlay_with_one_game(self):
        s = self.s
        s.set_odds("CAR", "PHI", [self.shots("CAR"), self.shots("PHI")], UPD)
        sl = s.at("13:02")
        self.assertEqual(len(sl["picks"]), 2)
        self.assertEqual(sl["parlays"], [])                            # both legs are in the same game


class TeamData(unittest.TestCase):
    def test_team_with_missing_logs_is_excluded_and_named(self):
        s = Sim(pool=12)
        try:
            # drop PHI's rows for its last game from the stats answer (the schedule still says it is final)
            p = s.path("..", "nhl", "skater_summary_20262027_2026-10-06_2026-10-12.json")
            rows = [r for r in helpers.load(p) if not (r["gameId"] == 2026020022 and r["teamAbbrev"] == "PHI")]
            world.write(p, rows)
            s.at("09:00")
            s.set_odds("CAR", "PHI", [s.line("CAR", 1, "shots", 2.5, 0.14), s.line("PHI", 1, "shots", 2.5, 0.14)], UPD)
            s.set_odds("VAN", "NYR", [s.line("NYR", 1, "shots", 2.5, 0.14)], UPD)
            sl = s.at("13:02")
            self.assertEqual(sl["status"]["excluded_teams"], [{"team": "PHI", "reason": "stats behind"}])
            self.assertIn("Not covered tonight: PHI (stats behind).", [b["text"] for b in sl["banners"]])
            self.assertEqual(sl["games"][0]["excluded_reason"], "stats behind")
            self.assertEqual(sl["games"][1]["excluded_reason"], None)
            self.assertEqual(s.status()["excluded_teams"], [{"team": "PHI", "reason": "stats behind"}])
            # one team of a two-game slate is half the slate: no new picks at all, and the page says why
            self.assertEqual(sl["status"]["stats_state"], "behind")
            self.assertEqual(sl["empty"]["text"], "Stats are behind, so no picks until they catch up.")
            self.assertEqual(sl["picks"], [])
            # the engine itself leaves out only the team that is behind
            inp = s.inputs()
            cands, _ = engine.candidates(inp)
            self.assertEqual(sorted(c["team"] for c in cands), ["CAR", "NYR"])
            # the rows arrive: the next stats read clears it and the picks post
            world.write(p, helpers.load(p) + [r for r in world.skater_api_rows("PHI", "VAN", True, 2026020022, "2026-10-08", 42)])
            sl = s.at("13:14")
            self.assertEqual(sl["status"]["excluded_teams"], [])
            self.assertEqual(sorted(p["team"] for p in sl["picks"]), ["CAR", "NYR", "PHI"])
        finally:
            s.close()

    def test_shots_that_do_not_add_up_exclude_the_team(self):
        s = Sim(pool=12)
        try:
            p = s.path("..", "nhl", "skater_summary_20262027_2026-10-06_2026-10-12.json")
            rows = helpers.load(p)
            victim = next(r for r in rows if r["gameId"] == 2026020021 and r["teamAbbrev"] == "CAR" and r["shots"] == 1)
            rows.remove(victim)                                        # one skater row with 1 shot went missing
            world.write(p, rows)
            sl = s.at("09:00")
            self.assertEqual(sl["status"]["excluded_teams"], [{"team": "CAR", "reason": "stats check failed"}])
        finally:
            s.close()

    def test_goalie_shot_explains_a_one_shot_difference(self):
        s = Sim(pool=12)
        try:
            p = s.path("..", "nhl", "team_summary_20262027_2026-10-06_2026-10-12.json")
            rows = helpers.load(p)
            for r in rows:                                             # CAR's goalie had a shot on goal in game 21
                if r["gameId"] == 2026020021 and r["homeRoad"] == "R":
                    r["shotsForPerGame"] += 1
                if r["gameId"] == 2026020021 and r["homeRoad"] == "H":
                    r["shotsAgainstPerGame"] += 1
            world.write(p, rows)
            world.write(s.path("..", "nhl", "gamecenter_2026020021_play-by-play.json"), {
                "awayTeam": {"id": 12, "abbrev": "CAR"}, "homeTeam": {"id": 3, "abbrev": "NYR"},
                "rosterSpots": [{"teamId": 12, "playerId": 99, "positionCode": "G"}],
                "plays": [{"typeDescKey": "shot-on-goal", "periodDescriptor": {"periodType": "REG"},
                           "details": {"eventOwnerTeamId": 12, "shootingPlayerId": 99}},
                          {"typeDescKey": "shot-on-goal", "periodDescriptor": {"periodType": "SO"},
                           "details": {"eventOwnerTeamId": 12, "shootingPlayerId": 99}}]})
            sl = s.at("09:00")
            self.assertEqual(sl["status"]["excluded_teams"], [])
            self.assertEqual(sl["status"]["stats_through"], "2026-10-08")
        finally:
            s.close()


class TopTier(unittest.TestCase):
    """Pool 40 over 4 games = 10 a game = top tier: pull B adds goals and saves, and Goal watch shows."""

    def test_pull_b_and_goal_watch(self):
        s = Sim(pool=40)
        try:
            s.at("09:00")
            self.assertEqual(s.status()["tier"], 4)
            s.set_odds("CAR", "PHI", [s.line("CAR", 1, "shots", 2.5, 0.14)], UPD)
            sl = s.at("13:02")
            self.assertEqual(sl["goal_watch"], [])                    # not before pull B
            self.assertEqual(sl["banners"], [])                       # no pool banner at this tier
            self.assertEqual(sl["status"]["next_price_read_at"], "2026-10-11T17:30:00-04:00")
            goals = [("player_goals", world.name_of(t, i), 0.5, price, None)
                     for t, i, price in (("CAR", 0, 150), ("CAR", 1, 140), ("PHI", 0, 160), ("PHI", 2, 170), ("PHI", 13, 900))]
            s.set_odds("CAR", "PHI", [s.line("CAR", 1, "shots", 2.5, 0.14)] + goals, "2026-10-11T21:25:00Z")
            s.set_lineup("CAR", "2026-10-11T20:00:00Z")
            s.set_lineup("PHI", "2026-10-11T20:00:00Z", gtd=[0])        # PHI player 0 is a game-time decision
            sl = s.at("17:31")
            doc = common.read_json(s.path("odds", "2026-10-11.json"))
            b = [f for f in doc["fetches"] if f["pull"] == "B" and f["away"] == "CAR"][0]
            self.assertEqual(b["requested"], ["goals", "points", "saves", "shots"])
            self.assertEqual(sorted(b["markets"]), ["goals", "shots"])
            gw = sl["goal_watch"]
            self.assertEqual(len(gw), 3)
            self.assertEqual(sorted(gw[0]), ["fair_price", "p", "player", "price", "team", "text"])
            self.assertNotIn("P. Phi00", [r["player"] for r in gw], "not lineup-confirmed: not on Goal watch")
            self.assertEqual([r["p"] for r in gw], sorted((r["p"] for r in gw), reverse=True))
            for r in gw:
                self.assertAlmostEqual(r["fair_price"], odds.american(1.0 / r["p"]), delta=1)   # p is shown rounded
                self.assertLess(r["p"], 0.5)
                self.assertTrue(r["text"].endswith("Not a pick."))
            self.assertFalse(any(e["id"].count("goals") for e in s.events()), "Goal watch is never on the Record")
            self.assertEqual(len([p for p in sl["picks"] if p["rank"]]), 1)
        finally:
            s.close()


class Paused(unittest.TestCase):
    def test_market_pauses_itself(self):
        ev = []
        for n in range(50):                                            # 50 graded shots picks at -120: 20 wins
            i = "2026-10-01:1:%d:shots:2.5:over" % n
            ev.append({"t": "shown", "kind": "single", "id": i, "at": "2026-10-01T13:00:00-04:00", "slate": "2026-10-01",
                       "pick": {"id": i, "market": "shots", "price": -120, "player": "X", "bet": "b", "game_id": 1,
                                "team": "A", "opp": "B", "home": True, "state": "early"}})
            res = "W" if n < 20 else "L"
            ev.append({"t": "graded", "id": i, "at": "2026-10-02T00:00:00-04:00", "result": res, "price": -120,
                       "actual": 3, "actual_text": "had 3", "units": record.single_units(res, -120)})
        out = engine.paused_markets(ev, CFG)                            # 40% hits, needs 54.5%: 14.5 points under
        self.assertEqual(list(out), ["shots"])
        self.assertEqual(engine.paused_markets(ev[:-2], CFG), {})       # 49 graded: too few to pause


if __name__ == "__main__":
    unittest.main()
