"""Run 21 tests II1-II3 (registered in HYPOTHESES.md run 21, commit 573a981, before testing).
Inputs (scratch, PC_R21_DIR): h/work/shots45_lines.jsonl (hist tgz), nhl/skater_2526.jsonl (r14/fetch14.py, Feb 28 cut-off).
Lockbox rows (Mar 1+) never built or scored.  python3 -I ii21.py [placebo NAME T]"""
import contextlib, io, json, os, random, sys
from bisect import bisect_left
from collections import defaultdict
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import rlib, wf  # noqa: E402

D = os.environ["PC_R21_DIR"]
SK = [json.loads(l) for l in open(os.path.join(D, "nhl/skater_2526.jsonl"))]
SK = [r for r in SK if r["gameDate"] < rlib.LOCKBOX]
dressed = defaultdict(dict)      # (gid, team) -> {pid: row}
tgames = defaultdict(set)        # team -> {(date, gid)}
for r in SK:
    dressed[(r["gameId"], r["teamAbbrev"])][r["playerId"]] = r
    tgames[r["teamAbbrev"]].add((r["gameDate"], r["gameId"]))
tgames = {t: sorted(v) for t, v in tgames.items()}
tdates = {t: [x[0] for x in v] for t, v in tgames.items()}
plog = defaultdict(list)
for r in SK:
    plog[r["playerId"]].append((r["gameDate"], r["gameId"], r["shots"] or 0, r["timeOnIcePerGame"] or 0.0, r["teamAbbrev"]))
for v in plog.values():
    v.sort()
pdates = {p: [x[0] for x in v] for p, v in plog.items()}


def prior_team_games(t, d):
    return [g for _, g in tgames.get(t, [])[:bisect_left(tdates.get(t, []), d)]]


lines = [json.loads(l) for l in open(os.path.join(D, "h/work/shots45_lines.jsonl"))]
lines = [r for r in lines if r["date"] < rlib.LOCKBOX and r["over"] is not None and r["under"] is not None]
miss_lineup = 0
for r in lines:
    d, t, pid, gid = r["date"], r["team"], r["pid"], r["gid"]
    tg = prior_team_games(t, d)
    me = {x[1]: x for x in plog.get(pid, [])[:bisect_left(pdates.get(pid, []), d)]}
    tonight = dressed.get((gid, t), {})
    if not tonight:
        miss_lineup += 1
    # II1 teammate return
    ret, shb, runlen = 0.0, 0.0, 0
    if len(tg) >= 2:
        for j in tonight:
            if j == pid:
                continue
            if tg[-1] in dressed and False:
                pass
            if j in dressed[(tg[-1], t)] or j in dressed[(tg[-2], t)]:
                continue
            jg = [x for x in plog[j] if x[0] < d and x[4] == t]
            if len(jg) < 10 or np.mean([x[2] for x in jg]) < 2.0:
                continue
            ret += float(np.mean([x[2] for x in jg]))
            run = []
            for g in reversed(tg):
                if j in dressed[(g, t)]:
                    break
                run.append(g)
            run = run[:10]
            runlen = max(runlen, len(run))
            during = [me[g][2] for g in run if g in me]
            other = [x[2] for g, x in me.items() if g not in run and x[4] == t]
            if len(during) >= 2 and len(other) >= 5:
                shb = max(shb, float(np.mean(during) - np.mean(other)))
    r["ret"] = ret; r["shb"] = shb; r["runlen"] = runlen; r["retshb"] = ret * float(np.clip(shb, -2, 2))
    # II2 streakiness x form
    s = [x[2] for x in plog.get(pid, [])[:bisect_left(pdates.get(pid, []), d)]]
    ac, fm = 0.0, 0.0
    if len(s) >= 15:
        a = np.array(s, float); m = a.mean(); z = a - m
        den = float((z * z).sum())
        ac = float((z[1:] * z[:-1]).sum() / den) if den > 0 else 0.0
        fm = float(a[-5:].mean() - m)
    r["ac"] = ac; r["fm"] = fm; r["acfm"] = ac * fm
    # II3 11F/7D
    nF = sum(1 for x in tonight.values() if x["positionCode"] in ("C", "L", "R"))
    nD = sum(1 for x in tonight.values() if x["positionCode"] == "D")
    el = float(nF == 11 and nD == 7)
    isF = float(r["pos"] != "D")
    r["el"] = el; r["elF"] = el * isF; r["elD"] = el * (1 - isF)
    toi = [x[3] for x in plog.get(pid, [])[:bisect_left(pdates.get(pid, []), d)]][-10:]
    r["avg10"] = float(np.mean(toi)) if toi else 0.0
    r["nF"] = nF; r["nD"] = nD

feats = {"II1": lambda r: [r["ret"], r["retshb"]], "II2": lambda r: [r["fm"], r["acfm"]], "II3": lambda r: [r["elF"], r["elD"]]}
KEYS = {"II1": ["ret", "retshb"], "II2": ["fm", "acfm"], "II3": ["elF", "elD"]}


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


RULES = {"II1r": (lambda r: "under" if r["ret"] >= 2.0 and r["shb"] >= 0.5 and r["runlen"] >= 3 else None, ["ret", "shb", "runlen"]),
         "II2r": (lambda r: "over" if r["ac"] >= 0.15 and r["fm"] >= 0.8 else None, ["ac", "fm"]),
         "II3r": (lambda r: "over" if r["el"] and r["pos"] != "D" and r["avg10"] >= 960 else None, ["el", "avg10"])}

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
    print("lines", len(lines), "graded Nov-Feb lines", len(te), "lines with no dressed list for tonight", miss_lineup)
    for k in ["ret", "shb", "runlen", "ac", "fm", "el", "elF", "elD"]:
        a = np.array([r[k] for r in te], float)
        print("feature %s mean %.4f sd %.4f nonzero %d" % (k, a.mean(), a.std(), int((a != 0).sum())))
    from collections import Counter
    print("lineup shapes (nF,nD) on graded lines:", Counter((r["nF"], r["nD"]) for r in te).most_common(6))
    for n in ("II1", "II2", "II3"):
        wf.run(n, lines, feats[n])
    fixed("II1r UNDER teammate shooter returns, he gained >= .5 SOG/g during a 3+ game absence", RULES["II1r"][0])
    fixed("II2r OVER streaky (ac >= .15) and hot (last 5 >= +.8)", RULES["II2r"][0])
    fixed("II3r OVER forwards 16+ min when team dresses 11F/7D", RULES["II3r"][0])
