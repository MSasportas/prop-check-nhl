"""Run 18 tests FF1-FF4 (registered in HYPOTHESES.md run 18, commit f4ed035, before testing).
Inputs (scratch, PC_R18_DIR): h/work/shots45_lines.jsonl (hist tgz), nhl/sched/*.json, nhl/teampp_2526.jsonl, nhl/toi_2526.jsonl
(r18/fetch18.py, Feb 28 cut-off). Lockbox rows (Mar 1+) never built or scored.  python3 -I ff18.py [placebo NAME T]"""
import contextlib, io, json, os, random, sys
from bisect import bisect_left
from collections import defaultdict
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import rlib, wf  # noqa: E402

D = os.environ["PC_R18_DIR"]; N = os.path.join(D, "nhl")
J = lambda f: [json.loads(l) for l in open(os.path.join(N, f))]

# FF2 schedule / TV
TV = {}
for f in os.listdir(os.path.join(N, "sched")):
    for g in json.load(open(os.path.join(N, "sched", f))):
        tv = g["tv"]
        TV[g["gid"]] = (any(m == "N" and c == "US" and n != "NHLN" for m, c, n in tv), any(m == "N" and c == "CA" for m, c, n in tv))

# FF3 team PP opportunities per team-game
pp = J("teampp_2526.jsonl")
bygame = defaultdict(list)
for r in pp:
    bygame[r["gameId"]].append(r)
tpp = defaultdict(list)  # abbrev -> [(date, ppopp)]
for gid, rs in bygame.items():
    if len(rs) != 2:
        continue
    for a, b in ((rs[0], rs[1]), (rs[1], rs[0])):
        tpp[b["opponentTeamAbbrev"]].append((a["gameDate"][:10], a["ppOpportunities"] or 0))
for v in tpp.values():
    v.sort()
lg = sorted(x for v in tpp.values() for x in v); lgd = [x[0] for x in lg]; lgc = np.cumsum([x[1] for x in lg])


def lgpp(d):
    i = bisect_left(lgd, d); return lgc[i - 1] / i if i else 3.0


def odraw(o, d):
    v = tpp.get(o, []); i = bisect_left([x[0] for x in v], d); last = v[max(0, i - 10):i]
    return (np.mean([x[1] for x in last]) if len(last) >= 3 else lgpp(d)) - lgpp(d)


sh = defaultdict(list)
for r in J("toi_2526.jsonl"):
    sh[r["playerId"]].append((r["gameDate"][:10], (r["shTimeOnIce"] or 0) / 60.0))
for v in sh.values():
    v.sort()
shd = {k: [x[0] for x in v] for k, v in sh.items()}


def shs(pid, d):
    v = sh.get(pid, []); i = bisect_left(shd.get(pid, []), d); last = v[max(0, i - 10):i]
    return float(np.mean([x[1] for x in last])) if len(last) >= 3 else 0.0


FL = {"FLA", "TBL"}
lines = [json.loads(l) for l in open(os.path.join(D, "h/work/shots45_lines.jsonl"))]
lines = [r for r in lines if r["date"] < rlib.LOCKBOX and r["over"] is not None and r["under"] is not None]
miss = 0
for r in lines:
    d = r["date"]
    r["own"], r["oppfl"] = float(r["team"] in FL), float(r["opp"] in FL)
    t = TV.get(r["gid"]); miss += t is None
    r["natus"], r["natca"] = (float(t[0]), float(t[1])) if t else (0.0, 0.0)
    r["shs"] = shs(r["pid"], d); r["odraw"] = float(odraw(r["opp"], d)); r["shx"] = r["shs"] * r["odraw"]
    tf = (r["etoi"] / 60.0 - 16.0) if (r.get("etoi") and r.get("pos") == "F") else 0.0
    r["tfa"], r["tfh"] = (0.0 if r["home"] else tf), (tf if r["home"] else 0.0)

feats = {"FF1": lambda r: [r["own"], r["oppfl"]], "FF2": lambda r: [r["natus"], r["natca"]],
         "FF3": lambda r: [r["shs"], r["shx"]], "FF4": lambda r: [r["tfa"], r["tfh"]]}
KEYS = {"FF1": ["own", "oppfl"], "FF2": ["natus", "natca"], "FF3": ["shs", "shx"], "FF4": ["tfa", "tfh"]}


def fixed(name, rule):
    b = []
    for r in lines:
        if r["date"][:7] not in rlib.TEST_MONTHS or r["result"] != "OK" or not r["ok"]:
            continue
        side = rule(r)
        if side is None or r[side] < -200:
            continue
        b.append(rlib.bet(r["gid"], r["date"], r[side], (r["actual"] > r["line"]) == (side == "over"), side=side, line=r["line"]))
    s = rlib.summ(b)
    print("%s %s | %s | p_one %s" % (name, rlib.fmt(s), rlib.by_month(b), s.get("p_one")), flush=True)
    return b


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "placebo":
        name, T = sys.argv[2], float(sys.argv[3])
        rr = rlib.summ(wf.run(name, lines, feats[name], Ts=(T,), verbose=False)[T])["roi"]
        rng = random.Random(7); out = []; grp = defaultdict(list)
        for r in lines:
            grp[(r["date"], r["line"])].append(r)
        ks = KEYS[name]; orig = {k: [r[k] for r in lines] for k in ks}
        for it in range(200):
            for gg in grp.values():
                idx = list(range(len(gg))); rng.shuffle(idx)
                vals = {k: [gg[j][k] for j in idx] for k in ks}
                for j, r in enumerate(gg):
                    for k in ks:
                        r[k] = vals[k][j]
            with contextlib.redirect_stdout(io.StringIO()):
                b = wf.run(name, lines, feats[name], Ts=(T,), verbose=False)[T]
            out.append(rlib.summ(b)["roi"] or 0.0)
            for k in ks:
                for r, x in zip(lines, orig[k]):
                    r[k] = x
        out = np.array(out)
        print("placebo %s T=%.2f real %+.2f%% shuffled mean %+.2f%% sd %.2f >= real %d/200" % (
            name, T, 100 * rr, 100 * out.mean(), 100 * out.std(), int((out >= rr).sum())))
        sys.exit()
    te = [r for r in lines if r["date"][:7] in rlib.TEST_MONTHS and r["result"] == "OK"]
    print("lines", len(lines), "graded Nov-Feb lines", len(te), "no schedule row", miss)
    for k in ["own", "oppfl", "natus", "natca", "shs", "odraw", "tfa", "tfh"]:
        a = np.array([r[k] for r in te], float)
        print("feature %s mean %.4f sd %.4f nonzero %d" % (k, a.mean(), a.std(), int((a != 0).sum())))
    for n in ("FF1", "FF2", "FF3", "FF4"):
        wf.run(n, lines, feats[n])
    fixed("FF1r UNDER on FLA/TBL players", lambda r: "under" if r["own"] else None)
    fixed("FF2r UNDER in US national-TV games", lambda r: "under" if r["natus"] else None)
    fixed("FF3r UNDER when shs >= 1.5 and odraw >= +0.4", lambda r: "under" if r["shs"] >= 1.5 and r["odraw"] >= 0.4 else None)
    fixed("FF4r UNDER on road forwards etoi >= 19 min", lambda r: "under" if (not r["home"] and r["tfa"] >= 3.0) else None)
