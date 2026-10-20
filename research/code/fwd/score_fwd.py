#!/usr/bin/env python3
"""Forward scorer for the registered live-feed tests Q1a-m and Q2a-b (research/HYPOTHESES.md, run 5).

Re-scores EVERY night to date (data/odds/<date>.json that carry `others`) each time it runs, so the daily Researcher run only has to
call it. Read-only on data/; writes research/fwd/scores.json and research/fwd/scores.md. No key is read or needed.

  python3 -I research/code/fwd/score_fwd.py [repo_root]

Definitions mirror the registration exactly (do not change them without registering a new variant).
"""
import json, os, random, statistics, subprocess, sys
from datetime import datetime, timezone

ROOT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "..", ".."))
STALE_MIN = 60.0
CONS_HOLD = (0.0, 0.15)
PIN = "pinnacle"
BONF = 15
BAR_N = 300
BOOT = 2000


def iso(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def dec(a):
    return 1 + a / 100.0 if a > 0 else 1 + 100.0 / -a


def fair_over(o, u):
    a, b = 1 / dec(o), 1 / dec(u)
    return a / (a + b)


def hold(o, u):
    return 1 / dec(o) + 1 / dec(u) - 1


def median(xs):
    xs = sorted(xs)
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2.0


def pairs(outcomes):
    out = {}
    for x in outcomes or []:
        if x.get("pid") is None or x.get("price") is None:
            continue
        out.setdefault((x["pid"], float(x["line"])), {})[x["side"]] = x["price"]
    return {k: v for k, v in out.items() if "over" in v and "under" in v}


def load(p):
    with open(p) as f:
        return json.load(f)


def dates():
    d = sorted(f[:-5] for f in os.listdir(os.path.join(ROOT, "data/odds")) if f.endswith(".json"))
    keep = []
    for x in d:
        doc = load(os.path.join(ROOT, "data/odds", x + ".json"))
        if any("others" in f for f in doc.get("fetches", [])):
            keep.append(x)
    return keep


# ---------------------------------------------------------------- reads -> per (read, line) consensus
def reads_for(date):
    doc = load(os.path.join(ROOT, "data/odds", date + ".json"))
    out = []
    for f in doc["fetches"]:
        if "others" not in f:
            continue
        hr = (f.get("markets") or {}).get("shots")
        if not hr:
            continue
        at = iso(f["at"])
        books = {}
        for b, mks in (f.get("others") or {}).items():
            mk = (mks or {}).get("shots")
            if not mk:
                continue
            lu = mk.get("last_update")
            if not lu or (at - iso(lu)).total_seconds() / 60.0 >= STALE_MIN:
                continue
            for k, p in pairs(mk.get("outcomes")).items():
                if CONS_HOLD[0] <= hold(p["over"], p["under"]) <= CONS_HOLD[1]:
                    books.setdefault(k, {})[b] = fair_over(p["over"], p["under"])
        for k, p in pairs(hr.get("outcomes")).items():
            fb = books.get(k, {})
            out.append({"date": date, "game": f["game_id"], "pull": f["pull"], "at": at, "pid": k[0], "line": k[1],
                        "over": p["over"], "under": p["under"], "hr_fair": fair_over(p["over"], p["under"]),
                        "books": len(fb), "cons": median(fb.values()) if fb else None,
                        "pin": fb.get(PIN), "fairs": fb})
    out.sort(key=lambda r: r["at"])
    return out


def shadow(date):
    p = os.path.join(ROOT, "data/shadow", date + ".json")
    if not os.path.exists(p):
        return {}, {}
    doc = load(p)
    res, start = {}, {}
    for r in doc["rows"]:
        if r["market"] != "shots":
            continue
        res[(r["game_id"], r["pid"], float(r["line"]))] = r
        st = (r.get("ctx") or {}).get("start")
        if st:
            start[r["game_id"]] = iso(st)
    return res, start


def grade(row, side, line, price):
    """+profit / -1 / None (void or not final)."""
    if not row or not row.get("result"):
        return None
    r = row["result"]
    toi = r.get("toi")
    if r.get("actual") is None or not toi or toi.replace(":", "").strip("0") == "":
        return None
    won = (r["actual"] > line) if side == "over" else (r["actual"] < line)
    return dec(price) - 1 if won else -1.0


def ev(fair_side, price):
    return fair_side * dec(price) - 1


# ---------------------------------------------------------------- Q1
Q1 = {}
for i, x in enumerate([0.0, 0.01, 0.02, 0.03, 0.05]):
    Q1["Q1" + "abcde"[i]] = dict(kind="med", X=x, B=1)
    Q1["Q1" + "fghij"[i]] = dict(kind="med", X=x, B=4)
Q1["Q1k"] = dict(kind="pin", X=0.0)
Q1["Q1l"] = dict(kind="pin", X=0.02)
Q1["Q1m"] = dict(kind="gap", X=0.03, B=4)


def qualifies(v, r, side, price):
    if price < -200:
        return None
    fs = lambda f: f if side == "over" else 1 - f
    if v["kind"] == "med":
        if r["cons"] is None or r["books"] < v["B"]:
            return None
        e = ev(fs(r["cons"]), price)
    elif v["kind"] == "pin":
        if r["pin"] is None:
            return None
        e = ev(fs(r["pin"]), price)
    else:
        if r["pull"] not in ("B", "C") or r["cons"] is None or r["books"] < v["B"] or r["pin"] is None or price > 120:
            return None
        if ev(fs(r["pin"]), price) < 0:
            return None
        e = ev(fs(r["cons"]), price)
    return e if e >= v["X"] - 1e-12 else None


def score_q1(all_reads, res, start):
    bets = {k: [] for k in Q1}
    last_cons = {}
    for r in all_reads:
        st = start.get(r["game"])
        if st and r["at"] < st and r["cons"] is not None:
            last_cons[(r["game"], r["pid"], r["line"])] = r["cons"]
    for name, v in Q1.items():
        done = set()
        for r in all_reads:
            st = start.get(r["game"])
            if st and r["at"] >= st:
                continue
            for side in ("over", "under"):
                key = (r["game"], r["pid"], r["line"], side)
                if key in done:
                    continue
                price = r[side]
                e = qualifies(v, r, side, price)
                if e is None:
                    continue
                done.add(key)
                lc = last_cons.get((r["game"], r["pid"], r["line"]))
                clv = None if lc is None else ev(lc if side == "over" else 1 - lc, price)
                pl = grade(res.get((r["game"], r["pid"], r["line"])), side, r["line"], price)
                bets[name].append({"date": r["date"], "game": r["game"], "pid": r["pid"], "line": r["line"], "side": side,
                                   "pull": r["pull"], "at": r["at"].isoformat(), "price": price, "ev": round(e, 4),
                                   "books": r["books"], "clv": None if clv is None else round(clv, 4), "pl": pl})
    return bets


# ---------------------------------------------------------------- stats
def summarize(bl):
    g = [b for b in bl if b["pl"] is not None]
    n = len(g)
    out = {"bets": len(bl), "graded": n, "w": sum(1 for b in g if b["pl"] > 0), "units": round(sum(b["pl"] for b in g), 3),
           "roi": None, "ci90": None, "p_one_sided": None, "mean_ev": None, "mean_clv": None}
    if bl:
        out["mean_ev"] = round(statistics.mean(b["ev"] for b in bl), 4)
        cl = [b["clv"] for b in bl if b["clv"] is not None]
        out["mean_clv"] = round(statistics.mean(cl), 4) if cl else None
    if not n:
        return out
    out["roi"] = round(out["units"] / n, 4)
    by = {}
    for b in g:
        by.setdefault((b["date"], b["game"]), []).append(b["pl"])
    cl = list(by.values())
    rng = random.Random(7)
    sims = []
    for _ in range(BOOT):
        s = [cl[rng.randrange(len(cl))] for _ in cl]
        tot = sum(len(x) for x in s)
        sims.append(sum(sum(x) for x in s) / tot)
    sims.sort()
    out["ci90"] = [round(sims[int(0.05 * BOOT)], 4), round(sims[int(0.95 * BOOT) - 1], 4)]
    out["p_one_sided"] = round(sum(1 for x in sims if x <= 0) / BOOT, 4)
    out["games"] = len(cl)
    out["candidate"] = bool(n >= BAR_N and out["roi"] > 0 and out["p_one_sided"] < 0.05 / BONF
                            and (out["mean_clv"] or 0) > 0)
    return out


# ---------------------------------------------------------------- Q2 lineup events from git history
FWD_TOP = ("f1", "f2")


def role(groups, pid):
    g = {k for k, v in (groups or {}).items() if pid in v}
    return ("top" if g & set(FWD_TOP) else ("bot" if g & {"f3", "f4"} else "none")), ("pp1" in g), g


def lineup_checks(date):
    """[(time, team, page)] every distinct state of data/state/lineups.json for that slate, oldest first."""
    try:
        log = subprocess.run(["git", "-C", ROOT, "log", "--reverse", "--format=%H %cI", "--", "data/state/lineups.json"],
                             capture_output=True, text=True, check=True).stdout.split("\n")
    except Exception:
        return []
    seen, out = {}, []
    for line in log:
        if not line.strip():
            continue
        h, ct = line.split()
        try:
            doc = json.loads(subprocess.run(["git", "-C", ROOT, "show", h + ":data/state/lineups.json"],
                                            capture_output=True, text=True, check=True).stdout)
        except Exception:
            continue
        if doc.get("date") != date:
            continue
        for team, t in (doc.get("teams") or {}).items():
            pg = t.get("page") or {}
            if not pg.get("today") or pg.get("page_date") != date or not pg.get("groups"):
                continue
            sig = json.dumps([pg.get("groups"), sorted(pg.get("out") or [])], sort_keys=True)
            if seen.get(team) == sig:
                continue
            seen[team] = sig
            out.append((iso(t.get("tried_at") or ct), team, pg))
    return out


def lineup_events(date):
    ev_ = []
    prev = {}
    for at, team, pg in lineup_checks(date):
        p = prev.get(team)
        prev[team] = pg
        if p is None:
            continue
        pids = set(sum((v for v in pg["groups"].values()), [])) | set(sum((v for v in p["groups"].values()), []))
        for pid in pids:
            r0, pp0, g0 = role(p["groups"], pid)
            r1, pp1, g1 = role(pg["groups"], pid)
            if pid in (pg.get("out") or []):
                continue
            if (r0 != "top" and r1 == "top") or (not pp0 and pp1):
                ev_.append({"at": at, "team": team, "pid": pid, "kind": "promotion", "side": "over"})
            elif (r0 == "top" and r1 != "top") or (pp0 and not pp1):
                ev_.append({"at": at, "team": team, "pid": pid, "kind": "demotion", "side": "under"})
        newly_out = set(pg.get("out") or []) - set(p.get("out") or [])
        for o in newly_out:
            mates = set()
            for k, v in p["groups"].items():
                if o in v and (k.startswith("f") or k == "pp1"):
                    mates |= set(v)
            for m in mates - {o}:
                ev_.append({"at": at, "team": team, "pid": m, "kind": "mate_out", "side": "over", "mate": o})
    return ev_


def score_q2(date, reads, res, start):
    evs = lineup_events(date)
    by_pid = {}
    for r in reads:
        by_pid.setdefault(r["pid"], []).append(r)
    bets = {"Q2a": [], "Q2b": []}
    desc = []
    used = {"Q2a": set(), "Q2b": set()}
    for e in evs:
        rs = by_pid.get(e["pid"], [])
        if not rs:
            desc.append(dict(e, at=e["at"].isoformat(), note="no Hard Rock line"))
            continue
        st = start.get(rs[0]["game"])
        if st and e["at"] >= st:
            continue
        before = [r for r in rs if r["at"] <= e["at"]]
        after = [r for r in rs if r["at"] > e["at"] and (not st or r["at"] < st)]
        d = dict(e, at=e["at"].isoformat())
        # latency (descriptive): first Hard Rock change and first consensus move >= 0.03 after the news
        if before:
            b0 = before[-1]
            for r in after:
                if r["line"] == b0["line"] and (r["over"], r["under"]) != (b0["over"], b0["under"]) and "hr_min" not in d:
                    d["hr_min"] = round((r["at"] - e["at"]).total_seconds() / 60, 1)
                if r["line"] == b0["line"] and b0["cons"] is not None and r["cons"] is not None and \
                        abs(r["cons"] - b0["cons"]) >= 0.03 and "cons_min" not in d:
                    d["cons_min"] = round((r["at"] - e["at"]).total_seconds() / 60, 1)
        desc.append(d)
        name = "Q2a" if e["kind"] == "promotion" else "Q2b"
        if e["pid"] in used[name] or not before or not after:
            continue
        lines = [r["line"] for r in after if any(b["line"] == r["line"] for b in before)]
        if not lines:
            continue
        a0 = [r for r in after if r["line"] in lines]
        a0 = min(a0, key=lambda r: (r["at"], abs(r["hr_fair"] - 0.5)))
        b0 = [r for r in before if r["line"] == a0["line"]][-1]
        if (a0["over"], a0["under"]) != (b0["over"], b0["under"]):
            continue
        price = a0[e["side"]]
        if price < -200:
            continue
        used[name].add(e["pid"])
        f = a0["cons"]
        evv = None if f is None else ev(f if e["side"] == "over" else 1 - f, price)
        bets[name].append({"date": date, "game": a0["game"], "pid": e["pid"], "line": a0["line"], "side": e["side"],
                           "kind": e["kind"], "pull": a0["pull"], "at": a0["at"].isoformat(), "price": price,
                           "ev": round(evv, 4) if evv is not None else 0.0, "books": a0["books"], "clv": None,
                           "pl": grade(res.get((a0["game"], e["pid"], a0["line"])), e["side"], a0["line"], price)})
    return bets, desc


# ---------------------------------------------------------------- descriptives
def describe(reads):
    w = [r for r in reads if r["cons"] is not None]
    side_ev = []
    for r in w:
        for side in ("over", "under"):
            f = r["cons"] if side == "over" else 1 - r["cons"]
            side_ev.append((ev(f, r[side]), side, r))
    beat = [x for x in side_ev if x[0] >= 0]
    gap = [r["hr_fair"] - r["cons"] for r in w]
    by_pull = {}
    for r in reads:
        k = r["pull"]
        by_pull.setdefault(k, [0, 0])
        by_pull[k][0] += 1
        by_pull[k][1] += r["cons"] is not None
    return {"line_reads": len(reads), "with_consensus": len(w),
            "unique_lines": len({(r["game"], r["pid"], r["line"]) for r in reads}),
            "unique_lines_with_cons": len({(r["game"], r["pid"], r["line"]) for r in w}),
            "by_pull_reads_cons": by_pull,
            "books_median": statistics.median([r["books"] for r in w]) if w else None,
            "sides": len(side_ev), "sides_ev_ge_0": len(beat),
            "unique_lines_side_ev_ge_0": len({(x[2]["game"], x[2]["pid"], x[2]["line"], x[1]) for x in beat}),
            "side_ev_pcts": {q: round(sorted(e for e, _, _ in side_ev)[min(len(side_ev) - 1, int(q / 100 * len(side_ev)))], 4)
                             for q in (50, 90, 99, 100)} if side_ev else None,
            "best_side_ev_by_line_mean": round(statistics.mean(max(e for e, s, rr in side_ev if rr is r) for r in w), 4) if w else None,
            "hr_minus_cons_fair_over_abs_mean": round(statistics.mean(abs(x) for x in gap), 4) if gap else None,
            "hr_hold_mean": round(statistics.mean(hold(r["over"], r["under"]) for r in w), 4) if w else None,
            "ev_ge_0_list": [{"game": x[2]["game"], "pid": x[2]["pid"], "line": x[2]["line"], "side": x[1], "pull": x[2]["pull"],
                              "price": x[2][x[1]], "ev": round(x[0], 4), "books": x[2]["books"]} for x in beat]}


def shadow_stale(date):
    p = os.path.join(ROOT, "data/shadow", date + ".json")
    if not os.path.exists(p):
        return []
    out = []
    for r in load(p)["rows"]:
        if r["market"] == "shots":
            for e in r.get("stale_events") or []:
                out.append(dict(e, game=r["game_id"], pid=r["pid"], line=r["line"]))
    return out


def main():
    ds = dates()
    sh = subprocess.run(["git", "-C", ROOT, "rev-parse", "--is-shallow-repository"], capture_output=True, text=True).stdout.strip()
    if sh == "true":
        print("WARNING: shallow clone; Q2 lineup events need full history. Run: git fetch --unshallow origin", file=sys.stderr)
    allq1 = {k: [] for k in Q1}
    allq2 = {"Q2a": [], "Q2b": []}
    nightly = {}
    for d in ds:
        reads = reads_for(d)
        res, start = shadow(d)
        b = score_q1(reads, res, start)
        for k in b:
            allq1[k] += b[k]
        b2, desc2 = score_q2(d, reads, res, start)
        for k in b2:
            allq2[k] += b2[k]
        ds_ = describe(reads)
        nightly[d] = {"describe": ds_, "stale_events": shadow_stale(d), "lineup_events": desc2,
                      "shadow_shots_rows": len(res), "shadow_shots_graded": sum(1 for r in res.values() if r.get("result"))}
    out = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "nights": ds,
           "bar": {"n": BAR_N, "p": round(0.05 / BONF, 4), "bonferroni": BONF, "roi": "> 0", "clv": "> 0"},
           "variants": {k: summarize(v) for k, v in list(allq1.items()) + list(allq2.items())},
           "bets": {k: v for k, v in list(allq1.items()) + list(allq2.items())}, "nightly": nightly}
    os.makedirs(os.path.join(ROOT, "research/fwd"), exist_ok=True)
    with open(os.path.join(ROOT, "research/fwd/scores.json"), "w") as f:
        json.dump(out, f, indent=1, default=str)
    md = (["**WARNING: shallow clone, Q2 lineup events incomplete (git fetch --unshallow origin, then re-run).**", ""]
          if sh == "true" else [])
    md += ["# Forward scores (auto, research/code/fwd/score_fwd.py). Nights: %s" % ", ".join(ds), "",
          "Bar: n >= %d graded, ROI > 0, one-sided p < %.4f, mean CLV > 0. Below that: too small to judge." % (BAR_N, 0.05 / BONF), "",
          "| variant | bets | graded | W | units | ROI | 90% CI | p | mean EV | mean CLV | candidate |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for k, s in out["variants"].items():
        md.append("| %s | %d | %d | %d | %s | %s | %s | %s | %s | %s | %s |" % (
            k, s["bets"], s["graded"], s["w"], s["units"], "-" if s["roi"] is None else "%+.1f%%" % (100 * s["roi"]),
            "-" if not s["ci90"] else "%+.0f..%+.0f%%" % (100 * s["ci90"][0], 100 * s["ci90"][1]),
            "-" if s["p_one_sided"] is None else s["p_one_sided"], s["mean_ev"], s["mean_clv"], s.get("candidate", False)))
    md += ["", "| night | line reads | with consensus | unique lines (w/ cons) | sides EV>=0 vs median | stale events | lineup events |",
           "|---|---|---|---|---|---|---|"]
    for d, n in nightly.items():
        x = n["describe"]
        md.append("| %s | %d | %d | %d (%d) | %d of %d | %d | %d |" % (d, x["line_reads"], x["with_consensus"], x["unique_lines"],
                                                                 x["unique_lines_with_cons"], x["sides_ev_ge_0"], x["sides"],
                                                                 len(n["stale_events"]), len(n["lineup_events"])))
    with open(os.path.join(ROOT, "research/fwd/scores.md"), "w") as f:
        f.write("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
