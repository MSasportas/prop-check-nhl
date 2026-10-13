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

ENV = ("PC_NOW", "PC_DATA_DIR", "PC_ODDS_FIXTURE_DIR", "PC_NHL_FIXTURE_DIR", "PC_LINEUP_FIXTURE_DIR", "ODDS_API_KEYS",
       "DISCORD_WEBHOOK_URL", "PC_DISCORD_FIXTURE_URL")
FIX = os.path.join(HERE, "fixtures")


def cfg():
    return common.load_config()


def slurp(path, mode="rb"):
    with open(path, mode) as f:
        return f.read()


def load(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


class Sim:
    """One made-up day. Use as: s = Sim(); s.at("13:02"); ...; s.close()"""

    def __init__(self, pool=12, states=None, skip_this_season=None):
        self.saved = {k: os.environ.get(k) for k in ENV}
        self.root = tempfile.mkdtemp(prefix="pc_test_")
        self.w = world.build(self.root, states, skip_this_season)
        world.write(os.path.join(self.w["odds"], "pool.json"), {"keys": pool if isinstance(pool, list) else [pool]})
        os.makedirs(self.w["lineups"], exist_ok=True)
        for _, away, home, _ in world.GAMES:                # a default answer for each game: one line nobody can pick
            self.set_odds(away, home, [], "2026-10-11T17:00:00Z")
        os.environ.pop("ODDS_API_KEYS", None)
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

    def set_odds(self, away, home, lines, last_update):
        lines = list(lines) + [("player_shots_on_goal", world.name_of(home, 17), 0.5, -600, 400)]   # outside the gate
        world.write(os.path.join(self.w["odds"], "odds_%s_%s.json" % (away.lower(), home.lower())),
                    world.odds_payload(away, home, lines, last_update))

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
