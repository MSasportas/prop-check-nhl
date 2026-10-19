"""S7-probe: re-pull saves at the original -45 timestamp with 10 books for 15 random Nov-Feb games."""
import json, os, random, glob
import oc3
SCR = "/tmp/claude-0/-home-claude/ab9b3f07-215a-50c7-96a2-d84b6c4f2d08/scratchpad"
src = SCR + "/r3/raw/odds/saves45"
match = json.load(open(SCR + "/r3/raw/odds/match.json"))
c = []
for f in sorted(glob.glob(src + "/*.json")):
    d = json.load(open(f))
    if not d or "data" not in d:
        continue
    ts = d["timestamp"]
    if "2025-11-01" <= ts[:10] < "2026-03-01":
        c.append((os.path.basename(f)[:-5], d["data"]["id"], ts))
random.Random(19).shuffle(c)
for gid, eid, ts in c[:15]:
    try:
        oc3.event_odds(eid, ts, "player_total_saves", "saves_" + gid)
    except oc3.Stop as e:
        print("STOP", e); break
print("candidates", len(c), "remaining", oc3.remaining())
