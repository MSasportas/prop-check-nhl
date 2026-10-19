"""Price-only look at a cached multi-book response: Hard Rock edge vs other-book consensus (no results used)."""
import json, statistics as st, sys
def ip(a): return 100 / (a + 100) if a > 0 else -a / (-a + 100)
d = json.load(open(sys.argv[1]))["data"]
P = {}
for b in d["bookmakers"]:
    for m in b["markets"]:
        for o in m["outcomes"]:
            P.setdefault((m["key"], o["description"], o.get("point")), {}).setdefault(b["key"], {})[o["name"]] = o["price"]
out = {}
for k, v in P.items():
    h = v.get("hardrockbet")
    if not h or len(h) < 2:
        continue
    f = [ip(x["Over"]) / (ip(x["Over"]) + ip(x["Under"])) for bk, x in v.items() if bk != "hardrockbet" and len(x) == 2 and "Over" in x]
    if len(f) < 2:
        continue
    c = st.mean(f)
    hold = ip(h["Over"]) + ip(h["Under"]) - 1
    e = max(c - ip(h["Over"]), (1 - c) - ip(h["Under"]))
    out.setdefault(k[0], []).append((round(e, 3), round(hold, 3), len(f), h["Over"], h["Under"], k[1]))
for mk, rows in out.items():
    rows.sort(reverse=True)
    print(mk, "n", len(rows), "mean hold %.3f" % st.mean(r[1] for r in rows), "edge>=0:", sum(r[0] >= 0 for r in rows), "edge>=.02:", sum(r[0] >= .02 for r in rows))
    print("   top", rows[:4])
