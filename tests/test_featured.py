"""Sides and totals tracking (featured.py, Matt 2026-11-03): one bulk call after each shots read, tracked only."""
import os
import unittest

import helpers
from helpers import Sim
import common
import featured
import world


def book(key, ml=(-150, 130), pl=(1.5, 170, -200), tot=(6.5, -110, -110)):
    return {"key": key, "markets": [
        {"key": "h2h", "last_update": "2026-10-11T17:00:00Z",
         "outcomes": [{"name": "Philadelphia Flyers", "price": ml[0]}, {"name": "Carolina Hurricanes", "price": ml[1]}]},
        {"key": "spreads", "last_update": "2026-10-11T17:00:00Z",
         "outcomes": [{"name": "Philadelphia Flyers", "price": pl[1], "point": -pl[0]},
                      {"name": "Carolina Hurricanes", "price": pl[2], "point": pl[0]}]},
        {"key": "totals", "last_update": "2026-10-11T17:00:00Z",
         "outcomes": [{"name": "Over", "price": tot[1], "point": tot[0]}, {"name": "Under", "price": tot[2], "point": tot[0]}]},
        {"key": "player_shots_on_goal", "last_update": "2026-10-11T17:00:00Z", "outcomes": []}]}


def payload():
    out = []
    for gid, a, h, st in world.GAMES:
        out.append({"id": "ev%d" % gid, "commence_time": st, "home_team": world.TEAMS[h], "away_team": world.TEAMS[a],
                    "bookmakers": [book("hardrockbet"), book("pinnacle"), book("draftkings"), book("notasked")]})
    return out


class Featured(unittest.TestCase):
    def test_one_bulk_call_per_new_shots_read_all_games_same_books_tracked_only(self):
        s = Sim(pool=200)
        try:
            world.write(os.path.join(s.w["odds"], "featured.json"), payload())
            s.at("09:00")
            self.assertFalse(os.path.exists(s.path("featured", "%s.json" % world.SLATE)), "no shots read yet")
            s.at("13:02")                                                     # pull A for both games
            st = common.read_json(s.path("featured", "%s.json" % world.SLATE))
            self.assertEqual(len(st["snaps"]), 1)
            snap = st["snaps"][0]
            self.assertEqual(snap["cost"], 3)                                 # h2h + spreads + totals, one region
            self.assertEqual(sorted(snap["games"]), ["2026020901", "2026020902"])
            g = snap["games"]["2026020901"]
            self.assertEqual(sorted(g["books"]), ["draftkings", "hardrockbet", "pinnacle"])   # only the books we ask
            self.assertEqual(sorted(g["books"]["hardrockbet"]), ["h2h", "spreads", "totals"])  # no player markets
            self.assertEqual(g["books"]["pinnacle"]["totals"]["outcomes"][0], {"name": "Over", "price": -110, "point": 6.5})
            self.assertEqual(sorted(st["done"]), ["2026020901:A", "2026020902:A"])
            led = common.read_json(s.path("state", "credits.json"))
            self.assertEqual([e["cost"] for e in led["spent"] if e["pull"] == "F"], [3])
            s.at("13:30")                                                     # no new shots read: no new call
            self.assertEqual(len(common.read_json(s.path("featured", "%s.json" % world.SLATE))["snaps"]), 1)
            sl = s.slate()
            self.assertNotIn("featured", str(sl.get("picks")))               # never on the page as a pick
            self.assertFalse(any(e.get("market") in ("h2h", "spreads", "totals") for e in s.events()))   # never the Record
        finally:
            s.close()

    def test_no_fixture_means_no_spend_and_never_in_a_dry_run(self):
        s = Sim(pool=60)
        try:
            s.at("13:02")
            self.assertFalse(os.path.exists(s.path("featured", "%s.json" % world.SLATE)))
            led = common.read_json(s.path("state", "credits.json")) or {}
            self.assertEqual([e for e in led.get("spent", []) if e["pull"] == "F"], [])
            games = list(s.inputs().games.values())
            res = featured.check(common.parse_iso("2026-10-11T13:05:00-04:00"), world.SLATE, games, {}, helpers.cfg(), dry_run=True)
            self.assertEqual(res["note"], "dry run")
        finally:
            s.close()

    def test_due_reads_skip_started_games_and_done_reads(self):
        games = [{"id": 1, "start": "2026-10-11T19:00:00-04:00"}, {"id": 2, "start": "2026-10-11T12:00:00-04:00"}]
        day = {"fetches": [{"game_id": 1, "pull": "A", "at": "2026-10-11T13:00:00-04:00", "markets": {"shots": {}}},
                           {"game_id": 1, "pull": "B", "at": "2026-10-11T17:30:00-04:00", "markets": {"shots": {}}},
                           {"game_id": 2, "pull": "A", "at": "2026-10-11T09:00:00-04:00", "markets": {"shots": {}}}]}
        now = common.parse_iso("2026-10-11T17:31:00-04:00")
        self.assertEqual(featured.due_reads(day, games, now, {}, {"1:A"}), ["1:B"])


if __name__ == "__main__":
    unittest.main()
