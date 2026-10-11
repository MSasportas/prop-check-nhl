#!/usr/bin/env python3
"""replay_day.py: replay one real day through the whole engine, offline, in a scratch folder.

It never touches the live data/ folder and never spends an odds credit: the clock (PC_NOW), the data
folder (PC_DATA_DIR) and all three sources (NHL, odds, Daily Faceoff) are pointed at saved files.

    python tests/replay_day.py PLAN.json

PLAN.json:
  {"data_dir": "/path/scratch/data",
   "odds_dir": "/path/odds",               events.json, odds_<away>_<home>.json, pool.json {"keys": [credits, ...]}
   "nhl_base": "/path/nhl_now",            saved NHL answers used by every step
   "steps": [{"label": "...", "now": "2026-10-11T09:00:00-04:00",
              "nhl_overlay": "/path/dir",  files here replace the base for this step (e.g. the schedule)
              "lineups_dir": "/path/dir",  Daily Faceoff pages for this step (missing team = page not read)
              "odds_dir": "/path/dir",     odds files for this step, when they differ from the plan's
              "set_states": {"date:2026-10-10": "FUT", "2026020086": "LIVE"},
                                           optional: rewrite game states in the saved schedule, for a whole
                                           date and/or single games (a game id wins over its date)
              "repeat": 2}]}                run the step again to show a second run changes nothing
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
RUN = os.path.join(os.path.dirname(HERE), "scripts", "run.py")


def tree_hash(root):
    h = hashlib.sha1()
    for d, _, files in sorted(os.walk(root)):
        for f in sorted(files):
            p = os.path.join(d, f)
            h.update(p.encode())
            with open(p, "rb") as f:
                h.update(f.read())
    return h.hexdigest()


def main(plan_path):
    with open(plan_path) as f:
        plan = json.load(f)
    data = plan["data_dir"]
    if os.path.isdir(data):
        shutil.rmtree(data)
    os.makedirs(data)
    work = tempfile.mkdtemp(prefix="pc_replay_")
    log_before = b""
    for n, st in enumerate(plan["steps"], 1):
        nhl_dir = os.path.join(work, "nhl_%d" % n)
        shutil.copytree(plan["nhl_base"], nhl_dir)
        if st.get("nhl_overlay"):
            for f in os.listdir(st["nhl_overlay"]):
                shutil.copy(os.path.join(st["nhl_overlay"], f), os.path.join(nhl_dir, f))
        if st.get("set_states"):
            for name in os.listdir(nhl_dir):                # every saved schedule week that holds the game
                if not name.startswith("schedule_"):
                    continue
                p = os.path.join(nhl_dir, name)
                with open(p) as f:
                    js = json.load(f)
                for wk in js["gameWeek"]:
                    for g in wk["games"]:
                        state = st["set_states"].get(str(g["id"]), st["set_states"].get("date:" + wk["date"]))
                        if state:
                            g["gameState"] = state
                with open(p, "w") as f:
                    json.dump(js, f)
            for name in os.listdir(nhl_dir):                # a saved boxscore is the FINAL one: give it the
                if not (name.startswith("gamecenter_") and name.endswith("_boxscore.json")):   # state of the step
                    continue
                p = os.path.join(nhl_dir, name)
                with open(p) as f:
                    js = json.load(f)
                state = st["set_states"].get(str(js.get("id")), st["set_states"].get("date:" + str(js.get("gameDate"))))
                if state:
                    js["gameState"] = state
                    with open(p, "w") as f:
                        json.dump(js, f)
        env = dict(os.environ, PC_NOW=st["now"], PC_DATA_DIR=data,
                   PC_ODDS_FIXTURE_DIR=st.get("odds_dir") or plan["odds_dir"],
                   PC_NHL_FIXTURE_DIR=nhl_dir,
                   PC_LINEUP_FIXTURE_DIR=st.get("lineups_dir") or os.path.join(work, "no_lineups"))
        env.pop("ODDS_API_KEYS", None)
        for rep in range(st.get("repeat", 1)):
            before = tree_hash(data)
            print("\n=== step %d%s: %s  (clock %s)" % (n, "" if rep == 0 else " again", st["label"], st["now"]))
            out = subprocess.run([sys.executable, RUN], env=env, capture_output=True, text=True)
            print(out.stdout.rstrip())
            if out.returncode != 0 or out.stderr.strip():
                print("STDERR:", out.stderr[-2000:])
                return 1
            if rep > 0:
                print("    second run changed files: %s" % ("NO" if tree_hash(data) == before else "YES"))
            log_path = os.path.join(data, "record", "events.jsonl")
            log_now = b""
            if os.path.exists(log_path):
                with open(log_path, "rb") as f:
                    log_now = f.read()
            if not log_now.startswith(log_before):
                print("RECORD CHANGED IN PLACE: not append-only")
                return 1
            added = log_now[len(log_before):].decode().splitlines()
            for line in added:
                e = json.loads(line)
                body = e.get("pick") or e.get("parlay") or {}
                print("    record + %-7s %s %s" % (e["t"], e["id"], " ".join(
                    str(x) for x in (body.get("player"), body.get("bet"), body.get("price") or e.get("price"),
                                     e.get("state"), e.get("reason") if e["t"] == "pulled" else None,
                                     e.get("result"), e.get("actual_text"), e.get("units")) if x is not None)))
            log_before = log_now
            with open(os.path.join(data, "slate.json")) as f:
                sl = json.load(f)
            print("    slate: prices %s | %d open, %d pulled, %d started | parlays %d | empty: %s" % (
                sl["status"]["prices_state"], sum(1 for p in sl["picks"] if p["rank"]),
                sum(1 for p in sl["picks"] if p["pulled"]),
                sum(1 for p in sl["picks"] if not p["rank"] and not p["pulled"]),
                len(sl["parlays"]), (sl["empty"] or {}).get("text")))
            for b in sl["banners"]:
                print("    banner [%s] %s" % (b["level"], b["text"]))
    shutil.rmtree(work, ignore_errors=True)
    print("\nreplay finished. Files are in %s" % data)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
