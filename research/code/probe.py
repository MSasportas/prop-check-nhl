"""Probe: which books post NHL shots (+ alt shots) in the historical feed, and the cost. python3 -I probe.py GID"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import oddsclient as oc
BOOKS = "hardrockbet,pinnacle,fanduel,draftkings,betmgm,williamhill_us,espnbet,fanatics,betrivers,betonlineag"
gid = sys.argv[1]
mk = sys.argv[2] if len(sys.argv) > 2 else "player_shots_on_goal,player_shots_alternate"
m = json.load(open(os.path.join(oc.H, "raw", "odds", "match.json")))[gid]
ts = json.load(open(os.path.join(oc.H, "raw", "odds", "shots45", gid + ".json")))["timestamp"]
cf = os.path.join(oc.H, "raw", "research", "probe", "%s_%s.json" % (gid, mk.replace(",", "+")))
js = oc.get("/events/%s/odds" % m["event"], {"date": ts, "regions": "us,us2,eu", "bookmakers": BOOKS, "markets": mk,
            "oddsFormat": "american"}, cf, 20)
print("snapshot", js and js.get("timestamp"), "want", ts)
for b in (js or {}).get("data", {}).get("bookmakers", []):
    for mm in b["markets"]:
        pts = sorted({o.get("point") for o in mm["outcomes"]})
        print(b["key"], mm["key"], len(mm["outcomes"]), "points", pts[:8])
print(open(oc.LEDGER).read().splitlines()[-1])
