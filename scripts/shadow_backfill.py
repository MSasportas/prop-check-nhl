#!/usr/bin/env python3
"""shadow_backfill.py: build data/shadow/<slate>.json for past slates from data/odds/ and the stats store.

    python scripts/shadow_backfill.py 2026-10-12 2026-10-17      build those slates (inclusive), then check
    python scripts/shadow_backfill.py --check 2026-10-12 2026-10-17   check only, write nothing

The model for each slate uses only games before that date (the engine's own Inputs, so the same numbers the
engine would have had). Only reads made before puck are used. Lineup and goalie state are left empty (not
known for the past). Results come from the NHL boxscore, read exactly as grade.py reads it, so the network is
needed. A row the live timer already wrote is kept as it is (it has lineup state); backfill adds what is missing.

CHECK: every shots single in the Record for those slates must find its line in the shadow log with the same
model chance the Record showed (to 4 decimals). Port of the Data Scientist's build_lines.py (2026-10-18), which
matched all 13 shots picks.
"""
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import common      # noqa: E402
import engine      # noqa: E402
import record      # noqa: E402
import sched       # noqa: E402
import shadow      # noqa: E402
import stats       # noqa: E402
import odds        # noqa: E402


def slates(a, b):
    d, out = date.fromisoformat(a), []
    while d <= date.fromisoformat(b):
        out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def inputs_for(cfg, slate, season, games, store):
    now = common.parse_iso(slate + "T12:00:00-04:00")
    return engine.Inputs(common.rules_for(cfg, slate), now, slate, season, games, store, {}, {}, {}, {}, [])


def build(slate, cfg, cache, store, now, box_fn=None):
    """Returns (doc, note). Does not write."""
    games = sched.games_on(cache, slate)
    odds_doc = common.read_json(odds.odds_path(slate))
    doc = shadow.load(slate)
    if not odds_doc or not games:
        return doc, "no odds file or no games"
    inp = inputs_for(cfg, slate, cache["season"], games, store)
    fresh = {"date": slate, "version": shadow.VERSION, "note": shadow.NOTE, "rows": []}
    shadow.add_reads(fresh, inp, odds_doc, games, cache["games"], now, historical=True)
    have = {shadow.key(r["game_id"], r["market"], r["pid"], r["line"]) for r in doc["rows"]}
    added = [r for r in fresh["rows"] if shadow.key(r["game_id"], r["market"], r["pid"], r["line"]) not in have]
    doc["rows"] += added
    graded, notes = shadow.fill_results(doc, now, cfg, cache["games"], box_fn)
    return doc, "%d rows added (%d kept from the live log), %d graded%s" % (
        len(added), len(have), graded, ("; " + "; ".join(notes[:3])) if notes else "")


def check(slate_list, events=None):
    """Record shots singles vs the shadow log. Returns (matched, total, problems)."""
    events = record.read_events() if events is None else events
    items = record.fold(events)
    total = matched = 0
    problems = []
    docs = {s: shadow.load(s) for s in slate_list}
    for it in sorted(items.values(), key=lambda x: x["id"]):
        if it["kind"] != "single" or it["slate"] not in docs or it["shown"]["market"] != "shots":
            continue
        total += 1
        sh = it["shown"]
        k = shadow.key(sh["game_id"], "shots", sh["player_id"], sh["line"])
        row = next((r for r in docs[it["slate"]]["rows"]
                    if shadow.key(r["game_id"], r["market"], r["pid"], r["line"]) == k), None)
        if row is None:
            problems.append("%s: not in the shadow log" % it["id"])
            continue
        mo = row["open"]["model_p_over"]
        if mo is None:
            problems.append("%s: no model value" % it["id"])
            continue
        side = mo if sh["side"] == "over" else 1.0 - mo
        if abs(round(side, 4) - sh["model"]) <= 0.00011:
            matched += 1
        else:
            problems.append("%s: shadow %.4f vs Record %.4f" % (it["id"], side, sh["model"]))
    return matched, total, problems


def main(argv):
    common.install_scrubbers()
    only_check = "--check" in argv
    args = [a for a in argv if not a.startswith("--")]
    if len(args) != 2:
        print(__doc__)
        return 2
    cfg = common.load_config()
    cache = common.read_json(sched.path())
    if not cache:
        print("no schedule file")
        return 1
    sl = slates(args[0], args[1])
    if not only_check:
        store, problems = stats.load(cache["season"])
        if problems:
            print("stats problems: %s" % problems)
        now = common.now()
        for s in sl:
            doc, note = build(s, cfg, cache, store, now)
            if doc["rows"]:
                doc["updated_at"] = common.iso(now)
                shadow.save(doc)
            print("%s: %s" % (s, note))
    matched, total, problems = check(sl)
    print("CHECK: %d of %d Record shots picks match the shadow log's model value" % (matched, total))
    for p in problems:
        print("  " + p)
    return 0 if matched == total else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
