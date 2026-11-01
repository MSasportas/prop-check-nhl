#!/usr/bin/env python3
"""Q17a-c (HYPOTHESES.md run 17): Q1b bets split by minutes from the read to the game's first goalie confirmation.
Needs a full (unshallow) clone (git history of data/state/goalies.json). Reads research/fwd/scores.json (run score_fwd.py first).
Scored on nights >= 2026-11-01. `--check` also prints the same split on earlier (seen) nights: a code check, NOT a result.
Writes research/fwd/q17.md.   python3 -I research/code/r17/score_q17.py [repo_root] [--check]"""
import importlib.util, json, os, random, subprocess, sys
from datetime import datetime
args = [a for a in sys.argv[1:] if not a.startswith("--")]; CHECK = "--check" in sys.argv
ROOT = os.path.abspath(args[0] if args else os.path.join(os.path.dirname(__file__), "..", "..", ".."))
START, BAR_N, ALPHA = "2026-11-01", 300, 0.05 / 34
iso = lambda s: datetime.fromisoformat(s.replace("Z", "+00:00"))
git = lambda *a: subprocess.run(["git", "-C", ROOT] + list(a), capture_output=True, text=True, check=True).stdout
spec = importlib.util.spec_from_file_location("sf", os.path.join(ROOT, "research/code/fwd/score_fwd.py"))
sys.argv = [sys.argv[0], ROOT]; sf = importlib.util.module_from_spec(spec); spec.loader.exec_module(sf)

vers = []
for line in git("log", "--format=%H %cI", "--", "data/state/goalies.json").split("\n"):
    if line.strip():
        h, t = line.split()
        try:
            vers.append((iso(t), json.loads(git("show", "%s:data/state/goalies.json" % h))))
        except Exception:
            pass
vers.sort(key=lambda x: x[0])
teams = {}
for fn in os.listdir(os.path.join(ROOT, "data/odds")):
    if fn.endswith(".json"):
        for f in json.load(open(os.path.join(ROOT, "data/odds", fn))).get("fetches", []):
            teams[f["game_id"]] = (f["away"], f["home"])


def first_conf(date, game):
    if game not in teams:
        return None
    for t, d in vers:
        if d.get("date") == date and any(((d.get("teams") or {}).get(x) or {}).get("status") == "confirmed" for x in teams[game]):
            return t
    return None


def stats(bs):
    g = [b for b in bs if b.get("pl") is not None]
    if not g:
        return dict(n=len(bs), graded=0)
    games = {}
    for b in g:
        games.setdefault((b["date"], b["game"]), []).append(b["pl"])
    keys = list(games); rng = random.Random(11); hits = 0; boots = []
    for _ in range(2000):
        s = [x for k in (rng.choice(keys) for _ in keys) for x in games[k]]
        r = sum(s) / len(s); boots.append(r); hits += r <= 0
    boots.sort(); roi = sum(b["pl"] for b in g) / len(g)
    clv = [b["clv"] for b in g if b.get("clv") is not None]; mc = sum(clv) / len(clv) if clv else None; p = hits / 2000
    return dict(n=len(bs), graded=len(g), roi=roi, lo=boots[100], hi=boots[1899], p=p, clv=mc,
                cand=len(g) >= BAR_N and roi > 0 and p < ALPHA and (mc or 0) > 0)


q1b = json.load(open(os.path.join(ROOT, "research/fwd/scores.json")))["bets"]["Q1b"]
starts = {}
for d in sorted({b["date"] for b in q1b}):
    starts.update({(d, k): v for k, v in sf.shadow(d)[1].items()})
for b in q1b:
    at = iso(b["at"]); c = first_conf(b["date"], b["game"]); st = starts.get((b["date"], b["game"]))
    st = iso(st) if isinstance(st, str) else st
    if c is not None and (st is None or c < st):
        b["lead"] = (c - at).total_seconds() / 60
    elif st is not None:
        b["lead"] = (st - at).total_seconds() / 60
    else:
        b["lead"] = None
split = lambda bs: {"Q17a lead >= 60": [b for b in bs if b["lead"] is not None and b["lead"] >= 60],
                    "Q17b 0 < lead < 60": [b for b in bs if b["lead"] is not None and 0 < b["lead"] < 60],
                    "Q17c lead <= 0": [b for b in bs if b["lead"] is not None and b["lead"] <= 0]}


def table(bs, title):
    out = [title, "", "| variant | bets | graded | ROI | 90% CI | p | mean CLV | candidate |", "|---|---|---|---|---|---|---|---|"]
    for k, v in split(bs).items():
        s = stats(v)
        if s["graded"]:
            out.append("| %s | %d | %d | %+.1f%% | %+.0f..%+.0f%% | %.3f | %s | %s |" % (k, s["n"], s["graded"], 100 * s["roi"], 100 * s["lo"],
                       100 * s["hi"], s["p"], "-" if s["clv"] is None else "%.4f" % s["clv"], s["cand"]))
        else:
            out.append("| %s | %d | 0 | - | - | - | - | False |" % (k, s["n"]))
    out.append("no lead (no start, no confirmation): %d" % sum(b["lead"] is None for b in bs))
    return out


out = table([b for b in q1b if b["date"] >= START], "# Q17 forward (research/code/r17/score_q17.py), nights >= %s. Bar: n >= 300, ROI > 0, "
            "p < %.5f, CLV > 0. goalies.json versions read: %d." % (START, ALPHA, len(vers)))
open(os.path.join(ROOT, "research/fwd/q17.md"), "w").write("\n".join(out) + "\n")
print("\n".join(out))
if CHECK:
    print("\n".join(table([b for b in q1b if b["date"] < START], "\n# CODE CHECK ONLY (seen nights < %s, not a result)" % START)))
