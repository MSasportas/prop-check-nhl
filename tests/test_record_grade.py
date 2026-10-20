"""The Record and grading: units, parlays, void / push / did not play, shootouts, append-only, the guard."""
import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest

import helpers
from helpers import Sim
import common
import grade
import guard_record
import odds
import record
import run
import world

CFG = helpers.cfg()
UPD = "2026-10-11T17:00:00Z"
G1, G2 = 2026020901, 2026020902


def shown(i, market="shots", line=2.5, side="over", price=-120, game=G1, pid=8480001, slate="2026-10-11",
          at="2026-10-11T13:02:00-04:00", start="2026-10-11T19:00:00-04:00"):
    return {"t": "shown", "kind": "single", "id": i, "at": at, "slate": slate,
            "pick": {"id": i, "rank": 1, "game_id": game, "player": "A. Car01", "player_id": pid, "team": "CAR",
                     "opp": "PHI", "home": False, "start": start, "market": market, "line": line, "side": side,
                     "bet": "x", "price": price, "price_at": at, "p": 0.6, "breakeven": 0.55, "reason": "r",
                     "state": "early", "thin": False, "games_used": 30, "games_this_season": 3}}


class Units(unittest.TestCase):
    def test_single(self):
        self.assertAlmostEqual(record.single_units("W", -145), 0.6897, places=4)      # 100/145
        self.assertAlmostEqual(record.single_units("W", 120), 1.2)
        self.assertEqual(record.single_units("L", -145), -1.0)
        self.assertEqual(record.single_units("PUSH", -145), 0.0)
        self.assertEqual(record.single_units("VOID", -145), 0.0)

    def test_parlay(self):
        # two winners at -120 and +100: 1.8333 x 2.0 = 3.6667 -> +267; units at that price: 2.67
        self.assertEqual(record.grade_parlay([("W", -120), ("W", 100)]), ("W", 267, 2.67))
        self.assertEqual(record.grade_parlay([("W", -120), ("L", 100)]), ("L", 267, -1.0))
        # a void leg drops out: the parlay is graded on what is left
        self.assertEqual(record.grade_parlay([("W", -120), ("VOID", 100)]), ("W", -120, 0.8333))
        self.assertEqual(record.grade_parlay([("L", -120), ("VOID", 100)]), ("L", -120, -1.0))
        self.assertEqual(record.grade_parlay([("W", -120), ("PUSH", 100), ("W", -150)])[0:2], ("W", 206))
        self.assertEqual(record.grade_parlay([("VOID", -120), ("PUSH", 100)]), ("VOID", None, 0.0))
        self.assertEqual(record.grade_parlay([("W", -120), (None, 100)]), (None, None, None))   # a leg not graded yet

    def test_result_for(self):
        self.assertEqual(grade.result_for("over", 2.5, 3), "W")
        self.assertEqual(grade.result_for("over", 2.5, 2), "L")
        self.assertEqual(grade.result_for("under", 2.5, 2), "W")
        self.assertEqual(grade.result_for("under", 0.5, 1), "L")
        self.assertEqual(grade.result_for("over", 3.0, 3), "PUSH")
        self.assertEqual(grade.result_for("under", 3.0, 3), "PUSH")

    def test_worst_price_is_the_lowest_payout(self):
        it = {"prices": [{"price": -135}, {"price": -150}, {"price": -140}]}
        self.assertEqual(record.worst_price(it), -150)
        it = {"prices": [{"price": 110}, {"price": -105}, {"price": 120}]}
        self.assertEqual(record.worst_price(it), -105)


class GradeUnit(unittest.TestCase):
    """grade.grade() on hand-written Record events, with the boxscore supplied directly."""

    def setUp(self):
        self.real = grade.nhl.boxscore
        self.real_pbp = grade.nhl.play_by_play
        grade.nhl.play_by_play = lambda gid: None
        self.now = common.parse_iso("2026-10-11T22:30:00-04:00")
        self.sched = {str(G1): {"id": G1, "sched": "OK"}}

    def tearDown(self):
        grade.nhl.boxscore = self.real
        grade.nhl.play_by_play = self.real_pbp

    def box(self, **kw):
        b = world.boxscore(G1, "CAR", "PHI", kw.pop("stats", {}), **kw)
        grade.nhl.boxscore = lambda gid: b
        return b

    def test_win_loss_at_the_worst_price(self):
        ev = [shown("a", price=-135), shown("b", side="under", price=110, pid=8480002),
              {"t": "price", "id": "a", "at": "2026-10-11T18:16:00-04:00", "price": -150, "p": 0.6, "breakeven": 0.6},
              {"t": "locked", "id": "a", "at": "2026-10-11T19:00:00-04:00", "state": "locked"},
              {"t": "locked", "id": "b", "at": "2026-10-11T19:00:00-04:00", "state": "locked"}]
        self.box(stats={8480001: (4, 1, 0), 8480002: (3, 0, 0)})
        new, notes = grade.grade(ev, self.now, CFG, self.sched)
        g = {e["id"]: e for e in new}
        self.assertEqual((g["a"]["result"], g["a"]["actual"], g["a"]["actual_text"], g["a"]["price"]), ("W", 4, "had 4", -150))
        self.assertAlmostEqual(g["a"]["units"], 0.6667, places=4)         # graded at -150, not the first -135
        self.assertEqual((g["b"]["result"], g["b"]["units"], g["b"]["actual_text"]), ("L", -1.0, "had 3"))
        self.assertEqual(grade.grade(ev + new, self.now, CFG, self.sched), ([], []))   # graded once

    def test_push_on_a_whole_number(self):
        ev = [shown("a", line=3.0)]
        self.box(stats={8480001: (3, 0, 0)})
        new, _ = grade.grade(ev, self.now, CFG, self.sched)
        g = [e for e in new if e["t"] == "graded"][0]
        self.assertEqual((g["result"], g["units"], g["actual_text"]), ("PUSH", 0.0, "had 3"))

    def test_did_not_play_is_void(self):
        ev = [shown("a"), shown("b", pid=8480002)]
        b = self.box(missing=[8480001])                              # scratched: not in the boxscore
        for p in b["playerByGameStats"]["awayTeam"]["forwards"]:
            if p["playerId"] == 8480002:
                p["toi"] = "00:00"                                   # dressed, never took a shift
                p["sog"] = 0
        b["awayTeam"]["sog"] -= 1
        new, _ = grade.grade(ev, self.now, CFG, self.sched)
        g = {e["id"]: e for e in new if e["t"] == "graded"}
        for i in ("a", "b"):
            self.assertEqual((g[i]["result"], g[i]["units"], g[i]["actual_text"]), ("VOID", 0.0, "did not play"))

    def test_not_final_is_not_graded(self):
        ev = [shown("a")]
        for state in ("LIVE", "CRIT", "FINAL"):
            self.box(state=state, stats={8480001: (4, 0, 0)})
            self.assertEqual(grade.grade(ev, self.now, CFG, self.sched)[0], [])
        grade.nhl.boxscore = lambda gid: None                        # source down: nothing graded, a note left
        new, notes = grade.grade(ev, self.now, CFG, self.sched)
        self.assertEqual(new, [])
        self.assertEqual(notes, ["boxscore for %s not available" % G1])

    def test_shootout_goal_never_counts(self):
        # team score includes the shootout goal; the player rows do not. Player 8480001 "scored" only in the shootout.
        ev = [shown("pts", market="points", line=0.5, side="over"), shown("pts_u", market="points", line=0.5, side="under", pid=8480002)]
        b = self.box(shootout=True, stats={8480001: (2, 0, 0), 8480002: (1, 0, 0)})
        self.assertEqual(b["awayTeam"]["score"], 3)
        self.assertEqual(sum(p["goals"] for p in b["playerByGameStats"]["awayTeam"]["forwards"]), 0)
        new, _ = grade.grade(ev, self.now, CFG, self.sched)
        g = {e["id"]: e for e in new if e["t"] == "graded"}
        self.assertEqual((g["pts"]["result"], g["pts"]["actual_text"]), ("L", "had 0"))
        self.assertEqual(g["pts_u"]["result"], "W")

    def test_overtime_counts(self):
        ev = [shown("pts", market="points", line=0.5, side="over")]
        b = self.box(stats={8480001: (2, 1, 0)})
        b["gameOutcome"] = {"lastPeriodType": "OT"}
        g = [e for e in grade.grade(ev, self.now, CFG, self.sched)[0] if e["t"] == "graded"][0]
        self.assertEqual((g["result"], g["actual"]), ("W", 1))

    def test_postponed_is_void(self):
        ev = [shown("a")]
        grade.nhl.boxscore = lambda gid: self.fail("a postponed game needs no boxscore")
        new, _ = grade.grade(ev, self.now, CFG, {str(G1): {"id": G1, "sched": "PPD"}})
        g = [e for e in new if e["t"] == "graded"][0]
        self.assertEqual((g["result"], g["actual_text"], g["units"]), ("VOID", "game postponed", 0.0))

    def test_shot_totals_that_do_not_add_up_wait(self):
        ev = [shown("a"), shown("pts", market="points", line=0.5, pid=8480002)]
        b = self.box(stats={8480001: (4, 0, 0), 8480002: (1, 1, 0)})
        b["awayTeam"]["sog"] += 3                                    # team says 3 more shots than the players add up to
        new, notes = grade.grade(ev, self.now, CFG, self.sched)
        self.assertEqual([e["id"] for e in new if e["t"] == "graded"], ["pts"])   # points are fine; shots wait
        self.assertIn("do not add up yet", notes[0])
        late = common.parse_iso("2026-10-12T19:01:00-04:00")         # a day later: grade with a note rather than never
        new, _ = grade.grade(ev, late, CFG, self.sched)
        a = [e for e in new if e["id"] == "a" and e["t"] == "graded"][0]
        self.assertEqual((a["result"], a["note"]), ("W", "team shot total did not match the player rows"))

    def test_goalie_shot_explains_the_difference(self):
        ev = [shown("a")]
        b = self.box(stats={8480001: (4, 0, 0)})
        b["awayTeam"]["sog"] += 1
        grade.nhl.play_by_play = lambda gid: {
            "awayTeam": {"id": 12, "abbrev": "CAR"}, "homeTeam": {"id": 4, "abbrev": "PHI"},
            "rosterSpots": [{"teamId": 12, "playerId": 99, "positionCode": "G"}],
            "plays": [{"typeDescKey": "shot-on-goal", "periodDescriptor": {"periodType": "REG"},
                       "details": {"eventOwnerTeamId": 12, "shootingPlayerId": 99}}]}
        new, notes = grade.grade(ev, self.now, CFG, self.sched)
        self.assertEqual(([e["result"] for e in new if e["t"] == "graded"], notes), (["W"], []))

    def test_pick_never_locked_is_locked_then_graded(self):
        ev = [shown("a")]                                            # runs were down from before puck to after the game
        self.box(stats={8480001: (1, 0, 0)})
        new, _ = grade.grade(ev, self.now, CFG, self.sched)
        self.assertEqual([(e["t"], e.get("state"), e.get("result")) for e in new],
                         [("locked", "locked_unconfirmed", None), ("graded", None, "L")])

    def test_parlay_with_a_void_leg(self):
        par = {"t": "shown", "kind": "parlay", "id": "P", "at": "2026-10-11T13:02:00-04:00", "slate": "2026-10-11",
               "parlay": {"id": "P", "legs": ["a", "b"], "price": 236, "p": 0.36, "breakeven": 0.3, "state": "early"}}
        ev = [shown("a", price=-120), shown("b", price=-120, pid=8480002), par]
        self.box(stats={8480001: (4, 0, 0)}, missing=[8480002])       # leg a wins, leg b did not play
        new, _ = grade.grade(ev, self.now, CFG, self.sched)
        g = {e["id"]: e for e in new if e["t"] == "graded"}
        self.assertEqual((g["a"]["result"], g["b"]["result"]), ("W", "VOID"))
        self.assertEqual((g["P"]["result"], g["P"]["price"], g["P"]["actual_text"]), ("W", -120, "1 of 1 legs hit"))
        self.assertAlmostEqual(g["P"]["units"], 0.8333, places=4)
        self.assertEqual(g["P"]["legs"], [{"id": "a", "result": "W"}, {"id": "b", "result": "VOID"}])
        self.assertEqual(grade.grade(ev + new, self.now, CFG, self.sched)[0], [])


class RecordLog(unittest.TestCase):
    def setUp(self):
        self.old = os.environ.get("PC_DATA_DIR")
        self.dir = tempfile.mkdtemp(prefix="pc_rec_")
        os.environ["PC_DATA_DIR"] = self.dir

    def tearDown(self):
        if self.old is None:
            os.environ.pop("PC_DATA_DIR", None)
        else:
            os.environ["PC_DATA_DIR"] = self.old

    def test_append_only_adds_at_the_end(self):
        record.append([shown("a")])
        first = record.read_raw()
        record.append([{"t": "locked", "id": "a", "at": "2026-10-11T19:00:00-04:00", "state": "locked"}])
        second = record.read_raw()
        self.assertTrue(second.startswith(first))
        self.assertEqual(second.count(b"\n"), 2)
        self.assertEqual(record.append([]), 0)
        self.assertEqual(record.read_raw(), second)

    def test_damaged_log_stops_everything(self):
        record.append([shown("a")])
        raw = record.read_raw()
        common.write_bytes(record.events_path(), raw[:-1])            # a write cut short: no final newline
        with self.assertRaises(record.RecordError):
            record.append([shown("b")])
        common.write_bytes(record.events_path(), raw + b"{not json\n")
        with self.assertRaises(record.RecordError):
            record.read_events()
        common.write_bytes(record.events_path(), raw)
        with self.assertRaises(record.RecordError):
            record.append([{"t": "edit", "id": "a", "at": "x"}])      # only the seven known event types
        self.assertEqual(record.read_raw(), raw)

    def test_fold(self):
        ev = [shown("a", price=-135),
              {"t": "price", "id": "a", "at": "t2", "price": -150, "p": 0.61, "breakeven": 0.6, "reason": "r2"},
              {"t": "state", "id": "a", "at": "t3", "state": "lineup"},
              {"t": "pulled", "id": "a", "at": "t4", "reason": "why", "code": "gate"},
              {"t": "pulled", "id": "a", "at": "t6", "reason": "second"}]           # a second pull changes nothing
        it = record.fold(ev)["a"]
        self.assertEqual([p["price"] for p in it["prices"]], [-135, -150])
        self.assertEqual((it["p"], it["reason"], it["state"]), (0.61, "r2", "lineup"))
        self.assertEqual(it["pulled"]["reason"], "why")
        self.assertFalse(record.is_open(it))

    def test_views_and_rebuild(self):
        ev = [shown("a", price=-120), shown("b", price=-150, pid=8480002), shown("c", market="points", line=0.5, price=110, pid=8480003),
              shown("d", price=-110, pid=8480004),
              {"t": "pulled", "id": "d", "at": "2026-10-11T18:41:00-04:00", "reason": "Scratched from the lineup", "code": "out"},
              {"t": "graded", "id": "a", "at": "2026-10-11T22:00:00-04:00", "result": "W", "actual": 4, "actual_text": "had 4", "price": -120, "units": 0.8333},
              {"t": "graded", "id": "b", "at": "2026-10-11T22:00:00-04:00", "result": "L", "actual": 1, "actual_text": "had 1", "price": -150, "units": -1.0},
              {"t": "graded", "id": "c", "at": "2026-10-11T22:00:00-04:00", "result": "VOID", "actual": None, "actual_text": "did not play", "price": 110, "units": 0.0},
              {"t": "graded", "id": "d", "at": "2026-10-11T22:00:00-04:00", "result": "L", "actual": 0, "actual_text": "had 0", "price": -110, "units": -1.0}]
        rec, months = record.build_views(ev, CFG)
        h = rec["summary"]["headline"]
        self.assertEqual((h["w"], h["l"], h["push"], h["void"], h["n"]), (1, 1, 0, 1, 2))
        self.assertAlmostEqual(h["units"], -0.17)                      # +0.8333 - 1.0; the pulled loss is not in here
        self.assertEqual(h["hit_rate"], 0.5)
        self.assertAlmostEqual(h["needed"], (120 / 220 + 150 / 250) / 2, places=4)
        rows = {r["key"]: r for r in rec["summary"]["rows"]}
        self.assertEqual(sorted(rows), ["points", "pulled", "shots"])
        self.assertEqual((rows["shots"]["w"], rows["shots"]["l"], rows["shots"]["label"]), (1, 1, "Shots on goal"))
        self.assertEqual((rows["points"]["void"], rows["points"]["n"], rows["points"]["hit_rate"]), (1, 0, None))
        self.assertEqual((rows["pulled"]["l"], rows["pulled"]["units"], rows["pulled"]["label"]), (1, -1.0, "Pulled (not counted above)"))
        n = rec["nights"][0]
        self.assertEqual((n["date"], n["graded"], n["w"], n["l"], n["units"]), ("2026-10-11", True, 1, 1, -0.17))
        d = next(e for e in n["entries"] if e["id"] == "d")
        self.assertEqual(d["pulled"], {"at": "2026-10-11T18:41:00-04:00", "reason": "Scratched from the lineup"})
        self.assertEqual((d["result"], d["actual"], d["units"], d["price"]), ("L", "had 0", -1.0, -110))
        self.assertEqual(rec["generated_at"], "2026-10-11T22:00:00-04:00")
        self.assertEqual(months, {})
        # written, deleted, rebuilt from the log alone: byte for byte the same
        record.append(ev)
        record.write_views(CFG)
        before = helpers.slurp(common.dpath("record.json"))
        os.unlink(common.dpath("record.json"))
        with contextlib.redirect_stdout(io.StringIO()):
            run.main(["--rebuild-record"])
        self.assertEqual(helpers.slurp(common.dpath("record.json")), before)
        self.assertEqual(record.write_views(CFG), [])                  # and a second rebuild writes nothing

    def test_empty_record(self):
        rec, months = record.build_views([], CFG)
        self.assertEqual(rec["summary"]["headline"]["n"], 0)
        self.assertEqual((rec["nights"], rec["older"], rec["generated_at"]), ([], [], None))

    def test_older_nights_go_to_month_files(self):
        ev = []
        for d in range(1, 11):                                         # ten nights
            day = "2026-10-%02d" % d
            ev.append(shown("p%d" % d, slate=day, at=day + "T13:00:00-04:00"))
        rec, months = record.build_views(ev, CFG)
        self.assertEqual([n["date"] for n in rec["nights"]], ["2026-10-%02d" % d for d in range(10, 3, -1)])
        self.assertEqual(rec["older"], ["record/2026-10.json"])
        self.assertEqual([n["date"] for n in months["2026-10"]["nights"]], ["2026-10-03", "2026-10-02", "2026-10-01"])
        self.assertFalse(rec["nights"][0]["graded"])
        self.assertIsNone(rec["nights"][0]["entries"][0]["result"])


class Guard(unittest.TestCase):
    A = b'{"t":"shown","id":"a","at":"1"}\n'
    B = b'{"t":"locked","id":"a","at":"2"}\n'

    def test_check(self):
        c = guard_record.check
        self.assertIsNone(c(b"", b""))
        self.assertIsNone(c(b"", self.A))
        self.assertIsNone(c(self.A, self.A))
        self.assertIsNone(c(self.A, self.A + self.B))
        self.assertEqual(c(self.A + self.B, self.A), "the Record lost lines (2 committed, 1 now)")
        self.assertEqual(c(self.A + self.B, self.B + self.A), "a committed Record line was changed")       # reordered
        self.assertEqual(c(self.A, self.A.replace(b'"1"', b'"9"') + self.B), "a committed Record line was changed")
        self.assertEqual(c(self.A, self.B + self.A), "a committed Record line was changed")                # inserted before
        self.assertEqual(c(self.A, self.A + self.B[:-1]), "the Record does not end with a newline")
        self.assertEqual(c(self.A, b""), "the Record lost lines (1 committed, 0 now)")

    def test_command_line(self):
        d = tempfile.mkdtemp(prefix="pc_guard_")
        old, new = os.path.join(d, "old"), os.path.join(d, "new")
        script = os.path.join(helpers.SCRIPTS, "guard_record.py")
        common.write_bytes(old, self.A)
        common.write_bytes(new, self.A + self.B)
        r = subprocess.run([sys.executable, script, "--old", old, "--new", new], capture_output=True, text=True)
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "RECORD GUARD: ok (1 lines committed, 2 now)"))
        common.write_bytes(new, self.A.replace(b"shown", b"SHOWN") + self.B)       # an edited line
        r = subprocess.run([sys.executable, script, "--old", old, "--new", new], capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("RECORD GUARD: FAILED: a committed Record line was changed", r.stdout)

    def test_against_a_real_git_repo(self):
        """The workflow path: `git show HEAD:data/record/events.jsonl` against the working file."""
        d = tempfile.mkdtemp(prefix="pc_guard_git_")
        os.makedirs(os.path.join(d, "scripts"))
        os.makedirs(os.path.join(d, "data", "record"))
        with open(os.path.join(helpers.SCRIPTS, "guard_record.py")) as f:
            src = f.read()
        with open(os.path.join(d, "scripts", "guard_record.py"), "w") as f:
            f.write(src)
        log = os.path.join(d, "data", "record", "events.jsonl")
        git = lambda *a: subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"] + list(a),
                                        cwd=d, capture_output=True, text=True)
        guard = lambda: subprocess.run([sys.executable, os.path.join(d, "scripts", "guard_record.py")], capture_output=True, text=True)
        if git("init", "-q").returncode != 0:
            self.skipTest("git not available")
        self.assertEqual(guard().returncode, 0)                          # nothing committed, nothing on disk
        common.write_bytes(log, self.A)
        self.assertEqual(guard().returncode, 0)                          # first lines: an addition
        git("add", "-A"); git("commit", "-q", "-m", "one")
        common.write_bytes(log, self.A + self.B)
        self.assertEqual(guard().returncode, 0)                          # appended
        common.write_bytes(log, self.B)
        self.assertEqual(guard().returncode, 1)                          # rewritten
        os.unlink(log)
        self.assertEqual(guard().returncode, 1)                          # deleted


class GradedDay(unittest.TestCase):
    """The whole chain on the made-up league: shown -> price moved -> pulled -> locked -> graded -> Record."""

    def test_full_day(self):
        s = Sim(pool=12)
        try:
            s.at("09:00")
            s.read("13:02")
            s.clock("17:00")
            cp = [s.gg_lines("CAR", 1), s.gg_lines("PHI", 1)]
            sl = s.read("17:31", cp=cp)                                        # 90-minute read, 7 PM game: two picks
            # 6:16 PM (45-minute read): PHI's price drifts so the gap is gone (pulled); CAR's stays
            sl = s.read("18:16", cp=[cp[0], s.gg_lines("PHI", 1, ev=-0.04)])
            self.assertEqual(s.pick("PHI", 1, sl)["pulled"]["reason"], "Hard Rock moved the price and the gap is gone")
            sl = s.read("18:31", cp=[cp[0], s.gg_lines("PHI", 1, ev=-0.04)], vn=[s.gg_lines("VAN", 1)])   # 8 PM game: the third pick
            first = {p["team"]: p["price"] for p in sl["picks"]}
            ids = {p["team"]: p["id"] for p in sl["picks"]}
            self.assertEqual(sorted(first), ["CAR", "PHI", "VAN"])
            self.assertEqual(sl["parlays"], [])
            self.assertEqual(s.pick("CAR", 1, sl)["price"], first["CAR"])      # the shown price never changes
            s.at("19:00")
            s.at("20:00")
            # results: CAR 4 shots (W), PHI 1 (L, pulled), VAN scratched (VOID)
            car, phi, van, nyr = (world.pid_of(t, 1) for t in ("CAR", "PHI", "VAN", "NYR"))
            s.set_box(G1, "CAR", "PHI", {car: (4, 0, 0), phi: (1, 0, 0)}, state="FINAL")
            s.set_states({G1: "FINAL", G2: "LIVE"})
            s.at("21:40")
            self.assertEqual([e for e in s.events() if e["t"] == "graded"], [], "FINAL is not final enough")
            s.set_box(G1, "CAR", "PHI", {car: (4, 0, 0), phi: (1, 0, 0)})
            s.set_box(G2, "VAN", "NYR", {nyr: (5, 0, 0)}, missing=[van])
            s.set_states({G1: "OFF", G2: "OFF"})
            sl = s.at("23:10")
            g = {e["id"]: e for e in s.events() if e["t"] == "graded"}
            self.assertEqual({t: g[ids[t]]["result"] for t in ids}, {"CAR": "W", "PHI": "L", "VAN": "VOID"})
            self.assertEqual(g[ids["CAR"]]["price"], first["CAR"])                 # graded at the price shown
            self.assertEqual(g[ids["PHI"]]["price"], first["PHI"])
            self.assertAlmostEqual(g[ids["CAR"]]["units"], round(odds.decimal(first["CAR"]) - 1, 4))
            self.assertEqual(g[ids["VAN"]]["units"], 0.0)
            self.assertEqual(s.pick("CAR", 1, sl)["graded"], {"result": "W", "actual": "had 4", "units": g[ids["CAR"]]["units"]})
            # the Record
            rec = common.read_json(s.path("record.json"))
            h = rec["summary"]["headline"]
            self.assertEqual((h["w"], h["l"], h["void"], h["n"]), (1, 0, 1, 1))
            self.assertAlmostEqual(h["units"], round(g[ids["CAR"]]["units"], 2))
            rows = {r["key"]: r for r in rec["summary"]["rows"]}
            self.assertEqual((rows["pulled"]["w"], rows["pulled"]["l"]), (0, 1))   # PHI: pulled, still graded, not in the headline
            self.assertNotIn("parlays", rows)
            night = rec["nights"][0]
            self.assertEqual((night["date"], night["graded"], night["w"], night["l"]), ("2026-10-11", True, 1, 0))
            self.assertEqual(len(night["entries"]), 3)
            self.assertEqual({e["kind"] for e in night["entries"]}, {"single"})
            # running again adds nothing, and the next morning starts a clean slate with the Record intact
            n = len(s.events())
            s.at("23:20")
            self.assertEqual(len(s.events()), n)
            sl = s.at("09:00", day="2026-10-12")
            self.assertEqual((sl["slate_date"], sl["picks"], sl["parlays"]), ("2026-10-12", [], []))
            self.assertEqual(len(s.events()), n)
            self.assertEqual(common.read_json(s.path("record.json")), rec)
            kinds = [e["t"] for e in s.events()]
            self.assertEqual({k: kinds.count(k) for k in set(kinds)}, {"shown": 3, "pulled": 1, "locked": 2, "graded": 3})
        finally:
            s.close()

    def test_game_final_after_the_slate_rolls_over_is_still_graded(self):
        s = Sim(pool=12)
        try:
            s.at("09:00")
            s.read("13:02")
            s.clock("17:00")
            s.read("18:31", vn=[s.gg_lines("NYR", 1, line=2.5)])
            self.assertEqual([e["t"] for e in s.events()], ["shown"])
            s.at("20:00")
            s.set_states({G1: "OFF", G2: "LIVE"})
            s.at("23:59")
            self.assertEqual([e for e in s.events() if e["t"] == "graded"], [])
            # the late game goes final at 5:20 AM the next day (after the 5:00 AM rollover)
            s.set_box(G2, "VAN", "NYR", {world.pid_of("NYR", 1): (2, 0, 0)})
            world.write(os.path.join(s.w["nhl"], "schedule_2026-10-12.json"), world.schedule_doc({}))
            p = os.path.join(s.w["nhl"], "schedule_2026-10-05.json")
            world.write(p, world.schedule_doc({"2026-10-11": [world.sched_game(G1, "CAR", "PHI", "2026-10-11T23:00:00Z", "OFF"),
                                                              world.sched_game(G2, "VAN", "NYR", "2026-10-12T00:00:00Z", "OFF")]}))
            s.at("05:20", day="2026-10-12")
            g = [e for e in s.events() if e["t"] == "graded"]
            self.assertEqual([(e["result"], e["actual_text"]) for e in g], [("L", "had 2")])
            rec = common.read_json(s.path("record.json"))
            self.assertEqual((rec["nights"][0]["date"], rec["nights"][0]["l"]), ("2026-10-11", 1))
        finally:
            s.close()


if __name__ == "__main__":
    unittest.main()
