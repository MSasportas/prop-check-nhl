"""world.py: a small made-up league for the tests. No network, no key, nothing real.

build(root) writes, under `root`:
  data/state/stats_seed_20252026.json.gz   last season: 4 teams x 18 skaters x 40 games
  nhl/...                                  schedule, this-season stat rows, rosters (NHL API shapes)
  odds/...                                 events.json, pool.json (prices are added by tests)
Slate day is 2026-10-11 with two games: CAR at PHI 7:00 PM and VAN at NYR 8:00 PM (Eastern).
Every number is produced by simple arithmetic on the player id, so the world is the same every time.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "scripts"))

SEASON, LAST = 20262027, 20252026
SLATE = "2026-10-11"
TEAMS = {"CAR": "Carolina Hurricanes", "PHI": "Philadelphia Flyers", "VAN": "Vancouver Canucks", "NYR": "New York Rangers"}
TEAM_ID = {"CAR": 12, "PHI": 4, "VAN": 23, "NYR": 3}
GAMES = [(2026020901, "CAR", "PHI", "2026-10-11T23:00:00Z"), (2026020902, "VAN", "NYR", "2026-10-12T00:00:00Z")]
FIRST = ["Adam", "Ben", "Carl", "Dan", "Eli", "Finn", "Gus", "Hank", "Ian", "Jack", "Karl", "Leo",
         "Mats", "Nils", "Olli", "Pavel", "Quinn", "Remy"]


def pid_of(team, i):
    return 8480000 + list(TEAMS).index(team) * 100 + i


def players(team):
    """18 skaters: 12 forwards then 6 defensemen. Player i shoots more the lower i is."""
    out = []
    for i in range(18):
        out.append({"id": pid_of(team, i), "first": FIRST[i], "last": "%s%02d" % (team.title(), i),
                    "pos": "F" if i < 12 else "D", "team": team})
    return out


def line_for(team, i, g):
    """One game line for player i in his g-th game: (toi seconds, shots, goals, assists)."""
    base = 4 if i < 3 else 3 if i < 6 else 2 if i < 12 else 1
    toi = (1200 - 30 * i) if i < 12 else (1300 - 40 * (i - 12))
    shots = max(0, base + ((i * 7 + g * 3) % 3) - 1)
    goals = 1 if (i < 6 and (g + i) % 4 == 0) else 0
    assists = 1 if (i < 9 and (g + 2 * i) % 3 == 0) else 0
    return toi, shots, goals, assists


def skater_api_rows(team, opp, home, gid, date, g, skip=()):
    rows = []
    for p in players(team):
        i = p["id"] % 100
        if i in skip:
            continue
        toi, shots, goals, assists = line_for(team, i, g)
        rows.append({"playerId": p["id"], "skaterFullName": "%s %s" % (p["first"], p["last"]),
                     "positionCode": "D" if p["pos"] == "D" else "C", "gameId": gid, "gameDate": date,
                     "teamAbbrev": team, "opponentTeamAbbrev": opp, "homeRoad": "H" if home else "R",
                     "timeOnIcePerGame": float(toi), "shots": shots, "goals": goals, "assists": assists,
                     "points": goals + assists, "ppPoints": 0})
    return rows


def team_api_rows(gid, date, away, home, sk_away, sk_home):
    sa, sh = sum(r["shots"] for r in sk_away), sum(r["shots"] for r in sk_home)
    ga, gh = sum(r["goals"] for r in sk_away), sum(r["goals"] for r in sk_home)
    mk = lambda opp, hr, sf, sag, gf, gag: {"gameId": gid, "gameDate": date, "opponentTeamAbbrev": opp, "homeRoad": hr,
                                            "shotsForPerGame": float(sf), "shotsAgainstPerGame": float(sag),
                                            "goalsFor": gf, "goalsAgainst": gag, "teamId": 0}
    return [mk(home, "R", sa, sh, ga, gh), mk(away, "H", sh, sa, gh, ga)]


def sched_game(gid, away, home, start, state="FUT", sched="OK"):
    return {"id": gid, "season": SEASON, "gameType": 2, "startTimeUTC": start, "gameState": state,
            "gameScheduleState": sched, "awayTeam": {"abbrev": away, "id": TEAM_ID[away]},
            "homeTeam": {"abbrev": home, "id": TEAM_ID[home]}}


def schedule_doc(days):
    """days: {date: [games]} -> the NHL schedule answer."""
    return {"regularSeasonStartDate": "2026-09-29", "regularSeasonEndDate": "2027-04-10",
            "gameWeek": [{"date": d, "games": g} for d, g in sorted(days.items())]}


def write(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f)


def build(root, states=None, skip_this_season=None):
    """Write the world. states: {game_id: gameState} for today's games (default FUT).
    skip_this_season: {(team, game_number): [player index, ...]} players left out of a game this season."""
    import stats
    states = states or {}
    skip_this_season = skip_this_season or {}
    nhl = os.path.join(root, "nhl")
    data = os.path.join(root, "data")
    # ---- last season seed: each pair of teams meets 20 times -> 40 games per team
    sk, tm, gid = [], [], 2025020001
    pairs = [("CAR", "PHI"), ("VAN", "NYR"), ("CAR", "NYR"), ("VAN", "PHI")]
    count = {t: 0 for t in TEAMS}
    for rnd in range(10):
        for a, h in pairs:
            date = "2026-%02d-%02d" % (1 + rnd // 4, 1 + (rnd % 4) * 6 + pairs.index((a, h)))
            ra = skater_api_rows(a, h, False, gid, date, count[a])
            rh = skater_api_rows(h, a, True, gid, date, count[h])
            sk += ra + rh
            tm += team_api_rows(gid, date, a, h, ra, rh)
            count[a] += 1; count[h] += 1; gid += 1
    seed = stats.compact(LAST, sk, tm)
    out = {"last_season": LAST, "skater_fields": stats.SKF, "team_fields": stats.TMF, "players": seed["players"],
           "skaters": seed["skaters"], "teams": seed["teams"], "team_seasons": {}}
    path = os.path.join(data, "state", stats.seed_name(LAST))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    import gzip
    with gzip.GzipFile(path, "wb", mtime=0) as g:
        g.write(json.dumps(out).encode())
    # ---- this season: three game days before the slate
    past = [("2026-10-01", [(2026020001, "CAR", "PHI"), (2026020002, "VAN", "NYR")]),
            ("2026-10-05", [(2026020011, "PHI", "CAR"), (2026020012, "NYR", "VAN")]),
            ("2026-10-08", [(2026020021, "CAR", "NYR"), (2026020022, "VAN", "PHI")])]
    win = {"2026-09-29": ([], []), "2026-10-06": ([], [])}
    days = {}
    seen = {t: 0 for t in TEAMS}
    for date, games in past:
        w = "2026-09-29" if date <= "2026-10-05" else "2026-10-06"
        for gid2, a, h in games:
            ra = skater_api_rows(a, h, False, gid2, date, 40 + seen[a], skip_this_season.get((a, seen[a]), ()))
            rh = skater_api_rows(h, a, True, gid2, date, 40 + seen[h], skip_this_season.get((h, seen[h]), ()))
            win[w][0].extend(ra + rh)
            win[w][1].extend(team_api_rows(gid2, date, a, h, ra, rh))
            seen[a] += 1; seen[h] += 1
            days.setdefault(date, []).append(sched_game(gid2, a, h, date + "T23:00:00Z", "OFF"))
    for w, (s, t) in win.items():
        d1 = "2026-10-05" if w == "2026-09-29" else "2026-10-12"
        write(os.path.join(nhl, "skater_summary_%s_%s_%s.json" % (SEASON, w, d1)), s)
        write(os.path.join(nhl, "team_summary_%s_%s_%s.json" % (SEASON, w, d1)), t)
    today = [sched_game(g, a, h, st, states.get(g, "FUT")) for g, a, h, st in GAMES]
    later = {"2026-10-13": [sched_game(2026020911, "PHI", "VAN", "2026-10-13T23:00:00Z")],
             "2026-10-20": [sched_game(2026020921, "NYR", "CAR", "2026-10-20T23:00:00Z")]}
    write(os.path.join(nhl, "schedule_2026-10-11.json"), schedule_doc({SLATE: today, "2026-10-13": later["2026-10-13"]}))
    write(os.path.join(nhl, "schedule_2026-10-04.json"), schedule_doc({d: g for d, g in days.items() if d >= "2026-10-04"}))
    write(os.path.join(nhl, "schedule_2026-09-27.json"), schedule_doc({d: g for d, g in days.items() if d < "2026-10-04"}))
    write(os.path.join(nhl, "schedule_2026-10-18.json"), schedule_doc({"2026-10-20": later["2026-10-20"]}))
    write(os.path.join(nhl, "schedule_2026-10-25.json"), schedule_doc({}))
    for t in TEAMS:
        ps = players(t)
        mk = lambda p: {"id": p["id"], "firstName": {"default": p["first"]}, "lastName": {"default": p["last"]}}
        write(os.path.join(nhl, "roster_%s_current.json" % t),
              {"forwards": [mk(p) for p in ps if p["pos"] == "F"], "defensemen": [mk(p) for p in ps if p["pos"] == "D"],
               "goalies": [{"id": 8489000 + TEAM_ID[t], "firstName": {"default": "Goalie"}, "lastName": {"default": t}}]})
    odds_dir = os.path.join(root, "odds")
    write(os.path.join(odds_dir, "events.json"),
          [{"id": "ev%d" % g, "commence_time": st, "home_team": TEAMS[h], "away_team": TEAMS[a]} for g, a, h, st in GAMES])
    write(os.path.join(odds_dir, "pool.json"), {"keys": [500]})
    return {"root": root, "data": data, "nhl": nhl, "odds": odds_dir, "lineups": os.path.join(root, "lineups")}


def name_of(team, i):
    p = players(team)[i]
    return "%s %s" % (p["first"], p["last"])


def american_from_prob(b):
    """A break-even -> the American price with that break-even (rounded to a whole number)."""
    return int(round(-100 * b / (1 - b))) if b >= 0.5 else int(round(100 * (1 - b) / b))


def two_sided(fair_over, hold=0.07):
    """Book prices (over, under) for a fair over chance and a hold."""
    return american_from_prob(fair_over * (1 + hold)), american_from_prob((1 - fair_over) * (1 + hold))


def book_markets(lines, last_update):
    markets = {}
    for key, who, line, over, under in lines:
        m = markets.setdefault(key, {"key": key, "last_update": last_update, "outcomes": []})
        if over is not None:
            m["outcomes"].append({"name": "Over", "description": who, "price": over, "point": line})
        if under is not None:
            m["outcomes"].append({"name": "Under", "description": who, "price": under, "point": line})
    return list(markets.values())


def odds_payload(away, home, lines, last_update, event_id="ev", others=None, hr=True):
    """lines: [(market feed key, player name, line, over price, under price)] -> the feed's answer for one game.
    A price of None leaves that side out. others: {book key: lines} for other books (listed after Hard Rock).
    hr=False leaves Hard Rock out of the answer."""
    books = [{"key": "hardrockbet", "title": "Hard Rock Bet", "markets": book_markets(lines, last_update)}] if hr else []
    for book, blines in (others or {}).items():
        books.append({"key": book, "title": book, "markets": book_markets(blines, last_update)})
    return {"id": event_id, "home_team": TEAMS.get(home, home), "away_team": TEAMS.get(away, away),
            "bookmakers": books}


def boxscore(gid, away, home, stats_by_pid, state="OFF", missing=(), shootout=False):
    """stats_by_pid: {pid: (sog, goals, assists)}; everyone else gets 1 shot, 0 points. missing: pids scratched."""
    def side(team):
        fw, df, total = [], [], 0
        for p in players(team):
            if p["id"] in missing:
                continue
            sog, g, a = stats_by_pid.get(p["id"], (1, 0, 0))
            row = {"playerId": p["id"], "name": {"default": p["last"]}, "position": "C" if p["pos"] == "F" else "D",
                   "goals": g, "assists": a, "points": g + a, "sog": sog, "toi": "15:00"}
            (fw if p["pos"] == "F" else df).append(row)
            total += sog
        gk = {"playerId": 8489000 + TEAM_ID[team], "name": {"default": "G"}, "position": "G", "toi": "60:00",
              "saves": 25, "shotsAgainst": 27, "starter": True}
        return {"forwards": fw, "defense": df, "goalies": [gk]}, total
    a, sa = side(away)
    h, sh = side(home)
    return {"id": gid, "gameState": state, "gameScheduleState": "OK",
            "gameOutcome": {"lastPeriodType": "SO" if shootout else "REG"},
            "awayTeam": {"abbrev": away, "id": TEAM_ID[away], "sog": sa, "score": 3 if shootout else 2},
            "homeTeam": {"abbrev": home, "id": TEAM_ID[home], "sog": sh, "score": 2},
            "playerByGameStats": {"awayTeam": a, "homeTeam": h}}


def df_page(team, updated_iso, out=(), gtd=(), missing=()):
    """A Daily Faceoff line-combination page (pageProps) for one team. out / gtd / missing: player indexes."""
    ps, rows = players(team), []
    fw = [p for p in ps if p["pos"] == "F"]
    df = [p for p in ps if p["pos"] == "D"]
    for n, p in enumerate(fw + df):
        i = p["id"] % 100
        if i in missing:
            continue
        nm = "%s %s" % (p["first"], p["last"])
        if i in out:
            rows.append({"name": nm, "groupIdentifier": "ir", "categoryIdentifier": "oi", "injuryStatus": "out",
                         "gameTimeDecision": False})
            continue
        grp = ("f%d" % (1 + n // 3)) if p["pos"] == "F" else ("d%d" % (1 + (n - len(fw)) // 2))
        rows.append({"name": nm, "groupIdentifier": grp, "categoryIdentifier": "ev",
                     "injuryStatus": "dtd" if i in gtd else None, "gameTimeDecision": i in gtd})
    return {"slug": "x", "combinations": {"teamAbbreviation": team, "updatedAt": updated_iso, "players": rows}}
