"""Probe deviation frequency (prices only) at a given snapshot time. python3 -I probe2.py GID ISO_TIME TAG"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import oddsclient as oc
BOOKS = "hardrockbet,pinnacle,fanduel,draftkings,betmgm,williamhill_us,espnbet,fanatics,betrivers,betonlineag"
gid, ts, tag = sys.argv[1], sys.argv[2], sys.argv[3]
m = json.load(open(os.path.join(oc.H, "raw", "odds", "match.json")))[gid]
cf = os.path.join(oc.H, "raw", "research", "probe", "%s_%s_shots.json" % (gid, tag))
js = oc.get("/events/%s/odds" % m["event"], {"date": ts, "regions": "us", "bookmakers": BOOKS, "markets": "player_shots_on_goal",
            "oddsFormat": "american"}, cf, 10)
print(gid, tag, "snapshot", js and js.get("timestamp"), "commence", m["commence"])
print(cf)
