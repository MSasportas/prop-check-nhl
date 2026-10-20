"""QA round 2 (2026-10-12): M1 + m11 (Record history guard), M2 (every key refused), m1, m2, m3, m4, m5, m7,
m10, m12. The cycle-level M1 cases live in test_cycle.py."""
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

import helpers
from helpers import Sim
import common
import guard_record
import odds
import run
import world

UPD = "2026-10-11T17:00:00Z"
KEYS = ["k1QBaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "k2QBbbbbbbbbbbbbbbbbbbbbbbbbbbbb"]
REPO = os.path.dirname(helpers.SCRIPTS)
A = b'{"t":"shown","id":"a","at":"1"}\n'
B = b'{"t":"locked","id":"a","at":"2"}\n'
C = b'{"t":"graded","id":"a","at":"3"}\n'


def open_day(s):
    s.at("09:00")
    s.set_odds("CAR", "PHI", [s.line("CAR", 1, "shots", 2.5, 0.14), s.line("PHI", 1, "shots", 2.5, 0.14)], UPD)
    s.set_odds("VAN", "NYR", [s.line("VAN", 1, "shots", 2.5, 0.14), s.line("NYR", 1, "shots", 2.5, 0.14)], UPD)
    return s.at("13:02")


def gg_day(s):
    """Baseline read, then the 90-minute read for CAR@PHI with one Gap + Guard candidate. Returns (slate, cp)."""
    s.at("09:00")
    s.read("13:02")
    s.clock("17:00")
    cp = [s.gg_lines("CAR", 1)]
    return s.read("17:31", cp=cp), cp


# ---------------------------------------------------------------- M1 / m11: the guard against git
@unittest.skipUnless(shutil.which("git"), "needs git")
class GuardHistory(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="pc_guard2_")
        os.makedirs(os.path.join(self.d, "scripts"))
        os.makedirs(os.path.join(self.d, "data", "record"))
        shutil.copy(os.path.join(helpers.SCRIPTS, "guard_record.py"), os.path.join(self.d, "scripts"))
        self.log = os.path.join(self.d, "data", "record", "events.jsonl")
        self.git("init", "-q", "-b", "main")

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def git(self, *a, cwd=None):
        r = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"] + list(a),
                           cwd=cwd or self.d, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def commit(self, data, msg):
        if data is None:
            os.unlink(self.log)
        else:
            common.write_bytes(self.log, data)
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", msg)

    def guard(self, *args, cwd=None):
        return subprocess.run([sys.executable, os.path.join(cwd or self.d, "scripts", "guard_record.py")] + list(args),
                              capture_output=True, text=True, env=dict(os.environ, GIT_CEILING_DIRECTORIES=os.path.dirname(cwd or self.d)))

    def test_an_edited_committed_version_fails_history_but_not_the_head_check(self):
        self.commit(A, "one")
        self.commit(A + B, "two")
        self.assertEqual(self.guard("--history").returncode, 0)
        self.commit(A.replace(b'"1"', b'"9"') + B, "edited from outside")      # pushed already: HEAD == working
        self.assertEqual(self.guard().returncode, 0, "the old HEAD-only guard cannot see this")
        r = self.guard("--history")
        self.assertEqual(r.returncode, 1)
        self.assertIn("RECORD HISTORY: FAILED: a committed Record line was changed in commit", r.stdout)
        common.write_bytes(self.log, A.replace(b'"1"', b'"9"') + B + C)     # appending on top does not repair it
        self.assertEqual(self.guard("--history").returncode, 1)

    def test_deleted_and_recreated_fails(self):
        self.commit(A + B, "one")
        self.commit(None, "deleted")
        self.commit(B, "recreated")
        r = self.guard("--history")
        self.assertEqual(r.returncode, 1)
        self.assertIn("lost lines", r.stdout)

    def test_working_file_must_extend_the_last_version(self):
        self.commit(A, "one")
        common.write_bytes(self.log, A + B)
        self.assertEqual(self.guard("--history").returncode, 0)
        common.write_bytes(self.log, B)
        self.assertIn("(working file vs HEAD)", self.guard("--history").stdout)

    def test_only_new_versions_are_walked_after_a_clean_check(self):
        self.commit(A, "one")
        self.commit(A + B, "two")
        self.assertIn("(2 version(s) walked)", self.guard("--history").stdout)
        self.commit(A + B + C, "three")
        self.assertIn("(2 version(s) walked)", self.guard("--history").stdout)   # from "two" on
        self.assertIn("(1 version(s) walked)", self.guard("--history").stdout)

    def test_shallow_clone_fails(self):
        self.commit(A, "one")
        self.commit(A + B, "two")
        shallow = os.path.join(self.d + "_shallow")
        self.git("clone", "-q", "--depth", "1", "file://" + self.d, shallow, cwd=os.path.dirname(self.d))
        try:
            r = self.guard("--history", cwd=shallow)
            self.assertEqual(r.returncode, 1)
            self.assertIn("shallow", r.stdout)
        finally:
            shutil.rmtree(shallow, ignore_errors=True)

    def test_m11_absent_passes_only_when_truly_absent(self):
        common.write_bytes(self.log, A)
        self.assertEqual(self.guard().returncode, 0, "brand-new repo, nothing committed: an addition")
        other = os.path.join(self.d, "README")
        common.write_bytes(other, b"x\n")
        self.git("add", "README")
        self.git("commit", "-q", "-m", "no record yet")
        self.assertEqual(self.guard().returncode, 0, "HEAD exists and truly has no Record")
        self.assertEqual(self.guard("--history").returncode, 0)
        # a damaged repository (HEAD points at a commit that does not exist) must FAIL, not count as "absent"
        with open(os.path.join(self.d, ".git", "refs", "heads", "main"), "w") as f:
            f.write("0123456789012345678901234567890123456789\n")
        r = self.guard()
        self.assertEqual(r.returncode, 1)
        self.assertIn("RECORD GUARD: FAILED: git", r.stdout)
        self.assertEqual(self.guard("--history").returncode, 1)

    def test_m11_not_a_repository_fails(self):
        shutil.rmtree(os.path.join(self.d, ".git"))
        common.write_bytes(self.log, A)
        r = self.guard()
        self.assertEqual(r.returncode, 1)
        self.assertIn("not a git repository", r.stdout)

    def test_check_function_unchanged(self):
        self.assertIsNone(guard_record.check(A, A + B))
        self.assertEqual(guard_record.check(A + B, A), "the Record lost lines (2 committed, 1 now)")


# ---------------------------------------------------------------- M2: every key refused
class KeysRefused(unittest.TestCase):
    def setUp(self):
        self.s = Sim(pool=12)
        os.environ.pop("PC_ODDS_FIXTURE_DIR")
        os.environ["ODDS_API_KEYS"] = ",".join(KEYS)
        self.real = common.http_get
        self.modes = ["401", "401"]                          # per key: 401 | usage | ok
        events = helpers.load(os.path.join(self.s.w["odds"], "events.json"))
        payload = world.odds_payload("CAR", "PHI", [("player_shots_on_goal", world.name_of("CAR", 1), 2.5, -120, -110)], UPD)

        def fake(url, **kw):
            mode = self.modes[[k in url for k in KEYS].index(True)]
            if mode == "401":
                return common.Http(401, {}, json.dumps({"message": "Invalid API key"}).encode(), "HTTP 401")
            if mode == "usage":
                return common.Http(401, {"x-requests-remaining": "0"},
                                   b'{"error_code":"OUT_OF_USAGE_CREDITS","message":"Usage quota has been reached"}', "HTTP 401")
            head = {"x-requests-remaining": "300", "x-requests-last": "1" if "/odds" in url else "0"}
            return common.Http(200, head, json.dumps(payload if "/odds" in url else events).encode())
        common.http_get = fake

    def tearDown(self):
        common.http_get = self.real
        self.s.close()

    def assert_refused(self, sl, priced=False):
        self.assertEqual(sl["status"]["prices_state"], "keys_refused")
        self.assertEqual(self.s.status()["prices_state"], "keys_refused")
        stop = [b for b in sl["banners"] if b["text"] == odds.KEYS_REFUSED_TEXT]
        self.assertEqual([b["level"] for b in stop], ["stop"])
        texts = json.dumps(sl)
        for wrong in ("odds feed did not answer", "trying again", "used up", "ran out", "running low",
                      "Part of the last update failed"):
            self.assertNotIn(wrong, texts)
        self.assertIsNone(sl["status"]["next_price_read_at"], "no read is coming")
        self.assertTrue(self.s.status()["ok"] or self.s.status()["failed_step"] != "odds")
        if sl["empty"]:
            self.assertEqual((sl["empty"]["code"], sl["empty"]["sub"]), ("keys_refused", odds.KEYS_REFUSED_TEXT))
            self.assertEqual(sl["empty"]["text"], "No picks yet today" if priced else "No Hard Rock prices today, so no picks.")

    def test_fresh_day_every_key_401(self):
        sl = self.s.at("13:02")
        self.assert_refused(sl)
        self.assertIsNotNone(sl["empty"])
        sl = self.s.at("13:12")                              # stays refused on the next run (not "trying again")
        self.assert_refused(sl)
        self.assertIn("key 1 refused (401)", self.s.status()["odds_notes"])
        self.modes = ["ok", "ok"]                            # new keys work: back to normal at once
        sl = self.s.at("13:22")
        self.assertEqual(sl["status"]["prices_state"], "ok")
        self.assertNotIn(odds.KEYS_REFUSED_TEXT, json.dumps(sl))

    def test_refused_plus_used_up_is_refused(self):
        self.modes = ["usage", "401"]
        self.assert_refused(self.s.at("13:02"))

    def test_all_used_up_is_still_pool_empty(self):
        self.modes = ["usage", "usage"]
        self.assertEqual(self.s.at("13:02")["status"]["prices_state"], "pool_empty")

    def test_one_good_key_is_not_refused(self):
        self.modes = ["401", "ok"]
        sl = self.s.at("13:02")
        self.assertEqual(sl["status"]["prices_state"], "ok")
        self.assertNotIn(odds.KEYS_REFUSED_TEXT, json.dumps(sl))

    def test_day_with_a_plan_then_keys_refused(self):
        self.modes = ["ok", "ok"]
        sl = self.s.at("13:02")                              # plan made, pull A read prices
        self.assertEqual(sl["status"]["prices_state"], "ok")
        for t in ("CAR", "PHI", "VAN", "NYR"):
            self.s.set_lineup(t, "2026-10-11T20:00:00Z")
        self.modes = ["401", "401"]                          # keys revoked; pull B (points) is due at 5:30 PM
        sl = self.s.at("17:31")
        self.assert_refused(sl, priced=True)
        self.assertIsNotNone(sl["status"]["prices_at"], "the earlier read is still the last read")
        sl = self.s.at("17:41")
        self.assert_refused(sl, priced=True)

    def test_gap12_used_up_after_a_read_promises_no_next_check(self):
        self.modes = ["ok", "ok"]
        sl = self.s.at("13:02")
        self.assertIsNotNone(sl["status"]["next_price_read_at"], "keys work: a later read is planned")
        for t in ("CAR", "PHI", "VAN", "NYR"):
            self.s.set_lineup(t, "2026-10-11T20:00:00Z")
        self.modes = ["usage", "usage"]                      # every key runs dry at pull B
        self.s.at("17:31")
        sl = self.s.at("17:41")
        self.assertIsNone(sl["status"]["next_price_read_at"], "all used up: no read is coming")
        self.assertNotIn("Next price check", json.dumps(sl))

    def test_gap12_no_keys_after_a_read_promises_no_next_check(self):
        self.modes = ["ok", "ok"]
        self.assertIsNotNone(self.s.at("13:02")["status"]["next_price_read_at"])
        os.environ.pop("ODDS_API_KEYS")                      # keys removed from the secret
        sl = self.s.at("13:12")
        self.assertIsNone(sl["status"]["next_price_read_at"], "no keys: no read is coming")
        self.assertNotIn("Next price check", json.dumps(sl))

    def test_refused_state_survives_a_run_with_no_pull(self):
        self.modes = ["ok", "ok"]
        self.s.at("13:02")
        for t in ("CAR", "PHI", "VAN", "NYR"):
            self.s.set_lineup(t, "2026-10-11T20:00:00Z")
        self.modes = ["401", "401"]
        self.s.at("17:31")
        led = common.read_json(self.s.path("state", "credits.json"))
        self.assertEqual([k["status"] for k in led["keys"]], ["invalid", "invalid"])
        self.assertEqual(self.s.at("17:36")["status"]["prices_state"], "keys_refused")


# ---------------------------------------------------------------- m1, m2, m3, m7, m9, m12 on the made-up league
class Minors2(unittest.TestCase):
    def setUp(self):
        self.s = Sim(pool=12)

    def tearDown(self):
        self.s.close()

    def test_m1_prices_at_ignores_a_stale_read(self):
        s = self.s
        sl = open_day(s)
        first_at = sl["status"]["prices_at"]
        self.assertEqual(first_at, "2026-10-11T13:02:00-04:00")
        # pull C at 6:16 PM for CAR@PHI comes back with prices last updated at 4:00 PM: stale, not used
        s.set_odds("CAR", "PHI", [s.line("CAR", 1, "shots", 2.5, 0.14), s.line("PHI", 1, "shots", 2.5, 0.14)],
                   "2026-10-11T20:00:00Z")
        sl = s.at("18:16")
        fetched = common.read_json(s.path("odds", "2026-10-11.json"))["fetches"]
        self.assertTrue(any(f["at"].startswith("2026-10-11T18:16") for f in fetched), "the stale read did happen")
        self.assertEqual(sl["status"]["prices_at"], first_at)
        self.assertEqual(s.status()["prices_at"], first_at)

    def test_m2_no_promise_after_a_failed_pull_a(self):
        s = self.s
        s.at("09:00")
        sl = s.slate()
        self.assertTrue(any("Picks come from the reads 90 and 45 minutes before each game" in b["text"] for b in sl["banners"]), sl["banners"])
        for _, away, home, _ in world.GAMES:
            s.drop_odds(away, home)                          # pull A gets no answer
        sl = s.at("13:02")
        self.assertEqual(sl["status"]["prices_state"], "feed_down")
        texts = [b["text"] for b in sl["banners"]]
        self.assertFalse(any("Picks come from the reads" in t or "One price check" in t for t in texts), texts)
        self.assertTrue(any(t.startswith("The odds feed did not answer at 1:02 PM") for t in texts), texts)
        s.set_odds("CAR", "PHI", [s.line("CAR", 1, "shots", 2.5, 0.14)], UPD)
        s.set_odds("VAN", "NYR", [s.line("VAN", 1, "shots", 2.5, 0.14)], UPD)
        sl = s.at("13:12")                                   # the retry reads prices: the promise is back
        self.assertIn("Prices checked at 1:12 PM (shots). Picks come from the reads 90 and 45 minutes before each game.",
                      [b["text"] for b in sl["banners"]])

    def test_m3_days_left_capped_at_the_reset(self):
        cfg = helpers.cfg()
        plan = {"allowance": 1.0, "budget_today": 2}
        self.assertEqual(odds.days_to_reset("2026-10-12"), 20)
        self.assertEqual(odds.days_to_reset("2026-10-31"), 1)
        self.assertEqual(odds.days_to_reset("2026-12-31"), 1)
        self.assertEqual(odds.pool_summary(1000, 4, plan, [], cfg, (), "2026-10-12")["days_left"], 20)   # not 500
        self.assertEqual(odds.pool_summary(1000, 4, plan, [], cfg, (), "2026-10-31")["days_left"], 1)
        self.assertEqual(odds.pool_summary(10, 4, plan, [], cfg, (), "2026-10-12")["days_left"], 5)      # under the cap

    def test_m7_explain_writes_nothing(self):
        s = self.s
        gg_day(s)
        os.unlink(s.path("state", "rosters.json"))           # would be re-fetched and saved by a normal run
        before = s.tree()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(run.main(["--explain"]), 0)
        self.assertIn("PASSES BOTH CHECKS", buf.getvalue())
        self.assertEqual(s.tree(), before)

    def test_m12_shown_pick_is_not_repriced_from_a_failed_pair(self):
        s = self.s
        sl, cp = gg_day(s)
        p = s.pick("CAR", 1, sl)
        n_events = len(s.events())
        # 6:16 PM read: the pair's hold is 20% (fails the feed checks) and the price is far worse
        bad = ("player_shots_on_goal", world.name_of("CAR", 1), 1.5, -150, -150)
        sl = s.read("18:16", cp=[(bad, cp[0][1])])
        p2 = s.pick("CAR", 1, sl)
        self.assertIsNone(p2["pulled"])
        self.assertEqual((p2["price"], p2["prices"]), (p["price"], p["prices"]), "kept the frozen price")
        mine = [e for e in s.events()[n_events:] if e.get("id") == p["id"]]
        self.assertFalse([e for e in mine if e["t"] in ("price", "pulled")], mine)


# ---------------------------------------------------------------- page sentences (m4, m5, m10, M2)
class PageText(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(REPO, "index.html"), encoding="utf-8") as f:
            cls.html = f.read()

    def test_m4_rules_sheet(self):
        self.assertIn("at {gap_guard.price_gate|price} or better and no longer than {gap_guard.max_price|price}", self.html)
        self.assertIn("Parlays are not offered", self.html)
        self.assertNotIn("parlay_min_legs", self.html)
        self.assertNotIn("two or three legs", self.html)

    def test_m5_m10_m2_sentences(self):
        self.assertIn("Last night's picks are in the Record.", self.html)
        self.assertNotIn("Last night's results are in the Record.", self.html)
        self.assertNotIn("No open parlay right now", self.html)
        self.assertIn("case 'keys_refused':", self.html)
        self.assertIn(odds.KEYS_REFUSED_TEXT, self.html)


if __name__ == "__main__":
    unittest.main()
