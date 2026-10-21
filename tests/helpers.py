"""helpers.py: shared setup for the tests. Builds the made-up league in a temp folder and runs the
engine in-process with the clock and all three sources pointed at files."""
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "scripts")
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, HERE)

import common   # noqa: E402
import run      # noqa: E402
import world    # noqa: E402

ENV = ("PC_NOW", "PC_DATA_DIR", "PC_ODDS_FIXTURE_DIR", "PC_NHL_FIXTURE_DIR", "PC_LINEUP_FIXTURE_DIR", "ODDS_API_KEYS", "ODDS_API_KEYS_2",
       "DISCORD_WEBHOOK_URL", "PC_DISCORD_FIXTURE_URL", "PC_CONFIG")
FIX = os.path.join(HERE, "fixtures")


def cfg():
    """The live rules (config/rules.json)."""
    return common.load_config()


def made_up_slate_config(root):
    """A copy of config/rules.json whose Gap + Guard goes live early enough for the made-up 2026-10-11 slate (the real
    live_from is 2026-10-20, the first slate it covers)."""
    c = json.loads(slurp(common.CONFIG_PATH, "r"))
    c["ops"]["gap_guard"]["live_from"] = "2026-10-01"
    path = os.path.join(root, "rules_made_up_slate.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(c, f)
    return path


def slurp(path, mode="rb"):
    with open(path, mode) as f:
        return f.read()


def load(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


class Sim:
    """One made-up day. Use as: s = Sim(); s.at("13:02"); ...; s.close()"""

    def __init__(self, pool=12, states=None, skip_this_season=None, rules=None):
        self.saved = {k: os.environ.get(k) for k in ENV}
        self.root = tempfile.mkdtemp(prefix="pc_test_")
        os.environ["PC_CONFIG"] = made_up_slate_config(self.root)
        self.w = world.build(self.root, states, skip_this_season)
        world.write(os.path.join(self.w["odds"], "pool.json"), {"keys": pool if isinstance(pool, list) else [pool]})
        os.makedirs(self.w["lineups"], exist_ok=True)
        for _, away, home, _ in world.GAMES:                # a default answer for each game: one line nobody can pick
            self.set_odds(away, home, [], "2026-10-11T17:00:00Z")
        os.environ.pop("ODDS_API_KEYS", None)
        os.environ.pop("ODDS_API_KEYS_2", None)
        os.environ.pop("DISCORD_WEBHOOK_URL", None)
        os.environ.pop("PC_DISCORD_FIXTURE_URL", None)
        os.environ.update(PC_DATA_DIR=self.w["data"], PC_NHL_FIXTURE_DIR=self.w["nhl"],
                          PC_ODDS_FIXTURE_DIR=self.w["odds"], PC_LINEUP_FIXTURE_DIR=self.w["lineups"])
        self.last = None
        self.output = ""
        self.prev_log = b""

    def close(self):
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.root, ignore_errors=True)

    # ---- driving the day
    def clock(self, hhmm, day=world.SLATE):
        os.environ["PC_NOW"] = "%sT%s:00-04:00" % (day, hhmm)

    def at(self, hhmm, day=world.SLATE):
        """Run the engine once at this Eastern time. Returns the slate."""
        self.clock(hhmm, day)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.last = run.run()
        self.output += buf.getvalue()
        log = self.log_bytes()                              # checked after EVERY run in EVERY test:
        assert log.startswith(self.prev_log), "the Record was changed in place (not append-only)"
        self.prev_log = log
        return self.slate()

    def set_states(self, states):
        p = os.path.join(self.w["nhl"], "schedule_%s.json" % world.SLATE)
        js = load(p)
        for wk in js["gameWeek"]:
            for g in wk["games"]:
                if g["id"] in states:
                    g["gameState"] = states[g["id"]]
        world.write(p, js)

    def set_odds(self, away, home, lines, last_update, others=None, hr=True):
        """others: {book: lines} for other books (consensus, shadow log only). hr=False: Hard Rock has nothing."""
        lines = list(lines) + [("player_shots_on_goal", world.name_of(home, 17), 0.5, -600, 400)]   # outside the gate
        world.write(os.path.join(self.w["odds"], "odds_%s_%s.json" % (away.lower(), home.lower())),
                    world.odds_payload(away, home, lines, last_update, others=others, hr=hr))

    def drop_odds(self, away, home):
        p = os.path.join(self.w["odds"], "odds_%s_%s.json" % (away.lower(), home.lower()))
        if os.path.exists(p):
            os.unlink(p)

    def set_lineup(self, team, updated_iso, **kw):
        import teams
        world.write(os.path.join(self.w["lineups"], teams.df_slug(team) + ".json"), world.df_page(team, updated_iso, **kw))

    def set_box(self, gid, away, home, stats_by_pid, **kw):
        world.write(os.path.join(self.w["nhl"], "gamecenter_%s_boxscore.json" % gid),
                    world.boxscore(gid, away, home, stats_by_pid, **kw))

    # ---- model-aware prices
    def inputs(self):
        r = run.Run(cfg(), common.now())
        return r.build_inputs()

    def model_over(self, team, i, market, line):
        opp = {"CAR": "PHI", "PHI": "CAR", "VAN": "NYR", "NYR": "VAN"}[team]
        return self.inputs().model(world.pid_of(team, i), team, opp, team in ("PHI", "NYR"), market, line)["p_over"]

    def line(self, team, i, market, line, gap, side="over", hold=0.07):
        """A feed line priced so that model - fair = gap for `side`."""
        key = {"shots": "player_shots_on_goal", "points": "player_points"}[market]
        p_over = self.model_over(team, i, market, line)
        fair_over = (p_over - gap) if side == "over" else (p_over + gap)
        over, under = world.two_sided(fair_over, hold)
        return (key, world.name_of(team, i), line, over, under)

    # ---- reading results
    def path(self, *parts):
        return os.path.join(self.w["data"], *parts)

    def slate(self):
        return common.read_json(self.path("slate.json"))

    def status(self):
        return common.read_json(self.path("status.json"))

    def log_bytes(self):
        p = self.path("record", "events.jsonl")
        return slurp(p) if os.path.exists(p) else b""

    def events(self):
        return [json.loads(l) for l in self.log_bytes().decode().splitlines() if l]

    def tree(self):
        out = {}
        for d, _, files in os.walk(self.w["data"]):
            for f in files:
                p = os.path.join(d, f)
                out[os.path.relpath(p, self.w["data"])] = slurp(p)
        return out

    def pick(self, team, i, slate=None):
        slate = slate or self.slate()
        return next((p for p in slate["picks"] if p["player_id"] == world.pid_of(team, i)), None)


# ---------------------------------------------------------------- Gap + Guard prices for the made-up league
BOOKS = ["draftkings", "fanduel", "betmgm", "espnbet", "pinnacle"]      # the books that return data (>= 4 with Pinnacle)


def _gg_methods():
    import world as w

    def gg_lines(self, team, i, line=1.5, side="over", ev=0.05, books=None, fair=None, hr_hold=0.05):
        """(hard rock line, {book: line}) that pass BOTH Gap + Guard steps for this player: the other books agree on a
        fair chance F (default: the model's own calibrated chance, so the guard agrees), Hard Rock pays +ev (EV%) on it."""
        T = common.gap_guard(common.load_config())["thresholds"]
        raw = self.model_over(team, i, "shots", line)
        cal = min(0.999, max(0.001, raw + T["offsets"]["%g" % line]))
        F_over = (min(0.66, max(0.48, cal)) if side == "over" else 1.0 - min(0.66, max(0.48, 1.0 - cal))) if fair is None else fair
        F = F_over if side == "over" else 1.0 - F_over                  # fair chance of the side we bet
        b = F / (1.0 + ev)                                               # Hard Rock's break-even for that side
        mine = w.american_from_prob(b)
        other = w.american_from_prob(1.0 + hr_hold - b)
        over, under = (mine, other) if side == "over" else (other, mine)
        name = w.name_of(team, i)
        hr = ("player_shots_on_goal", name, line, over, under)
        oth = {}
        for bk in (books or BOOKS):
            o, u = w.two_sided(F_over, 0.05)
            oth[bk] = ("player_shots_on_goal", name, line, o, u)
        return hr, oth

    def read(self, hhmm, cp=(), vn=(), day=w.SLATE, extra_hr_cp=(), extra_hr_vn=()):
        """One feed answer for both games, then one run. cp / vn: gg_lines() results for CAR@PHI / VAN@NYR."""
        hh, mm = int(hhmm[:2]), int(hhmm[3:])
        upd = "%sT%02d:%02d:00Z" % (day, hh + 4, max(0, mm - 1))
        for (away, home), picks, extra in ((("CAR", "PHI"), cp, extra_hr_cp), (("VAN", "NYR"), vn, extra_hr_vn)):
            hr = [x[0] for x in picks] + list(extra)
            oth = {}
            for x in picks:
                for bk, line in x[1].items():
                    oth.setdefault(bk, []).append(line)
            self.set_odds(away, home, hr, upd, others=oth or None)
        return self.at(hhmm, day)

    Sim.gg_lines, Sim.read = gg_lines, read


_gg_methods()
