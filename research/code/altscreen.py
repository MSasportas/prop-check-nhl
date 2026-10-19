"""Screen: Hard Rock alt-shots rung break-evens vs empirical tail frequency conditional on the main line's fair
(train months Oct-Feb only; lockbox outcomes never read). python3 -I altscreen.py ALT_JSON [ALT_JSON...]"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rlib  # noqa: E402

B = {}
for r in rlib.load("shots45_lines.jsonl"):
    if r["date"] >= rlib.LOCKBOX or r["result"] != "OK" or not r["ok"]:
        continue
    f = rlib.fair_prop(r["over"], r["under"])
    B.setdefault((r["line"], round(f * 40) / 40), []).append(r["actual"])


def emp(line, f, k):
    a = B.get((line, round(f * 40) / 40), [])
    return (sum(x >= k for x in a) / len(a), len(a)) if len(a) >= 60 else (None, len(a))


tot = []
for fn in sys.argv[1:]:
    d = json.load(open(fn))["data"]
    A, M = {}, {}
    for b in d["bookmakers"]:
        if b["key"] != "hardrockbet":
            continue
        for m in b["markets"]:
            for o in m["outcomes"]:
                if m["key"] == "player_shots_alternate":
                    A.setdefault(o["description"], {})[o["point"]] = o["price"]
                elif m["key"] == "player_shots_on_goal":
                    M.setdefault(o["description"], {})[o["name"]] = (o["point"], o["price"])
    for p, lad in A.items():
        if p not in M or len(M[p]) < 2:
            continue
        L = M[p]["Over"][0]
        f = rlib.fair_prop(M[p]["Over"][1], M[p]["Under"][1])
        for pt, pr in sorted(lad.items()):
            if pr < -200 or pt == L:
                continue
            e, n = emp(L, f, int(pt + 0.5))
            if e is None:
                continue
            tot.append((round(e - rlib.be(pr), 3), p, L, round(f, 3), pt, pr, round(rlib.be(pr), 3), round(e, 3), n))
tot.sort(reverse=True)
for t in tot:
    print(t)
