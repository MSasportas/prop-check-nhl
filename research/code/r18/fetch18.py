"""Run 18: free NHL data to scratch (PC_R18_DIR/nhl). Stats REST skater/timeonice + team/powerplay per-game 2025-26 (Oct 1 - Feb 28),
api-web daily schedules (tvBroadcasts) Oct 7 - Feb 28. Lockbox months never fetched.  python3 -I fetch18.py"""
import json, os, time, urllib.request, urllib.parse
from datetime import date, timedelta
OUT = os.path.join(os.environ["PC_R18_DIR"], "nhl"); os.makedirs(os.path.join(OUT, "sched"), exist_ok=True)
SORT = urllib.parse.quote(json.dumps([{"property": "gameId", "direction": "ASC"}, {"property": "%s", "direction": "ASC"}]))
BASE = "https://api.nhle.com/stats/rest/en/%s?isAggregate=false&isGame=true&limit=100&start=%d&sort=%s&cayenneExp=%s"


def get(url):
    for i in range(5):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (research)"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except Exception:
            time.sleep(2 + 3 * i)
    raise RuntimeError(url)


def pull(report, d0, d1, name):
    fn = os.path.join(OUT, name + ".jsonl")
    if os.path.exists(fn):
        return
    rows, d = [], d0
    while d <= d1:
        e = min(d + timedelta(days=6), d1)
        exp = urllib.parse.quote('seasonId=20252026 and gameTypeId=2 and gameDate>="%s" and gameDate<="%s 23:59:59"' % (d, e))
        st = 0
        while True:
            key = "teamId" if report.startswith("team") else "playerId"
            j = get(BASE % (report, st, SORT.replace("%25s", key), exp))
            rows += j["data"]
            if not j["data"]:
                break
            st += 100
            if st >= j["total"]:
                break
        d = e + timedelta(days=1)
    with open(fn + ".tmp", "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    os.replace(fn + ".tmp", fn)
    print(name, len(rows), flush=True)


d = date(2025, 10, 7)
while d <= date(2026, 2, 28):
    fn = os.path.join(OUT, "sched", "%s.json" % d)
    if not os.path.exists(fn):
        j = get("https://api-web.nhle.com/v1/schedule/%s" % d)
        day = [x for x in j["gameWeek"] if x["date"] == str(d)]
        gs = [{"gid": g["id"], "home": g["homeTeam"]["abbrev"], "away": g["awayTeam"]["abbrev"], "type": g.get("gameType"),
               "tv": [[b.get("market"), b.get("countryCode"), b.get("network")] for b in g.get("tvBroadcasts", [])]}
              for g in (day[0]["games"] if day else [])]
        json.dump(gs, open(fn, "w"))
    d += timedelta(days=1)
print("sched done", flush=True)
pull("team/powerplay", date(2025, 10, 1), date(2026, 2, 28), "teampp_2526")
pull("skater/timeonice", date(2025, 10, 1), date(2026, 2, 28), "toi_2526")
