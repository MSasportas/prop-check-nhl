"""record.py: THE RECORD.

data/record/events.jsonl is the source of truth: one JSON object per line, only ever added at the end.
  shown    a pick (or parlay) exactly as first shown on the page
  price    a new price seen for a live pick (with the chance and break-even shown with it)
  update   the shown chance or reason changed without a new price
  state    early -> lineup (or back)
  pulled   with the reason shown
  locked   puck dropped
  graded   result, what happened, the graded price (worst price shown) and units
  regraded a correction appended later, never an edit: ONLY a "did not play" VOID whose player the NHL box later shows
           with ice time (the box was incomplete when first read). The VOID line stays in the log; the item takes
           the new result and keeps the old one under graded.corrected. At most one per pick.

data/record.json and data/record/YYYY-MM.json are views rebuilt from the log (`run.py --rebuild-record`
does exactly that and nothing else). They contain no fact that is not in the log.

Units: 1 unit staked per pick and per parlay. Win = decimal(worst price shown) - 1, loss = -1,
push / void = 0. A parlay drops void and push legs and is graded on the rest.
"""
import json
import os

import common
import odds

EVENT_TYPES = ("shown", "price", "update", "state", "pulled", "locked", "graded", "regraded")


class RecordError(Exception):
    pass


def events_path():
    return common.dpath("record", "events.jsonl")


def read_raw():
    try:
        with open(events_path(), "rb") as f:
            return f.read()
    except FileNotFoundError:
        return b""


def parse(raw):
    """bytes -> list of events. A line that cannot be read stops everything: the Record is never guessed."""
    out = []
    if raw and not raw.endswith(b"\n"):
        raise RecordError("events.jsonl does not end with a newline (a write was cut short)")
    for i, line in enumerate(raw.decode("utf-8").split("\n")):
        if not line:
            continue
        try:
            e = json.loads(line)
        except ValueError:
            raise RecordError("events.jsonl line %d is not valid JSON" % (i + 1))
        if not isinstance(e, dict) or e.get("t") not in EVENT_TYPES or "id" not in e or "at" not in e:
            raise RecordError("events.jsonl line %d is not a Record event" % (i + 1))
        out.append(e)
    return out


def read_events():
    return parse(read_raw())


def append(events):
    """Add events at the end. The old bytes are written back untouched, then the new lines."""
    if not events:
        return 0
    raw = read_raw()
    parse(raw)                                              # refuse to build on a damaged log
    lines = []
    for e in events:
        if e.get("t") not in EVENT_TYPES or "id" not in e or "at" not in e:
            raise RecordError("refusing to write a malformed event")
        lines.append(json.dumps(e, separators=(",", ":"), ensure_ascii=True, sort_keys=True))
    common.write_bytes(events_path(), raw + ("\n".join(lines) + "\n").encode("utf-8"))
    return len(lines)


# ---------------------------------------------------------------- folding the log
def fold(events):
    """Replay the log. Returns {id: item}. An item is everything known about one pick or parlay."""
    items = {}
    for e in events:
        t, i = e["t"], e["id"]
        if t == "shown":
            if i in items:
                continue                                    # a second "shown" for the same id is ignored
            body = e.get("pick") or e.get("parlay") or {}
            items[i] = {"id": i, "kind": e.get("kind", "single"), "slate": e.get("slate"), "shown_at": e["at"],
                        "shown": body,
                        "prices": [{"at": body.get("price_at") or e["at"], "price": body.get("price"),
                                    "legs": body.get("leg_prices")}],
                        "p_pct": body.get("p_pct"), "breakeven_pct": body.get("breakeven_pct"),
                        "p": body.get("p"), "breakeven": body.get("breakeven"), "reason": body.get("reason"),
                        "fair": body.get("fair"),
                        "state": body.get("state"), "states": [{"at": e["at"], "state": body.get("state")}],
                        "pulled": None, "locked_at": None, "graded": None}
            continue
        it = items.get(i)
        if it is None:
            continue
        if t == "price":
            it["prices"].append({"at": e.get("price_at") or e["at"], "price": e["price"], "legs": e.get("leg_prices")})
            for k in ("p", "breakeven", "reason", "fair", "p_pct", "breakeven_pct"):
                if e.get(k) is not None:
                    it[k] = e[k]
        elif t == "update":
            for k in ("p", "breakeven", "reason", "fair", "p_pct", "breakeven_pct"):
                if e.get(k) is not None:
                    it[k] = e[k]
        elif t == "state":
            it["state"] = e["state"]
            it["states"].append({"at": e["at"], "state": e["state"]})
            if e.get("reason") is not None:
                it["reason"] = e["reason"]
        elif t == "pulled":
            if it["pulled"] is None and it["locked_at"] is None:
                it["pulled"] = {"at": e["at"], "reason": e.get("reason"), "code": e.get("code"), "if_bet": e.get("if_bet")}
        elif t == "locked":
            if it["locked_at"] is None:
                it["locked_at"] = e["at"]
                it["state"] = e.get("state", it["state"])
                it["states"].append({"at": e["at"], "state": it["state"]})
        elif t == "graded":
            if it["graded"] is None:
                it["graded"] = {k: e.get(k) for k in ("at", "result", "actual", "actual_text", "price", "units", "legs", "note")}
        elif t == "regraded":
            g = it["graded"]
            if g is not None and is_dnp_void(g) and not g.get("corrected"):
                new = {k: e.get(k) for k in ("at", "result", "actual", "actual_text", "price", "units", "legs", "note")}
                new["corrected"] = {"at": g["at"], "result": g["result"], "actual_text": g["actual_text"]}
                it["graded"] = new
    return items


def is_dnp_void(g):
    """A single graded VOID because the box showed no ice time: the only grade a later read may correct."""
    return bool(g) and g.get("result") == "VOID" and g.get("actual_text") == "did not play"


def worst_price(item):
    """The lowest-paying price ever shown for this pick."""
    return min((p["price"] for p in item["prices"] if p["price"] is not None), key=odds.decimal)


def parlay_snapshot(item):
    """The parlay price snapshot it is graded at: the WORST parlay price shown (lowest payout), with the leg
    prices it was made of. None for a parlay recorded before snapshots were stored."""
    snaps = [p for p in item["prices"] if p.get("legs") and p["price"] is not None]
    return min(snaps, key=lambda p: odds.decimal(p["price"])) if snaps else None


def first_price(item):
    return item["prices"][0]["price"]


def last_price(item):
    return item["prices"][-1]["price"]


def is_open(item):
    """Still bettable: not pulled, not locked, not graded."""
    return item["pulled"] is None and item["locked_at"] is None and item["graded"] is None


# ---------------------------------------------------------------- grading arithmetic
def single_units(result, price, stake=1):
    if result == "W":
        return round((odds.decimal(price) - 1.0) * stake, 4)
    if result == "L":
        return -float(stake)
    return 0.0


def grade_parlay(legs, stake=1):
    """legs: [(result, graded price)] for every leg. Returns (result, price, units).
    A void or push leg drops out. Any losing leg loses. No legs left = void."""
    alive = [(r, p) for r, p in legs if r in ("W", "L")]
    if any(r is None for r, _ in legs):
        return None, None, None
    if not alive:
        return "VOID", None, 0.0
    dec = 1.0
    for _, p in alive:
        dec *= odds.decimal(p)
    price = odds.american(dec)
    if any(r == "L" for r, _ in alive):
        return "L", price, -float(stake)
    return "W", price, round((odds.decimal(price) - 1.0) * stake, 4)    # paid at the price as shown (whole number)


# ---------------------------------------------------------------- views for the page
def _entry(it, items):
    sh, g = it["shown"], it["graded"]
    if it["kind"] == "parlay":
        legs = [_entry(items[l], items) for l in sh.get("legs", []) if l in items]
        e = {"id": it["id"], "kind": "parlay", "player": "Parlay", "bet": "%d legs" % len(sh.get("legs", [])),
             "price": (g or {}).get("price") if g else last_price(it), "first_price": first_price(it),
             "result": (g or {}).get("result"), "actual": (g or {}).get("actual_text"),
             "units": (g or {}).get("units"), "pulled": _pulled(it), "legs": legs}
        return e
    return {"id": it["id"], "kind": "single", "player": sh.get("player"), "bet": sh.get("bet"),
            "market": sh.get("market"), "team": sh.get("team"),
            "game": "%s at %s" % ((sh.get("team"), sh.get("opp")) if not sh.get("home") else (sh.get("opp"), sh.get("team"))),
            "price": (g or {}).get("price") if g else worst_price(it),
            "first_price": first_price(it), "last_price": last_price(it),
            "prices": [{"price": p["price"], "at": p["at"]} for p in it["prices"]],
            "result": (g or {}).get("result"), "actual": (g or {}).get("actual_text"),
            "units": (g or {}).get("units"), "pulled": _pulled(it), "legs": []}


def _pulled(it):
    return {"at": it["pulled"]["at"], "reason": it["pulled"]["reason"]} if it["pulled"] else None


def _row(key, label, entries, needed_of):
    w = sum(1 for e in entries if e["result"] == "W")
    l = sum(1 for e in entries if e["result"] == "L")
    need = [needed_of(e) for e in entries if e["result"] in ("W", "L") and e["price"] is not None]
    return {"key": key, "label": label, "w": w, "l": l,
            "push": sum(1 for e in entries if e["result"] == "PUSH"),
            "void": sum(1 for e in entries if e["result"] == "VOID"),
            "units": round(sum(e["units"] or 0 for e in entries if e["result"]), 2),
            "hit_rate": round(w / (w + l), 4) if (w + l) else None,
            "needed": round(sum(need) / len(need), 4) if need else None, "n": w + l}


# Cuts of the Record (summary only; the entries and the log are untouched). Every shown single counts, pulled ones too
# (Matt 2026-11-04), graded at the price it was graded at. Each band is (key, label, test).
LINE_BANDS = [("%s_%s" % (s, l), "%s %s" % (s.capitalize(), l), (lambda s, l: lambda f: f["side"] == s and f["line"] == float(l))(s, l))
              for s in ("over", "under") for l in ("1.5", "2.5", "3.5")]
EDGE_BANDS = [("edge_lt2", "Under 2 pts", lambda f: f["edge"] < 2.0),
              ("edge_2_3", "2 to 3 pts", lambda f: 2.0 <= f["edge"] < 3.0),
              ("edge_3_4", "3 to 4 pts", lambda f: 3.0 <= f["edge"] < 4.0),
              ("edge_4", "4 pts or more", lambda f: f["edge"] >= 4.0)]
SETTLED_BANDS = [("early", "Early", lambda f: f["settled"] == "early"),
                 ("lineup", "Lineup confirmed", lambda f: f["settled"] in ("lineup", "goalie"))]
PRICE_BANDS = [("fav_big", "-200 to -150", lambda f: -200 <= f["price"] <= -150),
               ("fav", "-149 to -101", lambda f: -150 < f["price"] <= -101),
               ("plus", "Even or plus money", lambda f: f["price"] >= 100 or f["price"] == -100)]


def _facts(e, it):
    """What a cut needs about one shown single, from the pick as first shown (the price is frozen there)."""
    sh = it["shown"]
    p, b = sh.get("p"), sh.get("breakeven")
    line = sh.get("line")
    return {"side": sh.get("side"), "line": float(line) if isinstance(line, (int, float)) else None,
            "edge": round(100.0 * (p - b), 2) if isinstance(p, (int, float)) and isinstance(b, (int, float)) else None,
            "settled": sh.get("state"), "price": e["price"]}


def cuts(rows, need):
    """rows: [(entry, facts)] for every shown single. -> the Record's cuts, each {key, label, note, rows}; a band with
    nothing graded is left out. A fact that is missing (an old pick) keeps that pick out of that one cut only."""
    out = []
    for key, label, note, bands, has in (
            ("line", "By line", None, LINE_BANDS, lambda f: f["side"] in ("over", "under") and f["line"] is not None),
            ("edge", "By edge", "Our chance minus what the price needs, in points, when shown", EDGE_BANDS,
             lambda f: f["edge"] is not None),
            ("settled", "By how settled when shown", "A Locked pick can't be bet, so it is not a row", SETTLED_BANDS,
             lambda f: f["settled"] is not None),
            ("price", "By price", "Hard Rock price at grading", PRICE_BANDS, lambda f: isinstance(f["price"], int))):
        cut_rows = []
        for bk, bl, test in bands:
            sub = [e for e, f in rows if has(f) and test(f)]
            if any(e["result"] in ("W", "L", "PUSH", "VOID") for e in sub):
                cut_rows.append(_row(bk, bl, sub, need))
        if cut_rows:
            out.append({"key": key, "label": label, "note": note, "rows": cut_rows})
    return out


def build_views(events, cfg):
    """-> (record.json dict, {"2026-10": month dict, ...})."""
    items = fold(events)
    labels = {k: m["label"] for k, m in cfg["ops"]["markets"].items()}
    by_night = {}
    for it in items.values():
        by_night.setdefault(it["slate"], []).append(it)
    nights = []
    for d in sorted(by_night, reverse=True):
        its = sorted(by_night[d], key=lambda x: (x["kind"] != "single", x["shown"].get("rank") or 999, x["shown_at"], x["id"]))
        entries = [_entry(x, items) for x in its]
        counted = [e for e in entries if e["kind"] == "single"]      # every shown single, pulled too (Matt 2026-11-04)
        nights.append({"date": d, "graded": all(e["result"] is not None for e in entries),
                       "w": sum(1 for e in counted if e["result"] == "W"),
                       "l": sum(1 for e in counted if e["result"] == "L"),
                       "units": round(sum(e["units"] or 0 for e in counted), 2), "entries": entries})
    every = [e for n in nights for e in n["entries"]]
    need = lambda e: odds.break_even(e["price"])
    singles = [e for e in every if e["kind"] == "single"]          # pulled singles count, at the price shown
    rows = []
    for key in cfg["ops"]["markets"]:
        sub = [e for e in singles if e.get("market") == key]
        if any(e["result"] for e in sub):
            rows.append(_row(key, labels[key], sub, need))
    par = [e for e in every if e["kind"] == "parlay" and not e["pulled"]]
    if any(e["result"] for e in par):
        rows.append(_row("parlays", "Parlays", par, need))
    head = _row("headline", "Singles", singles, need)
    head.pop("key"); head.pop("label")
    days = []
    for n in nights:                                        # one row per night for the page's calendar
        s = [e for e in n["entries"] if e["kind"] == "single"]
        days.append({"date": n["date"], "w": n["w"], "l": n["l"],
                     "push": sum(1 for e in s if e["result"] == "PUSH"), "void": sum(1 for e in s if e["result"] == "VOID"),
                     "units": n["units"], "n": len(s), "graded": n["graded"]})
    keep = cfg["ops"]["record_nights"]
    months = {}
    for n in nights[keep:]:
        months.setdefault(n["date"][:7], {"nights": []})["nights"].append(n)
    rec = {"generated_at": events[-1]["at"] if events else None,
           "summary": {"headline": head, "rows": rows,
                       "cuts": cuts([(e, _facts(e, items[e["id"]])) for e in singles], need), "days": days},
           "nights": nights[:keep],
           "older": ["record/%s.json" % m for m in sorted(months, reverse=True)]}
    return rec, months


def write_views(cfg, events=None):
    """Rebuild record.json and the month files from the log. Writes only files whose content changed."""
    events = read_events() if events is None else events
    rec, months = build_views(events, cfg)
    changed = []
    targets = [(common.dpath("record.json"), rec)] + \
              [(common.dpath("record", "%s.json" % m), doc) for m, doc in months.items()]
    for path, doc in targets:
        if common.read_json(path) != doc:
            common.write_json(path, doc)
            changed.append(os.path.basename(path))
    return changed
