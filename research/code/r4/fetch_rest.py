"""Fetch free NHL stats REST per-game logs into scratch (PC_R4_DIR/nhl): team summary 2024-25 + 2025-26,
skater summary 2024-25 (prior-season SOG/TOI) and skater realtime 2025-26 (missed / blocked attempts).
Paged by 7-day windows, 100 rows per call (the API's max), sorted by gameId + id. python3 -I fetch_rest.py"""
import json, os, time, urllib.request, urllib.parse
from datetime import date, timedelta
R4 = os.environ.get("PC_R4_DIR", "/tmp/claude-0/-home-claude/ab9b3f07-215a-50c7-96a2-d84b6c4f2d08/scratchpad/r4")
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

pull("team/summary", "20242025", date(2024, 10, 1), date(2025, 4, 20), "team_2425")
pull("team/summary", "20252026", date(2025, 10, 1), date(2026, 4, 20), "team_2526")
pull("skater/summary", "20242025", date(2024, 10, 1), date(2025, 4, 20), "skater_2425")
pull("skater/realtime", "20252026", date(2025, 10, 1), date(2026, 4, 20), "realtime_2526")
pull("skater/timeonice", "20252026", date(2025, 10, 1), date(2026, 4, 20), "toi_2526")
