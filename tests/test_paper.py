"""The Gap + Guard engine (paper.py, TEAM.md section 4): gap/guard math, flags, pulls, caps, CLV, grading, the research-log guard,
the Record staying untouched and the odds plan (B / C). Offline: made-up reads in a temp folder, never the live data/."""
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

import helpers  # noqa: F401  (puts scripts/ on sys.path)
import common
import guard_paper
import guard_record
import odds
import paper
import run
import world
from helpers import Sim

SLATE = "2026-10-21"
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BOOKS = ["draftkings", "fanduel", "betmgm", "espnbet", "pinnacle"]


def am(p):
    """A (float) American price whose break-even is p."""
    return -100.0 * p / (1.0 - p) if p >= 0.5 else 100.0 * (1.0 - p) / p


def pair_for(fair_over, hold=0.05):
    """(over, under) prices of a book whose proportionally de-vigged fair over is exactly fair_over."""
    return am(fair_over * (1 + hold)), am((1 - fair_over) * (1 + hold))


def entry_for(fairs, hold=0.05):
    """shadow.other_lines()-style entry from {book: fair over}."""
    return {"pairs": {b: pair_for(f, hold) for b, f in fairs.items()}, "best": {}, "stale": 0}


def thresholds():
    return json.loads(json.dumps(common.load_config()["ops"]["gap_guard"]["thresholds"]))


T = thresholds()
OFF15, OFF25 = T["offsets"]["1.5"], T["offsets"]["2.5"]


# ---------------------------------------------------------------- the maths
class Maths(unittest.TestCase):
    def a(self, side, line, price, fairs, raw, **kw):
        return paper.assess(side, line, price, entry_for(fairs), lambda: raw, kw.get("T", T))

    def test_config_is_frozen_and_inclusive(self):
        self.assertEqual((T["gap_ev"], T["books_min"], T["final_ev"], T["pull_ev"], T["pin_ev_min"]),
                         (0.03, 4, 0.02, 0.015, 0.0))
        self.assertEqual((T["market_weight"], T["model_weight"]), (0.8, 0.2))
        self.assertEqual((T["price_gate"], T["max_price"], T["lines"]), (-200, 120, [1.5, 2.5]))
        self.assertEqual((T["max_per_player"], T["max_per_game"], T["max_per_night"]), (1, 2, 3))
        self.assertEqual(T["flag_pulls"], ["B", "C"])
        self.assertAlmostEqual(OFF15, 0.0179)
        self.assertAlmostEqual(OFF25, 0.0158)

    def test_worked_example_killorn_is_a_bet(self):
        """Killorn O1.5 Hard Rock +100, market 52.9%, model 52.1%: final 52.7%, EV +5.5% -> BET (offset only helps)."""
        ok, final, fe = paper.guard(0.529, 0.521, 100, T)
        self.assertAlmostEqual(final, 0.5274, places=4)
        self.assertTrue(ok)
        self.assertAlmostEqual(fe, 0.0548, places=3)
        a = self.a("over", 1.5, 100, {b: 0.529 for b in BOOKS}, 0.521)
        self.assertTrue(a["step1"] and a["guard"])
        self.assertAlmostEqual(a["market_fair"], 0.529)
        self.assertAlmostEqual(a["model_cal_over"], 0.521 + OFF15)

    def test_worked_example_michkov_is_vetoed_even_with_the_offset(self):
        """Michkov O1.5 -120, market 56.6%, model 49.7%: final 55.2%, needs 55.6% -> VETO; the offset does not rescue it."""
        ok, final, fe = paper.guard(0.566, 0.497, -120, T)
        self.assertAlmostEqual(final, 0.5522, places=4)
        self.assertFalse(ok)
        need = (1 + T["final_ev"]) / odds.decimal(-120)
        self.assertAlmostEqual(need, 0.5564, places=4)
        a = self.a("over", 1.5, -120, {b: 0.566 for b in BOOKS}, 0.497)
        self.assertTrue(a["step1"])                                  # the gap is real (+3.8%) ...
        self.assertAlmostEqual(a["gap_ev"], 0.0377, places=3)
        self.assertIs(a["guard"], False)                             # ... and the model vetoes it, offset included
        self.assertAlmostEqual(a["final"], 0.8 * 0.566 + 0.2 * (0.497 + OFF15), places=6)
        self.assertLess(a["final"], need)

    def test_ev_boundary_is_inclusive_at_three_percent(self):
        for fair, passes in ((0.51495, False), (0.5149, False), (0.515, True), (0.5151, True)):
            with self.subTest(fair=fair):
                a = self.a("over", 1.5, 100, {b: fair for b in BOOKS}, 0.5)
                self.assertEqual("gap" not in a["fails"], passes)
                self.assertEqual(a["step1"], passes)
        a = self.a("over", 1.5, 100, {b: 0.51495 for b in BOOKS}, 0.5)
        self.assertEqual(round(100 * a["gap_ev"], 1), 3.0)          # displays as 3.0 but is 2.99: fails, no rounding
        self.assertFalse(a["step1"])

    def test_guard_boundary_is_inclusive_at_two_percent(self):
        self.assertTrue(paper.guard(0.51, 0.51, 100, T)[0])          # +2.0000%
        self.assertFalse(paper.guard(0.5099, 0.5099, 100, T)[0])

    def test_three_books_fail_four_pass(self):
        three = ["draftkings", "fanduel", "pinnacle"]
        self.assertIn("books", self.a("over", 1.5, 100, {b: 0.54 for b in three}, 0.5)["fails"])
        four = three + ["betmgm"]
        a = self.a("over", 1.5, 100, {b: 0.54 for b in four}, 0.5)
        self.assertEqual(a["n_books"], 4)
        self.assertTrue(a["step1"])

    def test_pinnacle_missing_or_disagreeing_fails(self):
        no_pin = {b: 0.54 for b in BOOKS if b != "pinnacle"}
        no_pin["bovada"] = 0.54
        self.assertEqual(len(no_pin), 5)
        self.assertEqual(self.a("over", 1.5, 100, no_pin, 0.5)["fails"], ["pinnacle"])
        # sign flip: the other books love it (+6%) but Pinnacle's own fair says the price loses (-2%)
        fairs = {b: 0.53 for b in BOOKS}
        fairs["pinnacle"] = 0.49
        a = self.a("over", 1.5, 100, fairs, 0.5)
        self.assertAlmostEqual(a["pin_ev"], -0.02)
        self.assertEqual(a["fails"], ["pinnacle"])
        self.assertTrue(self.a("over", 1.5, 100, dict(fairs, pinnacle=0.50), 0.5)["step1"])      # exactly 0.0% passes

    def test_market_fair_is_the_median_even_count_is_the_mean_of_the_middle_two(self):
        a = self.a("over", 1.5, 100, {"a": 0.50, "b": 0.52, "c": 0.58, "pinnacle": 0.54}, 0.5)
        self.assertAlmostEqual(a["market_fair"], 0.53)               # (0.52 + 0.54) / 2
        a = self.a("over", 1.5, 100, {"a": 0.50, "b": 0.52, "c": 0.58, "d": 0.60, "pinnacle": 0.54}, 0.5)
        self.assertAlmostEqual(a["market_fair"], 0.54)               # the middle one
        u = self.a("under", 1.5, 100, {"a": 0.50, "b": 0.52, "c": 0.58, "pinnacle": 0.54}, 0.5)
        self.assertAlmostEqual(u["market_fair"], 0.47)               # the under's own median (1 - 0.53)

    def test_price_gate_and_lines(self):
        fairs = {b: 0.80 for b in BOOKS}
        self.assertTrue(self.a("over", 1.5, -200, fairs, 0.5)["step1"])
        self.assertIn("price", self.a("over", 1.5, -201, fairs, 0.5)["fails"])
        hi = {b: 0.50 for b in BOOKS}
        self.assertNotIn("price", self.a("over", 1.5, 120, hi, 0.5)["fails"])
        self.assertIn("price", self.a("over", 1.5, 121, hi, 0.5)["fails"])
        self.assertIn("line", self.a("over", 3.5, 100, {b: 0.54 for b in BOOKS}, 0.5)["fails"])
        self.assertIn("line", self.a("over", 0.5, 100, {b: 0.54 for b in BOOKS}, 0.5)["fails"])

    def test_the_model_can_veto_but_never_create(self):
        a = self.a("over", 1.5, 100, {b: 0.51 for b in BOOKS}, 0.99)      # model loves it, the market gap is only +2%
        self.assertFalse(a["step1"])
        self.assertIsNone(a["guard"])                                    # step 2 never runs, nothing is created

    def test_under_uses_one_minus_the_calibrated_over(self):
        a = self.a("under", 2.5, 100, {b: 0.46 for b in BOOKS}, 0.40)     # under fair 0.54, EV +8%
        self.assertTrue(a["step1"])
        self.assertAlmostEqual(a["model_cal_over"], 0.40 + OFF25)
        self.assertAlmostEqual(a["model_side"], 1 - (0.40 + OFF25))
        self.assertAlmostEqual(a["final"], 0.8 * 0.54 + 0.2 * (1 - 0.40 - OFF25))

    def test_offsets_are_per_line_and_additive_on_the_over(self):
        self.assertAlmostEqual(paper.calibrated_over(0.50, 1.5, T), 0.50 + OFF15)
        self.assertAlmostEqual(paper.calibrated_over(0.50, 2.5, T), 0.50 + OFF25)
        self.assertIsNone(paper.calibrated_over(0.50, 3.5, T))


# ---------------------------------------------------------------- flags, pulls, caps, CLV, grading (made-up reads)
class Stub:
    """The bits of engine.Inputs the paper test reads."""

    def __init__(self):
        self.raw, self.lineup_state, self.missing = {}, {}, set()

    def model(self, pid, team, opp, home, market, line):
        p = self.raw.get((pid, line))
        return None if p is None else {"p_over": p, "mu": 2.0}

    def player(self, pid, team):
        return {"n": 60, "sitting": False, "missed_last": False}

    def display_name(self, pid, feed_name):
        return feed_name


def at(hhmm):
    return "%sT%s:00-04:00" % (SLATE, hhmm)


def minus(hhmm, m):
    h, mm = [int(x) for x in hhmm.split(":")]
    t = h * 60 + mm - m
    return "%02d:%02d" % (t // 60, t % 60)


def utc(hhmm):
    h, mm = [int(x) for x in hhmm.split(":")]
    return "%sT%02d:%02d:00Z" % (SLATE, h + 4, mm)


def rows(lines):
    out = []
    for pid, team, name, line, o, u in lines:
        if o is not None:
            out.append({"name": name, "pid": pid, "team": team, "side": "over", "line": line, "price": o})
        if u is not None:
            out.append({"name": name, "pid": pid, "team": team, "side": "under", "line": line, "price": u})
    return out


def fetch(gid, pull, hhmm, hr, oth=None, away="AAA", home="BBB"):
    lu = utc(minus(hhmm, 1))
    f = {"game_id": gid, "away": away, "home": home, "pull": pull, "at": at(hhmm), "cost": 1, "requested": ["shots"],
         "book": "hardrockbet", "markets": {"shots": {"last_update": lu, "outcomes": rows(hr)}}, "unmatched": []}
    if oth is not None:
        f["others"] = {b: {"shots": {"last_update": lu, "outcomes": rows(l)}} for b, l in oth.items()}
    return f


def game(gid, away, home, hhmm):
    return {"id": gid, "away": away, "home": home, "start": at(hhmm), "date": SLATE}


class Base(unittest.TestCase):
    def setUp(self):
        self.saved = {k: os.environ.get(k) for k in ("PC_NOW", "PC_DATA_DIR", "PC_CONFIG", "DISCORD_WEBHOOK_URL",
                                                     "PC_DISCORD_FIXTURE_URL")}
        self.dir = tempfile.mkdtemp(prefix="pc_paper_")
        os.environ["PC_DATA_DIR"] = self.dir
        os.environ.pop("PC_CONFIG", None)
        self.cfg = json.loads(json.dumps(common.load_config()))
        self.games = [game(1, "AAA", "BBB", "19:00"), game(2, "CCC", "DDD", "19:30")]
        self.inp = Stub()
        self.fetches = []

    def tearDown(self):
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.dir, ignore_errors=True)

    # ---- building reads
    def lines(self, pid, team, name, line, F, hr=(100, -125), side="over", raw=None, shift=None, books=BOOKS):
        """(hr line, {book: line}) for a player whose other books agree on fair over F (under: F is the UNDER fair)."""
        fo = F if side == "over" else 1 - F
        raw = (fo - (OFF15 if line == 1.5 else OFF25)) if raw is None else raw
        self.inp.raw[(pid, line)] = raw
        hr_line = (pid, team, name, line) + (tuple(hr) if side == "over" else (hr[1], hr[0]))
        oth = {b: (pid, team, name, line) + pair_for(fo + (shift or {}).get(b, 0.0)) for b in books}
        return hr_line, oth

    def read(self, gid, pull, hhmm, cands, away="AAA", home="BBB", others=True):
        hr = [c[0] for c in cands]
        oth = {}
        for c in cands:
            for b, l in c[1].items():
                oth.setdefault(b, []).append(l)
        f = fetch(gid, pull, hhmm, hr, oth if others else None, away, home)
        self.fetches.append(f)
        return f

    def write_odds(self):
        common.write_json(odds.odds_path(SLATE), {"date": SLATE, "fetches": self.fetches}, pretty=False)

    def step(self, hhmm):
        self.write_odds()
        os.environ["PC_NOW"] = at(hhmm)
        return paper.step(common.now(), SLATE, self.cfg, self.inp, {"games": {}}, self.games)

    def events(self, *kinds):
        ev = paper.read_events()
        return [e for e in ev if not kinds or e["t"] in kinds]

    def summary(self):
        return common.read_json(paper.summary_path())

    def shadow_result(self, rows_):
        """rows_: [(game_id, pid, line, {"over": W/L/VOID, "under": ...}, actual)] -> data/shadow/<slate>.json."""
        doc = {"date": SLATE, "version": 1, "rows": [
            {"game_id": g, "market": "shots", "pid": pid, "name": "x", "line": line, "ctx": {"start": at("19:00")},
             "result": dict(res, actual=actual)} for g, pid, line, res, actual in rows_]}
        common.write_json(os.path.join(self.dir, "shadow", SLATE + ".json"), doc, pretty=False)


class Flags(Base):
    def test_a_read_cannot_flag_but_b_does_and_the_price_is_frozen(self):
        c = self.lines(101, "AAA", "Ann Aa", 1.5, 0.52)
        self.read(1, "A", "13:00", [c])
        self.step("13:05")
        self.assertEqual(self.events(), [])                                  # the 1 PM read is baseline only
        self.read(1, "B", "17:30", [c])
        self.step("17:31")
        fl = self.events("flag")
        self.assertEqual(len(fl), 1)
        f = fl[0]
        self.assertEqual((f["id"], f["side"], f["line"], f["price"], f["read_pull"]),
                         ("%s:1:101:1.5:over" % SLATE, "over", 1.5, 100, "B"))
        for k in ("market_fair", "n_books", "books", "pin_fair", "gap_ev", "model_raw_over", "model_cal_over", "final",
                  "final_ev", "lineup", "settled", "read_at", "move30"):
            self.assertIn(k, f)
        self.assertEqual(f["n_books"], 5)
        self.assertAlmostEqual(f["market_fair"], 0.52, places=6)
        self.assertAlmostEqual(f["gap_ev"], 0.04, places=6)
        self.assertEqual(f["guard"], "pass")
        self.assertEqual(f["settled"], "Early")

    def test_move30_is_the_market_change_since_the_earlier_read(self):
        a = self.lines(101, "AAA", "Ann Aa", 1.5, 0.50)
        b = self.lines(101, "AAA", "Ann Aa", 1.5, 0.52)
        self.read(1, "A", "17:00", [a])
        self.read(1, "B", "17:30", [b])
        self.step("17:31")
        f = self.events("flag")[0]
        self.assertAlmostEqual(f["move30"], 0.02, places=6)                  # 17:00 read is 30 min older
        self.assertEqual(f["move30_from"], at("17:00"))

    def test_read_without_others_is_skipped_entirely(self):
        c = self.lines(101, "AAA", "Ann Aa", 1.5, 0.52)
        self.read(1, "B", "17:30", [c], others=False)
        self.step("17:31")
        self.assertEqual(self.events(), [])
        self.read(1, "C", "18:15", [c])                                      # the next read that asked others flags it
        self.step("18:16")
        fl = self.events("flag")
        self.assertEqual([(e["read_pull"], e["read_at"]) for e in fl], [("C", at("18:15"))])

    def test_no_double_add_and_no_new_events_when_nothing_is_new(self):
        c = self.lines(101, "AAA", "Ann Aa", 1.5, 0.52)
        self.read(1, "B", "17:30", [c])
        self.step("17:31")
        raw1 = paper.read_raw()
        self.step("17:41")
        self.step("17:51")
        self.assertEqual(paper.read_raw(), raw1)
        self.read(1, "C", "18:15", [c])                                      # same line again: dedup per (game, pid, line, side)
        self.step("18:16")
        self.assertEqual(len(self.events("flag")), 1)

    def test_vetoed_candidate_is_logged_once_with_the_same_closing_data(self):
        c = self.lines(101, "AAA", "Ann Aa", 1.5, 0.5175, hr=(100, -125), raw=0.30)   # market +3.5%, model far below
        self.read(1, "B", "17:30", [c])
        self.step("17:31")
        self.assertEqual([e["t"] for e in self.events()], ["veto"])
        v = self.events("veto")[0]
        self.assertEqual(v["guard"], "veto")
        self.assertLess(v["final_ev"], 0.02)
        self.read(1, "C", "18:15", [c])
        self.step("18:16")
        self.assertEqual([e["t"] for e in self.events()], ["veto", "close"])    # not vetoed twice; closed like a flag
        cl = self.events("close")[0]
        self.assertAlmostEqual(cl["close_fair"], 0.5175, places=6)
        self.assertAlmostEqual(cl["clv"], 0.5175 * 2.0 - 1, places=6)

    def test_candidate_can_pass_the_guard_at_a_later_read(self):
        c = self.lines(101, "AAA", "Ann Aa", 1.5, 0.5175, raw=0.30)
        self.read(1, "B", "17:30", [c])
        self.step("17:31")
        self.inp.raw[(101, 1.5)] = 0.5175 - OFF15                              # the model changed its mind
        self.read(1, "C", "18:15", [c])
        self.step("18:16")
        self.assertEqual([e["t"] for e in self.events()], ["veto", "flag", "close"])
        self.assertIsNone(self.events("close")[0]["clv"])                    # first caught at the 45-minute read

    def test_price_outside_the_gate_or_wrong_line_never_flags(self):
        hi = self.lines(101, "AAA", "Ann Aa", 1.5, 0.50, hr=(125, -160))     # +125 is longer than +120
        l35 = self.lines(102, "AAA", "Bo Bb", 3.5, 0.55)
        self.read(1, "B", "17:30", [hi, l35])
        self.step("17:31")
        self.assertEqual(self.events(), [])

    def test_player_out_per_daily_faceoff_is_not_flagged_and_pulls_a_live_flag(self):
        c = self.lines(101, "AAA", "Ann Aa", 1.5, 0.52)
        self.read(1, "B", "17:30", [c])
        self.step("17:31")
        self.inp.lineup_state = {"teams": {"AAA": {"page": {"today": True, "in": [], "unsure": [], "out": [101],
                                                             "complete": True}}}}
        self.step("17:41")
        pl = self.events("pull")
        self.assertEqual([(p["reason"], p["read_at"]) for p in pl], [("out per Daily Faceoff", None)])
        self.assertEqual(len(self.events("flag")), 1)                         # the flag stays in the log, marked pulled
        self.assertEqual(self.summary()["tonight"]["flags"][0]["state"], "pulled")
        self.step("17:51")
        self.assertEqual(len(self.events("pull")), 1)

    def test_quiet_cycles_do_not_rewrite_the_files(self):
        c = self.lines(101, "AAA", "Ann Aa", 1.5, 0.52)
        self.read(1, "B", "17:30", [c])
        self.step("17:31")
        sp, cp = paper.summary_path(), paper.cursor_path()
        before = (open(sp, "rb").read(), open(cp, "rb").read(), os.stat(sp).st_mtime_ns, os.stat(cp).st_mtime_ns)
        self.step("17:36")                                                     # nothing new, inside the heartbeat
        self.assertEqual((open(sp, "rb").read(), open(cp, "rb").read(), os.stat(sp).st_mtime_ns, os.stat(cp).st_mtime_ns), before)
        self.step("17:56")                                                     # a heartbeat later the stamp is refreshed
        self.assertNotEqual(open(sp, "rb").read(), before[0])

    def test_settled_level(self):
        c = self.lines(101, "AAA", "Ann Aa", 1.5, 0.52)
        self.inp.lineup_state = {"teams": {"AAA": {"page": {"today": True, "in": [101], "unsure": [], "out": [],
                                                             "complete": True}}}}
        self.read(1, "B", "17:30", [c])
        self.step("17:31")
        self.assertEqual(self.events("flag")[0]["settled"], "Lineup confirmed")
        common.write_json(common.dpath("state", "goalies.json"), {"date": SLATE, "teams": {
            "AAA": {"name": "G1", "status": "confirmed"}, "BBB": {"name": "G2", "status": "confirmed"}}})
        self.step("17:41")
        self.assertEqual(self.summary()["tonight"]["flags"][0]["settled"], "Goalie confirmed")


class Pulls(Base):
    def flag(self, F=0.52, raw=None, hr=(100, -125)):
        c = self.lines(101, "AAA", "Ann Aa", 1.5, F, hr=hr, raw=raw)
        self.read(1, "B", "17:30", [c])
        self.step("17:31")
        self.assertEqual(len(self.events("flag")), 1)
        return c

    def c_read(self, hr_price=None, F=0.52, books=BOOKS, shift=None, raw=None, drop_line=False, hhmm="18:15"):
        hr = (100, -125) if hr_price is None else hr_price
        c = self.lines(101, "AAA", "Ann Aa", 1.5, F, hr=hr, raw=raw, books=books, shift=shift)
        if drop_line:
            c = (None, c[1])
            hr_lines, oth = [], {}
            for b, l in c[1].items():
                oth.setdefault(b, []).append(l)
            self.fetches.append(fetch(1, "C", hhmm, hr_lines, oth))
        else:
            self.read(1, "C", hhmm, [c])
        self.step("18:16")

    def test_price_moves_and_the_gap_is_gone_pulls_but_the_flag_keeps_its_frozen_price(self):
        self.flag()
        self.c_read(hr_price=(-110, -110))
        pl = self.events("pull")
        self.assertEqual(len(pl), 1)
        self.assertEqual(pl[0]["reason"], "price moved, gap gone")
        fl = self.events("flag")
        self.assertEqual((len(fl), fl[0]["price"]), (1, 100))                   # frozen at +100
        s = self.summary()["tonight"]["flags"][0]
        self.assertEqual((s["state"], s["price"]), ("pulled", 100))

    def test_hysteresis_a_price_move_that_leaves_ev_at_or_above_1_5_percent_keeps_it(self):
        self.flag(raw=0.57 - OFF15)                                              # model well above the market
        self.c_read(hr_price=(-105, -115), raw=0.57 - OFF15)                     # -105: market EV = +1.52%
        self.assertEqual(self.events("pull"), [])
        self.step("18:26")
        self.assertEqual(self.events("pull"), [])

    def test_price_unchanged_never_pulls_on_the_gap_alone(self):
        self.flag(raw=0.57 - OFF15)
        self.c_read(F=0.505, raw=0.57 - OFF15)                                   # market fell: gap +1.0%, price still +100
        self.assertEqual(self.events("pull"), [])

    def test_fewer_than_four_books_pulls(self):
        self.flag()
        self.c_read(books=BOOKS[:3] + ["pinnacle"][:0])
        self.assertEqual([p["reason"] for p in self.events("pull")], ["fewer than 4 books"])

    def test_pinnacle_gone_or_flipped_pulls(self):
        self.flag()
        self.c_read(books=[b for b in BOOKS if b != "pinnacle"] + ["bovada"])
        self.assertEqual([p["reason"] for p in self.events("pull")], ["Pinnacle gone"])

    def test_pinnacle_sign_flip_pulls(self):
        self.flag()
        self.c_read(shift={"pinnacle": -0.04})
        self.assertEqual([p["reason"] for p in self.events("pull")], ["Pinnacle disagrees"])

    def test_guard_failing_later_pulls(self):
        self.flag()
        self.c_read(raw=0.30)                                                    # the model now disagrees a lot
        self.assertEqual([p["reason"] for p in self.events("pull")], ["model guard fails"])

    def test_line_removed_pulls(self):
        self.flag()
        self.c_read(drop_line=True)
        self.assertEqual([p["reason"] for p in self.events("pull")], ["line removed"])

    def test_a_pulled_flag_is_not_re_added_or_pulled_twice(self):
        self.flag()
        self.c_read(hr_price=(-110, -110))
        self.c_read(hr_price=(100, -125), hhmm="18:25")                          # price is back: still not re-added
        self.assertEqual((len(self.events("flag")), len(self.events("pull"))), (1, 1))


class Caps(Base):
    def test_one_side_per_player_two_per_game_three_per_night_ranked_by_final_ev(self):
        g1 = [self.lines(101, "AAA", "Ann Aa", 1.5, 0.54),      # +8%  -> flag
              self.lines(101, "AAA", "Ann Aa", 2.5, 0.535),     # same player, second line -> capped (player)
              self.lines(102, "AAA", "Bo Bb", 1.5, 0.53),       # +6%  -> flag (2nd in game)
              self.lines(103, "AAA", "Cy Cc", 1.5, 0.52)]       # +4%  -> capped (game)
        g2 = [self.lines(201, "CCC", "Di Dd", 1.5, 0.525),      # +5%  -> flag (3rd of the night)
              self.lines(202, "CCC", "Ed Ee", 1.5, 0.52)]       # +4%  -> capped (night)
        self.read(1, "B", "17:30", g1)
        self.read(2, "B", "18:00", g2, "CCC", "DDD")
        self.step("18:01")
        fl = {e["pid"]: e for e in self.events("flag")}
        self.assertEqual(sorted(fl), [101, 102, 201])
        self.assertEqual(fl[101]["line"], 1.5)                                   # the player's BEST side wins
        cap = {(e["pid"], e["line"]): e["cap"] for e in self.events("capped")}
        self.assertEqual(cap, {(101, 2.5): "player", (103, 1.5): "game", (202, 1.5): "night"})
        self.assertEqual(len(self.summary()["tonight"]["flags"]), 3)
        self.assertEqual(len(self.summary()["tonight"]["capped"]), 3)

    def test_best_of_a_players_two_sides_or_lines_is_picked_regardless_of_order(self):
        g1 = [self.lines(101, "AAA", "Ann Aa", 1.5, 0.52), self.lines(101, "AAA", "Ann Aa", 2.5, 0.56)]
        self.read(1, "B", "17:30", g1)
        self.step("17:31")
        self.assertEqual([(e["pid"], e["line"]) for e in self.events("flag")], [(101, 2.5)])

    def test_a_pulled_flag_still_counts_toward_the_caps(self):
        c = [self.lines(101, "AAA", "Ann Aa", 1.5, 0.54), self.lines(102, "AAA", "Bo Bb", 1.5, 0.53)]
        self.read(1, "B", "17:30", c)
        self.step("17:31")
        self.inp.lineup_state = {"teams": {"AAA": {"page": {"today": True, "in": [], "unsure": [], "out": [101, 102],
                                                             "complete": False}}}}
        self.step("17:41")
        self.assertEqual(len(self.events("pull")), 2)
        c3 = self.lines(103, "AAA", "Cy Cc", 1.5, 0.55)
        self.read(1, "C", "18:15", c + [c3])
        self.step("18:16")
        self.assertEqual([e["pid"] for e in self.events("capped")], [103])


class CloseAndGrade(Base):
    def test_clv_is_close_fair_times_frozen_decimal_minus_one_and_none_when_first_caught_at_close(self):
        a = self.lines(101, "AAA", "Ann Aa", 1.5, 0.52)
        self.read(1, "B", "17:30", [a])
        later = self.lines(101, "AAA", "Ann Aa", 1.5, 0.55)                     # market moved toward the flag
        late_only = self.lines(102, "AAA", "Bo Bb", 1.5, 0.53)
        self.read(1, "C", "18:15", [later, late_only])
        self.step("18:16")
        cl = {e["id"].split(":")[2]: e for e in self.events("close")}
        self.assertAlmostEqual(cl["101"]["close_fair"], 0.55, places=6)
        self.assertAlmostEqual(cl["101"]["clv"], 0.55 * 2.0 - 1, places=6)          # frozen decimal 2.0 (+100)
        self.assertFalse(cl["101"]["first_caught_at_close"])
        self.assertIsNone(cl["102"]["clv"])                                          # first caught at the 45-minute read
        self.assertTrue(cl["102"]["first_caught_at_close"])
        self.assertEqual(len([e for e in self.events("flag")]), 2)

    def test_a_b_read_inside_the_45_minute_window_is_the_close_and_one_close_per_line(self):
        a = self.lines(101, "AAA", "Ann Aa", 1.5, 0.52)
        self.read(1, "B", "17:30", [a])
        self.read(1, "B", "18:20", [a])                                          # B and C fell due together
        self.read(1, "C", "18:30", [a])
        self.step("18:31")
        cl = self.events("close")
        self.assertEqual([c["read_at"] for c in cl], [at("18:20")])

    def test_grades_w_l_void_at_the_frozen_price_even_after_a_pull(self):
        g1 = [self.lines(101, "AAA", "Ann Aa", 1.5, 0.54), self.lines(102, "AAA", "Bo Bb", 1.5, 0.53)]
        g2 = [self.lines(201, "CCC", "Di Dd", 1.5, 0.525, hr=(120, -150))]
        self.read(1, "B", "17:30", g1)
        self.read(2, "B", "18:00", g2, "CCC", "DDD")
        self.step("18:01")
        self.inp.lineup_state = {"teams": {"CCC": {"page": {"today": True, "in": [], "unsure": [], "out": [201],
                                                             "complete": False}}}}
        self.step("18:05")                                                        # 201 is pulled; still graded at +120
        self.assertEqual([p["id"].split(":")[2] for p in self.events("pull")], ["201"])
        self.shadow_result([(1, 101, 1.5, {"over": "W", "under": "L"}, 3),
                            (1, 102, 1.5, {"over": "L", "under": "W"}, 1),
                            (2, 201, 1.5, {"over": "W", "under": "L"}, 2)])
        self.step("23:30")
        gr = {e["id"].split(":")[2]: e for e in self.events("grade")}
        self.assertEqual((gr["101"]["result"], round(gr["101"]["units"], 4)), ("W", 1.0))            # +100
        self.assertEqual((gr["102"]["result"], gr["102"]["units"]), ("L", -1.0))
        self.assertEqual((gr["201"]["result"], round(gr["201"]["units"], 4)), ("W", 1.2))            # frozen +120
        self.step("23:40")
        self.assertEqual(len(self.events("grade")), 3)                            # graded once

    def test_void_has_no_ice_time_and_does_not_count_toward_n(self):
        g1 = [self.lines(101, "AAA", "Ann Aa", 1.5, 0.54), self.lines(102, "AAA", "Bo Bb", 1.5, 0.53)]
        self.read(1, "B", "17:30", g1)
        self.step("17:31")
        self.shadow_result([(1, 101, 1.5, {"over": "VOID", "under": "VOID"}, None),
                            (1, 102, 1.5, {"over": "W", "under": "L"}, 2)])
        self.step("23:30")
        nov2 = self.summary()["nov2"]
        self.assertEqual((nov2["graded_picks"], nov2["w"], nov2["l"], nov2["void"]), (1, 1, 0, 1))
        self.assertAlmostEqual(nov2["units"], 1.0)

    def test_under_is_graded_on_the_under_result(self):
        c = self.lines(101, "AAA", "Ann Aa", 1.5, 0.56, side="under", hr=(100, -125))
        self.read(1, "B", "17:30", [c])
        self.step("17:31")
        f = self.events("flag")[0]
        self.assertEqual((f["side"], f["price"]), ("under", 100))
        self.shadow_result([(1, 101, 1.5, {"over": "L", "under": "W"}, 1)])
        self.step("23:30")
        self.assertEqual(self.events("grade")[0]["result"], "W")

    def test_summary_nov2_numbers(self):
        g1 = [self.lines(101, "AAA", "Ann Aa", 1.5, 0.54), self.lines(102, "AAA", "Bo Bb", 1.5, 0.53),
              self.lines(103, "AAA", "Cy Cc", 1.5, 0.5175, raw=0.30)]            # a veto
        self.read(1, "B", "17:30", g1)
        self.read(1, "C", "18:15", g1)
        self.step("18:16")
        self.shadow_result([(1, 101, 1.5, {"over": "W", "under": "L"}, 2), (1, 102, 1.5, {"over": "L", "under": "W"}, 0),
                            (1, 103, 1.5, {"over": "W", "under": "L"}, 3)])
        self.step("23:30")
        n = self.summary()["nov2"]
        self.assertEqual((n["graded_picks"], n["w"], n["l"]), (2, 1, 1))
        self.assertAlmostEqual(n["units"], 0.0)
        self.assertEqual(n["gaps_logged"], 3)
        self.assertEqual(n["gaps_measured"], 3)                                  # CLV exists for flags and the veto
        self.assertEqual(n["clv_vetoed"]["n"], 1)
        self.assertIsNotNone(n["clv_gaps"]["lb80"])
        self.assertIsNone(n["population_slope"])
        self.assertEqual(n["checkpoint"], "2026-11-02")
        self.assertNotIn("hard_stop", n)                                     # no end date: this is the live rule


class Switches(Base):
    def test_off_outside_the_window_and_without_config(self):
        c = self.lines(101, "AAA", "Ann Aa", 1.5, 0.52)
        self.read(1, "B", "17:30", [c])
        self.cfg["ops"]["gap_guard"]["active"] = False
        self.step("17:31")
        self.assertEqual(self.events(), [])
        self.cfg["ops"]["gap_guard"]["active"] = True
        self.cfg["ops"]["gap_guard"]["live_from"] = "2026-10-22"
        self.step("17:32")
        self.assertEqual(self.events(), [])
        del self.cfg["ops"]["gap_guard"]
        os.environ["PC_NOW"] = at("17:33")
        self.assertEqual(paper.step(common.now(), SLATE, self.cfg, self.inp, {"games": {}}, self.games)["status"], "skipped")

    def test_live_from_is_the_first_slate_and_there_is_no_end_date(self):
        cfg = common.load_config()
        self.assertEqual(cfg["ops"]["gap_guard"]["live_from"], "2026-10-20")
        self.assertFalse(common.gap_guard_active(cfg, "2026-10-19"))          # nothing for the slate before it
        self.assertFalse(common.gap_guard_active(cfg, "2026-10-12"))
        self.assertTrue(common.gap_guard_active(cfg, "2026-10-20"))
        self.assertTrue(common.gap_guard_active(cfg, "2026-11-23"))
        self.assertTrue(common.gap_guard_active(cfg, "2027-03-01"))           # no hard stop any more
        self.assertFalse(common.gap_guard_active({"ops": {}}, "2026-10-20"))
        self.assertNotIn("end", cfg["ops"]["gap_guard"])


# ---------------------------------------------------------------- the paper log guard and the Record
def edit_config(fn):
    """Change the Sim's private copy of config/rules.json (PC_CONFIG)."""
    path = os.environ["PC_CONFIG"]
    with open(path, encoding="utf-8") as f:
        c = json.load(f)
    fn(c)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(c, f)


def tree_hash(root):
    h = hashlib.sha256()
    for d, _, files in sorted(os.walk(root)):
        for f in sorted(files):
            p = os.path.join(d, f)
            h.update(p.encode())
            with open(p, "rb") as fh:
                h.update(fh.read())
    return h.hexdigest()


class Guards(Base):
    def test_append_only_prefix_guard(self):
        paper.append([{"t": "flag", "id": "x"}, {"t": "pull", "id": "x"}])
        old = paper.read_raw()
        paper.append([{"t": "grade", "id": "x"}])
        self.assertTrue(paper.read_raw().startswith(old))
        self.assertIsNone(guard_record.check(old, paper.read_raw()))
        self.assertIn("changed", guard_record.check(old, old.replace(b"flag", b"FLAG") + b"\n"))
        self.assertIn("lost lines", guard_record.check(old, old.split(b"\n")[0] + b"\n"))
        with self.assertRaises(RuntimeError):                                      # an append that is not a prefix extension
            real = paper.read_raw
            paper.read_raw = lambda: b'{"t":"flag","id":"x"}\n' + b'{"broken"'
            try:
                paper.append([{"t": "x", "id": "y"}])
            finally:
                paper.read_raw = real

    def git(self, *a):
        subprocess.run(["git"] + list(a), cwd=self.repo, check=True, capture_output=True)

    def test_guard_paper_script_in_a_real_repo(self):
        self.repo = tempfile.mkdtemp(prefix="pc_gp_")
        try:
            self.git("init", "-q")
            self.git("config", "user.email", "t@t")
            self.git("config", "user.name", "t")
            self.assertEqual(guard_paper.main([], self.repo), 0)                   # nothing yet: fine
            p = os.path.join(self.repo, "data", "paper", "events.jsonl")
            os.makedirs(os.path.dirname(p))
            with open(p, "wb") as f:
                f.write(b'{"a":1}\n{"b":2}\n')
            self.git("add", "-A")
            self.git("commit", "-qm", "one")
            with open(p, "ab") as f:
                f.write(b'{"c":3}\n')
            self.assertEqual(guard_paper.main([], self.repo), 0)                   # appended: fine
            with open(p, "wb") as f:
                f.write(b'{"a":9}\n{"b":2}\n{"c":3}\n')
            self.assertEqual(guard_paper.main([], self.repo), 1)                   # a committed line changed
            with open(p, "wb") as f:
                f.write(b'{"a":1}\n')
            self.assertEqual(guard_paper.main([], self.repo), 1)                   # a line was dropped
            os.unlink(p)
            self.assertEqual(guard_paper.main([], self.repo), 1)                   # the file is gone
        finally:
            shutil.rmtree(self.repo, ignore_errors=True)

    def test_cycle_restores_the_paper_dir_on_a_breach_and_does_not_fail(self):
        with open(os.path.join(ROOT, "scripts", "cycle.sh"), encoding="utf-8") as f:
            src = f.read()
        self.assertRegex(src, r'guard_paper\.py \|\| \{')
        self.assertIn("git checkout -q HEAD -- data/paper", src)
        self.assertLess(src.index("guard_record.py || {"), src.index("guard_paper.py"))
        self.assertLess(src.index("guard_paper.py"), src.index("# 4. publish"))

    def test_paper_never_touches_the_record(self):
        src = open(os.path.join(ROOT, "scripts", "paper.py"), encoding="utf-8").read()
        self.assertIsNone(re.search(r"^\s*(import record\s*(#.*)?$|from record import)", src, re.M))
        self.assertNotIn("record.append", src)
        self.assertNotIn('"record"', src)                                                  # never builds a data/record path
        rec = os.path.join(self.dir, "record")
        os.makedirs(rec)
        with open(os.path.join(rec, "events.jsonl"), "wb") as f:
            f.write(b'{"t":"shown","id":"keep"}\n')
        with open(os.path.join(self.dir, "record.json"), "w") as f:
            f.write("{}")
        with open(os.path.join(self.dir, "record.json")) as fh:
            before, rj = tree_hash(rec), fh.read()
        c = self.lines(101, "AAA", "Ann Aa", 1.5, 0.52)
        self.read(1, "B", "17:30", [c])
        self.read(1, "C", "18:15", [c])
        self.step("18:16")
        self.shadow_result([(1, 101, 1.5, {"over": "W", "under": "L"}, 3)])
        self.step("23:30")
        self.assertTrue(self.events("flag") and self.events("grade"))
        self.assertEqual(tree_hash(rec), before)
        with open(os.path.join(self.dir, "record.json")) as fh:
            self.assertEqual(fh.read(), rj)
        self.assertEqual(sorted(os.listdir(os.path.join(self.dir, "paper"))), ["cursor.json", "events.jsonl", "summary.json"])
        self.assertFalse(os.path.exists(os.path.join(self.dir, "slate.json")))


# ---------------------------------------------------------------- the odds plan
class Plan(unittest.TestCase):
    V = common.load_config()["values"]

    def test_markets_for_b_is_shots_only_at_every_tier_while_paper_is_active(self):
        for tier in (1, 2, 3, 4):
            self.assertEqual(odds.markets_for(tier, "B", paper=True), ["shots"], tier)
        self.assertEqual(odds.markets_for(0, "B", paper=True), [])
        self.assertEqual(odds.markets_for(1, "B"), [])                                   # unchanged without paper
        self.assertEqual(odds.markets_for(2, "B"), ["shots"])
        self.assertEqual(odds.markets_for(3, "B"), ["shots", "saves"])
        self.assertEqual(odds.markets_for(4, "B"), ["shots", "saves", "goals"])
        self.assertEqual(odds.markets_for(4, "B", paper=True), ["shots"])                # no saves / goals pulls
        self.assertEqual(odds.markets_for(1, "A", paper=True), ["shots"])

    def test_markets_for_c_every_game_at_tier_3_and_up_or_when_asked(self):
        self.assertEqual(odds.markets_for(2, "C", (), None, paper=True), [])             # tier 2, no live pick, no floor
        self.assertEqual(odds.markets_for(2, "C", (), True, paper=True), ["shots"])      # run_pulls passes c_every_game
        self.assertEqual(odds.markets_for(3, "C", (), None, paper=True), ["shots"])
        self.assertEqual(odds.markets_for(4, "C", (), None, paper=True), ["shots"])

    def test_tier_floor_is_3_only_when_the_allowance_is_at_least_3(self):
        mk = lambda al, tier: {"allowance": al, "tier": tier}
        self.assertEqual(odds.eff_tier(mk(3.2, 2), True), 3)
        self.assertEqual(odds.eff_tier(mk(2.9, 2), True), 2)
        self.assertEqual(odds.eff_tier(mk(3.2, 2), False), 2)
        self.assertEqual(odds.eff_tier(mk(8.0, 4), True), 4)
        self.assertEqual(odds.eff_tier(mk(1.4, 1), True), 1)

    def games(self):
        return [{"id": 7, "date": SLATE, "away": "AAA", "home": "BBB", "start": at("19:00")}]

    def due(self, hhmm, fetched, paper, tier=3, lineups_ok=None):
        now = common.parse_iso(at(hhmm))
        return odds.due_pulls(now, self.games(), tier, self.V, fetched, {}, {}, 30, lineups_ok=lineups_ok,
                              c_every_game=True, paper=paper)

    def test_b_does_not_wait_for_lineups_while_paper_is_active(self):
        a = {7: [{"pull": "A", "at": common.parse_iso(at("13:00")), "markets": ["shots"], "returned": ["shots"]}]}
        self.assertEqual(self.due("17:31", a, False, lineups_ok={7: False}), [])             # old behavior: waits
        d = self.due("17:31", a, True, lineups_ok={7: False})
        self.assertEqual([(x["pull"], x["markets"]) for x in d], [("B", ["shots"])])

    def test_three_reads_a_game_with_unconfirmed_lineups_and_nothing_after_puck(self):
        fetched, got = {}, []
        for hhmm in ("13:00", "13:10", "17:20", "17:31", "17:41", "18:14", "18:16", "18:26", "18:56", "19:05"):
            for d in self.due(hhmm, fetched, True, lineups_ok={7: False}):
                got.append((hhmm, d["pull"], d["markets"]))
                fetched.setdefault(7, []).append({"pull": d["pull"], "at": common.parse_iso(at(hhmm)),
                                                  "markets": d["markets"], "returned": d["markets"]})
        self.assertEqual(got, [("13:00", "A", ["shots"]), ("17:31", "B", ["shots"]), ("18:16", "C", ["shots"])])
        self.assertEqual(self.due("19:05", fetched, True), [])                                # never a started game

    def test_next_read_promises_b_without_lineups(self):
        now = common.parse_iso(at("14:00"))
        done = {7: [{"pull": "A", "at": common.parse_iso(at("13:00")), "markets": ["shots"], "returned": ["shots"]}]}
        nxt = odds.next_read_at(now, self.games(), 3, self.V, done, {}, True, lineups_ok={7: False}, paper=True)
        self.assertEqual(nxt, common.parse_iso(at("17:30")))
        nxt = odds.next_read_at(now, self.games(), 3, self.V, done, {}, True, lineups_ok={7: False}, paper=False)
        self.assertEqual(nxt, common.parse_iso(at("18:15")))


class ClosingBudget(unittest.TestCase):
    """C on every game is kept while today's budget left covers the B and C reads still owed (not a flat 3 credits a
    game ahead). The 2026-10-20 slate: 11 games, budget 50, shots only (paper), tier 3."""
    V = common.load_config()["values"]
    TIMES = ["19:00"] * 5 + ["20:00"] * 6

    def setUp(self):
        self.games = [game(i, "A%02d" % i, "H%02d" % i, t) for i, t in enumerate(self.TIMES, 1)]
        self.fetched = {}
        for g in self.games:
            self.read(g["id"], "A", "13:00")                                     # A on all 11: 11 credits

    def read(self, gid, pull, hhmm):
        self.fetched.setdefault(gid, []).append({"pull": pull, "at": common.parse_iso(at(hhmm)), "markets": ["shots"],
                                                 "returned": ["shots"]})

    def spent(self):
        return sum(len(f["markets"]) for fs in self.fetched.values() for f in fs)

    def plan(self, hhmm, budget=50, live=None, started=None):
        now = common.parse_iso(at(hhmm))
        started = started or {}
        every = odds.c_for_every_game(now, self.games, 3, self.V, self.fetched, started, budget - self.spent(), paper=True)
        due = odds.due_pulls(now, self.games, 3, self.V, self.fetched, live or {}, started, 30, c_every_game=every,
                             paper=True)
        return every, [(d["pull"], d["game"]["id"], d["markets"]) for d in due]

    def test_tonight_c_reads_run_for_the_7_pm_and_then_the_8_pm_games(self):
        for gid in range(1, 6):
            self.read(gid, "B", "17:30")                                         # B on the five 7 PM games
        self.assertEqual(self.spent(), 16)
        now = common.parse_iso(at("18:15"))
        self.assertEqual(odds.credits_still_needed(now, self.games, 3, self.V, self.fetched, {}, paper=True), 17)
        every, due = self.plan("18:15")                                          # 34 left, 17 owed (old rule: 33)
        self.assertTrue(every)
        self.assertEqual(due, [("C", gid, ["shots"]) for gid in range(1, 6)])
        for gid in range(1, 6):
            self.read(gid, "C", "18:15")
        self.assertEqual(self.spent(), 21)
        every, due = self.plan("18:30")
        self.assertEqual(due, [("B", gid, ["shots"]) for gid in range(6, 12)])  # the 8 PM games' 90 minute read
        for gid in range(6, 12):
            self.read(gid, "B", "18:30")
        seven_started = {gid: True for gid in range(1, 6)}
        every, due = self.plan("19:15", started=seven_started)                   # 23 left, 6 owed
        self.assertTrue(every)
        self.assertEqual(due, [("C", gid, ["shots"]) for gid in range(6, 12)])

    def test_kept_where_the_old_flat_reserve_dropped_it(self):
        for gid in range(1, 6):
            self.read(gid, "B", "17:30")
        self.read(1, "B", "17:40")
        self.read(2, "B", "17:40")                                               # two extra reads: 18 spent
        every, due = self.plan("18:15")                                          # 32 left < 3 x 11 (old), 17 owed (new)
        self.assertTrue(every)
        self.assertEqual(len(due), 5)

    def test_tight_budget_c_goes_back_to_live_picks_only(self):
        for gid in range(1, 6):
            self.read(gid, "B", "17:30")
        every, due = self.plan("18:15", budget=20, live={2: {"shots"}})          # 4 left, 17 owed
        self.assertFalse(every)
        self.assertEqual(due, [("C", 2, ["shots"])])
        self.assertFalse(odds.c_for_every_game(common.parse_iso(at("18:15")), self.games, 2, self.V, self.fetched, {},
                                               99, paper=True))                  # tier 2: never every game
        late = {gid: True for gid in range(1, 12)}
        self.assertTrue(odds.c_for_every_game(common.parse_iso(at("21:00")), self.games, 3, self.V, self.fetched, late,
                                              1, paper=True))                    # nothing owed: needs at least 1
        self.assertFalse(odds.c_for_every_game(common.parse_iso(at("21:00")), self.games, 3, self.V, self.fetched, late,
                                               0, paper=True))


class FullDay(unittest.TestCase):
    """Three reads a game through the real pull code with unconfirmed lineups, ~3 credits a game, shots only."""

    def make(self, pool=500):
        s = Sim(pool=pool, rules="current")
        edit_config(lambda c: c["ops"]["gap_guard"].update(live_from="2026-10-01"))
        return s

    def test_three_shots_reads_per_game_about_three_credits(self):
        s = self.make()
        try:
            s.at("09:00")
            for hhmm in ("13:02", "17:31", "18:01", "18:16", "18:31", "19:16", "20:05"):
                for away, home in (("CAR", "PHI"), ("VAN", "NYR")):
                    s.set_odds(away, home, [s.line(away, 1, "shots", 2.5, 0.0)], "2026-10-11T%02d:%02d:00Z" % (
                        int(hhmm[:2]) + 4, int(hhmm[3:]) - 1))
                s.at(hhmm)
            doc = common.read_json(s.path("odds", world.SLATE + ".json"))
            for gid in (2026020901, 2026020902):
                fs = [(f["pull"], f["requested"], f["cost"]) for f in doc["fetches"] if f["game_id"] == gid]
                self.assertEqual(fs, [("A", ["shots"], 1), ("B", ["shots"], 1), ("C", ["shots"], 1)], gid)
            self.assertEqual(sum(f["cost"] for f in doc["fetches"]), 6)
            self.assertTrue(all(f["requested"] == ["shots"] for f in doc["fetches"]))       # no saves / goals / points
            self.assertEqual({st["step"]: st["status"] for st in s.status()["steps"]}["gapguard"], "ok")
        finally:
            s.close()

    def test_with_gap_guard_off_the_old_plan_b_still_waits_for_lineups(self):
        s = Sim(pool=500, rules="current")
        edit_config(lambda c: c["ops"]["gap_guard"].update(active=False))
        try:
            s.at("09:00")
            s.at("13:02")
            s.at("17:31")                                                                       # no lineups: B does not run
            doc = common.read_json(s.path("odds", world.SLATE + ".json"))
            self.assertEqual({f["pull"] for f in doc["fetches"]}, {"A"})
            self.assertFalse(os.path.exists(s.path("paper", "events.jsonl")))
        finally:
            s.close()

    def test_a_gap_guard_failure_is_a_failed_step_adds_no_pick_and_leaves_the_record_alone(self):
        s = self.make()
        try:
            s.at("09:00")
            s.at("13:02")
            before = (tree_hash(s.path("record")) if os.path.isdir(s.path("record")) else None, s.log_bytes())
            real = paper.step
            paper.step = lambda *a, **k: 1 / 0
            try:
                s.at("17:31")
            finally:
                paper.step = real
            steps = {st["step"]: st for st in s.status()["steps"]}
            self.assertEqual(steps["gapguard"]["status"], "failed")           # the pick source: not a soft step
            self.assertFalse(s.status()["ok"])
            self.assertEqual(s.status()["failed_step"], "gapguard")
            self.assertEqual(steps["engine"]["status"], "ok")                  # everything else carries on
            self.assertEqual(s.slate()["status"]["last_run"]["failed_step"], "gapguard")
            self.assertEqual((tree_hash(s.path("record")) if os.path.isdir(s.path("record")) else None, s.log_bytes()), before)
            s.at("18:16")                                                       # next run is fine again
            self.assertTrue(s.status()["ok"])
        finally:
            s.close()


# ---------------------------------------------------------------- replay of the real Oct 19 reads (Researcher/Builder replay)
class Oct19Replay(unittest.TestCase):
    """The real 2026-10-19 Hard Rock + other-book reads (A and B for ANA@NYR and COL@PHI, shots only), replayed through the
    paper step with the model values the engine produced that day. Expected: Killorn O1.5 +100 flagged at the 90-minute
    read, Michkov O1.5 -120 vetoed (gap real, guard says no), nothing else. Never the live data/."""
    DAY = "2026-10-19"

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="pc_oct19_")
        self.saved = {k: os.environ.get(k) for k in ("PC_NOW", "PC_DATA_DIR", "PC_CONFIG")}
        os.environ.update(PC_DATA_DIR=self.dir)
        os.environ.pop("PC_CONFIG", None)
        os.makedirs(os.path.join(self.dir, "odds"))
        shutil.copy(os.path.join(HERE, "fixtures", "paper_oct19", "odds_2026-10-19.json"),
                    os.path.join(self.dir, "odds", self.DAY + ".json"))
        self.cfg = json.loads(json.dumps(common.load_config()))
        self.cfg["ops"]["gap_guard"]["live_from"] = self.DAY
        self.games = [{"id": 2026020137, "away": "ANA", "home": "NYR", "start": "2026-10-19T19:00:00-04:00", "date": self.DAY},
                      {"id": 2026020138, "away": "COL", "home": "PHI", "start": "2026-10-19T19:00:00-04:00", "date": self.DAY}]
        self.inp = Stub()
        self.inp.raw[(8473986, 1.5)] = 0.5205948068315722        # Killorn (the engine's own number that day)
        self.inp.raw[(8484387, 1.5)] = 0.4973965194814922        # Michkov

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def step(self, hhmm):
        os.environ["PC_NOW"] = "%sT%s:00-04:00" % (self.DAY, hhmm)
        return paper.step(common.now(), self.DAY, self.cfg, self.inp, {"games": {}}, self.games)

    def test_killorn_flags_at_the_90_minute_read_and_michkov_is_vetoed(self):
        self.step("13:05")
        self.assertEqual(paper.read_events(), [])                                          # the 1 PM read can only baseline
        self.step("17:35")
        ev = paper.read_events()
        self.assertEqual([(e["t"], e["player"], e["line"], e["side"], e["price"]) for e in ev],
                         [("flag", "Alex Killorn", 1.5, "over", 100), ("veto", ev[1]["player"], 1.5, "over", -120)])
        self.assertIn("Michkov", ev[1]["player"])
        k, m = ev[0], ev[1]
        self.assertEqual((k["read_pull"], k["read_at"]), ("B", "2026-10-19T17:30:01-04:00"))
        self.assertAlmostEqual(k["market_fair"], 0.529, places=3)
        self.assertEqual(k["n_books"], 6)
        self.assertGreaterEqual(k["gap_ev"], 0.03)
        self.assertEqual(k["guard"], "pass")
        self.assertAlmostEqual(m["market_fair"], 0.566, places=3)
        self.assertEqual(m["guard"], "veto")
        self.assertLess(m["final_ev"], 0.02)
        self.assertLessEqual(len(self.summary_flags()), 3)
        self.step("17:45")
        self.assertEqual(len(paper.read_events()), 2)                                      # a rerun adds nothing

    def summary_flags(self):
        return common.read_json(paper.summary_path())["tonight"]["flags"]



if __name__ == "__main__":
    unittest.main()
