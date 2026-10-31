"""Run 16: fetch api-web play-by-play + right-rail for 2025-26 regular-season games dated Oct 7 - Feb 28 into scratch
(PC_R16_DIR/nhl/pbp/<gid>.json, compact). Lockbox games never fetched. python3 -I fetch16.py"""
import json, os, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
D = os.path.join(os.environ["PC_R16_DIR"], "nhl", "pbp"); os.makedirs(D, exist_ok=True)

def get(url):
    for i in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (research)"}), timeout=60) as r:
                return json.load(r)
        except Exception:
            time.sleep(2 + 3 * i)
    raise RuntimeError(url)

gids = {}
d = date(2025, 10, 7)
while d <= date(2026, 2, 28):
    j = get("https://api-web.nhle.com/v1/schedule/%s" % d)
    for wk in j["gameWeek"]:
        if date(2025, 10, 7) <= date.fromisoformat(wk["date"]) <= date(2026, 2, 28):
            for g in wk["games"]:
                if g["gameType"] == 2:
                    gids[g["id"]] = wk["date"]
    d += timedelta(days=7)
print("games", len(gids))

def one(gid):
    fn = os.path.join(D, "%d.json" % gid)
    if os.path.exists(fn):
        return
    p = get("https://api-web.nhle.com/v1/gamecenter/%d/play-by-play" % gid)
    rr = get("https://api-web.nhle.com/v1/gamecenter/%d/right-rail" % gid)
    keep = [{"t": x["typeDescKey"], "per": x["periodDescriptor"]["number"], "pt": x["periodDescriptor"].get("periodType"),
             "tm": x["timeInPeriod"], "sc": x.get("situationCode"), "d": {k: v for k, v in (x.get("details") or {}).items()
             if k in ("shootingPlayerId", "eventOwnerTeamId", "scoringPlayerId", "typeCode", "duration", "homeScore", "awayScore")}}
            for x in p["plays"] if x["typeDescKey"] in ("shot-on-goal", "missed-shot", "blocked-shot", "goal", "penalty", "stoppage", "period-start")]
    gi = rr.get("gameInfo", {})
    out = {"gid": gid, "date": gids[gid], "home": p["homeTeam"]["abbrev"], "away": p["awayTeam"]["abbrev"],
           "hid": p["homeTeam"]["id"], "aid": p["awayTeam"]["id"], "start": p["startTimeUTC"],
           "refs": [r["fullName"]["default"] for r in gi.get("referees", [])],
           "hcoach": (gi.get("homeTeam", {}).get("headCoach") or {}).get("default"),
           "acoach": (gi.get("awayTeam", {}).get("headCoach") or {}).get("default"), "plays": keep}
    json.dump(out, open(fn + ".tmp", "w")); os.replace(fn + ".tmp", fn)

with ThreadPoolExecutor(8) as ex:
    list(ex.map(one, sorted(gids)))
print("done", len(os.listdir(D)))
