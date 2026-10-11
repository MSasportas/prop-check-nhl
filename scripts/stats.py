"""stats.py: the store of per-game stat rows the model reads.

Two parts:
  data/state/stats_seed_<lastseason>.json.gz   last season's skater rows plus two seasons of team rows.
                                               Finished seasons never change, so this is built once and
                                               committed. Rebuilt from the NHL API if it is ever missing.
  data/state/stats/<season>/<window>.json.gz   this season, one file per fixed 7-day window. Only the
                                               window(s) holding newly finished games are re-fetched.
  data/state/stats_meta.json                   which team-games are verified, when we last looked.

A team-game counts as VERIFIED when both team rows exist, the team has skater rows, and the shots
add up: team shots = skater shots (+ shots by the team's goalies, read from play-by-play only when
the first sum is short by 1 or 2). A team whose finished games are not all verified is "behind" and
is left out of tonight's picks, by name.
"""
import glob
import os
from datetime import date, timedelta

import common
import nhl

SKF = ["pid", "gid", "date", "team", "opp", "home", "toi", "shots", "goals", "assists", "points"]
TMF = ["gid", "date", "team", "opp", "home", "sf", "sa", "gf", "ga"]


# ---------------------------------------------------------------- compact form
def compact(season, skater_api, team_api):
    """NHL API rows -> the small form we keep on disk."""
    players, skaters, teams = {}, [], []
    for s in skater_api or []:
        pid = s["playerId"]
        players[str(pid)] = [s.get("skaterFullName") or "", "D" if s.get("positionCode") == "D" else "F"]
        skaters.append([pid, s["gameId"], s["gameDate"][:10], s["teamAbbrev"], s["opponentTeamAbbrev"],
                        1 if s.get("homeRoad") == "H" else 0, int(round(s.get("timeOnIcePerGame") or 0)),
                        s.get("shots") or 0, s.get("goals") or 0, s.get("assists") or 0, s.get("points") or 0])
    # team/summary has no team abbreviation: a row's team is the OTHER row's opponent in that game
    by_game = {}
    for t in team_api or []:
        by_game.setdefault(t["gameId"], []).append(t)
    for gid, pair in by_game.items():
        if len(pair) != 2:
            continue                                        # one side missing: the game is not usable yet
        for me, other in ((pair[0], pair[1]), (pair[1], pair[0])):
            teams.append([gid, me["gameDate"][:10], other["opponentTeamAbbrev"], me["opponentTeamAbbrev"],
                          1 if me.get("homeRoad") == "H" else 0,
                          int(round(me.get("shotsForPerGame") or 0)), int(round(me.get("shotsAgainstPerGame") or 0)),
                          me.get("goalsFor") or 0, me.get("goalsAgainst") or 0])
    skaters.sort(key=lambda r: (r[2], r[1], r[0]))
    teams.sort(key=lambda r: (r[1], r[0], r[2]))
    return {"season": season, "skater_fields": SKF, "team_fields": TMF,
            "players": players, "skaters": skaters, "teams": teams}


# ---------------------------------------------------------------- paths
def seed_name(last_season):
    return "stats_seed_%s.json.gz" % last_season


def find_seed(last_season):
    """The seed is read from the data dir, or from the repo's committed copy (dry runs use a scratch dir)."""
    for base in (common.data_dir(), common.REPO_DATA):
        p = os.path.join(base, "state", seed_name(last_season))
        if os.path.exists(p):
            return p
    return None


def window_dir(season):
    return common.dpath("state", "stats", str(season))


def meta_path():
    return common.dpath("state", "stats_meta.json")


def windows(season_start, upto):
    """Fixed 7-day windows from the season's first day: [(d0, d1), ...] up to and including `upto`."""
    out, d = [], date.fromisoformat(season_start)
    end = date.fromisoformat(upto)
    while d <= end:
        out.append((d.isoformat(), (d + timedelta(days=6)).isoformat()))
        d += timedelta(days=7)
    return out


# ---------------------------------------------------------------- the seed (last season, immutable)
def _season_bounds(season):
    """First and last regular-season date of a finished season, asked from the schedule endpoint."""
    y = int(str(season)[4:])
    wk = nhl.schedule_week("%d-03-01" % y)
    if not wk or not wk.get("season_start") or not wk.get("season_end"):
        return None
    return wk["season_start"][:10], wk["season_end"][:10]


def build_seed(last_season, cache_dir=None):
    """Build the committed seed file. cache_dir: a folder of saved NHL responses (the Data Scientist's
    cache) to use instead of downloading. Returns a short note, or raises RuntimeError on failure."""
    prev_season = last_season - 10001

    def from_cache(report, season):
        rows, files = [], sorted(glob.glob(os.path.join(cache_dir, "%s_%s_*.json" % (report.replace("/", "_"), season))))
        if not files:
            raise RuntimeError("no cached %s files for %s" % (report, season))
        for fn in files:
            rows += common.read_json(fn, [])
        return rows

    def from_api(report, season):
        b = _season_bounds(season)
        if not b:
            raise RuntimeError("season dates for %s not available" % season)
        rows = []
        for d0, d1 in windows(b[0], b[1]):
            part = nhl.stats_report(report, season, d0, d1)
            if part is None:
                raise RuntimeError("%s %s %s failed" % (report, season, d0))
            rows += part
        return rows

    get = from_cache if cache_dir else from_api
    last = compact(last_season, get("skater/summary", last_season), get("team/summary", last_season))
    prev = compact(prev_season, [], get("team/summary", prev_season))
    if len(last["skaters"]) < 30000 or len(last["teams"]) < 2000 or len(prev["teams"]) < 2000:
        raise RuntimeError("seed looks too small (%d skater rows, %d + %d team rows)"
                           % (len(last["skaters"]), len(last["teams"]), len(prev["teams"])))
    out = {"last_season": last_season, "skater_fields": SKF, "team_fields": TMF,
           "players": last["players"], "skaters": last["skaters"],
           "teams": prev["teams"] + last["teams"],
           "team_seasons": {str(prev_season): len(prev["teams"]), str(last_season): len(last["teams"])}}
    common.write_gz_json(common.dpath("state", seed_name(last_season)), out)
    return "seed built: %d skater rows, %d team rows" % (len(out["skaters"]), len(out["teams"]))


# ---------------------------------------------------------------- this season (incremental)
def verify_window(doc, meta, fetch_pbp=True):
    """Check every team-game in one window file. Returns ({"gid:TEAM": True}, {"gid:TEAM": reason})."""
    shots, counts = {}, {}
    for r in doc["skaters"]:
        k = "%s:%s" % (r[1], r[3])
        shots[k] = shots.get(k, 0) + r[7]
        counts[k] = counts.get(k, 0) + 1
    ok, bad = {}, {}
    gs_cache = meta.setdefault("goalie_shots", {})
    for t in doc["teams"]:
        k = "%s:%s" % (t[0], t[2])
        if counts.get(k, 0) < 12:
            bad[k] = "skater rows missing"
            continue
        diff = t[5] - shots[k]
        if diff == 0:
            ok[k] = True
        elif diff < 0:
            bad[k] = "skater shots above team shots"
        elif diff > 2:
            bad[k] = "skater shots short of team shots"
        else:
            if k not in gs_cache and fetch_pbp:
                pbp = nhl.play_by_play(t[0])
                g = nhl.goalie_shots(pbp, t[2]) if pbp else None
                if g is not None:
                    gs_cache[k] = g
            if k not in gs_cache:
                bad[k] = "play-by-play not available"
            elif gs_cache[k] == diff:
                ok[k] = True
            else:
                bad[k] = "shots still off after goalie shots"
    return ok, bad


def expected_team_games(sched_games, season):
    """{"gid:TEAM": date} for every finished regular-season game in the schedule cache."""
    out = {}
    for g in sched_games:
        if g.get("season") == season and g.get("type") == nhl.REGULAR and g.get("sched") == "OK" \
                and g.get("state") in ("OFF", "FINAL"):
            out["%s:%s" % (g["id"], g["away"])] = g["date"]
            out["%s:%s" % (g["id"], g["home"])] = g["date"]
    return out


def update_season(season, season_start, sched_games, now, ops):
    """Fetch the window(s) that hold finished games we do not have verified yet.
    Returns dict(status ok|skipped|failed, note). Never raises for a source failure."""
    meta = common.read_json(meta_path(), {}) or {}
    if meta.get("season") != season:
        meta = {"season": season, "verified": {}, "bad": {}, "goalie_shots": {}}
    meta.setdefault("verified", {}); meta.setdefault("bad", {})
    expected = expected_team_games(sched_games, season)
    missing = {k: d for k, d in expected.items() if k not in meta["verified"]}
    bad_retry = timedelta(hours=ops.get("stats_bad_retry_hours", 6))
    due = {}
    for k, d in missing.items():
        b = meta["bad"].get(k)
        if b and b["reason"] != "skater rows missing" and common.parse_iso(b["at"]) + bad_retry > now >= common.parse_iso(b["at"]):
            continue                                        # shots do not add up: look again later, not every run
        due[k] = d
    if not due:
        return {"status": "skipped", "note": "nothing new" if not missing else "%d team-games held" % len(missing)}
    last = common.parse_iso(meta.get("last_attempt_at"))
    if last and now - last < timedelta(minutes=ops.get("stats_retry_min", 10)) and now >= last:
        return {"status": "skipped", "note": "waiting to retry"}
    meta["last_attempt_at"] = common.iso(now)
    todo = sorted({w for w in windows(season_start, max(due.values())) if any(w[0] <= d <= w[1] for d in due.values())})
    failed, changed = [], False
    for d0, d1 in todo:
        sk = nhl.stats_report("skater/summary", season, d0, d1)
        tm = nhl.stats_report("team/summary", season, d0, d1) if sk is not None else None
        if sk is None or tm is None:
            failed.append(d0)
            continue
        doc = compact(season, sk, tm)
        ok, bad = verify_window(doc, meta)
        path = os.path.join(window_dir(season), "%s.json.gz" % d0)
        if common.read_gz_json(path) != doc:
            common.write_gz_json(path, doc)
            changed = True
        for k in ok:
            if k not in meta["verified"]:
                meta["verified"][k] = 1
                changed = True
            meta["bad"].pop(k, None)
        for k, why in bad.items():
            meta["bad"][k] = {"reason": why, "at": common.iso(now)}
    if changed:
        meta["built_at"] = common.iso(now)
    still = [k for k in expected if k not in meta["verified"]]
    done_dates = sorted({d for k, d in expected.items()})
    through = None
    for d in done_dates:
        if any(expected[k] == d for k in still):
            break
        through = d
    meta["through"] = through
    meta["waiting"] = sorted(still)[:40]
    common.write_json(meta_path(), meta)
    if failed and not changed:
        return {"status": "failed", "note": "NHL stats did not answer for %d window(s)" % len(failed)}
    note = "%d window(s) read" % (len(todo) - len(failed))
    if still:
        note += ", %d team-games still missing" % len(still)
    return {"status": "ok", "note": note}


def team_status(season, sched_games, slate):
    """-> (behind: {team: reason}, through date, built_at). Uses only games dated before the slate date
    plus anything already final: a team is behind if any of its finished games is not verified."""
    meta = common.read_json(meta_path(), {}) or {}
    verified = meta.get("verified", {}) if meta.get("season") == season else {}
    bad = meta.get("bad", {})
    behind = {}
    for k, d in expected_team_games(sched_games, season).items():
        if k not in verified:
            team = k.split(":")[1]
            why = (bad.get(k) or {}).get("reason")
            behind[team] = "stats check failed" if why and why != "skater rows missing" else "stats behind"
    return behind, meta.get("through"), meta.get("built_at")


# ---------------------------------------------------------------- reading
class Store:
    """All rows in memory. skaters[pid] and teams[abbrev] are lists of dicts sorted oldest first."""

    def __init__(self):
        self.players, self.skaters, self.teams = {}, {}, {}
        self.loaded = []

    def add(self, doc, season_of=None):
        for pid, v in doc.get("players", {}).items():
            self.players[int(pid)] = {"name": v[0], "pos": v[1]}
        for r in doc.get("skaters", []):
            self.skaters.setdefault(r[0], []).append(
                {"season": int(str(r[1])[:4]) * 10001 + 1, "gid": r[1], "date": r[2], "team": r[3], "opp": r[4],
                 "home": bool(r[5]), "toi": r[6], "shots": r[7], "goals": r[8], "assists": r[9], "points": r[10]})
        for t in doc.get("teams", []):
            self.teams.setdefault(t[2], []).append(
                {"season": int(str(t[0])[:4]) * 10001 + 1, "gid": t[0], "date": t[1], "opp": t[3], "home": bool(t[4]),
                 "sf": t[5], "sa": t[6], "gf": t[7], "ga": t[8]})

    def finish(self):
        for rows in self.skaters.values():
            rows.sort(key=lambda r: (r["date"], r["gid"]))
        for rows in self.teams.values():
            rows.sort(key=lambda r: (r["date"], r["gid"]))
        return self


def load(season):
    """Seed (last season) + every window file of this season. Returns (Store, problems list)."""
    st, problems = Store(), []
    seed = find_seed(season - 10001)
    doc = common.read_gz_json(seed) if seed else None
    if doc:
        st.add(doc)
        st.loaded.append(os.path.basename(seed))
    else:
        problems.append("last season's stats are missing")
    for fn in sorted(glob.glob(os.path.join(window_dir(season), "*.json.gz"))):
        doc = common.read_gz_json(fn)
        if doc:
            st.add(doc)
            st.loaded.append(os.path.basename(fn))
        else:
            problems.append("could not read %s" % os.path.basename(fn))
    return st.finish(), problems
