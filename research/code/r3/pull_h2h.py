"""S1-S3 pull: featured h2h, 10 books, 22:30Z on every 2025-26 regular-season game day (one snapshot = all games)."""
import json, sys
import oc3
G = "/tmp/claude-0/-home-claude/ab9b3f07-215a-50c7-96a2-d84b6c4f2d08/scratchpad/hist/raw/nhl/games.json"
days = sorted({g["date"] for g in json.load(open(G))})
lim = int(sys.argv[1]) if len(sys.argv) > 1 else len(days)
done = 0
for d in days[:lim]:
    try:
        js = oc3.featured(d + "T22:30:00Z", "h2h")
    except oc3.Stop as e:
        print("STOP", e); break
    done += 1
print("days", len(days), "done", done, "remaining", oc3.remaining())
