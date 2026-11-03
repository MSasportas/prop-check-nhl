"""Run 19: fetch api-web player landing (birthDate) for every pid in shots45_lines (pre-lockbox) and the stats REST team list,
into scratch PC_R19_DIR/nhl/. Pbp comes from research/code/r17/fetch17.py (PC_R17_DIR = same dir). python3 -I fetch19.py"""
import json, os, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
D = os.environ["PC_R19_DIR"]; O = os.path.join(D, "nhl"); os.makedirs(O, exist_ok=True)


def get(url):
    for i in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (research)"}), timeout=60) as r:
                return json.load(r)
        except Exception:
            time.sleep(2 + 3 * i)
    return None


json.dump(get("https://api.nhle.com/stats/rest/en/team"), open(os.path.join(O, "teams.json"), "w"))
pids = sorted({json.loads(l)["pid"] for l in open(os.path.join(D, "h/work/shots45_lines.jsonl")) if json.loads(l)["date"] < "2026-03-01"})
fn = os.path.join(O, "birth.json")
B = json.load(open(fn)) if os.path.exists(fn) else {}


def one(pid):
    if str(pid) in B:
        return
    j = get("https://api-web.nhle.com/v1/player/%d/landing" % pid)
    B[str(pid)] = (j or {}).get("birthDate")


with ThreadPoolExecutor(8) as ex:
    list(ex.map(one, pids))
json.dump(B, open(fn, "w"))
print("pids", len(pids), "with birth", sum(1 for v in B.values() if v))
