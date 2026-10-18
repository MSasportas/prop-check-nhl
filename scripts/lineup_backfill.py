#!/usr/bin/env python3
"""lineup_backfill.py: rebuild data/state/lineup_history/<slate>.json for past slates from the git history of
data/state/lineups.json (every committed version, oldest first, folded exactly as the live step folds them).

    python scripts/lineup_backfill.py            every past slate found in the history (today is left to the timer)
    python scripts/lineup_backfill.py --force    also replace history files that already exist

Needs the full git history: in a shallow clone run `git fetch --unshallow origin main` first (the timer's
checkout already has it). A version's moment is its commit time; a page read at or after a team's puck is
ignored. Existing files are kept unless --force (the live timer's file is the better record).
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json            # noqa: E402

import common          # noqa: E402
import lineup_history  # noqa: E402
import sched           # noqa: E402

REL = "data/state/lineups.json"


def versions(root=common.ROOT):
    """[(commit time, parsed lineups.json)] oldest first."""
    log = subprocess.run(["git", "-C", root, "log", "--format=%H %cI", "--", REL], capture_output=True, text=True,
                         check=True).stdout.split("\n")
    commits = [l.split() for l in log if l.strip()]
    if not commits:
        return []
    req = "".join("%s:%s\n" % (c, REL) for c, _ in commits).encode()
    raw = subprocess.run(["git", "-C", root, "cat-file", "--batch"], input=req, capture_output=True,
                         check=True).stdout
    out, i = [], 0
    for c, t in commits:
        nl = raw.index(b"\n", i)
        head = raw[i:nl].decode().split()
        if len(head) < 3 or head[1] == "missing":
            i = nl + 1
            continue
        size = int(head[2])
        body = raw[nl + 1: nl + 1 + size]
        i = nl + 1 + size + 1
        try:
            out.append((common.parse_iso(t), json.loads(body)))
        except ValueError:
            continue
    out.sort(key=lambda x: x[0])
    return out


def rebuild(vers, cache, before_slate):
    """{slate: doc} for every slate older than before_slate."""
    docs = {}
    for at, st in vers:
        slate = st.get("date") if isinstance(st, dict) else None
        if not slate or slate >= before_slate:
            continue
        doc = docs.setdefault(slate, {"date": slate, "teams": {}})
        lineup_history.fold(doc, at, sched.games_on(cache, slate), st, historical=True)
    return docs


def main(argv):
    force = "--force" in argv
    cache = common.read_json(sched.path())
    if not cache:
        print("no schedule file")
        return 1
    if subprocess.run(["git", "-C", common.ROOT, "rev-parse", "--is-shallow-repository"], capture_output=True,
                      text=True).stdout.strip() == "true":
        print("shallow clone: run `git fetch --unshallow origin main` first")
        return 1
    today = common.slate_date(common.now())
    vers = versions()
    docs = rebuild(vers, cache, today)
    print("%d versions of lineups.json" % len(vers))
    for slate, doc in sorted(docs.items()):
        p = lineup_history.path(slate)
        if os.path.exists(p) and not force:
            print("%s: kept the existing file" % slate)
            continue
        if not doc["teams"]:
            print("%s: nothing before puck" % slate)
            continue
        common.write_json(p, doc, pretty=False)
        conf = sum(1 for t in doc["teams"].values() if t["first_today_at"])
        print("%s: %d teams, %d got a page dated today before puck" % (slate, len(doc["teams"]), conf))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
