"""Pull Hard Rock player_shots_alternate at the exact -45 snapshot already used for the main line (10 credits/game).
python3 -I pull_alt.py SET [limit]   SET = pre13 (pre-lockbox games with 1 PM prices) | lockbox13 | FILE of gids"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import oddsclient as oc  # noqa: E402
import rlib  # noqa: E402

which = sys.argv[1]
lim = int(sys.argv[2]) if len(sys.argv) > 2 else 10 ** 9
dates = {r["gid"]: r["date"] for r in rlib.load("shots45_lines.jsonl")}
g13 = sorted({r["gid"] for r in rlib.load("shots13_lines.jsonl")})
if which == "pre13":
    gids = [g for g in g13 if dates.get(g, "9") < rlib.LOCKBOX]
elif which == "lockbox13":
    gids = [g for g in g13 if dates.get(g, "0") >= rlib.LOCKBOX]
else:
    gids = [int(x) for x in open(which).read().split()]
m = json.load(open(os.path.join(oc.H, "raw", "odds", "match.json")))
n = 0
try:
    for g in gids:
        if n >= lim:
            break
        cf = os.path.join(oc.H, "raw", "research", "alt45", "%d.json" % g)
        if os.path.exists(cf):
            continue
        ts = json.load(open(os.path.join(oc.H, "raw", "odds", "shots45", "%d.json" % g)))["timestamp"]
        oc.get("/events/%s/odds" % m[str(g)]["event"], {"date": ts, "regions": "us2", "bookmakers": "hardrockbet",
               "markets": "player_shots_alternate", "oddsFormat": "american"}, cf, 10)
        n += 1
except oc.Stop as e:
    print("STOP", e)
print(which, "new calls", n, "remaining", oc.remaining())
