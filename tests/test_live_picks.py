"""Gap + Guard as THE live engine: real picks on the page, in the Record (events.jsonl) and in Discord, from the first slate
it covers (2026-10-20). One file for the whole path: flag -> shown (price frozen) -> pulled / locked -> graded, the caps, the
empty start, nothing before the first live slate, the Record staying append-only, the page and the credits plan.
Offline: the made-up league (Sim) and the real 2026-10-19 reads in tests/fixtures/paper_oct19; never the live data/."""
import hashlib
import json
import os
import shutil
import tempfile
import unittest

import helpers  # noqa: F401  (puts scripts/ on sys.path)
import common
import engine
import guard_record
import notify
import odds
import paper
import record
import run
import world
from helpers import Sim, BOOKS

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
G1, G2 = 2026020901, 2026020902


def day(s):
    """09:00 stats, the 1 PM baseline read. The clock is left at 17:00."""
    s.at("09:00")
    s.read("13:02")
    s.clock("17:00")


def kinds(s):
    return [e["t"] for e in s.events()]


# ---------------------------------------------------------------- shown at the first B read, price frozen
class Shown(unittest.TestCase):
    def setUp(self):
        self.s = Sim(pool=12)

    def tearDown(self):
        self.s.close()

    def test_the_1pm_read_only_sets_a_baseline_and_the_page_says_why_it_is_empty(self):
        s = self.s
        s.at("09:00")
        sl = s.read("13:02", cp=[s.gg_lines("CAR", 1)])             # a perfect candidate, but the 1 PM read can never flag
        self.assertEqual((sl["picks"], s.events()), ([], []))
        self.assertEqual(sl["empty"]["text"], "No picks yet today")
        self.assertTrue(sl["empty"]["sub"])                          # the next read time (or why not)

    def test_first_b_read_shows_the_pick_with_the_price_frozen_and_the_right_record_events(self):
        s = self.s
        day(s)
        gg = s.gg_lines("CAR", 1)
        sl = s.read("17:31", cp=[gg])
        ev = s.events()
        self.assertEqual([e["t"] for e in ev], ["shown"])
        e = ev[0]
        self.assertEqual((e["kind"], e["slate"], e["at"]), ("single", world.SLATE, "2026-10-11T17:31:00-04:00"))
        pk = e["pick"]
        self.assertEqual(e["id"], pk["id"])
        self.assertEqual((pk["player_id"], pk["market"], pk["line"], pk["side"], pk["bet"]),
                         (world.pid_of("CAR", 1), "shots", 1.5, "over", "Over 1.5 shots on goal"))
        self.assertEqual(pk["read_pull"], "B")
        self.assertEqual(pk["price_at"], "2026-10-11T17:31:00-04:00")
        self.assertGreaterEqual(pk["gap_ev"], 0.03 - 1e-9)
        self.assertGreaterEqual(pk["final_ev"], 0.02 - 1e-9)
        self.assertGreaterEqual(pk["n_books"], 4)
        self.assertEqual(pk["guard"], "agrees")
        self.assertTrue(pk["gg_id"])
        self.assertEqual(pk["state"], "early")
        # the page
        p = s.pick("CAR", 1, sl)
        for k in ("player", "bet", "price", "gap_pct", "market_fair_pct", "n_books", "guard", "settled", "settled_label",
                  "start", "state", "reason", "rank"):
            self.assertIsNotNone(p[k], k)
        self.assertEqual((p["price"], p["first_price"], p["worst_price"]), (pk["price"], pk["price"], pk["price"]))
        self.assertEqual((p["settled"], p["settled_label"], p["state"]), ("early", "Early", "early"))
        self.assertEqual(p["guard"]["verdict"], "agrees")
        self.assertEqual(p["start"], "2026-10-11T19:00:00-04:00")
        self.assertEqual(sl["parlays"], [])
        self.assertIsNone(sl["empty"])

    def test_later_reads_never_change_the_shown_price_better_or_worse(self):
        s = self.s
        day(s)
        gg = s.gg_lines("CAR", 1)
        p0 = s.read("17:31", cp=[gg])["picks"][0]
        worse = s.gg_lines("CAR", 1, ev=0.02)                        # still >= 1.5% above fair: stays, price not repriced
        sl = s.read("18:16", cp=[worse])
        p1 = s.pick("CAR", 1, sl)
        self.assertEqual((p1["price"], p1["worst_price"]), (p0["price"], p0["price"]))
        self.assertIsNone(p1["pulled"])
        better = s.gg_lines("CAR", 1, ev=0.15)
        sl = s.read("18:31", cp=[better])
        p2 = s.pick("CAR", 1, sl)
        self.assertEqual((p2["price"], p2["first_price"], p2["worst_price"]), (p0["price"],) * 3)
        self.assertEqual(kinds(s), ["shown"])                         # no price event, ever

    def test_lineup_confirmation_is_a_state_event_not_a_new_pick(self):
        s = self.s
        day(s)
        gg = s.gg_lines("CAR", 1)
        s.read("17:31", cp=[gg])
        s.set_lineup("CAR", "2026-10-11T20:00:00Z")
        sl = s.read("18:16", cp=[gg])
        p = s.pick("CAR", 1, sl)
        self.assertEqual((p["state"], p["settled"], p["settled_label"]), ("lineup", "lineup", "Lineup confirmed"))
        self.assertEqual(kinds(s), ["shown", "state"])
        self.assertEqual([h["text"] for h in p["history"]], ["Early: lineup not confirmed", "Lineup confirmed"])

    def test_a_candidate_must_be_in_the_other_books_not_only_at_hard_rock(self):
        s = self.s
        day(s)
        hr, oth = s.gg_lines("CAR", 1)
        sl = s.read("17:31", cp=[(hr, {})])                          # Hard Rock alone: no pick
        self.assertEqual((sl["picks"], s.events()), ([], []))


# ---------------------------------------------------------------- later reads only pull
class Pulled(unittest.TestCase):
    def setUp(self):
        self.s = Sim(pool=12)
        day(self.s)
        self.gg = self.s.gg_lines("CAR", 1)
        self.shown = self.s.read("17:31", cp=[self.gg])["picks"][0]

    def tearDown(self):
        self.s.close()

    def check_pulled(self, sl, code, text):
        p = self.s.pick("CAR", 1, sl)
        self.assertEqual(p["pulled"]["reason"], text)
        self.assertEqual(p["price"], self.shown["price"])             # the price it was shown at stays on the page / Record
        ev = self.s.events()
        self.assertEqual([e["t"] for e in ev], ["shown", "pulled"])
        self.assertEqual((ev[1]["code"], ev[1]["reason"]), (code, text))
        self.assertEqual(ev[1]["id"], self.shown["id"])
        return p

    def test_price_moved_and_the_gap_is_gone(self):
        sl = self.s.read("18:16", cp=[self.s.gg_lines("CAR", 1, ev=-0.04)])
        self.check_pulled(sl, "gap_gone", "Hard Rock moved the price and the gap is gone")

    def test_price_moved_but_the_gap_is_still_1_5_percent_keeps_it(self):
        sl = self.s.read("18:16", cp=[self.s.gg_lines("CAR", 1, ev=0.016)])
        self.assertIsNone(self.s.pick("CAR", 1, sl)["pulled"])
        self.assertEqual(kinds(self.s), ["shown"])

    def test_fewer_than_four_books(self):
        sl = self.s.read("18:16", cp=[self.s.gg_lines("CAR", 1, books=BOOKS[:3])])
        self.check_pulled(sl, "books_low", "Other books stopped quoting this line")

    def test_pinnacle_flips_sign(self):
        hr, oth = self.s.gg_lines("CAR", 1)
        k, name, line, o, u = oth["pinnacle"]
        oth["pinnacle"] = (k, name, line, u, o)                       # Pinnacle now has the other side as the favourite
        sl = self.s.read("18:16", cp=[(hr, oth)])
        self.check_pulled(sl, "pinnacle_flip", "Pinnacle no longer agrees with the price")

    def test_pinnacle_gone(self):
        hr, oth = self.s.gg_lines("CAR", 1)
        sl = self.s.read("18:16", cp=[(hr, {b: l for b, l in oth.items() if b != "pinnacle"})])
        p = self.s.pick("CAR", 1, sl)
        self.assertIsNotNone(p["pulled"])                             # fewer than 4 left or no Pinnacle: one of the two pulls

    def test_player_listed_out_by_daily_faceoff(self):
        self.s.set_lineup("CAR", "2026-10-11T20:00:00Z", out=[1])
        sl = self.s.read("18:16", cp=[self.gg])
        self.check_pulled(sl, "out", "Scratched from the lineup")

    def test_line_taken_down(self):
        sl = self.s.read("18:16", cp=[self.s.gg_lines("CAR", 2, ev=0.0)])   # another (non-qualifying) line only: his is gone
        self.check_pulled(sl, "line_gone", "Hard Rock took this line down")

    def test_a_pulled_pick_stays_in_the_record_and_is_not_pulled_twice_or_shown_again(self):
        s = self.s
        s.read("18:16", cp=[s.gg_lines("CAR", 1, ev=-0.04)])
        s.read("18:31", cp=[s.gg_lines("CAR", 1, ev=-0.04)])
        s.read("18:40", cp=[self.gg])                                  # the gap is back: it is NOT re-shown
        self.assertEqual(kinds(s), ["shown", "pulled"])
        sl = s.at("19:05")
        self.assertEqual(kinds(s), ["shown", "pulled"])               # a pulled pick is not locked either
        p = s.pick("CAR", 1, sl)
        self.assertEqual(p["pulled"]["reason"], "Hard Rock moved the price and the gap is gone")

    def test_a_pulled_pick_is_graded_at_its_shown_price_and_counted_under_pulled(self):
        s = self.s
        s.read("18:16", cp=[s.gg_lines("CAR", 1, ev=-0.04)])
        s.at("19:05")
        s.set_box(G1, "CAR", "PHI", {world.pid_of("CAR", 1): (4, 0, 0)})
        s.set_states({G1: "OFF", G2: "OFF"})
        s.at("23:10")
        g = [e for e in s.events() if e["t"] == "graded"]
        self.assertEqual([(e["result"], e["price"]) for e in g], [("W", self.shown["price"])])
        rec = common.read_json(s.path("record.json"))
        rows = {r["key"]: r for r in rec["summary"]["rows"]}
        self.assertEqual((rows["pulled"]["w"], rows["pulled"]["l"]), (1, 0))
        self.assertEqual(rec["summary"]["headline"]["n"], 0)          # pulled picks are not in the headline


# ---------------------------------------------------------------- caps, lock, grade
class CapsLockGrade(unittest.TestCase):
    def setUp(self):
        self.s = Sim(pool=12)

    def tearDown(self):
        self.s.close()

    def test_two_per_game_three_per_night_best_first(self):
        s = self.s
        day(s)
        cp = [s.gg_lines("CAR", 1), s.gg_lines("CAR", 2, ev=0.08), s.gg_lines("PHI", 1, ev=0.12), s.gg_lines("PHI", 2, ev=0.06)]
        sl = s.read("17:31", cp=cp)
        self.assertEqual(len(sl["picks"]), 2)                         # 2 per game
        sl = s.read("18:31", cp=cp, vn=[s.gg_lines("VAN", 1), s.gg_lines("NYR", 1, ev=0.09)])
        self.assertEqual(len([p for p in sl["picks"] if not p["pulled"]]), 3)      # 3 per night
        self.assertEqual(kinds(s).count("shown"), 3)
        self.assertEqual(sorted(p["rank"] for p in sl["picks"]), [1, 2, 3])

    def test_one_side_per_player(self):
        s = self.s
        day(s)
        a = s.gg_lines("CAR", 1)
        b = s.gg_lines("CAR", 1, line=2.5)
        sl = s.read("17:31", cp=[a, b])
        mine = [p for p in sl["picks"] if p["player_id"] == world.pid_of("CAR", 1)]
        self.assertEqual(len(mine), 1)

    def test_locked_at_puck_drop_and_no_pull_after(self):
        s = self.s
        day(s)
        gg = s.gg_lines("CAR", 1)
        s.read("17:31", cp=[gg])
        sl = s.read("19:00", cp=[s.gg_lines("CAR", 1, ev=-0.05)])      # puck is down: a bad read changes nothing
        p = s.pick("CAR", 1, sl)
        self.assertEqual(p["state"], "locked_unconfirmed")
        self.assertIsNone(p["pulled"])
        self.assertEqual(kinds(s), ["shown", "locked"])
        sl = s.read("19:05", cp=[gg])
        self.assertEqual(kinds(s), ["shown", "locked"])

    def test_locked_with_a_confirmed_lineup_says_so(self):
        s = self.s
        day(s)
        gg = s.gg_lines("CAR", 1)
        s.read("17:31", cp=[gg])
        s.set_lineup("CAR", "2026-10-11T20:00:00Z")
        s.read("18:16", cp=[gg])
        sl = s.at("19:01")
        self.assertEqual(s.pick("CAR", 1, sl)["state"], "locked")

    def test_grades_win_loss_and_void_at_the_shown_price_flat_one_unit(self):
        s = self.s
        day(s)
        cp = [s.gg_lines("CAR", 1), s.gg_lines("PHI", 1, ev=0.08)]
        sl = s.read("17:31", cp=cp, vn=[])
        sl = s.read("18:31", cp=cp, vn=[s.gg_lines("VAN", 1, ev=0.04)])
        price = {p["team"]: p["price"] for p in sl["picks"]}
        ids = {p["team"]: p["id"] for p in sl["picks"]}
        car, phi, van = (world.pid_of(t, 1) for t in ("CAR", "PHI", "VAN"))
        s.at("19:05")
        s.set_box(G1, "CAR", "PHI", {car: (3, 0, 0), phi: (0, 0, 0)})
        s.set_box(G2, "VAN", "NYR", {}, missing=[van])
        s.set_states({G1: "OFF", G2: "OFF"})
        s.at("23:10")
        g = {e["id"]: e for e in s.events() if e["t"] == "graded"}
        self.assertEqual({t: g[ids[t]]["result"] for t in ids}, {"CAR": "W", "PHI": "L", "VAN": "VOID"})
        self.assertEqual({t: g[ids[t]]["price"] for t in ids}, price)
        self.assertEqual(g[ids["CAR"]]["units"], round(odds.decimal(price["CAR"]) - 1, 4))
        self.assertEqual((g[ids["PHI"]]["units"], g[ids["VAN"]]["units"]), (-1.0, 0.0))
        s.at("23:20")
        self.assertEqual(kinds(s).count("graded"), 3)                  # never twice


# ---------------------------------------------------------------- the first live slate, the empty start, the Record guard
class FirstLiveSlate(unittest.TestCase):
    def test_the_config_goes_live_on_2026_10_20_and_nothing_before(self):
        cfg = common.load_config()
        self.assertEqual(cfg["ops"]["gap_guard"]["live_from"], "2026-10-20")
        for d in ("2026-10-11", "2026-10-18", "2026-10-19"):
            self.assertFalse(common.gap_guard_active(cfg, d), d)
        self.assertTrue(common.gap_guard_active(cfg, "2026-10-20"))

    def test_a_perfect_candidate_on_an_earlier_slate_shows_and_appends_nothing(self):
        """The Sim's 2026-10-11 slate under the REAL config (live_from 2026-10-20): reads are processed, nothing is shown."""
        s = Sim(pool=12)
        try:
            os.environ["PC_CONFIG"] = common.CONFIG_PATH
            day(s)
            cp = [s.gg_lines("CAR", 1)]
            sl = s.read("17:31", cp=cp)
            sl = s.read("18:16", cp=cp)
            self.assertEqual(s.events(), [])
            self.assertEqual(s.log_bytes(), b"")
            self.assertEqual(sl["picks"], [])
            self.assertEqual(sl["empty"]["code"], "not_live")
            self.assertEqual(paper.read_events(), [])                    # not even a research-log flag
        finally:
            s.close()

    def test_the_engine_itself_refuses_when_asked_about_an_earlier_slate(self):
        cfg = common.load_config()
        inp = engine.Inputs(cfg, common.parse_iso("2026-10-19T17:35:00-04:00"), "2026-10-19", "20262027", [], None, {}, {}, {}, {}, [])
        gg = [{"t": "flag", "id": "2026-10-19:1:8473986:1.5:over", "slate": "2026-10-19", "game_id": 1, "pid": 8473986,
               "read_at": "2026-10-19T17:30:00-04:00"}]
        new, _ = engine.evaluate(inp, gg)
        self.assertEqual(new, [])

    def test_the_committed_record_starts_empty_with_the_reset_on_file(self):
        self.assertEqual(os.path.getsize(os.path.join(ROOT, "data", "record", "events.jsonl")), 0)
        resets = common.read_json(os.path.join(ROOT, "data", "record", "resets.json"))
        self.assertEqual([r["at"] for r in resets], ["2026-10-19"])
        arch = os.path.join(ROOT, resets[0]["archive"])
        with open(arch, "rb") as f:
            self.assertEqual(hashlib.sha256(f.read()).hexdigest(), resets[0]["sha256"])      # the archived Record is intact
        rec = common.read_json(os.path.join(ROOT, "data", "record.json"))
        self.assertEqual(rec["nights"], [])


class RecordGuard(unittest.TestCase):
    def test_live_picks_only_ever_append_and_the_guard_passes(self):
        s = Sim(pool=12)
        try:
            day(s)
            cp = [s.gg_lines("CAR", 1), s.gg_lines("PHI", 2)]
            s.read("17:31", cp=cp)
            first = s.log_bytes()
            s.read("18:16", cp=[s.gg_lines("CAR", 1, ev=-0.04), s.gg_lines("PHI", 2)])
            s.at("19:05")
            second = s.log_bytes()
            self.assertTrue(second.startswith(first))                  # append-only: earlier lines are never touched
            self.assertGreater(len(second), len(first))
            # the guard the timer runs: appended lines pass, an edited or dropped committed line is caught
            self.assertIsNone(guard_record.check(first, second))
            tampered = second.replace(first[:40], b"X" * 40, 1)
            self.assertIn("changed", guard_record.check(first, tampered))
            self.assertIn("lost lines", guard_record.check(second, first))
        finally:
            s.close()

    def test_hash_of_the_log_prefix_is_unchanged_by_later_runs(self):
        s = Sim(pool=12)
        try:
            day(s)
            s.read("17:31", cp=[s.gg_lines("CAR", 1)])
            h = hashlib.sha256(s.log_bytes()).hexdigest()
            n = len(s.log_bytes())
            for hh in ("17:41", "18:16", "18:40", "19:05"):
                s.read(hh, cp=[s.gg_lines("CAR", 1)])
                self.assertEqual(hashlib.sha256(s.log_bytes()[:n]).hexdigest(), h, hh)
        finally:
            s.close()


# ---------------------------------------------------------------- the real 2026-10-19 reads, through the engine
class Oct19Engine(unittest.TestCase):
    """The real 19 Oct Hard Rock + other-book reads (tests/fixtures/paper_oct19), replayed as if Gap + Guard had been live that
    day: the engine shows Killorn Over 1.5 (+100) at the 90-minute read and Michkov Over 1.5 (-120) is vetoed. The Record gets
    exactly one `shown` event. The real run starts on 2026-10-20: this never touches data/."""
    DAY = "2026-10-19"

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="pc_oct19e_")
        self.saved = {k: os.environ.get(k) for k in ("PC_NOW", "PC_DATA_DIR", "PC_CONFIG")}
        os.environ.update(PC_DATA_DIR=self.dir)
        os.environ.pop("PC_CONFIG", None)
        os.makedirs(os.path.join(self.dir, "odds"))
        os.makedirs(os.path.join(self.dir, "record"))
        open(os.path.join(self.dir, "record", "events.jsonl"), "wb").close()
        shutil.copy(os.path.join(HERE, "fixtures", "paper_oct19", "odds_2026-10-19.json"),
                    os.path.join(self.dir, "odds", self.DAY + ".json"))
        self.cfg = json.loads(json.dumps(common.load_config()))
        self.cfg["ops"]["gap_guard"]["live_from"] = self.DAY
        self.games = [{"id": 2026020137, "away": "ANA", "home": "NYR", "start": "2026-10-19T19:00:00-04:00", "date": self.DAY},
                      {"id": 2026020138, "away": "COL", "home": "PHI", "start": "2026-10-19T19:00:00-04:00", "date": self.DAY}]

        class Inp(engine.Inputs):
            raw = {(8473986, 1.5): 0.5205948068315722, (8484387, 1.5): 0.4973965194814922}

            def model(self, pid, team, opp, home, market, line):
                p = self.raw.get((pid, line))
                return None if p is None else {"p_over": p, "mu": 2.0}

            def player(self, pid, team):
                return {"n": 60, "n_season": 3, "thin": False, "sitting": False, "missed_last": False}

            def display_name(self, pid, feed_name):
                return feed_name

        self.Inp = Inp

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def run_at(self, hhmm):
        os.environ["PC_NOW"] = "%sT%s:00-04:00" % (self.DAY, hhmm)
        now = common.now()
        inp = self.Inp(self.cfg, now, self.DAY, "20262027", self.games, None, {}, {}, {}, {}, record.read_events())
        paper.step(now, self.DAY, self.cfg, inp, {"games": {}}, self.games)
        new, _ = engine.evaluate(inp, paper.read_events())
        record.append(new)
        return new

    def test_killorn_is_shown_and_michkov_is_vetoed(self):
        self.assertEqual(self.run_at("13:05"), [])                      # the 1 PM read is a baseline only
        new = self.run_at("17:35")
        self.assertEqual([e["t"] for e in new], ["shown"])
        pk = new[0]["pick"]
        self.assertEqual((pk["player"], pk["bet"], pk["price"], pk["read_pull"]), ("Alex Killorn", "Over 1.5 shots on goal", 100, "B"))
        self.assertEqual(pk["price_at"], "2026-10-19T17:30:01-04:00")
        self.assertEqual(pk["n_books"], 6)
        self.assertAlmostEqual(pk["gap_ev"], 0.0558, places=1)
        self.assertIn("gg_id", pk)
        vetoes = [e for e in paper.read_events() if e["t"] == "veto"]
        self.assertEqual(len(vetoes), 1)
        self.assertIn("Michkov", vetoes[0]["player"])
        self.assertEqual(vetoes[0]["price"], -120)
        self.assertEqual(run_michkov_shown(record.read_events()), [])
        # a rerun adds nothing: the pick is shown once
        self.assertEqual(self.run_at("17:45"), [])
        self.assertEqual([e["t"] for e in record.read_events()], ["shown"])


def run_michkov_shown(events):
    return [e for e in events if e["t"] == "shown" and "Michkov" in e["pick"]["player"]]


# ---------------------------------------------------------------- Discord
class Discord(unittest.TestCase):
    def test_a_live_pick_pings_once_and_the_pull_pings_once_through_the_real_run(self):
        import test_notify
        srv = test_notify.Server()
        s = Sim(pool=12)
        try:
            os.environ.update(DISCORD_WEBHOOK_URL=test_notify.SECRET, PC_DISCORD_FIXTURE_URL=srv.url)   # after Sim() cleared them
            day(s)
            sl = s.read("17:31", cp=[s.gg_lines("CAR", 1)])             # run.main posts at the end of the run
            s.read("17:41", cp=[s.gg_lines("CAR", 1)])
            texts = [p["content"] for p in srv.posts]
            new = [t for t in texts if "NEW PICK" in t]
            self.assertEqual(len(new), 1)
            p = s.pick("CAR", 1, sl)
            self.assertIn("**%s OVER 1.5 shots  %s**" % (p["player"], common.fmt_price(p["price"])), new[0])
            self.assertIn("Gap %+.1f%% vs market, we say %d%%, price needs %d%%" % (p["gap_pct"], p["p_pct"], p["breakeven_pct"]), new[0])
            self.assertIn("Bet only at this price or better", new[0])
            self.assertIn("⏳ Early", new[0])
            self.assertNotIn("PAPER", " ".join(texts).upper().replace("PAGE", ""))
            s.read("18:16", cp=[s.gg_lines("CAR", 1, ev=-0.04)])
            s.read("18:21", cp=[s.gg_lines("CAR", 1, ev=-0.04)])
            pulled = [p["content"] for p in srv.posts if "PULLED" in p["content"]]
            self.assertEqual(len(pulled), 1)
            self.assertIn("Hard Rock moved the price and the gap is gone", pulled[0])
        finally:
            srv.close()
            s.close()

    def test_the_six_a_day_cap_and_quiet_hours_are_unchanged(self):
        self.assertEqual(notify.MAX_PER_DAY, 6)
        self.assertEqual((notify.QUIET_FROM, notify.QUIET_TO), ((0, 30), (8, 0)))


# ---------------------------------------------------------------- credits plan
class Credits(unittest.TestCase):
    def test_about_three_credits_a_game_shots_only_and_c_on_every_game(self):
        s = Sim(pool=500, rules="current")
        try:
            def edit(c):
                c["ops"]["gap_guard"]["live_from"] = "2026-10-01"
            path = os.environ["PC_CONFIG"]
            with open(path, encoding="utf-8") as f:
                c = json.load(f)
            edit(c)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(c, f)
            s.at("09:00")
            for hhmm in ("13:02", "17:31", "18:16", "18:31", "19:16", "20:05"):
                s.read(hhmm)
            doc = common.read_json(s.path("odds", world.SLATE + ".json"))
            for gid in (G1, G2):
                fs = [(f["pull"], f["requested"], f["cost"]) for f in doc["fetches"] if f["game_id"] == gid]
                self.assertEqual(fs, [("A", ["shots"], 1), ("B", ["shots"], 1), ("C", ["shots"], 1)], gid)
            self.assertEqual(sum(f["cost"] for f in doc["fetches"]), 6)
        finally:
            s.close()


if __name__ == "__main__":
    unittest.main()
