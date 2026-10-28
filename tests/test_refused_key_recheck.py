"""A refused (401) key is not a feed failure, and is asked again at most hourly (2026-10-28 fix).

Before: every 10-minute run asked the refused key again, got 401 and recorded "The odds feed did not answer",
so odds_day.json and credits.json changed every run and a false feed failure could reach the page."""
import json
import os
import unittest

import helpers
from helpers import Sim
import common
import odds
import world

UPD = "2026-10-11T17:00:00Z"
KEYS = ["k1RKaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "k2RKbbbbbbbbbbbbbbbbbbbbbbbbbbbb"]


class RefusedKeyRecheck(unittest.TestCase):
    def setUp(self):
        self.s = Sim(pool=12)
        os.environ.pop("PC_ODDS_FIXTURE_DIR")                # the real client, with the network replaced below
        os.environ["ODDS_API_KEYS"] = ",".join(KEYS)
        self.real = common.http_get
        self.modes = ["401", "ok"]                           # per key: 401 | down | ok
        self.calls = []                                      # (key position, "events" | "odds")
        events = helpers.load(os.path.join(self.s.w["odds"], "events.json"))
        payload = world.odds_payload("CAR", "PHI", [("player_shots_on_goal", world.name_of("CAR", 1), 2.5, -120, -110)], UPD)

        def fake(url, **kw):
            i = [k in url for k in KEYS].index(True)
            self.calls.append((i + 1, "odds" if "/odds" in url else "events"))
            mode = self.modes[i]
            if mode == "401":
                return common.Http(401, {}, json.dumps({"message": "Invalid API key"}).encode(), "HTTP 401")
            if mode == "down":
                return common.Http(0, {}, None, "TimeoutError")
            head = {"x-requests-remaining": "300", "x-requests-last": "1" if "/odds" in url else "0"}
            return common.Http(200, head, json.dumps(payload if "/odds" in url else events).encode())
        common.http_get = fake

    def tearDown(self):
        common.http_get = self.real
        self.s.close()

    def day(self):
        return common.read_json(self.s.path("state", "odds_day.json"))

    def key1(self):
        return common.read_json(self.s.path("state", "credits.json"))["keys"][0]

    def key1_asked(self):
        return [c for c in self.calls if c == (1, "events")]

    def open_morning(self):
        self.s.at("09:00")                                   # the daily refresh: key 1 refused, key 2 answers
        self.assertEqual(self.key1()["status"], "invalid")
        self.assertEqual(self.key1()["checked_at"], "2026-10-11T09:00:00-04:00")
        self.assertIsNone(self.day()["last_fail_at"])
        self.calls.clear()

    def test_refused_key_not_asked_again_within_the_hour(self):
        self.open_morning()
        before = {k: v for k, v in self.s.tree().items() if k in ("state/odds_day.json", "state/credits.json")}
        for t in ("09:10", "09:20", "09:59"):
            self.s.at(t)
        self.assertEqual(self.key1_asked(), [], "a key refused under an hour ago is not asked again")
        self.assertEqual(self.key1()["checked_at"], "2026-10-11T09:00:00-04:00", "skipping does not touch checked_at")
        self.assertIsNone(self.day()["last_fail_at"])
        after = {k: v for k, v in self.s.tree().items() if k in before}
        self.assertEqual(after, before, "a quiet run leaves the odds day and the ledger unchanged")

    def test_refused_key_asked_again_after_an_hour_and_refusal_is_not_a_feed_failure(self):
        self.open_morning()
        self.s.at("10:00")
        self.assertEqual(self.key1_asked(), [(1, "events")], "an hour later the refused key is asked again")
        self.assertEqual(self.key1()["checked_at"], "2026-10-11T10:00:00-04:00")
        self.assertEqual(self.key1()["status"], "invalid")
        self.assertIsNone(self.day()["last_fail_at"], "a refusal is not the feed failing")
        self.assertIsNone(self.day()["fail_note"])
        self.assertNotIn("odds feed did not answer", json.dumps(self.s.slate()))

    def test_fixed_key_is_picked_up_within_the_hour(self):
        self.open_morning()
        self.modes = ["ok", "ok"]                            # Matt fixes key 1
        self.s.at("09:30")
        self.assertEqual(self.key1()["status"], "invalid", "not asked yet")
        self.s.at("10:00")
        self.assertEqual((self.key1()["status"], self.key1()["left"]), ("ok", 300))

    def test_a_real_feed_failure_is_still_recorded(self):
        self.open_morning()
        self.modes = ["down", "ok"]                          # an hour later the feed does not answer key 1
        self.s.at("10:00")
        self.assertEqual(self.key1_asked(), [(1, "events")])
        self.assertEqual(self.day()["last_fail_at"], "2026-10-11T10:00:00-04:00")
        self.assertEqual(self.day()["fail_note"], "The odds feed did not answer.")


class RefreshKeysUnit(unittest.TestCase):
    """refresh_keys on its own: which keys it asks and what it calls a feed failure."""
    NOW = "2026-10-11T13:00:00-04:00"

    def setUp(self):
        self.s = Sim(pool=12)
        os.environ.pop("PC_ODDS_FIXTURE_DIR")
        os.environ["ODDS_API_KEYS"] = ",".join(KEYS)
        self.real = common.http_get
        self.calls = []

    def tearDown(self):
        common.http_get = self.real
        self.s.close()

    def client(self, key1_checked_at, answer):
        now = common.parse_iso(self.NOW)
        common.write_json(odds.ledger_path(), {"count": 2, "spent": [], "keys": [
            {"n": 1, "left": None, "status": "invalid", "checked_at": key1_checked_at, "month": "2026-10"},
            {"n": 2, "left": 300, "status": "ok", "checked_at": key1_checked_at, "month": "2026-10"}]})

        def fake(url, **kw):
            self.calls.append([k in url for k in KEYS].index(True) + 1)
            return answer
        common.http_get = fake
        return odds.Client(odds.Pool(odds.load_keys(), now), helpers.cfg())

    def test_invalid_key_checked_59_minutes_ago_is_skipped(self):
        c = self.client("2026-10-11T12:01:00-04:00", common.Http(401, {}, b'{"message":"Invalid"}', "HTTP 401"))
        self.assertIsNone(c.refresh_keys(only_unknown=True))
        self.assertEqual(self.calls, [])
        self.assertFalse(c.refresh_failed)
        self.assertEqual(c.pool.state[0]["checked_at"], "2026-10-11T12:01:00-04:00")

    def test_invalid_key_checked_60_minutes_ago_is_asked(self):
        c = self.client("2026-10-11T12:00:00-04:00", common.Http(401, {}, b'{"message":"Invalid"}', "HTTP 401"))
        self.assertIsNone(c.refresh_keys(only_unknown=True))
        self.assertEqual(self.calls, [1])
        self.assertFalse(c.refresh_failed, "a refusal alone is not a feed failure")
        self.assertEqual(c.pool.state[0]["checked_at"], self.NOW)

    def test_feed_down_is_a_failure(self):
        c = self.client("2026-10-11T12:00:00-04:00", common.Http(0, {}, None, "TimeoutError"))
        self.assertIsNone(c.refresh_keys(only_unknown=True))
        self.assertTrue(c.refresh_failed)

    def test_full_refresh_still_asks_every_key(self):
        c = self.client("2026-10-11T12:59:00-04:00", common.Http(401, {}, b'{"message":"Invalid"}', "HTTP 401"))
        c.refresh_keys(only_unknown=False)
        self.assertEqual(self.calls, [1, 2], "the daily refresh is not throttled")


if __name__ == "__main__":
    unittest.main()
