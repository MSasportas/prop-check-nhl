"""R10: follow Hard Rock's own 1 PM -> -45 move. Pre-lockbox games only. python3 -I r10.py"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rlib  # noqa: E402
a = {(r["gid"], r["pid"]): r for r in rlib.load("shots13_lines.jsonl") if r["ok"]}
b = {(r["gid"], r["pid"]): r for r in rlib.load("shots45_lines.jsonl") if r["ok"]}
res = {d: [] for d in (0.005, 0.02, 0.04)}
for k, r1 in a.items():
    r2 = b.get(k)
    if not r2 or r2["date"] >= rlib.LOCKBOX or r2["result"] != "OK":
        continue
    f1, f2 = rlib.fair_prop(r1["over"], r1["under"]), rlib.fair_prop(r2["over"], r2["under"])
    for d in res:
        if r2["line"] != r1["line"]:
            side = "under" if r2["line"] < r1["line"] else "over"   # line lowered = book expects fewer shots
        elif f2 - f1 >= d:
            side = "over"
        elif f1 - f2 >= d:
            side = "under"
        else:
            continue
        pr = r2[side]
        if pr < -200:
            continue
        res[d].append(rlib.bet(r2["gid"], r2["date"], pr, (r2["actual"] > r2["line"]) == (side == "over"), side=side))
for d, x in res.items():
    print("R10 d=%.3f %s | %s | overs %d" % (d, rlib.fmt(rlib.summ(x)), rlib.by_month(x), sum(z["side"] == "over" for z in x)))
