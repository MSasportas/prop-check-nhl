"""notify.py: Discord messages. Local fake HTTP server only; never a real Discord URL, never the real data/."""
import contextlib
import http.server
import io
import json
import os
import shutil
import tempfile
import threading
import unittest
from pathlib import Path

import helpers  # noqa: F401  (puts scripts/ on sys.path)
import common
import notify

SECRET = "https://discord.com/api/webhooks/123456789/SECRETTOKENabcdefghijklmnop"
DAY = "2026-10-12"


class Server:
    def __init__(self):
        self.posts, self.status, self.headers = [], 200, {}
        outer = self

        class H(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                n = int(self.headers.get("Content-Length", 0))
                outer.posts.append(json.loads(self.rfile.read(n)))
                self.send_response(outer.status)
                for k, v in outer.headers.items():
                    self.send_header(k, v)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, *a):
                pass
        self.srv = http.server.HTTPServer(("127.0.0.1", 0), H)
        self.url = "http://127.0.0.1:%d/hook" % self.srv.server_port
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()


def pick(n, rank=None, start="19:00", state="early", pulled=None):
    return {"id": "%s:g1:p%d:shots:2.5:over" % (DAY, n), "price": -120, "p_pct": 62, "breakeven_pct": 55, "state": state,
            "pulled": pulled, "graded": None, "rank": rank if rank is not None else n, "player": "P. Player%d" % n,
            "bet": "Over 2.5 shots on goal", "start": "%sT%s:00-04:00" % (DAY, start)}


def slate(picks=(), parlays=(), banners=(), prices_state="ok", date=DAY):
    return {"slate_date": date, "status": {"prices_state": prices_state}, "banners": list(banners),
            "picks": list(picks), "parlays": list(parlays)}


class T(unittest.TestCase):
    def setUp(self):
        self.srv = Server()
        self.dir = tempfile.mkdtemp(prefix="pc_notify_")
        self.saved = {k: os.environ.get(k) for k in ("PC_NOW", "PC_DATA_DIR", "DISCORD_WEBHOOK_URL", "PC_DISCORD_FIXTURE_URL")}
        os.environ.update(PC_DATA_DIR=self.dir, DISCORD_WEBHOOK_URL=SECRET, PC_DISCORD_FIXTURE_URL=self.srv.url)
        self.at("10:00")
        self.hello_done()

    def tearDown(self):
        self.srv.close()
        shutil.rmtree(self.dir, ignore_errors=True)
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def at(self, hhmm, day=DAY):
        os.environ["PC_NOW"] = "%sT%s:00-04:00" % (day, hhmm)

    def hello_done(self):
        notify.notify(slate())
        self.assertEqual(len(self.srv.posts), 1)
        self.assertIn("notifications are on", self.srv.posts[0]["content"])
        self.srv.posts.clear()

    def texts(self):
        return [p["content"] for p in self.srv.posts]

    def state(self):
        return common.read_json(notify.state_path())

    def test_batch_one_message_with_cap_and_link(self):
        ps = [pick(i) for i in range(1, 12)]
        self.assertEqual(notify.notify(slate(ps)), 1)
        t = self.texts()[0]
        self.assertEqual(t.count("P. Player"), 8)
        self.assertIn("**11 new bets", t)
        self.assertIn("+3 more on the page", t)
        self.assertIn(notify.PAGE, t)
        self.assertIn("We say 62% to hit · price needs 55%", t)
        self.assertIn("7:00 PM ET", t)
        self.assertIn("-120", t)
        self.assertIn("Bet only at these prices or better", t)
        self.assertLessEqual(len(t), 2000)
        self.assertEqual(len(self.state()["picks"]), 11)       # the overflow ones count as told

    def test_dedupe_price_move_and_state_change(self):
        a = pick(1)
        notify.notify(slate([a]))
        a2 = dict(a, price=-150, state="lineup")
        notify.notify(slate([a2]))
        self.assertEqual(len(self.srv.posts), 1)
        notify.notify(slate([a2, pick(2)]))
        self.assertEqual(len(self.srv.posts), 2)
        self.assertNotIn("Player1", self.texts()[1])
        self.assertIn("Lineup confirmed", notify.pick_line(a2))

    def test_readable_block_and_length_budget(self):
        rich = dict(side="over", line=2.5, market="shots", team="NYI", opp="TOR", home=False, state="lineup",
                    reason="62% to clear 2.5 shots; -120 needs 55%. Projects 3.1 shots in 19 min. TOR allow "
                           "13% more shots than average, and a lot more words here to make the reason run long.")
        ps = [dict(pick(i), **rich) for i in range(1, 12)]
        notify.notify(slate(ps))
        t = self.texts()[0]
        self.assertIn("**P. Player1 OVER 2.5 shots  -120**", t)
        self.assertIn("NYI @ TOR · 7:00 PM ET · ✅ Lineup confirmed", t)
        self.assertIn("Why: Projects 3.1 shots in 19 min", t)
        self.assertNotIn("Why: 62%", t)
        self.assertLessEqual(len(t), 1990)
        self.assertTrue(t.endswith(notify.PAGE))                 # the link is never cut off
        self.assertIn("more on the page", t)

    def test_parlay_in_same_message(self):
        a, b = pick(1), pick(2)
        pl = {"id": "%s:parlay:x" % DAY, "legs": [a["id"], b["id"]], "price": 165, "p_pct": 40, "breakeven_pct": 37,
              "state": "early", "pulled": None, "graded": None}
        notify.notify(slate([a, b], [pl]))
        self.assertEqual(len(self.srv.posts), 1)
        self.assertIn("about +165", self.texts()[0])
        notify.notify(slate([a, b], [pl]))
        self.assertEqual(len(self.srv.posts), 1)

    def test_started_pulled_graded_not_new(self):
        old = pick(1, start="09:00")
        pulled = pick(2, pulled={"at": "x", "reason": "r"})
        locked = pick(3, state="locked")
        norank = pick(4)
        norank["rank"] = None
        self.assertEqual(notify.notify(slate([old, pulled, locked, norank])), 0)

    def test_pull_only_if_notified_and_before_puck(self):
        a, b = pick(1), pick(2)
        notify.notify(slate([a]))
        self.srv.posts.clear()
        pa = dict(a, pulled={"at": "x", "reason": "Scratched from the lineup"})
        pb = dict(b, pulled={"at": "x", "reason": "Scratched from the lineup"})
        notify.notify(slate([pa, pb]))                          # b was never notified
        self.assertEqual(len(self.srv.posts), 1)
        t = self.texts()[0]
        self.assertIn("Don't bet these", t)
        self.assertIn("P. Player1 Over 2.5 shots on goal (Scratched from the lineup)", t)
        self.assertNotIn("Player2", t)
        notify.notify(slate([pa, pb]))                          # not again
        self.assertEqual(len(self.srv.posts), 1)

    def test_pull_after_puck_is_silent(self):
        a = pick(1, start="19:00")
        notify.notify(slate([a]))
        self.srv.posts.clear()
        self.at("19:05")
        notify.notify(slate([dict(a, pulled={"at": "x", "reason": "r"})]))
        self.assertEqual(self.srv.posts, [])

    def test_quiet_hours_hold_then_send_at_eight(self):
        a = pick(1, start="19:00")
        for hhmm in ("00:30", "03:00", "07:59"):
            self.at(hhmm)
            self.assertEqual(notify.notify(slate([a])), 0, hhmm)
        self.at("00:29", "2026-10-13")
        late = dict(a, start="2026-10-13T19:00:00-04:00")
        self.assertEqual(notify.notify(slate([late])), 1)          # before 12:30 AM is allowed
        self.srv.posts.clear()
        os.remove(notify.state_path())
        self.at("08:00", "2026-10-12")
        self.hello_done()
        self.assertEqual(notify.notify(slate([a])), 1)

    def test_held_item_gone_by_eight_is_not_sent(self):
        self.at("03:00")
        notify.notify(slate([pick(1)]))
        self.at("08:00")
        self.assertEqual(notify.notify(slate([pick(1, start="07:00")])), 0)

    def test_daily_cap_six(self):
        for i in range(1, 12):
            notify.notify(slate([pick(i)]))
        self.assertEqual(len(self.srv.posts), 5)                # hello used 1 of 6
        self.assertEqual(self.state()["sent"][DAY], 6)
        self.at("10:00", "2026-10-13")
        notify.notify(slate([pick(1)], date="2026-10-13"))
        self.assertEqual(len(self.srv.posts), 5)                # slate date is old -> silent
        self.at("11:00", "2026-10-13")
        p = pick(1)
        p["id"] = "2026-10-13:g1:p1:shots:2.5:over"
        p["start"] = "2026-10-13T19:00:00-04:00"
        notify.notify(slate([p], date="2026-10-13"))
        self.assertEqual(len(self.srv.posts), 6)                # new day, new count

    def test_action_needed_once_per_day_each(self):
        sl = slate(prices_state="keys_refused", banners=[{"level": "stop", "text": "ignored"}])
        notify.notify(sl)
        notify.notify(sl)
        self.assertEqual(len(self.srv.posts), 1)
        self.assertIn("odds keys were refused", self.texts()[0])
        low = slate(banners=[{"level": "warn", "text": "Odds pulls are running low: about 3 days left. Fewer price "
                                                       "checks until more keys are added."}])
        notify.notify(low)
        notify.notify(low)
        self.assertEqual(len(self.srv.posts), 2)
        self.assertIn("about 3 days left", self.texts()[1])
        self.at("11:00", "2026-10-13")
        low2 = dict(low, slate_date="2026-10-13")
        notify.notify(low2)
        self.assertEqual(len(self.srv.posts), 3)                # next day again

    def test_info_banner_and_empty_night_silent(self):
        sl = slate(banners=[{"level": "info", "text": "Prices checked at 1 PM (shots). Odds pulls later."}])
        self.assertEqual(notify.notify(sl), 0)
        self.assertEqual(notify.notify(slate()), 0)

    def test_hello_once(self):
        self.srv.posts.clear()
        notify.notify(slate())
        notify.notify(slate())
        self.assertEqual(self.srv.posts, [])
        self.assertTrue(self.state()["hello"])

    def test_unset_env_is_noop(self):
        os.remove(notify.state_path())
        for v in (None, "", "  "):
            if v is None:
                os.environ.pop("DISCORD_WEBHOOK_URL")
            else:
                os.environ["DISCORD_WEBHOOK_URL"] = v
            self.assertEqual(notify.notify(slate([pick(1)])), 0)
        self.assertFalse(os.path.exists(notify.state_path()))
        self.assertEqual(self.srv.posts, [])

    def test_test_mode_never_posts_real_without_fixture(self):
        os.environ.pop("PC_DISCORD_FIXTURE_URL")
        self.assertIsNone(notify.endpoint())

    def test_429_and_5xx_not_marked_then_retry(self):
        for code in (429, 503, 400):
            self.srv.status = code
            self.srv.headers = {"Retry-After": "1"} if code == 429 else {}
            self.assertEqual(notify.notify(slate([pick(1)])), 0, code)
            self.assertNotIn(pick(1)["id"], self.state()["picks"] if self.state() else {})
        self.srv.status, self.srv.headers = 200, {}
        self.srv.posts.clear()
        self.assertEqual(notify.notify(slate([pick(1)])), 1)
        self.assertIn(pick(1)["id"], self.state()["picks"])

    def test_429_stops_further_sends_this_run(self):
        self.srv.status = 429
        n = len(self.srv.posts)
        notify.notify(slate([pick(1)], prices_state="keys_refused"))
        self.assertEqual(len(self.srv.posts) - n, 1)            # first 429 ends the run's sending

    def test_one_retry_on_5xx_and_budget(self):
        self.srv.status = 500
        notify.notify(slate([pick(1)]))
        self.assertEqual(len(self.srv.posts), 2)                # one try + one retry

    def test_unreachable_server_never_raises(self):
        self.srv.close()
        os.environ["PC_DISCORD_FIXTURE_URL"] = "http://127.0.0.1:9/x"
        self.assertEqual(notify.notify(slate([pick(1)])), 0)
        self.srv = Server()

    def test_garbage_slate_never_raises(self):
        for bad in ({"slate_date": DAY, "picks": [{"id": "x"}]}, {"slate_date": DAY, "picks": "no"}, []):
            self.assertEqual(notify.notify(bad), 0)

    def test_url_never_in_files_or_stdout(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            notify.notify(slate([pick(1)], prices_state="keys_refused"))
            print(common.scrub("token " + SECRET + " end"))
        self.assertNotIn("SECRETTOKEN", buf.getvalue())
        for root, _, files in os.walk(self.dir):
            for f in files:
                self.assertNotIn(b"SECRETTOKEN", Path(os.path.join(root, f)).read_bytes())
                self.assertNotIn(b"discord.com", Path(os.path.join(root, f)).read_bytes())
        for p in self.srv.posts:
            self.assertNotIn("SECRETTOKEN", p["content"])
            self.assertEqual(p["allowed_mentions"], {"parse": []})

    def test_state_has_only_ids_and_times(self):
        notify.notify(slate([pick(1)]))
        st = self.state()
        self.assertEqual(set(st), {"picks", "parlays", "pulled", "sent", "action", "hello", "sent_paper", "pulled_paper", "paper_sent"})
        self.assertNotIn("http", json.dumps(st))


class InRun(unittest.TestCase):
    def test_run_unaffected_when_notify_blows_up(self):
        import run
        s = helpers.Sim(pool=12)
        try:
            os.environ["DISCORD_WEBHOOK_URL"] = SECRET
            real = notify.notify
            notify.notify = lambda *a, **k: 1 / 0
            try:
                s.at("13:02")
            finally:
                notify.notify = real
            self.assertTrue(s.last is not None)
            self.assertFalse(os.path.exists(os.path.join(s.w["data"], "state", "notified.json")))
        finally:
            s.close()

    def test_run_sends_nothing_without_fixture_in_test_mode(self):
        s = helpers.Sim(pool=12)
        try:
            os.environ["DISCORD_WEBHOOK_URL"] = SECRET
            s.at("13:02")
            self.assertFalse(os.path.exists(os.path.join(s.w["data"], "state", "notified.json")))
        finally:
            s.close()


if __name__ == "__main__":
    unittest.main()
