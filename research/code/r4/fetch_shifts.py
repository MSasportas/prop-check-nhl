"""K12: fetch free NHL shift charts for 2025-26 regular-season games before the lockbox (Mar 1 2026) and reduce each game to
shared seconds between same-team skaters (overlapping shifts, all strengths). Writes R4/nhl/shared_2526.jsonl, one line per
game: {"gid", "date", "pairs": [[pid_a, pid_b, seconds], ...], "skaters": [pid, ...]}. Resumable. python3 -I fetch_shifts.py"""
import json
import os
import time
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

R4 = os.environ.get("PC_R4_DIR", "/tmp/claude-0/-home-claude/ab9b3f07-215a-50c7-96a2-d84b6c4f2d08/scratchpad/r4")
BOX = os.environ.get("PC_BOX_DIR", "/tmp/claude-0/-home-claude/ab9b3f07-215a-50c7-96a2-d84b6c4f2d08/scratchpad/hist/raw/nhl")
OUT = os.path.join(R4, "nhl", "shared_2526.jsonl")
URL = "https://api.nhle.com/stats/rest/en/shiftcharts?cayenneExp=gameId=%d"


def sec(t):
    m, s = t.split(":")
    return int(m) * 60 + int(s)


def goalies(gid):
    b = json.load(open(os.path.join(BOX, "box", "%d.json" % gid)))
    return {p["playerId"] for side in ("awayTeam", "homeTeam") for p in b["playerByGameStats"][side].get("goalies", [])}


def one(g):
    gid = g["id"]
    for i in range(5):
        try:
            req = urllib.request.Request(URL % gid, headers={"User-Agent": "Mozilla/5.0 (research)"})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.load(r)["data"]
            break
        except Exception:
            time.sleep(2 + 3 * i)
    else:
        return None
    gk = goalies(gid)
    sh = defaultdict(list)   # (team, pid) -> [(start, end)] in game seconds
    for s in data:
        if s.get("typeCode") != 517 or not s.get("startTime") or not s.get("endTime") or s["playerId"] in gk:
            continue
        p0 = (s["period"] - 1) * 1200
        a, b = p0 + sec(s["startTime"]), p0 + sec(s["endTime"])
        if b > a:
            sh[(s["teamAbbrev"], s["playerId"])].append((a, b))
    pairs = []
    keys = sorted(sh)
    for i, ka in enumerate(keys):
        for kb in keys[i + 1:]:
            if ka[0] != kb[0]:
                continue
            tot = 0
            for a0, a1 in sh[ka]:
                for b0, b1 in sh[kb]:
                    o = min(a1, b1) - max(a0, b0)
                    if o > 0:
                        tot += o
            if tot > 0:
                pairs.append([ka[1], kb[1], tot])
    return {"gid": gid, "date": g["date"], "pairs": pairs, "skaters": [k[1] for k in keys]}


def main():
    done = set()
    if os.path.exists(OUT):
        done = {json.loads(l)["gid"] for l in open(OUT)}
    games = [g for g in json.load(open(os.path.join(BOX, "games.json")))
             if g["id"] // 10000 % 100 == 2 and g["date"] < "2026-03-01" and g["id"] not in done
             and os.path.exists(os.path.join(BOX, "box", "%d.json" % g["id"]))]
    print("to fetch", len(games))
    with open(OUT, "a") as f, ThreadPoolExecutor(6) as ex:
        for k, res in enumerate(ex.map(one, games)):
            if res and res["pairs"]:
                f.write(json.dumps(res) + "\n")
            if k % 100 == 0:
                print(k, flush=True)


if __name__ == "__main__":
    main()
