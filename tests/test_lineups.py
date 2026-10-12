"""Daily Faceoff line pages: parsing the saved real page, the "dated today" rule, in / out / not sure."""
import json
import os
import unittest

import helpers
from helpers import FIX
import common
import lineups
import nhl
import teams
import world


def phi_people():
    old = os.environ.get("PC_NHL_FIXTURE_DIR")
    os.environ["PC_NHL_FIXTURE_DIR"] = FIX
    try:
        return nhl.roster("PHI")
    finally:
        if old is None:
            os.environ.pop("PC_NHL_FIXTURE_DIR", None)
        else:
            os.environ["PC_NHL_FIXTURE_DIR"] = old


class RealPage(unittest.TestCase):
    def setUp(self):
        self.props = helpers.load(os.path.join(FIX, "df_lines_sample.json"))     # Flyers page saved 2026-10-11
        self.people = phi_people()
        self.id = {("%s %s" % (p["first"], p["last"])): p["id"] for p in self.people}

    def test_parse(self):
        page = lineups.parse_page(self.props, self.people, "2026-10-10")
        self.assertEqual((page["page_date"], page["today"]), ("2026-10-10", True))   # updated 12:40 PM ET on the 10th
        self.assertEqual(page["unmatched"], [])
        self.assertTrue(page["complete"])
        self.assertIn(self.id["Trevor Zegras"], page["in"])
        self.assertIn(self.id["Travis Sanheim"], page["in"])
        self.assertIn(self.id["Travis Konecny"], page["out"])          # listed only under injuries (day-to-day)
        self.assertNotIn(self.id["Travis Konecny"], page["in"])

    def test_a_page_from_yesterday_does_not_count(self):
        page = lineups.parse_page(self.props, self.people, "2026-10-11")
        self.assertFalse(page["today"])
        st = {"teams": {"PHI": {"page": page}}}
        self.assertEqual(lineups.player_status(st, "PHI", self.id["Trevor Zegras"]), "unknown")
        self.assertEqual(lineups.player_status(st, "PHI", self.id["Travis Konecny"]), "unknown")

    def test_status_from_a_page_dated_today(self):
        page = lineups.parse_page(self.props, self.people, "2026-10-10")
        st = {"teams": {"PHI": {"page": page}}}
        self.assertEqual(lineups.player_status(st, "PHI", self.id["Trevor Zegras"]), "in")
        self.assertEqual(lineups.player_status(st, "PHI", self.id["Travis Konecny"]), "out")
        self.assertEqual(lineups.player_status(st, "PHI", 123456), "out")          # listed nowhere on a complete page
        self.assertEqual(lineups.player_status(st, "CAR", 123456), "unknown")      # no page for that team
        self.assertEqual(lineups.player_status({}, "PHI", 1), "unknown")

    def test_unreadable_name_means_not_listed_is_no_longer_trusted(self):
        people = [p for p in self.people if p["last"] != "Zegras"]     # pretend the NHL roster lacks one listed player
        page = lineups.parse_page(self.props, people, "2026-10-10")
        self.assertEqual(page["unmatched"], ["Trevor Zegras"])
        self.assertFalse(page["complete"])
        st = {"teams": {"PHI": {"page": page}}}
        self.assertEqual(lineups.player_status(st, "PHI", self.id["Trevor Zegras"]), "unknown")   # not "out"
        self.assertEqual(lineups.player_status(st, "PHI", self.id["Travis Konecny"]), "out")       # explicit injury list

    def test_game_time_decision_is_not_confirmed(self):
        props = json.loads(json.dumps(self.props))
        for p in props["combinations"]["players"]:
            if p["name"] == "Owen Tippett":
                p["gameTimeDecision"] = True
        page = lineups.parse_page(props, self.people, "2026-10-10")
        self.assertIn(self.id["Owen Tippett"], page["unsure"])
        self.assertNotIn(self.id["Owen Tippett"], page["in"])
        self.assertEqual(lineups.player_status({"teams": {"PHI": {"page": page}}}, "PHI", self.id["Owen Tippett"]), "unknown")

    def test_broken_pages_are_rejected(self):
        self.assertIsNone(lineups.parse_page({}, self.people, "2026-10-10"))
        self.assertIsNone(lineups.parse_page({"combinations": {"updatedAt": "nonsense", "players": []}}, self.people, "2026-10-10"))
        short = json.loads(json.dumps(self.props))
        short["combinations"]["players"] = short["combinations"]["players"][:6]     # not a full lineup
        self.assertIsNone(lineups.parse_page(short, self.people, "2026-10-10"))

    def test_next_data_from_html(self):
        html = '<html><script id="__NEXT_DATA__" type="application/json">%s</script></html>' % json.dumps(
            {"props": {"pageProps": self.props}})
        self.assertEqual(lineups.next_data(html)["combinations"]["teamAbbreviation"], "PHI")
        self.assertIsNone(lineups.next_data("<html>blocked</html>"))
        self.assertIsNone(lineups.next_data('<script id="__NEXT_DATA__">{broken</script>'))


class Slugs(unittest.TestCase):
    def test_all_32_teams(self):
        self.assertEqual(len(teams.TEAMS), 32)
        slugs = [teams.df_slug(t) for t in teams.TEAMS]
        self.assertEqual(len(set(slugs)), 32)
        listed = {t["slug"] for t in helpers.load(os.path.join(FIX, "df_lines_sample.json"))["sortedTeams"]}
        self.assertEqual(set(slugs), listed, "slugs must match the list Daily Faceoff itself publishes")
        self.assertEqual(teams.abbrev_for("Montréal Canadiens"), "MTL")
        self.assertEqual(teams.abbrev_for("St Louis Blues"), "STL")
        self.assertEqual(teams.abbrev_for("Utah Mammoth"), "UTA")
        self.assertIsNone(teams.abbrev_for("Quebec Nordiques"))


class Degrade(unittest.TestCase):
    def test_source_down_is_stated_and_nothing_breaks(self):
        s = helpers.Sim(pool=12)
        try:
            s.at("09:00")
            s.set_odds("CAR", "PHI", [s.line("CAR", 1, "shots", 2.5, 0.14)], "2026-10-11T17:00:00Z")
            s.at("13:02")
            sl = s.at("16:30")                                          # no page files at all: every fetch fails
            self.assertIsNone(sl["status"]["lineups_at"])
            self.assertEqual(sl["status"]["lineups_note"], "Lineups not checked: Daily Faceoff did not answer.")
            self.assertEqual([p["state"] for p in sl["picks"]], ["early"])
            st = s.status()
            self.assertTrue(st["ok"])
            self.assertEqual(st["sources"]["dailyfaceoff"], "failed")
            self.assertEqual([x for x in st["steps"] if x["step"] == "lineups"][0]["note"],
                             "Daily Faceoff did not answer: lineups not checked")
        finally:
            s.close()

    def test_a_later_failure_keeps_the_last_good_page(self):
        s = helpers.Sim(pool=12)
        try:
            s.at("09:00")
            s.set_odds("CAR", "PHI", [s.line("CAR", 1, "shots", 2.5, 0.14)], "2026-10-11T17:00:00Z")
            s.at("13:02")
            s.set_lineup("CAR", "2026-10-11T20:00:00Z")
            sl = s.at("16:30")
            self.assertEqual(sl["picks"][0]["state"], "lineup")
            os.unlink(os.path.join(s.w["lineups"], "carolina-hurricanes.json"))
            sl = s.at("17:00")
            self.assertEqual(sl["picks"][0]["state"], "lineup")
            self.assertEqual([h["text"] for h in sl["picks"][0]["history"]],
                             ["Early: lineup not confirmed", "Lineup confirmed"])
        finally:
            s.close()


if __name__ == "__main__":
    unittest.main()


class TimeCap(unittest.TestCase):
    def test_cap_marks_unreached_teams_and_skips_fetching(self):
        import time as _t
        import lineups
        import common
        import helpers
        ops = dict(helpers.cfg()["ops"], lineup_cycle_cap_s=-1)
        games = [{"id": 1, "away": "CAR", "home": "PHI", "start": "2026-10-11T19:00:00-04:00", "date": "2026-10-11"}]
        s = helpers.Sim(pool=12)
        try:
            calls = []
            real = lineups.fetch_page
            lineups.fetch_page = lambda slug: calls.append(slug)
            res = lineups.check(common.parse_iso("2026-10-11T17:30:00-04:00"), "2026-10-11", games, {}, ops, lambda t: [])
            lineups.fetch_page = real
        finally:
            s.close()
        self.assertEqual(calls, [])
        self.assertEqual(sorted(res["state"]["teams"]), ["CAR", "PHI"])
        self.assertTrue(all(r.get("tried_at") for r in res["state"]["teams"].values()))
