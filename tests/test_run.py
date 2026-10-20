"""run.py as a whole: safe to run twice, quiet when nothing changed, honest when something failed,
and never lets an odds key reach a file or the console."""
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
import lineups
import odds
import run
import world

UPD = "2026-10-11T17:00:00Z"
KEYS = ["k1SECRETaaaaaaaaaaaaaaaaaaaaaaaa", "k2SECRETbbbbbbbbbbbbbbbbbbbbbbbb"]


def day_lines(s):
    """Two Gap + Guard candidates in each game (CAR@PHI 7 PM, VAN@NYR 8 PM)."""
    return [s.gg_lines("CAR", 1), s.gg_lines("PHI", 2)], [s.gg_lines("VAN", 1), s.gg_lines("NYR", 2)]


def open_day(s):
    """09:00 stats, 1 PM baseline read, 90-minute read for the 7 PM game (2 picks), 90-minute read for the 8 PM game
    (the night cap of 3 leaves one pick). Returns the slate."""
    s.at("09:00")
    s.read("13:02")
    s.clock("17:00")
    cp, vn = day_lines(s)
    s.read("17:31", cp=cp)
    return s.read("18:31", cp=cp, vn=vn)


class Idempotent(unittest.TestCase):
    def setUp(self):
        self.s = Sim(pool=12)

    def tearDown(self):
        self.s.close()

    def twice(self, hhmm, day=world.SLATE):
        """Run three times at one clock time. The 2nd run may only touch status.json; the 3rd touches nothing."""
        self.s.at(hhmm, day)
        one = self.s.tree()
        self.s.at(hhmm, day)
        two = self.s.tree()
        changed = sorted(k for k in set(one) | set(two) if one.get(k) != two.get(k))
        self.assertIn(changed, ([], ["status.json"]), "second run at %s changed %s" % (hhmm, changed))
        self.s.at(hhmm, day)
        self.assertEqual(self.s.tree(), two, "third run at %s changed something" % hhmm)

    def test_every_stage_of_the_day_is_safe_to_run_again(self):
        s = self.s
        self.twice("09:00")
        s.read("13:02")
        self.twice("13:02")
        s.set_lineup("CAR", "2026-10-11T20:00:00Z")
        self.twice("16:30")
        s.clock("17:00")
        cp, vn = day_lines(s)
        s.read("17:31", cp=cp)
        self.twice("17:31")
        self.assertEqual([e["t"] for e in s.events()], ["shown", "shown"])      # 2 picks, shown once
        s.read("18:16", cp=cp)
        self.twice("18:16")
        s.read("18:31", cp=cp, vn=vn)
        self.twice("18:31")
        self.twice("19:00")
        self.twice("20:01")
        car, phi, van, nyr = (world.pid_of(t, i) for t, i in (("CAR", 1), ("PHI", 2), ("VAN", 1), ("NYR", 2)))
        s.set_box(2026020901, "CAR", "PHI", {car: (4, 0, 0), phi: (1, 0, 0)})
        s.set_box(2026020902, "VAN", "NYR", {nyr: (5, 0, 0), van: (3, 0, 0)})
        s.set_states({2026020901: "OFF", 2026020902: "OFF"})
        self.twice("23:10")
        self.twice("09:00", day="2026-10-12")
        kinds = [e["t"] for e in s.events()]
        self.assertEqual(kinds.count("shown"), 4)                      # no night cap (2026-10-20)
        self.assertEqual(kinds.count("graded"), 4)
        self.assertEqual(kinds.count("locked"), 4)
        ids = [(e["t"], e["id"]) for e in s.events() if e["t"] in ("shown", "locked", "graded", "pulled")]
        self.assertEqual(len(ids), len(set(ids)), "no pick is shown, locked, pulled or graded twice")

    def test_nothing_changed_means_no_file_changes_until_the_heartbeat(self):
        s = self.s
        open_day(s)
        base = s.tree()
        gen = s.slate()["generated_at"]
        s.at("18:41")                                                   # 10 minutes on: nothing to do
        diff = sorted(k for k in set(base) | set(s.tree()) if base.get(k) != s.tree().get(k))
        self.assertEqual(diff, [], "an idle run must not create a commit")
        s.at("18:50")
        self.assertEqual(s.tree(), base)
        sl = s.at("18:51")                                              # 20 minutes: refresh the heartbeat
        self.assertNotEqual(sl["generated_at"], gen)
        self.assertEqual(sl["generated_at"][11:16], "18:51")
        self.assertEqual({k for k in s.tree() if s.tree()[k] != base[k]} - {"paper/summary.json", "state/lineups.json"}, {"slate.json", "status.json"})
        self.assertEqual(s.status()["finished_at"][11:16], "18:51")


class Failures(unittest.TestCase):
    def setUp(self):
        self.s = Sim(pool=12)

    def tearDown(self):
        self.s.close()

    def test_one_bad_step_does_not_stop_the_run_and_the_page_is_told(self):
        s = self.s
        open_day(s)
        good = s.status()["last_ok_at"]
        real = lineups.check
        lineups.check = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
        try:
            sl = s.at("18:40")
        finally:
            lineups.check = real
        st = s.status()
        self.assertEqual((st["ok"], st["failed_step"], st["last_ok_at"]), (False, "lineups", good))
        self.assertEqual([x["status"] for x in st["steps"] if x["step"] == "lineups"], ["failed"])
        self.assertEqual([x["status"] for x in st["steps"] if x["step"] == "engine"], ["ok"])
        self.assertEqual(sl["status"]["last_run"], {"ok": False, "at": "2026-10-11T18:40:00-04:00", "failed_step": "lineups"})
        self.assertEqual(sl["banners"][0]["text"],
                         "Part of the last update failed at 6:40 PM (lineups). Some of what is below may be older.")
        self.assertEqual(len([p for p in sl["picks"] if p["rank"]]), 4)       # picks are still there
        sl = s.at("18:50")                                                    # next good run clears it
        self.assertTrue(s.status()["ok"])
        self.assertTrue(sl["status"]["last_run"]["ok"])
        self.assertFalse(any("failed" in b["text"] for b in sl["banners"]))

    def test_damaged_record_stops_the_engine_and_keeps_the_old_slate(self):
        s = self.s
        sl0 = open_day(s)
        log = s.log_bytes()
        common.write_bytes(s.path("record", "events.jsonl"), log + b"{broken\n")
        s.prev_log = log + b"{broken\n"
        sl = s.at("18:41")
        st = s.status()
        self.assertEqual((st["ok"], st["failed_step"]), (False, "odds"))      # the first step that reads the Record
        self.assertEqual(s.log_bytes(), log + b"{broken\n", "a damaged Record is never written to")
        self.assertEqual(sl["picks"], sl0["picks"])                           # old slate kept as it was ...
        self.assertEqual(sl["generated_at"], sl0["generated_at"])
        self.assertEqual(sl["banners"][0], {"level": "stop", "text": "The last update failed at 6:41 PM (odds). Showing 6:31 PM data."})
        self.assertEqual(sl["status"]["last_run"]["ok"], False)

    def test_workflow_failure_script(self):
        s = self.s
        sl0 = open_day(s)
        log = s.log_bytes()
        env = dict(os.environ, PC_NOW="2026-10-11T18:50:00-04:00")
        r = subprocess.run([sys.executable, os.path.join(helpers.SCRIPTS, "fail_status.py"), "push"],
                           env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        st, sl = s.status(), s.slate()
        self.assertEqual((st["ok"], st["failed_step"], st["failed_at"]), (False, "push", "2026-10-11T18:50:00-04:00"))
        self.assertEqual(sl["banners"][0], {"level": "stop", "text": "The last update failed at 6:50 PM (push). Showing 6:31 PM data."})
        self.assertEqual(sl["status"]["last_run"], {"ok": False, "at": "2026-10-11T18:50:00-04:00", "failed_step": "push"})
        self.assertEqual((sl["picks"], sl["generated_at"]), (sl0["picks"], sl0["generated_at"]))
        self.assertEqual(s.log_bytes(), log)
        subprocess.run([sys.executable, os.path.join(helpers.SCRIPTS, "fail_status.py"), "run"], env=env, capture_output=True)
        self.assertEqual(sum(1 for b in s.slate()["banners"] if b["text"].startswith("The last update failed")), 1)
        sl = s.at("18:55")                                                    # the next good run clears it
        self.assertTrue(s.status()["ok"])
        self.assertIsNone(s.status()["failed_step"])
        self.assertFalse(any(b["text"].startswith("The last update failed") for b in sl["banners"]))

    def test_nhl_down_with_no_saved_schedule(self):
        s2 = Sim(pool=12)
        try:
            os.environ["PC_NHL_FIXTURE_DIR"] = os.path.join(s2.root, "empty")
            s2.at("09:00")
            st = s2.status()
            self.assertEqual((st["ok"], st["failed_step"], st["sources"]["nhl_web"]), (False, "schedule", "failed"))
            self.assertIsNone(s2.slate(), "with nothing known, no slate is invented")
        finally:
            s2.close()

    def test_nhl_down_later_uses_the_saved_schedule_and_says_so(self):
        s = self.s
        open_day(s)
        os.environ["PC_NHL_FIXTURE_DIR"] = os.path.join(s.root, "empty")
        sl = s.at("18:41")
        self.assertEqual(s.status()["failed_step"], "schedule")
        self.assertEqual(len([p for p in sl["picks"] if p["rank"]]), 4)
        self.assertIn("Part of the last update failed at 6:41 PM (schedule).", sl["banners"][0]["text"])
        sl = s.at("19:05")                                              # still down at puck time: the clock locks the picks
        self.assertEqual([p["state"] for p in sl["picks"] if p["game_id"] == 2026020901], ["locked_unconfirmed"] * 2)


class Modes(unittest.TestCase):
    def setUp(self):
        self.s = Sim(pool=12)

    def tearDown(self):
        self.s.close()

    def test_dry_run_changes_nothing(self):
        s = self.s
        s.at("09:00")
        s.set_odds("CAR", "PHI", [s.line("CAR", 1, "shots", 2.5, 0.14)], UPD)
        before = s.tree()
        s.clock("13:02")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            run.main(["--dry-run"])
        os.environ["PC_DATA_DIR"] = s.w["data"]
        self.assertEqual(s.tree(), before)
        self.assertIn("DRY RUN", buf.getvalue())
        self.assertIn("no odds credits spent", buf.getvalue())

    def test_only_one_step(self):
        s = self.s
        open_day(s)
        s.clock("18:55")
        with contextlib.redirect_stdout(io.StringIO()):
            run.main(["--only", "grade"])
        self.assertEqual([x["step"] for x in s.status()["steps"]], ["grade"])
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(run.main(["--only", "nonsense"]), 2)
        self.assertIn("unknown step", buf.getvalue())

    def test_rules_json_is_generated_from_config(self):
        self.s.at("09:00")
        rules = common.read_json(self.s.path("rules.json"))
        cfg = helpers.cfg()
        gg = rules["values"]["gap_guard"]
        self.assertEqual(sorted(gg), ["books_min", "final_ev", "gap_ev", "lines", "live_from", "market_weight", "max_per_game",
                                      "max_per_night", "max_per_player", "max_price", "model_weight", "pin_ev_min",
                                      "price_gate", "pull_ev", "safety_units"])
        self.assertEqual((gg["gap_ev"], gg["final_ev"], gg["books_min"], gg["price_gate"], gg["max_price"]), (0.03, 0.02, 4, -200, 120))
        self.assertEqual(rules["version"], cfg["version"])
        self.assertEqual(rules["ui"], {"stale_after_min": 75, "refresh_sec": 120, "picks_open": 8})
        self.assertNotIn("offsets", json.dumps(rules))                    # the page gets the rule's numbers, not the frozen offsets
        self.assertNotIn("paper", rules)
        for k in ("min_history", "absence_games", "absence_sitout", "stake", "min_sample"):
            self.assertIn(k, rules["values"], k)
        for k in ("min_p", "margin_confirmed", "model_weight", "market_weight", "edge_cap", "parlay_cap", "pause_legs",
                  "uncertainty", "news_gap", "too_good", "drift_pull", "devig", "price_gate", "max_price"):
            self.assertNotIn(k, rules["values"], k)                       # the old rules are gone, not kept as options
        self.assertEqual(rules["values"]["min_sample"], 30)

    def test_slate_shape(self):
        sl = open_day(self.s)
        self.assertEqual(sorted(sl), ["banners", "empty", "games", "generated_at", "parlays", "parlays_note", "picks",
                                      "slate_date", "status", "status_at", "valid_until"])
        self.assertEqual(sl["parlays"], [])
        self.assertEqual(sl["valid_until"], "2026-10-12T05:00:00-04:00")
        for k in ("prices_state", "prices_at", "next_price_read_at", "stats_built_at", "stats_through", "lineups_at",
                  "goalies_at", "stats_state", "last_run", "pool", "excluded_teams", "lines_checked"):
            self.assertIn(k, sl["status"], k)
        self.assertEqual(sorted(sl["status"]["pool"]), ["days_left", "game_days_left", "keys", "low", "pulls_left"])
        self.assertEqual(sl["status"]["stats_through"], "2026-10-08")
        p = sl["picks"][0]
        for k in ("id", "rank", "game_id", "player", "team", "opp", "home", "start", "market", "bet", "price",
                  "reason", "state", "gap_pct", "market_fair_pct", "n_books", "guard", "settled", "settled_label"):
            self.assertIn(k, p, k)
        self.assertRegex(p["player"], r"^[A-Z]\. \w+$")
        self.assertEqual(sorted(p["guard"]), ["model_pct", "ours_pct", "verdict"])
        g = sl["games"][0]
        self.assertEqual((g["away"], g["home"]), ("CAR", "PHI"))


class NeverLeaksAKey(unittest.TestCase):
    """Real odds client, fake network that does its worst: echoes the URL (with the key) into error bodies
    and exception text. No key may reach any file or the console."""

    def setUp(self):
        self.s = Sim(pool=12)
        os.environ.pop("PC_ODDS_FIXTURE_DIR")
        os.environ["ODDS_API_KEYS"] = ",".join(KEYS)
        self.real = common.http_get
        self.out, self.err = io.StringIO(), io.StringIO()
        self.std = (sys.stdout, sys.stderr)

    def tearDown(self):
        common.http_get = self.real
        sys.stdout, sys.stderr = self.std
        self.s.close()

    def go(self, hhmm, fake):
        common.http_get = fake
        self.s.clock(hhmm)
        sys.stdout, sys.stderr = self.out, self.err
        try:
            run.main([])
        finally:
            sys.stdout, sys.stderr = self.std

    def assert_clean(self):
        blob = self.out.getvalue() + self.err.getvalue()
        for name, data in self.s.tree().items():
            blob += "\n" + data.decode("utf-8", "replace") if not name.endswith(".gz") else ""
        for k in KEYS:
            self.assertNotIn(k, blob)
        self.assertNotIn("SECRET", blob)

    def test_errors_that_echo_the_url(self):
        def fake(url, **kw):
            return common.Http(500, {}, ("server error while fetching " + url).encode(), "HTTP 500 for " + url)
        self.go("13:02", fake)
        self.assert_clean()
        st = self.s.status()
        self.assertEqual(st["keys"], [{"n": 1, "left": None}, {"n": 2, "left": None}])
        self.assertTrue(any("did not answer" in n for n in st["odds_notes"]))

    def test_exception_with_the_key_in_its_message(self):
        def fake(url, **kw):
            raise RuntimeError("could not open " + url)
        self.go("13:02", fake)
        self.assert_clean()
        st = self.s.status()
        self.assertEqual((st["ok"], st["failed_step"]), (False, "odds"))
        self.assertIn("***", json.dumps(st))                             # the key was there, and was scrubbed

    def test_a_normal_paid_pull(self):
        payload = world.odds_payload("CAR", "PHI", [self.s_line()], UPD)
        events = helpers.load(os.path.join(self.s.w["odds"], "events.json"))

        def fake(url, **kw):
            key = url.split("apiKey=")[1].split("&")[0]
            if key == KEYS[0]:
                return common.Http(401, {}, json.dumps({"message": "quota reached for " + key,
                                                        "error_code": "OUT_OF_USAGE_CREDITS"}).encode(), "HTTP 401")
            head = {"x-requests-remaining": "41", "x-requests-last": "1" if "/odds" in url else "0"}
            body = payload if "/odds" in url else events
            return common.Http(200, head, json.dumps(body).encode())
        self.go("13:02", fake)
        self.assert_clean()
        st = self.s.status()
        self.assertEqual(st["keys"], [{"n": 1, "left": 0}, {"n": 2, "left": 41}])
        self.assertEqual(st["pool_total"], 41)
        self.assertEqual(st["budget_used_today"], 2)
        doc = common.read_json(self.s.path("odds", "2026-10-11.json"))
        self.assertEqual(len(doc["fetches"]), 2)

    def s_line(self):
        return ("player_shots_on_goal", world.name_of("CAR", 1), 2.5, -120, -110)

    def test_scrub_helpers(self):
        common.register_secret(KEYS[0])
        self.assertEqual(common.scrub("x %s y" % KEYS[0]), "x *** y")
        self.assertNotIn(KEYS[0], common.short_err(ValueError("bad " + KEYS[0])))
        p = self.s.path("state", "probe.json")
        common.write_json(p, {"url": "https://x/?apiKey=" + KEYS[0]})
        self.assertNotIn(KEYS[0], helpers.slurp(p, "r"))


if __name__ == "__main__":
    unittest.main()
