"""Parlay caps hold for the whole night, not just for parlays still open (fix 2026-10-18).

Oct 13 showed 6 parlays (cap 3) with one leg in 4 of them: once the first parlays locked at puck drop they
stopped counting, and the next cycle built a fresh set from the same legs."""
import json
import os
import types
import unittest

import helpers  # noqa: F401
import common
import engine

SLATE = "2026-10-13"


def live_leg(n, game, price=-120, p=0.62):
    b = 1 / (1 + 100 / abs(price))
    return {"price": price, "p": p, "b": b, "price_at": common.parse_iso("2026-10-13T17:00:00-04:00"),
            "conf": True, "game_id": game, "pid": n}


def shown_leg(n):
    return {"kind": "single", "slate": SLATE, "pulled": None, "locked_at": None, "graded": None,
            "shown": {"player": "P. Player%d" % n, "bet": "Under 1.5 shots on goal"}}


class T(unittest.TestCase):
    def setUp(self):
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, "..", "config", "rules.json")) as f:
            self.v = json.load(f)["values"]
        self.inp = types.SimpleNamespace(v=self.v, slate=SLATE)
        self.ids = ["%s:g%d:p%d:shots:1.5:under" % (SLATE, i, i) for i in range(1, 7)]
        self.live = {l: live_leg(i + 1, 100 + i) for i, l in enumerate(self.ids)}
        self.items = {l: shown_leg(i + 1) for i, l in enumerate(self.ids)}

    def run_cycle(self):
        new = engine._parlays(self.inp, self.items, self.live, "2026-10-13T17:00:00-04:00")
        made = [e for e in new if e["t"] == "shown"]
        for e in made:
            self.items[e["id"]] = {"kind": "parlay", "slate": SLATE, "pulled": None, "locked_at": None,
                                   "graded": None, "shown": e["parlay"], "state": e["parlay"]["state"],
                                   "prices": [{"price": e["parlay"]["price"], "legs": e["parlay"]["leg_prices"]}],
                                   "p": e["parlay"]["p"]}
        return made

    def test_no_new_set_after_the_first_ones_lock(self):
        first = self.run_cycle()
        self.assertTrue(first)
        for e in first:                                      # puck drop: every parlay locks
            self.items[e["id"]]["locked_at"] = "2026-10-13T19:00:00-04:00"
        second = self.run_cycle()
        used = {}
        for e in first + second:
            for l in e["parlay"]["legs"]:
                used[l] = used.get(l, 0) + 1
        self.assertLessEqual(len(first) + len(second), self.v["parlay_cap"])
        self.assertLessEqual(max(used.values()), self.v["parlay_leg_max_use"])

    def test_a_leg_goes_in_one_parlay(self):
        made = self.run_cycle()
        legs = [l for e in made for l in e["parlay"]["legs"]]
        self.assertEqual(len(legs), len(set(legs)))

    def test_a_pulled_parlay_does_not_use_up_the_cap(self):
        first = self.run_cycle()
        self.items[first[0]["id"]]["pulled"] = {"reason": "x leg pulled"}
        for l in first[0]["parlay"]["legs"]:                 # its legs are gone too
            self.live.pop(l, None)
        second = self.run_cycle()
        self.assertLessEqual(len(first) - 1 + len(second), self.v["parlay_cap"])


if __name__ == "__main__":
    unittest.main()
