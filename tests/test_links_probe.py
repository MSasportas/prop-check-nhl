"""2026-10-25: Hard Rock bet-slip links (feed includeLinks) and the one-time all-books probe (TEAM.md item 24)."""
import gzip
import json
import os
import unittest

import helpers
from helpers import Sim
import common
import notify
import odds
import shadow
import book_probe
import world


def outcome(who, side, price, point, link=None):
    o = {"name": side, "description": who, "price": price, "point": point}
    if link is not None:
        o["link"] = link
    return o


class Links(unittest.TestCase):
    def test_only_good_https_links_are_kept_and_only_on_request(self):
        m = {"outcomes": [outcome("A B", "Over", -120, 1.5, "https://hardrock.example/slip/1"),
                          outcome("A B", "Under", 100, 1.5, "http://insecure.example/x"),
                          outcome("C D", "Over", 110, 2.5, "javascript:alert(1)"),
                          outcome("C D", "Under", -130, 2.5, "https://x.example/" + "a" * 700)]}
        find = lambda who: {"id": 1, "team": "CAR"}
        rows = odds._outcome_rows(m, find, [], links=True)
        self.assertEqual([r.get("link") for r in rows], ["https://hardrock.example/slip/1", None, None, None])
        self.assertTrue(all("link" not in r for r in odds._outcome_rows(m, find, [], links=False)))

    def test_hostile_links_are_refused(self):
        for bad in ("https://a>\n@everyone", "https://x.example/a b", "https://", "javascript:alert(1)", "http://x.example/a",
                    'https://x.example/"onmouseover="x', "https://x.example/\u202eevil", "https://x.example/" + "a" * 700):
            self.assertIsNone(odds.safe_link(bad), bad)
        self.assertEqual(odds.safe_link("https://hardrock.example/slip?a=1&b=2"), "https://hardrock.example/slip?a=1&b=2")

    def test_links_are_asked_on_b_and_c_not_a(self):
        self.assertEqual([odds.wants_links(x) for x in ("A", "B", "C", "M")], [False, True, True, False])

    def test_pairs_carry_the_link_per_side(self):
        mk = {"outcomes": [{"pid": 1, "line": 1.5, "side": "over", "price": -120, "name": "A", "team": "X", "link": "https://h/o"},
                           {"pid": 1, "line": 1.5, "side": "under", "price": 100, "name": "A", "team": "X"}]}
        p = shadow.pairs_of(mk)[(1, 1.5)]
        self.assertEqual(p["links"], {"over": "https://h/o"})

    def test_discord_block_has_the_slip_link_and_the_page_gets_it(self):
        base = {"player": "P. X", "side": "over", "line": 1.5, "market": "shots", "price": -110, "team": "CAR", "opp": "PHI",
                "home": False, "start": "2026-10-25T19:00:00-04:00", "p_pct": 55, "breakeven_pct": 52, "gap_pct": 4.0, "state": "early"}
        self.assertNotIn("Bet slip", notify.pick_line(dict(base, link="https://hardrock.example/slip/1")))   # feature removed 2026-10-26
        self.assertNotIn("Bet slip", notify.pick_line(base))
        self.assertNotIn("Bet slip", notify.pick_line(dict(base, link="http://nope")))


class _FakePool:
    fixture = None


class LinkFallback(unittest.TestCase):
    def client(self, answers):
        cfg = helpers.cfg()
        cfg["ops"]["odds_links"] = True                      # the option still works; production has it off since 2026-10-26
        c = odds.Client(_FakePool(), cfg)
        calls = []

        def fake_get(path, params, need, slate=None, pull=None, game_id=None, flat_cost=None):
            calls.append(dict(params))
            return answers.pop(0)
        c._get = fake_get
        return c, calls

    def test_an_empty_or_failed_read_with_links_is_asked_again_without_them(self):
        for first in (({}, 0), (None, 0)):
            c, calls = self.client([first, ({"bookmakers": []}, 3)])
            js, cost = c.event_odds("e1", "CAR", "PHI", ["player_shots_on_goal"], "2026-10-25", "B", 1)
            self.assertEqual((js, cost), ({"bookmakers": []}, 3))
            self.assertEqual(["includeLinks" in x for x in calls], [True, False])

    def test_a_good_read_with_links_is_one_call_and_the_1pm_read_never_asks(self):
        c, calls = self.client([({"bookmakers": [1]}, 3)])
        c.event_odds("e1", "CAR", "PHI", ["player_shots_on_goal"], "2026-10-25", "B", 1)
        self.assertEqual(len(calls), 1)
        c, calls = self.client([({"bookmakers": [1]}, 3)])
        c.event_odds("e1", "CAR", "PHI", ["player_shots_on_goal"], "2026-10-25", "A", 1)
        self.assertNotIn("includeLinks", calls[0])

    def test_an_unreadable_200_is_not_asked_twice(self):
        c, calls = self.client([(None, 0)])
        c.errors.append("odds feed sent an unreadable answer")
        c.event_odds("e1", "CAR", "PHI", ["player_shots_on_goal"], "2026-10-25", "B", 1)
        self.assertEqual(len(calls), 1)


class LinkEndToEnd(unittest.TestCase):
    def test_a_link_in_the_hard_rock_read_reaches_the_pick_and_the_record(self):
        s = Sim(pool=12)
        try:
            s.at("09:00")
            s.read("13:02")
            s.clock("17:00")
            hr, oth = s.gg_lines("CAR", 1)
            upd = "2026-10-11T21:30:00Z"
            others = {bk: [line] for bk, line in oth.items()}
            s.set_odds("CAR", "PHI", [hr], upd, others=others)
            f = os.path.join(s.w["odds"], "odds_car_phi.json")
            js = json.load(open(f))
            for b in js["bookmakers"]:
                for m in b["markets"]:
                    for o in m["outcomes"]:
                        o["link"] = "https://hardrock.example/slip/%s/%s" % (b["key"], o["name"].lower())
            json.dump(js, open(f, "w"))
            sl = s.at("17:31")
            pick = s.pick("CAR", 1, sl)
            self.assertEqual(pick["link"], "https://hardrock.example/slip/hardrockbet/over")      # Hard Rock's, the picked side
            self.assertEqual(s.events()[0]["pick"]["link"], pick["link"])                          # frozen in the Record
            doc = json.load(open(s.path("odds", "%s.json" % world.SLATE)))
            for ft in doc["fetches"]:
                for b, mk in (ft.get("others") or {}).items():
                    for m in mk.values():
                        self.assertTrue(all("link" not in o for o in m["outcomes"]), "other books' links are never stored")
        finally:
            s.close()

    def test_no_link_from_the_feed_means_no_link_on_the_pick(self):
        s = Sim(pool=12)
        try:
            s.at("09:00")
            s.read("13:02")
            s.clock("17:00")
            sl = s.read("17:31", cp=[s.gg_lines("CAR", 1)])
            self.assertIsNone(s.pick("CAR", 1, sl)["link"])
        finally:
            s.close()


def payload_with(books):
    """books: {key: {(player, point): (over, under)}} -> a feed answer."""
    out = []
    for k, prs in books.items():
        outs = []
        for (who, pt), (o, u) in prs.items():
            outs += [outcome(who, "Over", o, pt), outcome(who, "Under", u, pt)]
        out.append({"key": k, "title": k.title(), "last_update": "2026-10-25T20:30:00Z",
                    "markets": [{"key": "player_shots_on_goal", "last_update": "2026-10-25T20:30:00Z", "outcomes": outs}]})
    return {"id": "e1", "bookmakers": out}


class Probe(unittest.TestCase):
    def test_summary_ranks_by_gap_to_pinnacle_and_hold(self):
        pl = [("Ann A", 1.5), ("Bo B", 2.5), ("Cy C", 3.5)]
        books = {"pinnacle": {p: (-120, 100) for p in pl},
                 "sharp": {p: (-122, 102) for p in pl},
                 "soft": {p: (-160, 130) for p in pl},
                 "oneway": {("Ann A", 1.5): (-110, None)}}
        rows = book_probe.summarize(book_probe.collect(payload_with(books)), common.parse_iso("2026-10-25T20:40:00-04:00"))
        self.assertNotIn("oneway", rows)                                      # no two-sided pair, no row
        self.assertEqual(rows["pinnacle"]["gap_abs"], 0.0)
        self.assertEqual(rows["pinnacle"]["by_line"], {"1.5": 1, "2.5": 1, "3.5": 1})
        self.assertLess(rows["sharp"]["gap_abs"], rows["soft"]["gap_abs"])
        self.assertLess(rows["sharp"]["hold_mean"], rows["soft"]["hold_mean"])
        self.assertEqual(rows["soft"]["shared_with_pinnacle"], 3)

    def test_probe_runs_once_costs_the_regions_and_writes_the_files(self):
        s = Sim(pool=60)
        try:
            pl = [("Ann A", 1.5), ("Bo B", 2.5)]
            world.write(os.path.join(s.w["odds"], "books_all.json"),
                        payload_with({"pinnacle": {p: (-120, 100) for p in pl}, "lowvig": {p: (-118, 98) for p in pl}}))
            s.at("09:00")
            s.at("13:02")
            self.assertIsNone(common.read_json(s.path("state", "book_probe.json", )) if os.path.exists(s.path("state", "book_probe.json")) else None,
                              "no game 35-120 minutes from puck yet")
            s.at("17:40")                                                    # CAR@PHI is 80 minutes away
            st = common.read_json(s.path("state", "book_probe.json"))
            self.assertEqual((st["done"]["cost"], sorted(st["books"])), (5, ["lowvig", "pinnacle"]))
            pairs = json.loads(gzip.decompress(open(s.path("state", "book_probe_pairs.json.gz"), "rb").read()))
            self.assertEqual(len(pairs), 4)
            led = common.read_json(s.path("state", "credits.json"))
            self.assertEqual([e["cost"] for e in led["spent"] if e["pull"] == "P"], [5])
            s.at("17:55")
            self.assertEqual(len([e for e in common.read_json(s.path("state", "credits.json"))["spent"] if e["pull"] == "P"]), 1, "once")
        finally:
            s.close()

    def test_no_fixture_no_spend_and_never_in_a_dry_run(self):
        s = Sim(pool=60)
        try:
            s.at("09:00")
            s.at("17:40")
            self.assertFalse(os.path.exists(s.path("state", "book_probe.json")))
            games = list(s.inputs().games.values())
            res = book_probe.check(common.parse_iso("2026-10-11T17:40:00-04:00"), world.SLATE, games, {}, helpers.cfg(), dry_run=True)
            self.assertEqual(res["note"], "dry run")
        finally:
            s.close()


if __name__ == "__main__":
    unittest.main()
