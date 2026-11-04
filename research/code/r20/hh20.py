"""Run 20 tests HH1-HH3 (registered in HYPOTHESES.md run 20, commit 3e76dea, before testing).
Inputs (scratch, PC_R20_DIR): h/work/shots45_lines.jsonl (hist tgz), nhl/pbp/<gid>.json (r20/fetch20.py, Feb 28 cut-off),
nhl/skater_2526.jsonl (r14/fetch14.py, Feb 28 cut-off). Lockbox rows (Mar 1+) never built or scored.
python3 -I hh20.py [placebo NAME T]"""
import contextlib, io, json, os, random, sys
from bisect import bisect_left
from collections import defaultdict
from datetime import date
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import rlib, wf  # noqa: E402

D = os.environ["PC_R20_DIR"]
# skater per-game logs: TOI and player -> team per game
SK = [json.loads(l) for l in open(os.path.join(D, "nhl/skater_2526.jsonl"))]
SK = [r for r in SK if r["gameDate"] < rlib.LOCKBOX]
pteam = {(r["gameId"], r["playerId"]): r["teamAbbrev"] for r in SK}
plog = defaultdict(list)  # pid -> [(date, gid, toi)]
for r in SK:
    plog[r["playerId"]].append((r["gameDate"], r["gameId"], r["timeOnIcePerGame"] or 0.0))
for v in plog.values():
    v.sort()
pdates = {p: [x[0] for x in v] for p, v in plog.items()}

P = os.path.join(D, "nhl/pbp")
G = {}
for f in os.listdir(P):
    j = json.load(open(os.path.join(P, f)))
    if j["date"] < rlib.LOCKBOX:
        G[j["gid"]] = j

A = {}  # (gid, team) -> per-game aggregates
for gid, g in G.items():
    ab = {g["hid"]: g["home"], g["aid"]: g["away"]}
    other = {g["home"]: g["away"], g["away"]: g["home"]}
    for t in (g["home"], g["away"]):
        A[(gid, t)] = {"date": g["date"], "att": defaultdict(int), "blkd": defaultdict(int), "attT": 0, "blocks": 0,
                       "goals": 0, "sog": 0, "opp": other[t]}
    for x in g["plays"]:
        if x["pt"] == "SO" or x["t"] not in ("shot-on-goal", "goal", "missed-shot", "blocked-shot"):
            continue
        pid = x["d"].get("shootingPlayerId") or x["d"].get("scoringPlayerId")
        t = pteam.get((gid, pid)) if pid else None
        if t not in other:
            t = ab.get(x["d"].get("eventOwnerTeamId")) if x["t"] != "blocked-shot" else None
        if t not in other:
            continue
        a = A[(gid, t)]
        a["attT"] += 1
        if pid:
            a["att"][pid] += 1
        if x["t"] == "blocked-shot":
            A[(gid, other[t])]["blocks"] += 1
            if pid:
                a["blkd"][pid] += 1
        if x["t"] in ("shot-on-goal", "goal"):
            a["sog"] += 1
        if x["t"] == "goal":
            a["goals"] += 1

sched = defaultdict(list)
for (gid, t), a in A.items():
    sched[t].append((a["date"], gid))
for v in sched.values():
    v.sort()
sd = {t: [x[0] for x in v] for t, v in sched.items()}


def prev(t, d, k=None):
    i = bisect_left(sd.get(t, []), d); lo = 0 if k is None else max(0, i - k)
    return [gid for _, gid in sched.get(t, [])[lo:i]]


# league means before d (by date, cached)
dates = sorted({a["date"] for a in A.values()})
_lg = {}


def league(d):
    if d in _lg:
        return _lg[d]
    # player blocked share: mean over players with >= 20 attempts in their team's last 20 games is costly; use pooled ratio over
    # eligible players computed from all team-games before d (pooled blocked / attempts of players with >= 20 attempts season-to-date)
    pa, pb = defaultdict(int), defaultdict(int); tb, ta = 0, 0
    for (gid, t), a in A.items():
        if a["date"] < d:
            for p, n in a["att"].items():
                pa[p] += n; pb[p] += a["blkd"][p]
            tb += a["blocks"]; ta += A[(gid, a["opp"])]["attT"]
    el = [pb[p] / pa[p] for p in pa if pa[p] >= 20]
    _lg[d] = (float(np.mean(el)) if el else 0.25, tb / ta if ta else 0.25)
    return _lg[d]


lines = [json.loads(l) for l in open(os.path.join(D, "h/work/shots45_lines.jsonl"))]
lines = [r for r in lines if r["date"] < rlib.LOCKBOX and r["over"] is not None and r["under"] is not None and r["gid"] in G]
for r in lines:
    d, t, o, pid = r["date"], r["team"], r["opp"], r["pid"]
    # HH1 short last game
    lt, avg10 = 1.0, 0.0
    pl = plog.get(pid, []); i = bisect_left(pdates.get(pid, []), d)
    tp = prev(t, d)
    if i >= 6 and tp and pl[i - 1][1] == tp[-1]:
        prior = [x[2] for x in pl[max(0, i - 11):i - 1]]
        if len(prior) >= 5 and np.mean(prior) > 0:
            avg10 = float(np.mean(prior)); lt = pl[i - 1][2] / avg10
    r["lt"] = lt; r["avg10"] = avg10; r["short"] = float(lt < 0.6); r["ltc"] = min(lt, 1.5) - 1
    # HH2 lanes
    lgbs, lgob = league(d)
    pg = prev(t, d, 20)
    att = sum(A[(x, t)]["att"].get(pid, 0) for x in pg); blk = sum(A[(x, t)]["blkd"].get(pid, 0) for x in pg)
    bs = blk / att if att >= 20 else lgbs
    og = prev(o, d, 20)
    ob = 0.0
    if len(og) >= 5:
        b = sum(A[(x, o)]["blocks"] for x in og); f = sum(A[(x, A[(x, o)]["opp"])]["attT"] for x in og)
        ob = (b / f if f else lgob) - lgob
    r["bs"] = bs; r["bsc"] = bs - lgbs; r["ob"] = ob; r["bsob"] = r["bsc"] * ob
    # HH3 opponent after blowout
    r["oblow"] = 0.0; r["osog"] = 0.0
    og = prev(o, d)
    if og:
        last = og[-1]; la = A[(last, o)]; lo = A[(last, la["opp"])]
        if (date.fromisoformat(d) - date.fromisoformat(la["date"])).days <= 4:
            r["oblow"] = float(lo["goals"] - la["goals"] >= 3)
            r["osog"] = float(lo["sog"] >= 35)

feats = {"HH1": lambda r: [r["short"], r["ltc"]], "HH2": lambda r: [r["bsc"], r["bsob"]], "HH3": lambda r: [r["oblow"], r["osog"]]}
KEYS = {"HH1": ["short", "ltc"], "HH2": ["bsc", "bsob"], "HH3": ["oblow", "osog"]}


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
    print("%s %s | %s | p_one %s" % (name, rlib.fmt(s), rlib.by_month(b), s.get("p_one")))
    return b


def placebo_fixed(name, rule, keys, reps=200):
    real = rlib.summ(fixed(name, rule))["roi"]
    rng = random.Random(7); grp = defaultdict(list); out = []
    for r in lines:
        grp[(r["date"], r["line"])].append(r)
    orig = {k: [r[k] for r in lines] for k in keys}
    for _ in range(reps):
        for gg in grp.values():
            idx = list(range(len(gg))); rng.shuffle(idx)
            vals = {k: [gg[j][k] for j in idx] for k in keys}
            for j, r in enumerate(gg):
                for k in keys:
                    r[k] = vals[k][j]
        with contextlib.redirect_stdout(io.StringIO()):
            out.append(rlib.summ(fixed(name, rule))["roi"] or 0.0)
        for k in keys:
            for r, x in zip(lines, orig[k]):
                r[k] = x
    out = np.array(out)
    print("placebo %s real %+.2f%% shuffled mean %+.2f%% sd %.2f >= real %d/%d" % (name, 100 * real, 100 * out.mean(), 100 * out.std(),
          int((out >= real).sum()), reps))


RULES = {"HH1r": (lambda r: "over" if r["lt"] < 0.6 and r["avg10"] >= 720 else None, ["lt", "avg10"]),
         "HH2r": (lambda r: "over" if r["bs"] >= 0.30 and r["ob"] <= -0.03 else None, ["bs", "ob"]),
         "HH3r": (lambda r: "under" if r["oblow"] else None, ["oblow"])}

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "placebo":
        name = sys.argv[2]
        if name in RULES:
            placebo_fixed(name, *RULES[name]); sys.exit()
        T = float(sys.argv[3])
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
    print("games", len(G), "lines", len(lines), "graded Nov-Feb lines", len(te))
    for k in ["lt", "short", "bs", "ob", "oblow", "osog"]:
        a = np.array([r[k] for r in te], float)
        print("feature %s mean %.4f sd %.4f nonzero %d" % (k, a.mean(), a.std(), int((a != 0).sum())))
    print("league blocked share / team block rate at Feb 28:", [round(x, 4) for x in league("2026-02-28")])
    for n in ("HH1", "HH2", "HH3"):
        wf.run(n, lines, feats[n])
    fixed("HH1r OVER lt < .6 and avg10 >= 12 min", RULES["HH1r"][0])
    fixed("HH2r OVER bs >= .30 and ob <= -.03", RULES["HH2r"][0])
    fixed("HH3r UNDER vs opponent off a 3+ goal loss", RULES["HH3r"][0])
