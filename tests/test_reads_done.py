"""2026-11-02 (Matt): a game whose pick reads are all in says so on the page ("Checks done"), so a 0-pick game reads as
finished, not pending. odds.shots_reads_done is the rule; run.py facts -> slate.json games[].reads_done carries it."""
import json
import os
import unittest
from datetime import timedelta

import helpers
from helpers import Sim
import common
import odds
import world

V = helpers.cfg()["values"]
G1, G2 = 2026020901, 2026020902
START = "2026-11-02T19:00:00-05:00"
G = {"id": 1, "start": START}


def at(hhmm):
    return common.parse_iso("2026-11-02T%s:00-05:00" % hhmm)


def read(hhmm, pull="C", others=True, shots=True, gid=1):
    f = {"game_id": gid, "pull": pull, "at": common.iso(at(hhmm)), "markets": {"shots": {}} if shots else {}}
    if others:
        f["others"] = {}
    return f


class Rule(unittest.TestCase):
    def test_not_done_before_the_45_minute_read(self):
        self.assertFalse(odds.shots_reads_done(at("17:40"), G, 4, V, [read("17:31", "B")]))

    def test_done_once_the_45_minute_read_returned_shots_with_other_books(self):
        self.assertTrue(odds.shots_reads_done(at("18:20"), G, 4, V, [read("17:31", "B"), read("18:16")]))

    def test_a_hard_rock_only_or_empty_read_does_not_count(self):
        self.assertFalse(odds.shots_reads_done(at("18:20"), G, 4, V, [read("18:16", others=False)]))
        self.assertFalse(odds.shots_reads_done(at("18:20"), G, 4, V, [read("18:16", shots=False)]))

    def test_the_1pm_read_and_other_games_never_count(self):
        self.assertFalse(odds.shots_reads_done(at("18:20"), G, 4, V, [read("18:16", "A"), read("18:16", gid=2)]))

    def test_done_when_the_last_window_closed_even_without_the_read(self):
        self.assertFalse(odds.shots_reads_done(at("18:49"), G, 4, V, []))     # 11 min out: a retry can still come
        self.assertTrue(odds.shots_reads_done(at("18:51"), G, 4, V, []))      # 9 min out: nothing more is read

    def test_tier_1_has_no_45_minute_read_so_the_90_minute_read_is_the_last(self):
        self.assertTrue(odds.shots_reads_done(at("17:40"), G, 1, V, [read("17:31", "B")]))
        self.assertFalse(odds.shots_reads_done(at("17:40"), G, 2, V, [read("17:31", "B")]))

    def test_tier_0_is_never_done(self):
        self.assertFalse(odds.shots_reads_done(at("18:55"), G, 0, V, [read("18:16")]))


class EndToEnd(unittest.TestCase):
    def test_slate_marks_each_game_once_its_45_minute_read_is_in_and_drops_it_at_puck(self):
        s = Sim(pool=500, rules="current")
        try:
            path = os.environ["PC_CONFIG"]
            with open(path, encoding="utf-8") as f:
                c = json.load(f)
            c["ops"]["gap_guard"]["live_from"] = "2026-10-01"
            with open(path, "w", encoding="utf-8") as f:
                json.dump(c, f)
            s.at("09:00")
            done = {}
            for hhmm in ("13:02", "17:31", "18:16", "18:31", "19:16", "20:05"):
                sl = s.read(hhmm)
                done[hhmm] = {g["id"]: g["reads_done"] for g in sl["games"]}
            self.assertEqual(done["17:31"], {G1: False, G2: False})
            self.assertEqual(done["18:16"], {G1: True, G2: False})     # G1's 45-minute read is in
            self.assertEqual(done["19:16"], {G1: False, G2: True})     # G1 started (locked), G2's last read is in
        finally:
            s.close()


if __name__ == "__main__":
    unittest.main()
