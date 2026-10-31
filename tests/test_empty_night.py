"""TEAM.md section 7 item 29 (2026-10-30): (a) the all_started empty state gives the real reason when nothing was
posted; (b) stats.team_status does not mark a team "stats behind" for its own game on the slate date."""
import os
import shutil
import tempfile
import unittest
from datetime import datetime
from types import SimpleNamespace

import helpers  # noqa: F401  (puts scripts/ on sys.path)
import common
import engine
import nhl
import stats

SLATE = "2026-10-30"
NOW = datetime(2026, 10, 30, 22, 0, tzinfo=common.ET)


def _inp(facts):
    cfg = {"ops": {"gap_guard": {"active": True, "live_from": "2026-10-20"}}}
    return SimpleNamespace(facts=facts, cfg=cfg, slate=SLATE, now=NOW)


def _status():
    return {"stats_state": "ok", "prices_state": "ok", "prices_at": "2026-10-30T17:50:00-04:00",
            "next_price_read_at": None}


GAMES = [{"id": i, "started": True} for i in (1, 2, 3)]


def _pick(pulled, gid=1):
    return {"game_id": gid, "pulled": pulled}


class AllStartedEmpty(unittest.TestCase):
    def empty(self, facts, picks=()):
        return engine._empty(_inp(facts), _status(), list(picks), GAMES, None)

    def test_the_real_reason_when_nothing_was_posted(self):
        e = self.empty({"flag_reads": {"games": 3, "lines": 59}})
        self.assertEqual(e["code"], "all_started")
        self.assertEqual(e["text"], "Every game has started.")
        self.assertEqual(e["sub"], "No picks were posted tonight. 59 lines read across 3 games, none cleared both checks.")

    def test_vetoes_are_said(self):
        e = self.empty({"flag_reads": {"games": 3, "lines": 59}, "gg_vetoes": 1})
        self.assertTrue(e["sub"].endswith("none cleared both checks. 1 had a gap but our model said no."), e["sub"])
        e = self.empty({"flag_reads": {"games": 1, "lines": 1}, "gg_vetoes": 2})
        self.assertEqual(e["sub"], "No picks were posted tonight. 1 line read across 1 game, none cleared both checks. "
                                   "2 had a gap but our model said no.")

    def test_no_reads_keeps_the_short_sentence(self):
        for facts in ({}, {"flag_reads": {"games": 0, "lines": 0}}):
            self.assertEqual(self.empty(facts)["sub"], "No picks were posted tonight.")

    def test_all_pulled_says_where_they_are(self):
        e = self.empty({"flag_reads": {"games": 3, "lines": 59}}, [_pick(True), _pick(True, 2)])
        self.assertEqual(e["code"], "all_started")
        self.assertEqual(e["sub"], "Tonight's 2 picks were pulled; see Pulled today.")
        e = self.empty({"flag_reads": {"games": 3, "lines": 59}}, [_pick(True)])
        self.assertEqual(e["sub"], "Tonight's pick was pulled; see Pulled today.")

    def test_shown_picks_unchanged(self):
        e = self.empty({"flag_reads": {"games": 3, "lines": 59}}, [_pick(False), _pick(True)])
        self.assertEqual(e, {"code": "all_started", "text": "Every game has started.",
                             "sub": "Tonight's picks are under Started."})


class TeamStatusSlateDate(unittest.TestCase):
    SEASON = 20262027

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="pc_ts_")
        self.old = os.environ.get("PC_DATA_DIR")
        os.environ["PC_DATA_DIR"] = self.root
        os.makedirs(os.path.join(self.root, "state"), exist_ok=True)

    def tearDown(self):
        if self.old is None:
            os.environ.pop("PC_DATA_DIR", None)
        else:
            os.environ["PC_DATA_DIR"] = self.old
        shutil.rmtree(self.root, ignore_errors=True)

    def game(self, gid, date, away, home):
        return {"id": gid, "date": date, "away": away, "home": home, "season": self.SEASON,
                "type": nhl.REGULAR, "sched": "OK", "state": "FINAL"}

    def test_tonights_final_game_is_not_stats_behind(self):
        games = [self.game(1, "2026-10-29", "BOS", "TOR"), self.game(2, SLATE, "NJD", "VGK")]
        common.write_json(stats.meta_path(), {"season": self.SEASON, "bad": {}, "through": "2026-10-29",
                                              "verified": {"1:BOS": 1, "1:TOR": 1}})
        behind, through, _ = stats.team_status(self.SEASON, games, SLATE)
        self.assertEqual(behind, {})
        self.assertEqual(through, "2026-10-29")
        # an earlier unverified game still counts
        common.write_json(stats.meta_path(), {"season": self.SEASON, "bad": {}, "verified": {"1:BOS": 1}})
        behind, _, _ = stats.team_status(self.SEASON, games, SLATE)
        self.assertEqual(behind, {"TOR": "stats behind"})
        # the next slate does count it
        behind, _, _ = stats.team_status(self.SEASON, games, "2026-10-31")
        self.assertEqual(set(behind), {"TOR", "NJD", "VGK"})


if __name__ == "__main__":
    unittest.main()
