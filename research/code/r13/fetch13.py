"""Run 13: fetch free NHL stats REST per-game logs into scratch (PC_R13_DIR/nhl), 2024-25 + 2025-26 through Feb 28 only
Reports: skater summary + goalie summary (both seasons). Lockbox months never fetched for 2025-26.
Paged by 7-day windows, 100 rows per call (the API's max), sorted by gameId + id. python3 -I fetch13.py"""
import json, os, time, urllib.request, urllib.parse
from datetime import date, timedelta
R4 = os.environ["PC_R13_DIR"]
OUT = os.path.join(R4, "nhl"); os.makedirs(OUT, exist_ok=True)
SORT = urllib.parse.quote(json.dumps([{"property": "gameId", "direction": "ASC"}, {"property": "%s", "direction": "ASC"}]))
BASE = "https://api.nhle.com/stats/rest/en/%s?isAggregate=false&isGame=true&limit=100&start=%d&sort=%s&cayenneExp=%s"

def get(url):
    for i in range(5):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (research)"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except Exception as e:
            time.sleep(2 + 3 * i)
    raise RuntimeError(url)

def pull(report, season, d0, d1, name):
    fn = os.path.join(OUT, name + ".jsonl")
    if os.path.exists(fn):
        return
    rows = []
    d = d0
    while d <= d1:
        e = min(d + timedelta(days=6), d1)
        exp = urllib.parse.quote('seasonId=%s and gameTypeId=2 and gameDate>="%s" and gameDate<="%s 23:59:59"' % (season, d, e))
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
    print(name, len(rows))

pull("skater/summary", "20242025", date(2024, 10, 1), date(2025, 4, 20), "skater_2425")
pull("skater/summary", "20252026", date(2025, 10, 1), date(2026, 2, 28), "skater_2526")
pull("goalie/summary", "20242025", date(2024, 10, 1), date(2025, 4, 20), "goalie_2425")
pull("goalie/summary", "20252026", date(2025, 10, 1), date(2026, 2, 28), "goalie_2526")
