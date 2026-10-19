"""Build h2h rows: one per (game, snapshot) with Hard Rock + other books, consensus/Pinnacle fair, result."""
import json, glob, os
from datetime import datetime
SCR = "/tmp/claude-0/-home-claude/ab9b3f07-215a-50c7-96a2-d84b6c4f2d08/scratchpad"
NHL = SCR + "/hist/raw/nhl"
R3 = SCR + "/r3pull"
match = json.load(open(SCR + "/r3/raw/odds/match.json"))
ev2gid = {v["event"]: int(k) for k, v in match.items()}
games = {g["id"]: g for g in json.load(open(NHL + "/games.json"))}


def be(a):
    return -a / (-a + 100.0) if a < 0 else 100.0 / (a + 100.0)


def ts(s):
    return datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S")


res = {}
for f in glob.glob(NHL + "/box/*.json"):
    b = json.load(open(f))
    if b.get("gameState") not in ("OFF", "FINAL"):
        continue
    res[b["id"]] = (b["homeTeam"]["score"], b["awayTeam"]["score"], (b.get("gameOutcome") or {}).get("lastPeriodType"))
rows, unmatched = [], 0
for f in sorted(glob.glob(R3 + "/feat/h2h_*.json")):
    d = json.load(open(f))
    snap = d["timestamp"]
    for ev in d["data"]:
        gid = ev2gid.get(ev["id"])
        if gid is None:
            unmatched += 1
            continue
        hrs = (ts(ev["commence_time"]) - ts(snap)).total_seconds() / 3600
        if hrs <= 0.25:
            continue
        books = {}
        for bk in ev["bookmakers"]:
            for m in bk["markets"]:
                if m["key"] != "h2h":
                    continue
                pr = {o["name"]: o["price"] for o in m["outcomes"]}
                if ev["home_team"] in pr and ev["away_team"] in pr:
                    books[bk["key"]] = (pr[ev["home_team"]], pr[ev["away_team"]])
        if "hardrockbet" not in books or gid not in res:
            continue
        fairs = {}
        for k, (h, a) in books.items():
            fairs[k] = be(h) / (be(h) + be(a))
        oth = [v for k, v in fairs.items() if k != "hardrockbet"]
        g = games[gid]
        hs, as_, lpt = res[gid]
        rows.append({"gid": gid, "date": g["date"], "snap": snap, "hrs": round(hrs, 2), "home": g["home"], "away": g["away"],
                     "hr_h": books["hardrockbet"][0], "hr_a": books["hardrockbet"][1], "n_oth": len(oth),
                     "cons_h": sum(oth) / len(oth) if oth else None, "pin_h": fairs.get("pinnacle"),
                     "hr_fair_h": fairs["hardrockbet"], "books": books, "home_win": hs > as_, "hs": hs, "as": as_, "lpt": lpt})
out = R3 + "/h2h_rows.jsonl"
with open(out, "w") as fo:
    for r in rows:
        fo.write(json.dumps(r) + "\n")
late = [r for r in rows if r["hrs"] <= 6]
early = [r for r in rows if 18 <= r["hrs"] <= 34]
print("rows", len(rows), "unmatched", unmatched, "late", len(late), "early", len(early),
      "games late", len({r['gid'] for r in late}), "games early", len({r['gid'] for r in early}))
