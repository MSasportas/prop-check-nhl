"""R4 (alt rungs vs NB tails from Hard Rock's own main line) and R4b (stale alt ladder). Walk-forward Nov-Feb;
Oct games are training only. Lockbox games are not in the pulled set. python3 -I r4.py"""
import json, os, sys
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rlib  # noqa: E402
import nbtail  # noqa: E402

D = os.path.join(rlib.RAW, "research", "alt45")
main = {(r["gid"], r["name"]): r for r in rlib.load("shots45_lines.jsonl") if r["ok"]}
allrows = [r for r in main.values() if r["result"] == "OK" and r["date"] < rlib.LOCKBOX]
lad = []
for f in sorted(os.listdir(D)):
    gid = int(f[:-5])
    d = json.load(open(os.path.join(D, f)))
    data = d.get("data") if isinstance(d.get("data"), dict) else {}
    for b in data.get("bookmakers", []):
        for m in b["markets"]:
            if m["key"] != "player_shots_alternate":
                continue
            for o in m["outcomes"]:
                if o["name"] != "Over":
                    continue
                r = main.get((gid, o["description"]))
                if r is None:
                    continue
                lad.append({"gid": gid, "date": r["date"], "name": o["description"], "pt": o["point"], "price": o["price"], "row": r})
print("rungs with a main line", len(lad), "games", len({x["gid"] for x in lad}))
rfit = {}
for m in rlib.TEST_MONTHS:
    tr = [(r["line"], rlib.fair_prop(r["over"], r["under"]), r["actual"]) for r in allrows if r["date"][:7] < m]
    import random
    random.seed(7)
    tr = random.sample(tr, min(len(tr), 5000))
    rfit[m] = nbtail.fit_r(tr)[0]
print("NB r by test month", rfit)
res = defaultdict(list)
stale = []
for x in lad:
    r = x["row"]
    mo = x["date"][:7]
    if r["result"] != "OK" or x["price"] < -200:
        continue
    win = r["actual"] > x["pt"]
    L = r["line"]
    f = rlib.fair_prop(r["over"], r["under"])
    if x["pt"] == L and x["price"] > r["over"]:
        stale.append(x)
        if mo in rlib.TEST_MONTHS or True:
            res["R4b" + ("" if mo in rlib.TEST_MONTHS else "_oct")].append(rlib.bet(x["gid"], x["date"], x["price"], win, pt=x["pt"]))
    if mo not in rlib.TEST_MONTHS:
        continue
    rr = rfit[mo]
    q = nbtail.nb_sf(int(x["pt"] + 0.5), nbtail.mu_for(L, f, rr), rr)
    ev = q * rlib.dec(x["price"]) - 1
    for T in (0.02, 0.04):
        if ev >= T:
            res["R4 T=%.2f" % T].append(rlib.bet(x["gid"], x["date"], x["price"], win, pt=x["pt"], ev=ev))
    res["all rungs (ref)"].append(rlib.bet(x["gid"], x["date"], x["price"], win, pt=x["pt"], ev=ev))
# R4b2: stale player -> also higher rungs with EV >= 0
st = {(x["gid"], x["name"]) for x in stale}
for x in lad:
    r = x["row"]
    mo = x["date"][:7]
    if (x["gid"], x["name"]) not in st or r["result"] != "OK" or x["price"] < -200 or mo not in rlib.TEST_MONTHS:
        continue
    if x["pt"] < r["line"]:
        continue
    rr = rfit[mo]
    f = rlib.fair_prop(r["over"], r["under"])
    q = nbtail.nb_sf(int(x["pt"] + 0.5), nbtail.mu_for(r["line"], f, rr), rr)
    if x["pt"] == r["line"] or q * rlib.dec(x["price"]) - 1 >= 0:
        res["R4b2"].append(rlib.bet(x["gid"], x["date"], x["price"], r["actual"] > x["pt"], pt=x["pt"]))
for k, b in sorted(res.items()):
    s = rlib.summ(b)
    evm = (sum(z.get("ev", 0) for z in b) / len(b)) if b and "ev" in b[0] else None
    print("%-16s %s | %s%s" % (k, rlib.fmt(s), rlib.by_month(b), "" if evm is None else " | mean model EV %+.3f" % evm))
print("stale-ladder rungs (alt > main over at main point):", len(stale), "of", sum(1 for x in lad if x["pt"] == x["row"]["line"]))
for x in stale[:12]:
    print("  ", x["date"], x["name"], x["pt"], "alt", x["price"], "main", x["row"]["over"], x["row"]["under"])
mev = [rlib.fair_prop(x["row"]["over"], x["row"]["under"]) * rlib.dec(x["price"]) - 1 for x in stale if x["price"] >= -200]
print("stale rungs: mean mechanical EV vs Hard Rock's own main-line fair %+.3f (n %d); rate per player-game %.2f%%" % (
    sum(mev) / len(mev), len(mev), 100 * len(stale) / sum(1 for x in lad if x["pt"] == x["row"]["line"])))
