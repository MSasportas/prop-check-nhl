"""goalies.py: starting goalies for the game list (display only)."""
import json
import os
import shutil
import tempfile
import unittest

import helpers  # noqa: F401
import common
import goalies

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.join(HERE, "fixtures", "df_goalies_sample.json")


def sample():
    with open(SAMPLE) as f:
        return json.load(f)


class T(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="pc_goalies_")
        self.saved = {k: os.environ.get(k) for k in ("PC_DATA_DIR", "PC_LINEUP_FIXTURE_DIR", "PC_NOW")}
        os.environ.update(PC_DATA_DIR=self.dir, PC_LINEUP_FIXTURE_DIR=self.dir)
        os.environ["PC_NOW"] = "2026-10-11T10:00:00-04:00"

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_parse_names_and_status(self):
        d = sample()
        out = goalies.parse(d, str(d["date"])[:10])
        self.assertEqual(out["WSH"], {"name": "Logan Thompson", "status": "confirmed"})
        self.assertEqual(out["SEA"]["name"], "Joey Daccord")
        self.assertIn(out["SEA"]["status"], ("confirmed", "expected"))

    def test_not_confirmed_is_expected(self):
        d = sample()
        d["data"][0]["homeNewsStrengthName"] = "Likely"
        self.assertEqual(goalies.parse(d, str(d["date"])[:10])["WSH"]["status"], "expected")

    def test_other_days_page_is_ignored(self):
        d = sample()
        self.assertIsNone(goalies.parse(d, "2030-01-01"))
        self.assertIsNone(goalies.parse({"nope": 1}, "2026-10-11"))
        self.assertIsNone(goalies.parse(None, "2026-10-11"))

    def test_check_saves_only_on_change_and_survives_a_dead_page(self):
        d = sample()
        slate = str(d["date"])[:10]
        page = os.path.join(self.dir, "starting-goalies.json")
        with open(page, "w") as f:
            json.dump(d, f)
        games = [{"id": 1}]
        now = common.now()
        self.assertEqual(goalies.check(now, slate, games, {})["note"], "%d goalies read" % len(goalies.parse(d, slate)))
        self.assertEqual(goalies.load(slate)["teams"]["WSH"]["status"], "confirmed")
        before = os.stat(goalies.path()).st_mtime_ns
        goalies.check(now, slate, games, {})
        self.assertEqual(os.stat(goalies.path()).st_mtime_ns, before)             # nothing changed: no write
        os.remove(page)
        self.assertEqual(goalies.check(now, slate, games, {})["note"], "goalie page not read")
        self.assertEqual(goalies.load(slate)["teams"]["WSH"]["name"], "Logan Thompson")    # last good read kept
        self.assertEqual(goalies.check(now, slate, games, {1: True})["status"], "skipped")  # nothing ahead


if __name__ == "__main__":
    unittest.main()
