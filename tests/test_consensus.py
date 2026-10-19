"""Other books beside Hard Rock (TEAM.md Q1): one price read asks Hard Rock plus up to 9 other books for the same
credits, keeps them under "others" in data/odds, and the shadow log compares Hard Rock to their consensus.
Hard Rock stays THE book: picks, page and Record must be byte-for-byte the same with or without other books."""
import json
import os
import time
import unittest

import helpers
import world
from helpers import Sim, FIX

import common
import odds
import shadow
from test_odds import real_matcher

UPD = "2026-10-11T17:00:00Z"
CAR_PHI, VAN_NYR = 2026020901, 2026020902
OTHERS9 = ["draftkings", "fanduel", "betmgm", "williamhill_us", "espnbet", "betrivers", "fanatics", "pinnacle",
           "betonlineag"]


def shifted(lines, d):
    """The same lines at another book: fair over moved by d/1000, hold 5%."""
    out = []
    for k, who, line, o, u in lines:
        if o is None or u is None:
            out.append((k, who, line, o, u))
            continue
        fo = min(0.9, max(0.1, odds.fair_two_sided(o, u) + d / 1000.0))
        out.append((k, who, line) + world.two_sided(fo, 0.05))
    return out


class Books(unittest.TestCase):
    def test_config_lists_at_most_nine_others_and_hard_rock_first(self):
        cfg = helpers.cfg()
        others = cfg["ops"]["consensus_books"]
        self.assertLessEqual(len(others), 9)
        self.assertNotIn("hardrockbet", others)
        books = odds.request_books(cfg)
        self.assertEqual(books[0], "hardrockbet")
        self.assertEqual(books, ["hardrockbet"] + others)
        self.assertLessEqual(len(books), odds.MAX_BOOKS_PER_REGION)
        self.assertEqual(odds.request_books(cfg, others=False), ["hardrockbet"])

    def test_list_is_capped_at_ten_and_deduplicated(self):
        cfg = json.loads(json.dumps(helpers.cfg()))
        cfg["ops"]["consensus_books"] = ["hardrockbet"] + ["b%d" % i for i in range(15)]
        books = odds.request_books(cfg)
        self.assertEqual(len(books), 10)
        self.assertEqual(books[:2], ["hardrockbet", "b0"])
        cfg["ops"]["consensus_books"] = []
        self.assertEqual(odds.request_books(cfg), ["hardrockbet"])

    def test_cost_counts_markets_returned_never_books(self):
        lines = [("player_shots_on_goal", "A B", 2.5, -120, -110)]
        js = world.odds_payload("CAR", "PHI", lines, UPD, others={b: lines for b in OTHERS9})
        books = ["hardrockbet"] + OTHERS9
        self.assertEqual(len(js["bookmakers"]), 10)
        self.assertEqual(odds.cost_estimate(js, books), 1)            # 10 books, 1 market -> 1 credit
        two = world.odds_payload("CAR", "PHI", lines + [("player_total_saves", "G X", 25.5, -115, -105)], UPD,
                                 others={b: lines for b in OTHERS9})
        self.assertEqual(odds.cost_estimate(two, books), 2)           # 2 markets -> 2, whatever the book count
        only_dk = world.odds_payload("CAR", "PHI", [], UPD, others={"draftkings": lines}, hr=False)
        self.assertEqual(odds.cost_estimate(only_dk, books), 1)       # billed even though Hard Rock had nothing
        self.assertEqual([odds.regions_billed(n) for n in (1, 10, 11, 20, 21)], [1, 1, 2, 2, 3])
        self.assertEqual(odds.cost_estimate(js, books + ["x"]), 2)    # an 11th book would double the bill


class RealClient(unittest.TestCase):
    def setUp(self):
        self.sim = Sim()
        os.environ.pop("PC_ODDS_FIXTURE_DIR")
        os.environ["ODDS_API_KEYS"] = "kkkkkkkkkkkkkkkk4444"
        self.real_get, self.urls = common.http_get, []
        lines = [("player_shots_on_goal", "A B", 2.5, -120, -110)]
        self.payload = json.dumps(world.odds_payload("CAR", "PHI", lines, UPD,
                                                     others={b: lines for b in OTHERS9})).encode()

    def tearDown(self):
        common.http_get = self.real_get
        self.sim.close()

    def read(self, headers, others=True):
        def get(url, **kw):
            self.urls.append(url)
            return common.Http(200, headers, self.payload)
        common.http_get = get
        pool = odds.Pool(odds.load_keys(), common.parse_iso("2026-10-11T13:02:00-04:00"))
        pool.state[0]["left"] = 100
        client = odds.Client(pool, helpers.cfg())
        js, cost = client.event_odds("ev1", "CAR", "PHI", ["player_shots_on_goal"], world.SLATE, "A", CAR_PHI,
                                     others=others)
        return pool, js, cost

    def test_one_read_asks_ten_books_and_the_ledger_takes_the_feed_header(self):
        pool, js, cost = self.read({"x-requests-remaining": "99", "x-requests-last": "1"})
        q = self.urls[0].split("?", 1)[1]
        books = dict(p.split("=", 1) for p in q.split("&"))["bookmakers"].split("%2C")
        self.assertEqual(books, ["hardrockbet"] + OTHERS9)
        self.assertEqual(cost, 1)
        self.assertEqual(pool.spent[-1]["cost"], 1)
        self.assertEqual(pool.state[0]["left"], 99)
        self.assertEqual(len(js["bookmakers"]), 10)

    def test_without_the_header_the_estimate_is_one_credit_per_market(self):
        pool, js, cost = self.read({})
        self.assertEqual(cost, 1)
        self.assertEqual(pool.spent[-1]["cost"], 1)
        self.assertEqual(pool.state[0]["left"], 99)

    def test_header_wins_over_the_estimate(self):
        pool, js, cost = self.read({"x-requests-remaining": "97", "x-requests-last": "3"})
        self.assertEqual((cost, pool.spent[-1]["cost"], pool.state[0]["left"]), (3, 3, 97))

    def test_hard_rock_only_read(self):
        self.read({"x-requests-last": "1"}, others=False)
        self.assertIn("bookmakers=hardrockbet&", self.urls[0])


class Normalize(unittest.TestCase):
    def setUp(self):
        self.cfg = helpers.cfg()
        self.hr = helpers.load(os.path.join(FIX, "odds_car_phi.json"))
        self.keys = ["player_shots_on_goal", "player_points", "player_goals", "player_total_saves"]
        self.at = common.parse_iso("2026-10-11T18:26:00-04:00")
        self.game = {"id": 2026020086, "away": "CAR", "home": "PHI"}

    def multi(self):
        js = json.loads(json.dumps(self.hr))
        hr = js["bookmakers"][0]
        dk = json.loads(json.dumps(hr))
        dk["key"] = "draftkings"
        for m in dk["markets"]:
            for o in m["outcomes"]:
                o["price"] += 5
        next(m for m in dk["markets"] if m["key"] == "player_shots_on_goal")["outcomes"].append(
            {"name": "Over", "description": "Nobody Known", "price": 100, "point": 1.5})
        pin = {"key": "pinnacle", "markets": [m for m in json.loads(json.dumps(hr["markets"]))
                                              if m["key"] == "player_shots_on_goal"]}
        js["bookmakers"] = [dk, hr, pin]                              # Hard Rock need not come first
        return js

    def test_hard_rock_part_is_identical_and_others_are_matched(self):
        m = real_matcher()
        alone = odds.normalize(self.hr, self.game, m, self.keys, "A", self.at, 4, self.cfg)
        both = odds.normalize(self.multi(), self.game, m, self.keys, "A", self.at, 4, self.cfg, others=True)
        self.assertNotIn("others", alone)
        self.assertEqual({k: v for k, v in both.items() if k != "others"}, alone)
        self.assertEqual(sorted(both["others"]), ["draftkings", "pinnacle"])
        self.assertEqual(sorted(both["others"]["pinnacle"]), ["shots"])
        dk = both["others"]["draftkings"]["shots"]
        hr = alone["markets"]["shots"]
        self.assertEqual(dk["last_update"], hr["last_update"])
        hr_rows = {(o["pid"], o["side"], o["line"]): o["price"] for o in hr["outcomes"]}
        for o in dk["outcomes"]:
            if o["pid"] is not None:
                self.assertEqual(o["price"], hr_rows[(o["pid"], o["side"], o["line"])] + 5)
                self.assertIn(o["team"], ("CAR", "PHI"))
        self.assertIn("Nobody Known", [o["name"] for o in dk["outcomes"] if o["pid"] is None])
        self.assertNotIn("Nobody Known", both["unmatched"])           # Hard Rock's unmatched list stays Hard Rock's

    def test_others_asked_but_none_answered(self):
        f = odds.normalize(self.hr, self.game, real_matcher(), self.keys, "A", self.at, 4, self.cfg, others=True)
        self.assertEqual(f["others"], {})

    def test_hard_rock_missing_from_the_answer(self):
        js = self.multi()
        js["bookmakers"] = [b for b in js["bookmakers"] if b["key"] != "hardrockbet"]
        f = odds.normalize(js, self.game, real_matcher(), self.keys, "A", self.at, 4, self.cfg, others=True)
        self.assertIsNone(f["book"])
        self.assertEqual(f["markets"], {})
        self.assertEqual(sorted(f["others"]), ["draftkings", "pinnacle"])
        self.assertEqual(odds.build_view({"fetches": [f]}, self.cfg), {2026020086: {}})


class Retry(unittest.TestCase):
    def test_hr_missing_last(self):
        t = lambda hh: common.parse_iso("2026-10-11T%s:00-04:00" % hh)
        done = [{"at": t("13:02"), "markets": ["shots"], "returned": []}]
        self.assertTrue(odds.hr_missing_last(done, ["shots"]))
        self.assertFalse(odds.hr_missing_last(done, ["saves"]))
        self.assertFalse(odds.hr_missing_last([], ["shots"]))
        done.append({"at": t("13:32"), "markets": ["shots"], "returned": ["shots"]})
        self.assertFalse(odds.hr_missing_last(done, ["shots"]))        # Hard Rock answered: others again
        done.append({"at": t("17:31"), "markets": ["shots", "saves"], "returned": ["shots"]})
        self.assertTrue(odds.hr_missing_last(done, ["saves"]))
        self.assertFalse(odds.hr_missing_last(done, ["shots"]))        # C (shots) still asks other books

    def test_market_hard_rock_has_not_posted_is_paid_once_then_asked_hard_rock_only(self):
        s = Sim(pool=12)
        try:
            s.at("09:00")
            dk = [("player_shots_on_goal", world.name_of("VAN", 1), 2.5, -120, -110)]
            path = os.path.join(s.w["odds"], "odds_van_nyr.json")
            world.write(path, world.odds_payload("VAN", "NYR", [], UPD, others={"draftkings": dk}))
            s.at("13:02")                                     # Hard Rock: nothing; DraftKings: shots -> billed 1
            s.at("13:32")                                     # retry: Hard Rock only, free
            s.set_odds("VAN", "NYR", [s.line("VAN", 1, "shots", 2.5, 0.0)], UPD, others={"draftkings": dk})
            s.at("14:02")                                     # Hard Rock posts: read Hard Rock only (1 credit)
            doc = common.read_json(s.path("odds", "2026-10-11.json"))
            van = [f for f in doc["fetches"] if f["game_id"] == VAN_NYR]
            self.assertEqual([(f["at"][11:16], f["cost"], "others" in f, sorted(f["markets"])) for f in van],
                             [("13:02", 1, True, []), ("13:32", 0, False, []), ("14:02", 1, False, ["shots"])])
            self.assertEqual(sorted(van[0]["others"]), ["draftkings"])
            led = common.read_json(s.path("state", "credits.json"))
            self.assertEqual(sum(e["cost"] for e in led["spent"] if e["game_id"] == VAN_NYR), 2)
            s.set_lineup("VAN", "2026-10-11T19:00:00-04:00")
            s.set_lineup("NYR", "2026-10-11T19:00:00-04:00")
            s.at("18:35")                                     # B (90 min before 8 PM): other books asked again
            doc = common.read_json(s.path("odds", "2026-10-11.json"))
            last = [f for f in doc["fetches"] if f["game_id"] == VAN_NYR][-1]
            self.assertEqual((last["pull"], sorted(last["others"])), ("B", ["draftkings"]))
        finally:
            s.close()

    def test_saves_only_at_other_books_is_not_paid_again_and_again(self):
        s = Sim(pool=20)                                      # tier 3: B is shots + saves
        try:
            s.at("09:00")
            hr = [s.line("CAR", 1, "shots", 2.5, 0.0)]
            oth = {"draftkings": hr + [("player_total_saves", "Goalie CAR", 25.5, -115, -105)]}
            s.set_odds("CAR", "PHI", hr, UPD, others=oth)
            s.at("13:02")
            s.set_lineup("CAR", "2026-10-11T17:00:00-04:00")
            s.set_lineup("PHI", "2026-10-11T17:00:00-04:00")
            s.at("17:31")                                     # B: Hard Rock shots, DraftKings shots + saves -> 2
            s.at("18:01")                                     # retry saves: Hard Rock only -> free
            s.at("18:15")                                     # C (shots): other books again -> 1
            doc = common.read_json(s.path("odds", "2026-10-11.json"))
            got = [(f["pull"], f["requested"], f["cost"], "others" in f) for f in doc["fetches"]
                   if f["game_id"] == CAR_PHI]
            self.assertEqual(got, [("A", ["shots"], 1, True), ("B", ["saves", "shots"], 2, True),
                                   ("B", ["saves"], 0, False), ("C", ["shots"], 1, True)])
        finally:
            s.close()


class HardRockUnchanged(unittest.TestCase):
    """The same Hard Rock data with and without other books: every file the picks, page and Record use is
    byte-for-byte the same. Only data/odds (an extra "others" key per read), the odds stage file and the shadow
    log (consensus fields) may differ."""

    def strip(self, raw):
        doc = json.loads(raw)
        for f in doc.get("fetches", []) + ((doc.get("stage") or {}).get("fetches", [])):
            f.pop("others", None)
        return doc

    def day(self, with_others):
        """One whole made-up day (pull A, lineups, B, C, lock, grade). Returns (data tree, graded events)."""
        s = Sim(pool=20)
        try:
            def set_odds(game, lines, upd):
                away, home = game
                oth = None
                if with_others:
                    oth = {bk: shifted(lines, 5 + i) for i, bk in enumerate(OTHERS9)}
                    oth["draftkings"] = oth["draftkings"] + [
                        ("player_shots_on_goal", world.name_of(away, 9), 1.5, -150, 120),
                        ("player_shots_on_goal", "Not A Player", 2.5, -110, -110)]
                    # (a market only another book has is billed: see Retry, it is not "the same Hard Rock data")
                s.set_odds(away, home, lines, upd, others=oth)

            s.at("09:00")
            lines = {("CAR", "PHI"): [s.line("CAR", 1, "shots", 2.5, 0.14), s.line("PHI", 1, "shots", 2.5, 0.14),
                                      s.line("PHI", 2, "shots", 1.5, 0.05, "under")],
                     ("VAN", "NYR"): [s.line("VAN", 1, "shots", 2.5, 0.14), s.line("NYR", 1, "shots", 2.5, 0.14)]}
            for g, ls in lines.items():
                set_odds(g, ls, UPD)
            sl = s.at("13:02")
            self.assertTrue(sl["picks"], "the test needs picks on the page")
            s.set_lineup("CAR", "2026-10-11T17:00:00-04:00")
            s.set_lineup("PHI", "2026-10-11T17:00:00-04:00")
            price = next(p["price"] for p in sl["picks"] if p["team"] == "CAR")
            set_odds(("CAR", "PHI"), [("player_shots_on_goal", world.name_of("CAR", 1), 2.5, price - 10, 102)]
                     + lines[("CAR", "PHI")][1:], "2026-10-11T21:30:00Z")
            set_odds(("VAN", "NYR"), lines[("VAN", "NYR")], "2026-10-11T22:30:00Z")   # fresh feed stamps for B/C
            for hh in ("17:31", "18:01", "18:15", "18:35", "19:05", "19:15", "20:00"):
                s.at(hh)
            car, phi, van, nyr = (world.pid_of(t, 1) for t in ("CAR", "PHI", "VAN", "NYR"))
            s.set_box(CAR_PHI, "CAR", "PHI", {car: (4, 0, 0), phi: (1, 0, 0)})
            s.set_box(VAN_NYR, "VAN", "NYR", {nyr: (5, 0, 0), van: (2, 0, 0)})
            s.set_states({CAR_PHI: "OFF", VAN_NYR: "OFF"})
            s.at("23:10")
            return s.tree(), [e for e in s.events() if e["t"] == "graded"]
        finally:
            s.close()

    def test_full_day_byte_for_byte(self):
        ta, ga = self.day(False)
        tb, gb = self.day(True)
        self.assertTrue(ga, "the test needs graded picks")
        self.assertEqual(sorted(ta), sorted(tb))
        differ = []
        for k in sorted(ta):
            if k.startswith("shadow/"):
                continue
            if k in ("odds/2026-10-11.json", "state/odds_day.json"):
                self.assertEqual(self.strip(ta[k]), self.strip(tb[k]), k)
                differ += [k] if ta[k] != tb[k] else []
                continue
            self.assertEqual(ta[k], tb[k], k)
        self.assertIn("odds/2026-10-11.json", differ)                  # the other books really were there
        ob = json.loads(tb["odds/2026-10-11.json"])
        got = [(f["pull"], f["requested"], len(f.get("others", ())) if "others" in f else None) for f in ob["fetches"]]
        # every read asks the 9 other books, except a retry of saves (which Hard Rock has not posted) asks Hard Rock only
        self.assertTrue(all(n == 9 for _, req, n in got if req != ["saves"]), got)
        self.assertTrue(all(n is None for _, req, n in got if req == ["saves"]), got)
        rows = json.loads(tb["shadow/2026-10-11.json"])["rows"]
        shots = [r for r in rows if r["market"] == "shots"]
        self.assertTrue(shots)
        self.assertEqual([(r["name"], r["line"], r["close"]["cons_books"]) for r in shots
                          if r["close"]["cons_books"] != 9 and r["line"] != 0.5],
                         [], "every Hard Rock shots line has all 9 other books in its consensus")


class ShadowConsensus(unittest.TestCase):
    def setUp(self):
        self.s = Sim(pool=12)
        self.s.at("09:00")
        self.inp = self.s.inputs()
        self.games = list(self.inp.games.values())
        self.pid = world.pid_of("CAR", 1)

    def tearDown(self):
        self.s.close()

    def rows(self, pid, line, over, under):
        return [{"name": "X", "pid": pid, "team": "CAR", "side": "over", "line": line, "price": over},
                {"name": "X", "pid": pid, "team": "CAR", "side": "under", "line": line, "price": under}]

    def fetch(self, at, hr, others=None, market="shots"):
        f = {"game_id": CAR_PHI, "away": "CAR", "home": "PHI", "pull": "B", "at": at, "book": "hardrockbet",
             "requested": [market], "markets": {market: {"last_update": at, "outcomes": self.rows(self.pid, 2.5, *hr)}}}
        if others is not None:
            f["others"] = {}
            for bk, (o, u, lu) in others.items():
                outs = self.rows(self.pid, 2.5, o, u) if u is not None else self.rows(self.pid, 2.5, o, 0)[:1]
                f["others"][bk] = {market: {"last_update": lu or at, "outcomes": outs}}
        return f

    def add(self, fetches, now="2026-10-11T18:50:00-04:00"):
        doc = {"date": world.SLATE, "rows": []}
        for f in fetches:
            shadow.add_reads(doc, self.inp, {"fetches": [f]}, self.games, {}, common.parse_iso(now))
        return doc

    def test_consensus_fields(self):
        at = "2026-10-11T17:30:00-04:00"
        oth = {"draftkings": (-130, 100, None), "fanduel": (-125, -105, None), "pinnacle": (-120, 100, None),
               "betmgm": (140, None, None),                                    # one side only: best price, no fair
               "espnbet": (200, -300, "2026-10-11T15:00:00-04:00"),             # stale book: left out
               "betrivers": (-500, -500, None)}                                 # absurd hold: no fair
        r = self.add([self.fetch(at, (-120, -110), oth)])["rows"][0]
        o = r["open"]
        fairs = sorted([odds.fair_two_sided(-130, 100), odds.fair_two_sided(-125, -105), odds.fair_two_sided(-120, 100)])
        self.assertEqual(o["cons_books"], 3)
        self.assertAlmostEqual(o["cons_fair_over_med"], fairs[1], places=5)
        self.assertAlmostEqual(o["cons_fair_over_mean"], sum(fairs) / 3, places=5)
        self.assertAlmostEqual(o["pin_fair_over"], odds.fair_two_sided(-120, 100), places=5)
        self.assertAlmostEqual(o["hr_vs_consensus"], odds.fair_two_sided(-120, -110) - fairs[1], places=4)
        self.assertEqual((o["best_over"], o["best_over_book"]), (140, "betmgm"))
        self.assertEqual((o["best_under"], o["best_under_book"]), (100, "draftkings"))
        self.assertEqual((o["cons_move"], o["stale"], r["stale_events"]), (None, None, []))
        self.assertEqual(o["cons_stale_books"], 1)

    def test_not_asked_is_none_and_asked_with_no_book_is_zero(self):
        o = self.add([self.fetch("2026-10-11T17:30:00-04:00", (-120, -110))])["rows"][0]["open"]
        for k in ("cons_books", "cons_fair_over_med", "cons_fair_over_mean", "pin_fair_over", "hr_vs_consensus",
                  "best_over", "best_under", "stale"):
            self.assertIsNone(o[k], k)
        o = self.add([self.fetch("2026-10-11T17:30:00-04:00", (-120, -110), {})])["rows"][0]["open"]
        self.assertEqual(o["cons_books"], 0)
        self.assertIsNone(o["cons_fair_over_med"])

    def test_stale_flag(self):
        t1, t2, t3, t4 = ("2026-10-11T%s:00-04:00" % h for h in ("13:02", "17:31", "18:15", "18:40"))
        doc = {"date": world.SLATE, "rows": []}
        now = common.parse_iso("2026-10-11T18:50:00-04:00")
        reads = [self.fetch(t1, (-120, -110), {"draftkings": (-120, -110, None), "fanduel": (-118, -112, None)}),
                 # Hard Rock unchanged, consensus over moves up ~0.06: stale
                 self.fetch(t2, (-120, -110), {"draftkings": (-150, 120, None), "fanduel": (-145, 115, None)}),
                 # Hard Rock moves: not stale even though the consensus moved again
                 self.fetch(t3, (-150, 115), {"draftkings": (-110, -120, None), "fanduel": (-112, -118, None)}),
                 # Hard Rock-only read: unknown
                 self.fetch(t4, (-150, 115))]
        flags = []
        for f in reads:
            shadow.add_reads(doc, self.inp, {"fetches": [f]}, self.games, {}, now)
            flags.append(doc["rows"][0]["close"]["stale"])
        self.assertEqual(flags, [None, True, False, None])
        r = doc["rows"][0]
        self.assertEqual(r["n_reads"], 4)
        self.assertEqual(len(r["stale_events"]), 1)
        ev = r["stale_events"][0]
        self.assertEqual((ev["at"], ev["from_at"], ev["over"], ev["under"]), (t2, t1, -120, -110))
        self.assertGreaterEqual(ev["cons_to"] - ev["cons_from"], shadow.STALE_MOVE)
        self.assertEqual(r["open"]["at"], t1)                          # open never changes

    def test_small_consensus_move_is_not_stale(self):
        t1, t2 = "2026-10-11T13:02:00-04:00", "2026-10-11T17:31:00-04:00"
        doc = self.add([self.fetch(t1, (-120, -110), {"draftkings": (-120, -110, None)}),
                        self.fetch(t2, (-120, -110), {"draftkings": (-130, 100, None)})])
        c = doc["rows"][0]["close"]
        self.assertLess(abs(c["cons_move"]), shadow.STALE_MOVE)
        self.assertFalse(c["stale"])

    def test_ten_books_of_lines_stays_fast_and_inside_the_time_budget(self):
        """A full read: 2 games x 36 players x 2 lines x 10 books, 5 reads a game."""
        fetches = []
        for gid, away, home in ((CAR_PHI, "CAR", "PHI"), (VAN_NYR, "VAN", "NYR")):
            for n, hh in enumerate(("13:02", "16:00", "17:31", "18:15", "18:40")):
                at = "2026-10-11T%s:00-04:00" % hh
                outs = []
                for t in (away, home):
                    for i in range(18):
                        for line in (1.5, 2.5):
                            outs += [{"name": world.name_of(t, i), "pid": world.pid_of(t, i), "team": t, "side": sd,
                                      "line": line, "price": pr} for sd, pr in (("over", -120 + n), ("under", -110 - n))]
                f = {"game_id": gid, "away": away, "home": home, "pull": "B", "at": at, "book": "hardrockbet",
                     "requested": ["shots"], "markets": {"shots": {"last_update": at, "outcomes": outs}},
                     "others": {bk: {"shots": {"last_update": at, "outcomes": outs}} for bk in OTHERS9}}
                fetches.append(f)
        doc = {"date": world.SLATE, "rows": []}
        t0 = time.monotonic()
        shadow.add_reads(doc, self.inp, {"fetches": fetches}, self.games, {},
                         common.parse_iso("2026-10-11T18:50:00-04:00"), deadline=time.monotonic() + shadow.BUDGET_S)
        took = time.monotonic() - t0
        self.assertEqual(len(doc["rows"]), 144)
        self.assertTrue(all(r["close"]["cons_books"] == 9 for r in doc["rows"]))
        self.assertLess(took, 20, "consensus must not blow the shadow step's 60 s budget")
        doc2 = {"date": world.SLATE, "rows": []}                     # out of time: stops cleanly
        self.assertEqual(shadow.add_reads(doc2, self.inp, {"fetches": fetches}, self.games, {},
                                          common.parse_iso("2026-10-11T18:50:00-04:00"),
                                          deadline=time.monotonic() - 1), 0)


if __name__ == "__main__":
    unittest.main()
