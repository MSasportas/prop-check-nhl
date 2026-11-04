# Gap + Guard (current thresholds) run on DraftKings shots prices instead of Hard Rock (2026-11-03, Matt). Consensus = other books minus the target. Usage: python3 research/code/dk_same_rules.py hardrock|draftkings [cap120]
import sys, json, glob, os, math, collections
sys.path.insert(0, "scripts")
import common, odds, shadow, paper, model
cfg = json.load(open("config/rules.json"))
v = cfg["values"]
T = dict(common.gap_guard(cfg)["thresholds"])
if len(sys.argv) > 2 and sys.argv[2] == "cap120": T["max_price"] = 120
TARGET = sys.argv[1]  # hardrock | draftkings
r_sh = model.SK["shots"]["r"]

def model_over(row_snaps, line, at):
    s = None
    for sn in row_snaps:
        if sn and sn.get("mu") is not None and common.parse_iso(sn["at"]) <= at: s = sn
    if s is None:
        s = next((sn for sn in row_snaps if sn and sn.get("mu") is not None), None)
    if s is None: return None
    return model.calibrate(model.nb_sf(math.floor(line) + 1, s["mu"], r_sh), "shots", line)

out = []
miss_model = 0
for fn in sorted(glob.glob("data/odds/*.json")):
    day = os.path.basename(fn)[:10]
    if day < "2026-10-20" or day > "2026-11-02": continue
    sh = json.load(open("data/shadow/%s.json" % day))
    info = {}   # (gid,pid) -> dict(ctx, snaps, actual, lineup)
    for r in sh["rows"]:
        if r["market"] != "shots": continue
        k = (r["game_id"], r["pid"])
        d = info.setdefault(k, {"ctx": r.get("ctx"), "snaps": [], "actual": None, "toi": None})
        d["snaps"] += [r.get("open"), r.get("close")]
        res = r.get("result") or {}
        if res.get("actual") is not None: d["actual"], d["toi"] = res["actual"], res.get("toi")
    starts = {g: d["ctx"]["start"] for (g, p), d in info.items() if d["ctx"]}
    flagged = set(); flags = []
    fetches = sorted(json.load(open(fn))["fetches"], key=lambda f: f["at"])
    for f in fetches:
        g = f["game_id"]
        if g not in starts or f.get("pull") not in T["flag_pulls"] or "others" not in f: continue
        at = common.parse_iso(f["at"])
        if (common.parse_iso(starts[g]) - at).total_seconds() <= 0: continue
        oth = shadow.other_lines(f, "shots", v) or {}
        if TARGET == "hardrock":
            mk = (f.get("markets") or {}).get("shots")
            if not mk: continue
            tp = shadow.pairs_of(mk)
            for k, p in tp.items(): p["why"] = odds.check_pair(p["over"], p["under"], mk.get("last_update"), at, v)
            cons = oth
        else:
            mk = ((f.get("others") or {}).get("draftkings") or {}).get("shots")
            if not mk or odds.is_stale(mk.get("last_update"), at, v): continue
            tp = shadow.pairs_of(mk)
            for p in tp.values(): p["why"] = None
            f2 = dict(f); f2["others"] = {b: m for b, m in f["others"].items() if b != "draftkings"}
            cons = shadow.other_lines(f2, "shots", v) or {}
        passed = []
        for (pid, line), pair in sorted(tp.items()):
            if pair["over"] is None or pair["under"] is None or pair["why"] is not None or not paper.line_ok(line, T): continue
            entry = cons.get((pid, line))
            if not entry or len(entry["pairs"]) < T["books_min"]: continue
            d = info.get((g, pid))
            for side in ("over", "under"):
                if (g, pid) in flagged: continue
                fnm = (lambda d=d, line=line: None if d is None else model_over(d["snaps"], line, at))
                a = paper.assess(side, line, pair[side], entry, fnm, T)
                if not a["step1"]: continue
                if a["guard"] is None: miss_model += 1; continue
                c = d["ctx"] or {}
                if c.get("n_hist", 0) < T["min_history"] or c.get("sitting"): continue
                if not a["guard"]: continue
                a.update(pid=pid, name=pair["name"], g=g, day=day, read=f["pull"], actual=d["actual"], toi=d["toi"])
                passed.append(a)
        passed.sort(key=lambda a: -a["final_ev"])
        for a in passed:
            if (g, a["pid"]) in flagged: continue
            flagged.add((g, a["pid"])); flags.append(a)
    out += flags
res = collections.Counter(); units = 0.0
for a in out:
    act = a["actual"]
    if act is None or a["toi"] in (None, "0:00", "00:00"): a["res"] = "V"; continue
    win = act > a["line"] if a["side"] == "over" else act < a["line"]
    a["res"] = "W" if win else "L"
    units += (odds.decimal(a["price"]) - 1) if win else -1
for a in out: res[a["res"]] += 1
print(TARGET, dict(res), "units %+.2f" % units, "picks", len(out), "no-model skips", miss_model)
json.dump([{k: a[k] for k in ("day","g","pid","name","line","side","price","final_ev","res","read")} for a in out],
          open("/tmp/dkbt_%s.json" % TARGET, "w"))
