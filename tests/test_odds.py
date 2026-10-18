"""Odds: price arithmetic, parsing the real Hard Rock payload, feed checks, key rotation, the plan and
the pull schedule, and a pull that fails part-way."""
import json
import os
import unittest
from datetime import timedelta

import helpers
from helpers import Sim, FIX
import common
import names
import nhl
import odds
import world

V = helpers.cfg()["values"]


def real_matcher():
    old = os.environ.get("PC_NHL_FIXTURE_DIR")
    os.environ["PC_NHL_FIXTURE_DIR"] = FIX
    try:
        return names.Matcher(nhl.roster("CAR") + nhl.roster("PHI"))
    finally:
        if old is None:
            os.environ.pop("PC_NHL_FIXTURE_DIR", None)
        else:
            os.environ["PC_NHL_FIXTURE_DIR"] = old


class Arithmetic(unittest.TestCase):
    def test_prices(self):
        self.assertAlmostEqual(odds.break_even(-200), 2 / 3)
        self.assertAlmostEqual(odds.break_even(120), 100 / 220)
        self.assertAlmostEqual(odds.break_even(100), 0.5)
        self.assertAlmostEqual(odds.decimal(-200), 1.5)
        self.assertAlmostEqual(odds.decimal(120), 2.2)
        self.assertEqual(odds.american(1.5), -200)
        self.assertEqual(odds.american(2.65), 165)
        self.assertEqual(odds.american(2.0), 100)

    def test_fair_and_hold(self):
        # Jordan Staal points 0.5 in the real payload: over +125, under -165
        # break-evens 100/225 = 0.4444 and 165/265 = 0.6226 -> hold 0.0671, fair under 0.6226/1.0671 = 0.5835
        self.assertAlmostEqual(odds.hold(125, -165), 0.06709, places=4)
        self.assertAlmostEqual(odds.fair_two_sided(-165, 125), 0.58350, places=4)
        self.assertAlmostEqual(odds.fair_two_sided(125, -165) + odds.fair_two_sided(-165, 125), 1.0)


class RealPayload(unittest.TestCase):
    def setUp(self):
        self.cfg = helpers.cfg()
        self.payload = helpers.load(os.path.join(FIX, "odds_car_phi.json"))
        self.game = {"id": 2026020086, "away": "CAR", "home": "PHI"}
        self.at = common.parse_iso("2026-10-11T18:26:00-04:00")
        keys = ["player_shots_on_goal", "player_points", "player_goals", "player_total_saves", "player_shots_alternate"]
        self.fetch = odds.normalize(self.payload, self.game, real_matcher(), keys, "A", self.at, 5, self.cfg)

    def test_parse(self):
        f = self.fetch
        self.assertEqual(f["book"], "hardrockbet")
        self.assertEqual(sorted(f["markets"]), ["goals", "player_shots_alternate", "points", "saves", "shots"])
        self.assertEqual(len(f["markets"]["shots"]["outcomes"]), 28)
        self.assertEqual(len(f["markets"]["points"]["outcomes"]), 36)
        self.assertEqual(f["unmatched"], [], "every name in the real payload should match an NHL player")
        aho = [o for o in f["markets"]["shots"]["outcomes"] if o["name"] == "Sebastian Aho"]
        self.assertEqual({(o["side"], o["line"], o["price"]) for o in aho}, {("over", 2.5, -140), ("under", 2.5, 105)})
        self.assertEqual({o["pid"] for o in aho}, {8478427})
        miller = [o for o in f["markets"]["shots"]["outcomes"] if o["name"] == "K'Andre Miller"][0]
        self.assertEqual((miller["pid"], miller["team"]), (8480817, "CAR"))

    def test_view_and_feed_checks(self):
        view = odds.build_view({"date": "2026-10-11", "fetches": [self.fetch]}, self.cfg)[2026020086]
        self.assertEqual((view["shots"]["checked"], view["shots"]["failed"]), (14, 0))
        self.assertEqual((view["points"]["checked"], view["points"]["failed"]), (18, 0))
        # Kochetkov saves 20.5: -115 / -140 -> hold 0.5349 + 0.5833 - 1 = 0.118 > 0.11 -> skipped
        # Woll saves 25.5:      -150 / -105 -> hold 0.6000 + 0.5122 - 1 = 0.112 > 0.11 -> skipped
        saves = view["saves"]["pairs"]
        self.assertEqual([p["why"] for p in saves.values()], ["hold out of range", "hold out of range"])
        # one-sided goals market: every pair fails "one side missing"
        self.assertTrue(all(p["why"] == "one side missing" for p in view["goals"]["pairs"].values()))

    def test_stale_payload_is_not_used(self):
        late = dict(self.fetch, at="2026-10-11T19:30:00-04:00")       # feed last_update 6:25 PM, read 7:30 PM
        view = odds.build_view({"fetches": [late]}, self.cfg)[2026020086]
        self.assertTrue(all(not p["ok"] and p["why"] == "price is stale" for p in view["shots"]["pairs"].values()))
        # a stale read never replaces an earlier good one
        view = odds.build_view({"fetches": [self.fetch, late]}, self.cfg)[2026020086]
        self.assertEqual(view["shots"]["at"], self.at)
        self.assertEqual(view["shots"]["failed"], 0)

    def test_check_pair(self):
        at = self.at
        fresh = "2026-10-11T22:20:00Z"
        self.assertIsNone(odds.check_pair(-120, -110, fresh, at, V))           # hold 0.069
        self.assertEqual(odds.check_pair(-120, None, fresh, at, V), "one side missing")
        self.assertEqual(odds.check_pair(100, -100, fresh, at, V), "hold out of range")    # 0.0
        self.assertEqual(odds.check_pair(-103, -103, fresh, at, V), "hold out of range")   # 0.0148 < 0.03
        self.assertEqual(odds.check_pair(-130, -130, fresh, at, V), "hold out of range")   # 0.130 > 0.11
        self.assertEqual(odds.check_pair(-120, -110, "2026-10-11T21:25:00Z", at, V), "price is stale")  # 61 min
        self.assertIsNone(odds.check_pair(-120, -110, "2026-10-11T21:27:00Z", at, V))      # 59 min

    def test_events_matched_by_teams_and_time(self):
        events = helpers.load(os.path.join(FIX, "events.json"))
        games = [{"id": 2026020086, "away": "CAR", "home": "PHI", "start": "2026-10-11T19:00:00-04:00"},
                 {"id": 2026020084, "away": "SEA", "home": "WSH", "start": "2026-10-11T17:00:00-04:00"},
                 {"id": 1, "away": "FLA", "home": "BUF", "start": "2026-10-11T13:00:00-04:00"}]   # a day early: no match
        got, unknown = odds.match_events(events, games, 6)
        self.assertEqual(got, {"2026020086": "a49ddd8a44071e340299ae7f22b4f359",
                               "2026020084": "12a90ee4a941f857d0fc417663fb00c1"})
        self.assertEqual(unknown, [])
        got, unknown = odds.match_events([{"id": "x", "away_team": "Hartford Whalers", "home_team": "Boston Bruins",
                                           "commence_time": "2026-10-11T23:00:00Z"}], games, 6)
        self.assertEqual((got, unknown), ({}, ["Hartford Whalers"]))


class NameMatching(unittest.TestCase):
    def test_rules(self):
        people = [{"id": 1, "first": "Sebastian", "last": "Aho", "team": "CAR", "pos": "F"},
                  {"id": 2, "first": "K'Andre", "last": "Miller", "team": "CAR", "pos": "D"},
                  {"id": 3, "first": "Zachary", "last": "L'Heureux", "team": "PHI", "pos": "F"},
                  {"id": 4, "first": "Tim", "last": "Stützle", "team": "PHI", "pos": "F"},
                  {"id": 5, "first": "Josh", "last": "Miller", "team": "PHI", "pos": "F"},
                  {"id": 6, "first": "James", "last": "van Riemsdyk", "team": "PHI", "pos": "F"},
                  {"id": 7, "first": "Jake", "last": "Miller", "team": "PHI", "pos": "F"}]
        m = names.Matcher(people)
        self.assertEqual(m.find("Sebastian Aho")["id"], 1)
        self.assertEqual(m.find("KAndre Miller")["id"], 2)           # punctuation
        self.assertEqual(m.find("Zachary L'Heureux Jr.")["id"], 3)   # suffix
        self.assertEqual(m.find("Tim Stutzle")["id"], 4)             # accents
        self.assertEqual(m.find("Zach L'Heureux")["id"], 3)          # short first name, same initial, one candidate
        self.assertEqual(m.find("S. Aho")["id"], 1)                  # initial
        self.assertEqual(m.find("James Van Riemsdyk")["id"], 6)
        self.assertIsNone(m.find("J. Miller"))                       # two J. Millers: never guessed
        self.assertIsNone(m.find("Bill Aho"))                        # different initial: never guessed
        self.assertIsNone(m.find("Nobody Here"))
        self.assertEqual(names.display("Nathan", "MacKinnon"), "N. MacKinnon")


class Plan(unittest.TestCase):
    def test_tiers(self):
        for allowance, tier in ((0.0, 0), (0.99, 0), (1.0, 1), (1.99, 1), (2.0, 2), (3.99, 2), (4.0, 3), (6.99, 3),
                                (7.0, 4), (50, 4)):
            self.assertEqual(odds.tier_of(allowance, V), tier, allowance)

    def test_markets_by_tier(self):
        self.assertEqual(odds.markets_for(0, "A"), ["shots"])
        self.assertEqual(odds.markets_for(1, "A"), ["shots"])
        self.assertEqual(odds.markets_for(2, "A"), ["shots"])           # A is shots only at every tier
        self.assertEqual(odds.markets_for(4, "A"), ["shots"])
        self.assertEqual(odds.markets_for(2, "B"), ["shots"])               # points picks are off (2026-10-18)
        self.assertEqual(odds.markets_for(3, "B"), ["shots", "saves"])      # saves logged to build the 2nd market
        self.assertEqual(odds.markets_for(4, "B"), ["shots", "saves", "goals"])
        for t in (0, 1, 2, 3, 4):
            for pull in ("A", "B", "C"):
                self.assertNotIn("points", odds.markets_for(t, pull, {"shots", "points"}))
        self.assertEqual(odds.markets_for(1, "C", {"shots"}), [])
        self.assertEqual(odds.markets_for(0, "C"), [])
        self.assertEqual(odds.markets_for(2, "C", {"shots"}), ["shots"])
        self.assertEqual(odds.markets_for(2, "C", set()), [])                # tier 2: live picks only (QA fix)
        self.assertEqual(odds.markets_for(3, "C", set()), ["shots"])        # tier 3+: closing price for every game
        self.assertEqual(odds.markets_for(4, "C"), ["shots"])
        self.assertEqual(odds.markets_for(3, "C", set(), c_every_game=False), [])        # tight budget
        self.assertEqual(odds.markets_for(3, "C", {"shots"}, c_every_game=False), ["shots"])

    def test_allowance_and_budget(self):
        # the real pool on 2026-10-11: 109 credits, 143 games left this month, 3 today
        p = odds.make_plan(109, 143, 3, V)
        self.assertEqual((p["tier"], p["budget_today"]), (0, 2))
        self.assertAlmostEqual(p["allowance"], 0.7622, places=4)
        p = odds.make_plan(400, 143, 3, V)                    # 2.797 a game -> shots + points, 8 credits today
        self.assertEqual((p["tier"], p["budget_today"]), (2, 8))
        p = odds.make_plan(0, 143, 3, V)
        self.assertEqual((p["tier"], p["budget_today"]), (0, 0))
        p = odds.make_plan(1500, 150, 10, V)                  # exactly 10 a game
        self.assertEqual((p["tier"], p["budget_today"]), (4, 100))

    def test_pull_times(self):
        g = lambda hh: {"id": hh, "date": "2026-10-11", "start": "2026-10-11T%02d:00:00-04:00" % hh}
        t = odds.pull_times("2026-10-11", [g(19), g(22)], V)
        self.assertEqual((common.fmt_time(t["A"]), common.fmt_time(t["B"])), ("1:00 PM", "5:30 PM"))
        t = odds.pull_times("2026-10-11", [g(13), g(19)], V)   # matinee: 3 hours before the first puck
        self.assertEqual((common.fmt_time(t["A"]), common.fmt_time(t["B"])), ("10:00 AM", "11:30 AM"))


class Schedule(unittest.TestCase):
    """due_pulls at several clock times. Two games: 7:00 PM and 10:00 PM."""

    def setUp(self):
        self.games = [{"id": 1, "date": "2026-10-11", "start": "2026-10-11T19:00:00-04:00"},
                      {"id": 2, "date": "2026-10-11", "start": "2026-10-11T22:00:00-04:00"}]

    def due(self, hhmm, tier, fetched=None, live=None, started=None, lineups_ok=None):
        now = common.parse_iso("2026-10-11T%s:00-04:00" % hhmm)
        f = {}
        for gid, items in (fetched or {}).items():
            f[gid] = [{"pull": p, "at": common.parse_iso("2026-10-11T%s:00-04:00" % t), "markets": m, "returned": r}
                      for p, t, m, r in items]
        out = odds.due_pulls(now, self.games, tier, V, f, live or {}, started or {}, lineups_ok=lineups_ok)
        return [(d["pull"], d["game"]["id"], d["markets"]) for d in out]

    def test_before_a_nothing(self):
        self.assertEqual(self.due("12:59", 2), [])
        self.assertEqual(self.due("09:00", 4), [])

    def test_a_all_games(self):
        for tier in (1, 2, 3, 4):                                  # A is shots only, never points
            self.assertEqual(self.due("13:00", tier), [("A", 1, ["shots"]), ("A", 2, ["shots"])])
        self.assertEqual(self.due("13:00", 1), [("A", 1, ["shots"]), ("A", 2, ["shots"])])

    def test_a_done_is_not_repeated(self):
        sp = ["shots"]
        self.assertEqual(self.due("13:10", 2, {1: [("A", "13:02", sp, sp)], 2: [("A", "13:02", sp, sp)]}), [])

    def test_late_cron(self):
        # 6:40 PM is exactly 20 minutes before the first puck: A still runs for game 1
        self.assertEqual(self.due("18:40", 1), [("A", 1, ["shots"]), ("A", 2, ["shots"])])
        # 6:41 PM: under 20 minutes left for game 1, so only game 2 is read
        self.assertEqual(self.due("18:41", 1), [("A", 2, ["shots"])])
        self.assertEqual(self.due("19:05", 1, started={1: True}), [("A", 2, ["shots"])])
        self.assertEqual(self.due("21:41", 1, started={1: True}), [])

    def test_b_waits_for_lineups_and_the_window(self):
        sh, sp = ["shots"], ["shots", "saves"]
        done = {1: [("A", "13:02", sh, sh)], 2: [("A", "13:02", sh, sh)]}
        ok = {1: True, 2: True}
        self.assertEqual(self.due("17:29", 3, done, lineups_ok=ok), [])                  # before the window
        # B is per game: 90 minutes before EACH game's puck (game 1 at 7 PM -> 5:30; game 2 at 10 PM -> 8:30)
        self.assertEqual(self.due("17:30", 3, done, lineups_ok=ok), [("B", 1, sp)])
        b1 = done[1] + [("B", "17:31", sp, sp)]
        self.assertEqual(self.due("20:29", 3, {1: b1, 2: done[2]}, lineups_ok=ok), [])
        self.assertEqual(self.due("20:30", 3, {1: b1, 2: done[2]}, lineups_ok=ok), [("B", 2, sp)])
        self.assertEqual(self.due("17:30", 2, done, lineups_ok=ok), [("B", 1, ["shots"])])    # tier 2: shots re-price once
        self.assertEqual(self.due("17:30", 4, done, lineups_ok=ok)[0], ("B", 1, ["shots", "saves", "goals"]))
        self.assertEqual(self.due("17:30", 1, done, lineups_ok=ok), [])                  # lower tiers: no B
        self.assertEqual(self.due("17:30", 0, done, lineups_ok=ok), [])

    def test_b_not_pulled_before_lineups_confirm(self):
        sh = ["shots"]
        done = {1: [("A", "13:02", sh, sh)], 2: [("A", "13:02", sh, sh)]}
        for tier in (2, 3, 4):
            for hhmm in ("17:30", "17:50", "18:14"):                                     # inside B window, before 45 min
                self.assertEqual(self.due(hhmm, tier, done, lineups_ok={1: False, 2: False}), [], (tier, hhmm))
                self.assertEqual(self.due(hhmm, tier, done), [], (tier, hhmm))              # no lineup info at all
        # one team confirmed is not enough
        self.assertEqual(self.due("17:40", 3, done, lineups_ok={1: False}), [])
        # confirmed late inside the window: pulled on the very next cycle
        self.assertEqual(self.due("17:52", 3, done, lineups_ok={1: True}), [("B", 1, ["shots", "saves"])])

    def test_fallback_shots_at_45_minutes_when_lineups_never_confirm(self):
        sh = ["shots"]
        done = {1: [("A", "13:02", sh, sh)], 2: [("A", "13:02", sh, sh)]}
        self.assertEqual(self.due("18:14", 4, done), [])
        self.assertEqual(self.due("18:15", 4, done), [("B", 1, ["shots"])])              # shots re-price only, no saves/goals
        self.assertEqual(self.due("18:15", 2, done), [("B", 1, ["shots"])])
        self.assertEqual(self.due("18:15", 1, done), [])                                 # lower tiers get no B
        # with a live pick the 45 minute read is one combined read, not two
        self.assertEqual(self.due("18:15", 3, done, live={1: {"shots"}}), [("B", 1, ["shots"])])
        # last chance is 20 minutes before puck; after that nothing
        self.assertEqual(self.due("18:40", 3, done), [("B", 1, ["shots"])])
        # 19 minutes left: too late for B, but the closing read C (every game since 2026-10-18) still runs
        self.assertEqual(self.due("18:41", 3, done), [("C", 1, ["shots"])])
        self.assertEqual(self.due("18:51", 3, done), [])
        # once the shots came back the fallback is not repeated
        got = {1: done[1] + [("B", "18:16", ["shots"], ["shots"])], 2: done[2]}
        self.assertEqual(self.due("18:30", 3, got), [])

    def test_malformed_lineups_state_is_unconfirmed(self):
        for bad in (None, [], {"teams": []}, {"teams": {"A": 1, "B": None}}, {"teams": {"A": {"page": "x"}}},
                    {"teams": {"A": {"page": []}}}):
            g = [dict(x, away="A", home="B") for x in self.games]
            self.assertEqual(odds.lineups_confirmed(bad, g), {1: False, 2: False})

    def test_late_confirmation_after_fallback_allows_the_rest(self):
        sh = ["shots"]
        done = {1: [("A", "13:02", sh, sh), ("B", "18:16", ["shots"], ["shots"])], 2: [("A", "13:02", sh, sh)]}
        self.assertEqual(self.due("18:30", 4, done, lineups_ok={1: True}), [("B", 1, ["saves", "goals"])])
        self.assertEqual(self.due("18:41", 4, done, lineups_ok={1: True}), [])

    def test_started_games_never_pulled(self):
        sh = ["shots"]
        done = {1: [("A", "13:02", sh, sh)], 2: [("A", "13:02", sh, sh)]}
        self.assertEqual(self.due("19:05", 4, done, lineups_ok={1: True, 2: True}, started={1: True}), [])
        self.assertEqual(self.due("18:30", 4, done, lineups_ok={1: True}, started={1: True}), [])

    def test_credits_per_game_lower_than_before(self):
        def old(tier):                       # the pre-2026-10-12 shape: A (shots+points from tier 2) then B
            a = 1 if tier <= 1 else 2
            b = {3: 2, 4: 4}.get(tier, 0)
            return a + b
        def new(tier):
            return len(odds.markets_for(tier, "A")) + len(odds.markets_for(tier, "B"))
        self.assertLess(new(3), old(3))
        self.assertLess(new(4), old(4))
        self.assertLessEqual(new(2), old(2))
        self.assertEqual(new(1), old(1))
        # a game whose lineups never confirm and has no live pick costs shots + points (fallback) at most
        self.assertEqual(len(odds.markets_for(4, "A")) + len(["shots"]), 2)
        self.assertLess(2, old(4))

    def test_next_read_time_follows_the_rules(self):
        sh = ["shots"]
        g = self.games
        f = lambda items: {gid: [{"pull": p, "at": common.parse_iso("2026-10-11T%s:00-04:00" % t), "markets": sh,
                                  "returned": r} for p, t, r in its] for gid, its in items.items()}
        done = f({1: [("A", "13:02", sh)], 2: [("A", "13:02", sh)]})
        nr = lambda hhmm, ok=None, tier=3, fetched=None: odds.next_read_at(
            common.parse_iso("2026-10-11T%s:00-04:00" % hhmm), g, tier, V, fetched if fetched is not None else done, {},
            True, lineups_ok=ok)
        iso = lambda t: common.parse_iso("2026-10-11T%s:00-04:00" % t)
        self.assertEqual(nr("14:00"), iso("18:15"))                                      # no lineup info: fallback time
        self.assertEqual(nr("17:40", ok={1: True}), iso("17:40"))                        # confirmed: next cycle
        self.assertEqual(nr("17:40", ok={}), iso("18:15"))                               # unconfirmed: the 45 min fallback
        self.assertEqual(nr("14:00", ok={}), iso("18:15"))                               # never the 90 min time
        self.assertEqual(nr("14:00", ok={1: True}), iso("17:30"))                        # confirmed already: B time
        self.assertEqual(nr("18:20", ok={}, tier=3, fetched=f({1: [("A", "13:02", sh), ("B", "18:16", ["shots"])],
                                                               2: [("A", "13:02", sh)]})), iso("21:15"))

    def test_c_closing_read_for_every_game(self):
        sh, sp = ["shots"], ["shots", "points"]
        done = {1: [("A", "13:02", sh, sh), ("B", "17:35", ["shots"], ["shots"])], 2: [("A", "13:02", sh, sh)]}
        self.assertEqual(self.due("18:14", 2, done, {1: {"shots"}}), [])
        self.assertEqual(self.due("18:15", 2, done, {1: {"shots"}}), [("C", 1, ["shots"])])
        self.assertEqual(self.due("18:15", 2, done, {}), [])                       # tier 2: no live pick, no C
        self.assertEqual(self.due("18:15", 3, done, {}), [("C", 1, ["shots"])])    # tier 3: closing read anyway
        now = common.parse_iso("2026-10-11T18:15:00-04:00")
        f = {g: [{"pull": p, "at": common.parse_iso("2026-10-11T%s:00-04:00" % t), "markets": m, "returned": r}
                 for p, t, m, r in done[g]] for g in done}
        tight = odds.due_pulls(now, self.games, 3, V, f, {}, {}, c_every_game=False)
        self.assertEqual(tight, [], "budget tight: C back to live picks only")
        self.assertEqual(self.due("18:15", 1, done, {1: {"shots"}}), [])           # tier 1 has no pull C
        self.assertEqual(self.due("18:50", 2, done, {1: {"shots"}}), [("C", 1, ["shots"])])    # 10 minutes left
        self.assertEqual(self.due("18:51", 2, done, {1: {"shots"}}), [])           # 9 minutes left: too late
        done[1].append(("C", "18:16", ["shots"], ["shots"]))
        self.assertEqual(self.due("18:30", 2, done, {1: {"shots"}}), [])           # C done once

    def test_unposted_market_is_asked_again_for_free(self):
        # A at 1:02 PM returned shots but points were not posted yet
        done = {1: [("A", "13:02", ["shots"], ["shots"])], 2: [("A", "13:02", ["shots"], [])]}
        self.assertEqual(self.due("13:12", 2, done), [])                           # asked 10 minutes ago: wait
        self.assertEqual(self.due("13:32", 2, done), [("A", 2, ["shots"])])


class KeyRotation(unittest.TestCase):
    def setUp(self):
        self.sim = Sim()
        os.environ.pop("PC_ODDS_FIXTURE_DIR")                 # use the real client, with the network replaced below
        os.environ["ODDS_API_KEYS"] = "aaaaaaaaaaaaaaaa1111\nbbbbbbbbbbbbbbbb2222, cccccccccccccccc3333"
        self.real_get = common.http_get
        self.calls = []

    def tearDown(self):
        common.http_get = self.real_get
        self.sim.close()

    def fake(self, behaviour):
        def get(url, **kw):
            key = url.split("apiKey=")[1].split("&")[0]
            self.calls.append(key[-4:])
            return behaviour(key, url)
        common.http_get = get

    def test_rotates_past_used_up_and_refused_keys(self):
        payload = json.dumps(world.odds_payload("CAR", "PHI", [("player_shots_on_goal", "X Y", 2.5, -120, -110)],
                                                "2026-10-11T17:00:00Z")).encode()

        def behaviour(key, url):
            if key.endswith("1111"):
                return common.Http(401, {}, b'{"message":"Usage quota has been reached","error_code":"OUT_OF_USAGE_CREDITS"}', "HTTP 401")
            if key.endswith("2222"):
                return common.Http(429, {}, b'{"message":"Too many requests"}', "HTTP 429")
            return common.Http(200, {"x-requests-remaining": "88", "x-requests-last": "1", "x-requests-used": "412"}, payload)
        self.fake(behaviour)
        now = common.parse_iso("2026-10-11T13:02:00-04:00")
        keys = odds.load_keys()
        self.assertEqual(len(keys), 3)                         # comma and newline separated both work
        pool = odds.Pool(keys, now)
        client = odds.Client(pool, helpers.cfg())
        js, cost = client.event_odds("ev1", "CAR", "PHI", ["player_shots_on_goal"], "2026-10-11", "A", 1)
        self.assertEqual(self.calls, ["1111", "2222", "3333"])
        self.assertEqual(cost, 1)
        self.assertEqual(js["bookmakers"][0]["key"], "hardrockbet")
        self.assertEqual([(s["left"], s["status"]) for s in pool.state], [(0, "empty"), (None, "limited"), (88, "ok")])
        self.assertEqual(pool.spent_on("2026-10-11"), 1)
        self.assertEqual(pool.public(), [{"n": 1, "left": 0}, {"n": 2, "left": None}, {"n": 3, "left": 88}])
        # the used-up key is not tried again
        self.calls.clear()
        client.event_odds("ev1", "CAR", "PHI", ["player_shots_on_goal"], "2026-10-11", "A", 1)
        self.assertEqual(self.calls, ["3333"])
        pool.save()
        raw = helpers.slurp(odds.ledger_path(), "r")
        for k in keys:
            self.assertNotIn(k, raw)

    def test_all_keys_dead(self):
        self.fake(lambda key, url: common.Http(401, {}, b'{"error_code":"OUT_OF_USAGE_CREDITS"}', "HTTP 401"))
        pool = odds.Pool(odds.load_keys(), common.parse_iso("2026-10-11T13:02:00-04:00"))
        client = odds.Client(pool, helpers.cfg())
        js, cost = client.event_odds("ev1", "CAR", "PHI", ["player_shots_on_goal"], "2026-10-11", "A", 1)
        self.assertIsNone(js)
        self.assertEqual(pool.total_left(), 0)
        self.assertIn("no odds key with credits left", client.errors)

    def test_network_failure_does_not_burn_through_keys(self):
        self.fake(lambda key, url: common.Http(0, {}, None, "TimeoutError"))
        pool = odds.Pool(odds.load_keys(), common.parse_iso("2026-10-11T13:02:00-04:00"))
        client = odds.Client(pool, helpers.cfg())
        js, cost = client.event_odds("ev1", "CAR", "PHI", ["player_shots_on_goal"], "2026-10-11", "A", 1)
        self.assertIsNone(js)
        self.assertEqual(self.calls, ["1111"])                 # a timeout is not the key's fault
        self.assertEqual([s["status"] for s in pool.state], ["ok", "ok", "ok"])


class Pulls(unittest.TestCase):
    def setUp(self):
        self.sim = Sim(pool=12)                                # 4 games left -> 3.0 a game -> tier 2, 6 today

    def tearDown(self):
        self.sim.close()

    def lines(self, away, home):
        s = self.sim
        return [s.line(away, 1, "shots", 2.5, 0.05), s.line(home, 1, "shots", 2.5, 0.05),
                s.line(away, 0, "points", 0.5, 0.02)]

    def test_plan_and_one_write(self):
        s = self.sim
        sl = s.at("09:00")
        self.assertEqual(sl["status"]["prices_state"], "not_yet")
        self.assertEqual(sl["empty"]["code"], "not_yet")
        self.assertEqual(sl["empty"]["sub"], "First read is due at 1:00 PM.")
        self.assertEqual(s.status()["tier"], 2)
        self.assertEqual(s.status()["budget_today"], 6)
        self.assertFalse(os.path.exists(s.path("odds", "2026-10-11.json")))
        s.set_odds("CAR", "PHI", self.lines("CAR", "PHI"), "2026-10-11T17:00:00Z")
        s.set_odds("VAN", "NYR", self.lines("VAN", "NYR"), "2026-10-11T17:00:00Z")
        sl = s.at("13:02")
        doc = common.read_json(s.path("odds", "2026-10-11.json"))
        self.assertEqual([(f["pull"], f["away"], f["cost"]) for f in doc["fetches"]], [("A", "CAR", 1), ("A", "VAN", 1)])
        self.assertEqual(s.status()["budget_used_today"], 2)
        self.assertEqual(s.status()["keys"], [{"n": 1, "left": 10}])
        self.assertEqual(sl["status"]["prices_state"], "ok")
        self.assertEqual(sl["status"]["pool"]["pulls_left"], 10)
        before = s.tree()
        s.at("13:12")                                          # nothing due: no second read, no spend
        self.assertEqual(s.status()["budget_used_today"], 2)
        self.assertEqual(s.tree()["odds/2026-10-11.json"], before["odds/2026-10-11.json"])

    def test_failure_midway_keeps_old_prices_and_never_pays_twice(self):
        s = self.sim
        s.at("09:00")
        s.set_odds("CAR", "PHI", self.lines("CAR", "PHI"), "2026-10-11T17:00:00Z")
        s.drop_odds("VAN", "NYR")                              # the feed will not answer for VAN at NYR
        s.at("13:02")
        self.assertFalse(os.path.exists(s.path("odds", "2026-10-11.json")), "a half pull must not be published")
        self.assertEqual(s.status()["budget_used_today"], 1)
        self.assertEqual(s.slate()["status"]["prices_state"], "feed_down")
        s.set_odds("VAN", "NYR", self.lines("VAN", "NYR"), "2026-10-11T17:00:00Z")
        s.at("13:12")                                          # retry: only the missing game is fetched
        doc = common.read_json(s.path("odds", "2026-10-11.json"))
        self.assertEqual(sorted((f["away"], f["at"][11:16]) for f in doc["fetches"]), [("CAR", "13:02"), ("VAN", "13:12")])
        self.assertEqual(s.status()["budget_used_today"], 2)
        self.assertEqual(s.slate()["status"]["prices_state"], "ok")

    def test_a_game_that_keeps_failing_does_not_hold_the_others_hostage(self):
        s = self.sim
        s.at("09:00")
        s.set_odds("CAR", "PHI", self.lines("CAR", "PHI"), "2026-10-11T17:00:00Z")
        s.drop_odds("VAN", "NYR")
        s.at("13:02")
        s.at("13:12")
        self.assertFalse(os.path.exists(s.path("odds", "2026-10-11.json")))
        s.at("13:32")                                          # held 30 minutes (limit 25): publish what we have
        doc = common.read_json(s.path("odds", "2026-10-11.json"))
        self.assertEqual([f["away"] for f in doc["fetches"]], ["CAR"])
        self.assertEqual(s.status()["budget_used_today"], 1)

    def test_small_pool_prices_the_earliest_games_only(self):
        s2 = Sim(pool=3)                                       # 3 credits / 4 games = 0.75 -> tier 0, budget 1
        try:
            s2.at("09:00")
            self.assertEqual((s2.status()["tier"], s2.status()["budget_today"]), (0, 1))
            self.assertIn("Hard Rock prices limited: 1 of 2 games, shots only. Odds keys nearly out.",
                          [b["text"] for b in s2.slate()["banners"]])
            s2.set_odds("CAR", "PHI", self.lines("CAR", "PHI"), "2026-10-11T17:00:00Z")
            s2.set_odds("VAN", "NYR", self.lines("VAN", "NYR"), "2026-10-11T17:00:00Z")
            sl = s2.at("13:02")
            doc = common.read_json(s2.path("odds", "2026-10-11.json"))
            self.assertEqual([(f["away"], f["requested"], f["cost"]) for f in doc["fetches"]], [("CAR", ["shots"], 1)])
            self.assertEqual(sl["status"]["prices_state"], "limited")
            self.assertEqual(s2.status()["budget_used_today"], 1)
        finally:
            s2.close()

    def test_empty_pool(self):
        s2 = Sim(pool=0)
        try:
            sl = s2.at("13:02")
            self.assertEqual(sl["status"]["prices_state"], "pool_empty")
            self.assertEqual(sl["empty"], {"code": "pool_empty", "text": "No Hard Rock prices today, so no picks.",
                                           "sub": "The odds pulls ran out."})
            self.assertIn("No Hard Rock prices today, odds keys are used up. No picks.",
                          [b["text"] for b in sl["banners"]])
        finally:
            s2.close()


if __name__ == "__main__":
    unittest.main()
