"""The Data Scientist's model self-test, ported unchanged (asserts are identical to ds/model.py)."""
import math
import unittest

import helpers  # noqa: F401  (puts scripts/ on the path)
from model import (break_even, nb_sf, skater_mu, skater_prob, naive_last10, team_factor, goalie_prob,
                   skater_detail, calibrate)


class ModelSelfTest(unittest.TestCase):
    def test_selftest(self):
        assert abs(break_even(-200) - 2 / 3) < 1e-9 and abs(break_even(120) - 100 / 220) < 1e-9
        assert abs(nb_sf(1, 1.0) - (1 - math.exp(-1))) < 1e-12
        assert abs(nb_sf(3, 2.5) - (1 - math.exp(-2.5) * (1 + 2.5 + 2.5 ** 2 / 2))) < 1e-12
        assert abs(sum(nb_sf(k, 3.0, 9.0) for k in range(1, 400)) - 3.0) < 1e-6       # E[X] = sum of P(X>=k)
        assert nb_sf(3, 2.5, 9.0) < nb_sf(3, 2.5) + 0.02 and nb_sf(0, 1.0) == 1.0
        # no history -> positional prior
        m0 = skater_mu([], "F", 20262027, "shots")
        assert abs(m0 - 7.37 / 3600 * 950 * 0.972) < 1e-9, m0
        mk = lambda i, season, shots, toi=1200: dict(season=season, date="2026-%02d-%02d" % (1 + i // 28, 1 + i % 28),
                                                     gid=i, toi=toi, shots=shots, goals=0, assists=1, points=1)
        hot = [mk(i, 20252026, 4) for i in range(80)]
        cold = [mk(i, 20252026, 1) for i in range(80)]
        a = skater_prob(hot, "F", 20262027, "shots", 2.5)
        b = skater_prob(cold, "F", 20262027, "shots", 2.5)
        assert a["p"] > 0.6 > 0.2 > b["p"], (a, b)
        assert not a["thin"] and skater_prob(hot[:5], "F", 20262027, "shots", 2.5)["thin"]
        assert skater_prob(hot, "F", 20262027, "shots", 2.5, {"games_with_team": 3})["thin"]
        # shrink: 3 hot games move the estimate only part of the way
        few = skater_mu([mk(i, 20262027, 6) for i in range(3)], "F", 20262027, "shots")
        assert m0 < few < 6 * 0.972, few
        # role change: same per-minute rate, more recent ice time -> higher mean
        up = cold[:75] + [mk(75 + i, 20252026, 1, toi=1500) for i in range(5)]
        assert skater_mu(up, "F", 20262027, "shots") > skater_mu(cold, "F", 20262027, "shots")
        # context
        assert skater_mu(hot, "F", 20262027, "shots", {"opp_sa_f": 1.1}) > skater_mu(hot, "F", 20262027, "shots")
        # order of rows must not matter; rows older than last season are ignored
        old = [mk(i, 20232024, 9) for i in range(50)]
        assert abs(skater_mu(list(reversed(hot)) + old, "F", 20262027, "shots") - skater_mu(hot, "F", 20262027, "shots")) < 1e-12
        assert naive_last10(hot, "shots", 2.5) == 1.0 and naive_last10(hot[:5], "shots", 2.5) is None
        tr = [dict(date="2026-01-%02d" % (i + 1), gid=i, sa=33, sf=28, ga=3) for i in range(20)]
        f = team_factor(tr, "sa", 28.0, 10.0)
        assert 1.0 < f < 33 / 28.0
        assert team_factor([], "sa", 28.0, 10.0) == 1.0
        g = goalie_prob(24.5, dict(home=False, league_sf=28.0, team_sa_f=1.0, opp_sf_f=1.0))
        g2 = goalie_prob(24.5, dict(home=False, league_sf=28.0, team_sa_f=1.1, opp_sf_f=1.1))
        assert 0.3 < g["p"] < 0.6 < g2["p"], (g, g2)
        for ln in (20.5, 22.5, 26.5):
            assert goalie_prob(ln, dict(home=True, league_sf=28.0))["p"] > goalie_prob(ln + 1, dict(home=True, league_sf=28.0))["p"]

    def test_detail_matches_mu(self):
        """skater_detail (added for the reason sentence) must return exactly skater_mu's number."""
        rows = [dict(season=20252026, date="2026-01-%02d" % (1 + i), gid=i, toi=1000 + 10 * i, shots=i % 5,
                     goals=0, assists=i % 2, points=i % 2) for i in range(25)]
        for market in ("shots", "points", "goals", "assists"):
            for ctx in (None, {"home": True, "opp_sa_f": 1.07, "opp_ga_f": 0.93}, {"home": False}):
                d = skater_detail(rows, "F", 20262027, market, ctx)
                self.assertEqual(d["mu"], skater_mu(rows, "F", 20262027, market, ctx))
                self.assertGreater(d["etoi"], 0)

    def test_known_values(self):
        """Pinned numbers: any change to the model's maths shows up here."""
        self.assertAlmostEqual(skater_mu([], "D", 20262027, "points"), 1.08 / 3600 * 1150 * 0.972, places=12)
        self.assertAlmostEqual(calibrate(0.5, "shots", 2.5), 1 / (1 + math.exp(-0.066)), places=12)
        self.assertAlmostEqual(calibrate(0.5, "points", 0.5), 1 / (1 + math.exp(-0.044)), places=12)
        self.assertAlmostEqual(calibrate(0.7, "nope", 9.5), 0.7, places=9)


if __name__ == "__main__":
    unittest.main()
