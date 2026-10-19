"""S7-probe: Hard Rock saves vs other books' de-vigged consensus at the same -45 snapshot (prices only)."""
import json, glob, os, sys
from collections import defaultdict
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from rlib import be, dec
R3 = "/tmp/claude-0/-home-claude/ab9b3f07-215a-50c7-96a2-d84b6c4f2d08/scratchpad/r3pull"
evs, books_seen, n_hr, n_cmp, n_diffpt = [], defaultdict(int), 0, 0, 0
for f in sorted(glob.glob(R3 + "/ev/saves_*.json")):
    d = json.load(open(f))
    if not d or not d.get("data"):
        continue
    L = defaultdict(dict)  # (player) -> book -> (point, over, under)
    for b in d["data"]["bookmakers"]:
        books_seen[b["key"]] += 1
        for m in b["markets"]:
            tmp = defaultdict(dict)
            for o in m["outcomes"]:
                tmp[(o["description"], o.get("point"))][o["name"]] = o["price"]
            for (pl, pt), pr in tmp.items():
                if "Over" in pr and "Under" in pr:
                    L[pl][b["key"]] = (pt, pr["Over"], pr["Under"])
    for pl, bk in L.items():
        if "hardrockbet" not in bk:
            continue
        n_hr += 1
        pt, o, u = bk["hardrockbet"]
        same = [be(x[1]) / (be(x[1]) + be(x[2])) for k, x in bk.items() if k != "hardrockbet" and x[0] == pt]
        diff = [x[0] for k, x in bk.items() if k != "hardrockbet" and x[0] != pt]
        n_diffpt += bool(diff)
        if len(same) >= 2:
            n_cmp += 1
            fo = np.mean(same)
            evs += [fo * dec(o) - 1, (1 - fo) * dec(u) - 1]
            print("%-22s HR %.1f %+d/%+d  cons fair over %.3f (n%d)  EV over %+.3f under %+.3f  other pts %s" % (
                pl[:22], pt, o, u, fo, len(same), fo * dec(o) - 1, (1 - fo) * dec(u) - 1, sorted(set(diff))))
ev = np.array(evs)
print("books:", dict(books_seen))
print("HR goalie lines %d, comparable (>=2 books same point) %d, with another book at a different point %d" % (n_hr, n_cmp, n_diffpt))
print("sides %d, EV mean %+.3f, max %+.3f, share EV>=0 %.1f%%" % (len(ev), ev.mean(), ev.max(), 100 * (ev >= 0).mean()))
