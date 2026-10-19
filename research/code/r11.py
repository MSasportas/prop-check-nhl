"""R11: saves vs the shots props. Walk-forward Nov-Feb on the saves sample (pre-lockbox). python3 -I r11.py"""
import json, os, sys
from collections import defaultdict
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rlib  # noqa: E402
import nbtail  # noqa: E402

shots = defaultdict(list)
gdate = {}
for r in rlib.load("shots45_lines.jsonl"):
    gdate[r["gid"]] = r["date"]
    if r["ok"]:
        shots[(r["gid"], r["team"])].append(nbtail.mu_for(r["line"], rlib.fair_prop(r["over"], r["under"]), 20))
tsog = {}
for (gid, team) in shots:
    f = os.path.join(rlib.RAW, "nhl", "box", "%d.json" % gid)
    if os.path.exists(f):
        b = json.load(open(f))
        for s in ("awayTeam", "homeTeam"):
            tsog[(gid, b[s]["abbrev"])] = b[s].get("sog")
sv = [r for r in rlib.load("saves45_lines.jsonl") if r["ok"] and r["date"] < rlib.LOCKBOX]
for r in sv:
    m = shots.get((r["gid"], r["opp"]), [])
    r["sum_mu"], r["n_listed"] = sum(m), len(m)
print("saves lines pre-lockbox", len(sv), "graded", sum(r["result"] == "OK" for r in sv))
res = {T: [] for T in (0.01, 0.02, 0.03)}
for mo in rlib.TEST_MONTHS:
    tr = [r for r in sv if r["date"][:7] < mo and r["result"] == "OK" and r["n_listed"] >= 4]
    te = [r for r in sv if r["date"][:7] == mo and r["result"] == "OK" and r["n_listed"] >= 4]
    # ratio from all shots games before the month (team SOG / listed sum)
    pairs = [(tsog[k], sum(v)) for k, v in shots.items() if k in tsog and tsog[k] is not None and len(v) >= 4
             and gdate.get(k[0], "9") < mo]   # games before the test month only
    ratio = np.mean([a for a, b in pairs]) / np.mean([b for a, b in pairs])
    feat = lambda r: (r["sum_mu"] * ratio * 0.9 - r["line"]) / np.sqrt(r["line"])
    X = lambda rs: np.array([[1.0, float(rlib.logit(rlib.fair_prop(r["over"], r["under"]))), feat(r)] for r in rs])
    if len(tr) < 30 or not te:
        continue
    w = rlib.fit_logit(X(tr), [r["actual"] > r["line"] for r in tr], l2=2.0)
    q = rlib.predict(w, X(te))
    print(mo, "train", len(tr), "test", len(te), "w", np.round(w, 3).tolist(), "ratio %.3f" % ratio)
    for r, p in zip(te, q):
        for T in res:
            for side, pr, ps in (("over", r["over"], p), ("under", r["under"], 1 - p)):
                if pr >= -200 and ps - rlib.be(pr) >= T:
                    res[T].append(rlib.bet(r["gid"], r["date"], pr, (r["actual"] > r["line"]) == (side == "over"), side=side))
for T, b in res.items():
    print("R11 T=%.2f %s | %s" % (T, rlib.fmt(rlib.summ(b)), rlib.by_month(b)))
