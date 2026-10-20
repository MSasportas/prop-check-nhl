"""QA round 1 (2026-10-11): B1, B2, M1-M3, m1, m2, m5, m6, m8, m12."""
import contextlib
import io
import json
import os
import subprocess
import sys
import unittest

import helpers
from helpers import Sim
import common
import engine
import grade
import odds
import record
import run
import world

UPD = "2026-10-11T17:00:00Z"
KEYS = ["k1QAaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "k2QAbbbbbbbbbbbbbbbbbbbbbbbbbbbb"]
V = helpers.cfg()["values"]


def open_day(s):
    s.at("09:00")
    s.set_odds("CAR", "PHI", [s.line("CAR", 1, "shots", 2.5, 0.14), s.line("PHI", 1, "shots", 2.5, 0.14)], UPD)
    s.set_odds("VAN", "NYR", [s.line("VAN", 1, "shots", 2.5, 0.14), s.line("NYR", 1, "shots", 2.5, 0.14)], UPD)
    return s.at("13:02")


def gg_day(s, vn=False):
    """Baseline read, then the 90-minute read for CAR@PHI (and VAN@NYR) with one Gap + Guard candidate each."""
    s.at("09:00")
    s.read("13:02")
    s.clock("17:00")
    cp = [s.gg_lines("CAR", 1)]
    return s.read("17:31", cp=cp, vn=[s.gg_lines("VAN", 1)] if vn else ()), cp


class B1KeysRefused(unittest.TestCase):
    """The real client against a fake feed. Morning: every key refused (429 or plain 401). Later: the feed is fine."""

    def setUp(self):
        self.s = Sim(pool=12)
        os.environ.pop("PC_ODDS_FIXTURE_DIR")
        os.environ["ODDS_API_KEYS"] = ",".join(KEYS)
        self.real = common.http_get
        self.mode = "429"
        events = helpers.load(os.path.join(self.s.w["odds"], "events.json"))
        payload = world.odds_payload("CAR", "PHI", [("player_shots_on_goal", world.name_of("CAR", 1), 2.5, -120, -110)], UPD)

        def fake(url, **kw):
            if self.mode in ("429", "401"):
                code = int(self.mode)
                return common.Http(code, {}, json.dumps({"message": "Invalid or limited key"}).encode(), "HTTP %d" % code)
            if self.mode == "usage":
                return common.Http(401, {"x-requests-remaining": "0"},
                                   b'{"error_code":"OUT_OF_USAGE_CREDITS","message":"Usage quota has been reached"}', "HTTP 401")
            head = {"x-requests-remaining": "300", "x-requests-last": "1" if "/odds" in url else "0"}
            return common.Http(200, head, json.dumps(payload if "/odds" in url else events).encode())
        common.http_get = fake

    def tearDown(self):
        common.http_get = self.real
        self.s.close()

    def check_unread(self, sl):
        st = self.s.status()
        self.assertEqual(st["keys"], [{"n": 1, "left": None}, {"n": 2, "left": None}])
        self.assertIsNone(common.read_json(self.s.path("state", "odds_day.json"))["plan"], "no plan from unread keys")
        self.assertEqual(sl["status"]["prices_state"], "not_yet")
        texts = [b["text"] for b in sl["banners"]]
        self.assertIn("Hard Rock prices couldn't be read yet; trying again.", texts)
        self.assertFalse(any("used up" in t or "ran out" in t for t in texts + [json.dumps(sl["empty"])]), texts)
        self.assertEqual(sl["empty"]["sub"], "Hard Rock prices couldn't be read yet; trying again.")
        self.assertIsNone(sl["status"]["pool"]["pulls_left"])

    def recover(self):
        self.mode = "ok"
        sl = self.s.at("13:22")
        plan = common.read_json(self.s.path("state", "odds_day.json"))["plan"]
        self.assertEqual(plan["pool_at_plan"], 600)
        self.assertGreater(plan["budget_today"], 0)
        self.assertEqual(self.s.status()["keys"], [{"n": 1, "left": 300}, {"n": 2, "left": 300}])   # as the feed reports
        self.assertEqual(sl["status"]["prices_state"], "ok")
        self.assertEqual(self.s.status()["budget_used_today"], 2)              # two games, 1 market each

    def test_429(self):
        self.mode = "429"
        self.check_unread(self.s.at("13:02"))
        self.recover()

    def test_401(self):
        # QA round 2 (M2): every key refused with a plain 401 is no longer "trying again": it is keys_refused
        self.mode = "401"
        sl = self.s.at("13:02")
        self.assertEqual(self.s.status()["keys"], [{"n": 1, "left": None}, {"n": 2, "left": None}])
        self.assertIsNone(common.read_json(self.s.path("state", "odds_day.json"))["plan"], "no plan from unread keys")
        self.assertEqual(sl["status"]["prices_state"], "keys_refused")
        self.assertIn(odds.KEYS_REFUSED_TEXT, [b["text"] for b in sl["banners"]])
        self.assertEqual(sl["empty"]["sub"], odds.KEYS_REFUSED_TEXT)
        self.recover()

    def test_used_up_only_when_every_key_says_zero(self):
        self.mode = "usage"
        sl = self.s.at("13:02")
        self.assertEqual(self.s.status()["keys"], [{"n": 1, "left": 0}, {"n": 2, "left": 0}])
        self.assertEqual(sl["status"]["prices_state"], "pool_empty")
        self.assertIn("No Hard Rock prices today, odds keys are used up. No picks.", [b["text"] for b in sl["banners"]])

    def test_plan_made_on_zero_is_remade_when_a_key_reports_credits(self):
        day = {"date": "2026-10-11", "plan": {"allowance": 0.0, "tier": 0, "budget_today": 0, "pool_at_plan": 0,
                                              "games_left": 4, "games_today": 2, "key_count": 2, "unknown_keys": 0,
                                              "made_at": "2026-10-11T13:00:00-04:00"}}
        common.write_json(self.s.path("state", "odds_day.json"), day)
        self.mode = "ok"
        self.s.at("13:02")
        plan = common.read_json(self.s.path("state", "odds_day.json"))["plan"]
        self.assertEqual((plan["pool_at_plan"], plan["replaced"]), (600, "2026-10-11T13:00:00-04:00"))

    def test_too_few_credits_is_not_called_used_up(self):
        s2 = Sim(pool=[1])                                      # 1 credit / 4 games: budget today 0
        try:
            sl = s2.at("13:02")
            self.assertEqual(sl["status"]["prices_state"], "limited")
            self.assertEqual(sl["empty"]["code"], "pool_low")
            texts = [b["text"] for b in sl["banners"]] + [sl["empty"]["text"], sl["empty"]["sub"]]
            self.assertFalse(any("used up" in t or "ran out" in t for t in texts), texts)
        finally:
            s2.close()


class B2ParlayGradedAtAShownPrice(unittest.TestCase):
    """Parlays are not offered, but an old parlay event in a Record still folds and grades the way it always did."""

    def test_void_leg_uses_the_same_snapshot(self):
        par = {"t": "shown", "kind": "parlay", "id": "P", "at": "2026-10-11T13:02:00-04:00", "slate": "2026-10-11",
               "parlay": {"id": "P", "legs": ["a", "b"], "price": 229, "leg_prices": {"a": -120, "b": 110},
                          "p": 0.36, "breakeven": 0.3, "state": "early"}}
        rep = {"t": "price", "id": "P", "at": "2026-10-11T18:16:00-04:00", "price": 242,
               "leg_prices": {"a": -110, "b": 105}}
        rep2 = {"t": "price", "id": "P", "at": "2026-10-11T18:30:00-04:00", "price": 220,
                "leg_prices": {"a": -130, "b": 115}}
        items = record.fold([par, rep, rep2])
        snap = record.parlay_snapshot(items["P"])
        self.assertEqual(snap["price"], 220)
        # leg b void: graded on leg a at its price IN THAT SNAPSHOT (-130), not leg a's worst of the day
        self.assertEqual(record.grade_parlay([("W", snap["legs"]["a"]), ("VOID", snap["legs"]["b"])]), ("W", -130, 0.7692))


class M2PriceIsFrozen(unittest.TestCase):
    def test_a_better_price_later_changes_nothing(self):
        s = Sim(pool=12)
        try:
            sl, cp = gg_day(s)
            p = s.pick("CAR", 1, sl)
            self.assertEqual(p["price"], p["first_price"])
            first = p["price"]
            hr = ("player_shots_on_goal", world.name_of("CAR", 1), 1.5, 150, -190)      # far better than the flagged price
            sl = s.read("18:16", cp=[(hr, cp[0][1])])
            p = s.pick("CAR", 1, sl)
            self.assertIsNone(p["pulled"])
            self.assertEqual((p["price"], p["first_price"], p["worst_price"]), (first, first, first))
            self.assertEqual([e["t"] for e in s.events()], ["shown"])
        finally:
            s.close()


class M3LineupsState(unittest.TestCase):
    def test_states_and_banner(self):
        s = Sim(pool=12)
        try:
            sl = open_day(s)
            self.assertEqual(sl["status"]["lineups_state"], "not_yet")
            sl = s.at("16:30")                                      # within 3 hours, no page answers
            self.assertEqual(sl["status"]["lineups_state"], "failed")
            self.assertIn("Lineups couldn't be checked, so picks stay Early.", [b["text"] for b in sl["banners"]])
            self.assertEqual(sl["status"]["lineups_note"], "Lineups not checked: Daily Faceoff did not answer.")
            s.set_lineup("CAR", "2026-10-11T20:00:00Z")
            sl = s.at("16:51")
            self.assertEqual(sl["status"]["lineups_state"], "partial")
            for t in ("PHI", "VAN", "NYR"):                         # by 5:12 PM the 8 PM game is inside 3 hours too
                s.set_lineup(t, "2026-10-11T20:00:00Z")
            sl = s.at("17:12")
            self.assertEqual(sl["status"]["lineups_state"], "ok")
            self.assertNotIn("Lineups couldn't be checked, so picks stay Early.", [b["text"] for b in sl["banners"]])
        finally:
            s.close()


class Minors(unittest.TestCase):
    def setUp(self):
        self.s = Sim(pool=12)

    def tearDown(self):
        self.s.close()

    def test_m1_percents_match_the_sentence(self):
        sl, _ = gg_day(self.s)
        self.assertTrue(sl["picks"])
        for p in sl["picks"]:
            self.assertEqual(p["p_pct"], int(p["p"] * 100 + 1e-9), p["p"])               # shown as a whole percent, never rounded up
            self.assertIn("(our blend: %.1f%%)" % (100 * p["p"]), p["reason"])
            self.assertIn("%d other books say %.1f%%" % (p["n_books"], p["market_fair_pct"]), p["reason"])
            self.assertEqual(p["breakeven_pct"], round(100 * p["breakeven"]))
        # an exact edge case: p just under a whole percent, rounded to 4 places it would read one higher
        self.assertEqual((engine.pct_floor(0.589996), engine.pct_round(0.5555)), (58, 56))

    def test_m5_failure_moves_status_at_not_generated_at(self):
        sl0 = open_day(self.s)
        env = dict(os.environ, PC_NOW="2026-10-11T13:20:00-04:00")
        subprocess.run([sys.executable, os.path.join(helpers.SCRIPTS, "fail_status.py"), "push"], env=env, capture_output=True)
        sl = self.s.slate()
        self.assertEqual((sl["generated_at"], sl["status_at"]), (sl0["generated_at"], "2026-10-11T13:20:00-04:00"))
        self.assertEqual(self.s.status()["status_at"], "2026-10-11T13:20:00-04:00")

    def test_m6_days_left(self):
        sl = open_day(self.s)
        pool = sl["status"]["pool"]
        # no earlier game days in the ledger, so today's budget (6) is the daily rate
        self.assertEqual((pool["pulls_left"], pool["days_left"]), (10, 1))      # 12 - 2 spent; 10 // 6
        spent = [{"date": "2026-10-0%d" % d, "cost": c} for d, c in ((7, 4), (8, 2), (9, 0))]
        self.assertEqual(odds.pool_summary(30, 1, {"allowance": 3.0, "budget_today": 6}, [], helpers.cfg(), spent,
                                           "2026-10-11")["days_left"], 10)   # 30 / avg(4, 2) = 10

    def test_m12_low_pool_banner(self):
        s2 = Sim(pool=[7])                                       # 7 / 4 games = 1.75 a game: low
        try:
            sl = s2.at("09:00")
            self.assertTrue(sl["status"]["pool"]["low"])
            n = sl["status"]["pool"]["days_left"]
            self.assertIn("Odds pulls are running low: about %d day%s left. Fewer price checks until more keys are added."
                          % (n, "" if n == 1 else "s"), [b["text"] for b in sl["banners"]])
        finally:
            s2.close()

    def test_m8_slate_failure_takes_back_this_runs_events(self):
        s = self.s
        s.at("09:00")
        s.read("13:02")
        s.clock("17:00")
        cp = [s.gg_lines("CAR", 1)]
        real = engine.build_slate
        engine.build_slate = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("slate broke"))
        try:
            sl = s.read("17:31", cp=cp)
        finally:
            engine.build_slate = real
        self.assertEqual(s.log_bytes(), b"", "the pick was never on the page, so it is not on the Record")
        self.assertEqual(sl["picks"], [])
        st = s.status()
        self.assertEqual(st["failed_step"], "slate")
        self.assertIn("taken back", json.dumps(st["steps"]))
        sl = s.read("17:41", cp=cp)                               # the next run shows it and records it together
        self.assertEqual(len(sl["picks"]), 1)
        self.assertEqual([e["t"] for e in s.events()], ["shown"])
        self.assertEqual(s.events()[0]["id"], sl["picks"][0]["id"])


if __name__ == "__main__":
    unittest.main()
