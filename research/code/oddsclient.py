"""Researcher's historical Odds API client (stdlib). Cache-first, ledger, hard floor on remaining credits.
The key is read from a file at call time and never printed, logged or written. Raw responses are cached OUTSIDE
the repo (PC_HIST_DIR, session scratch) and must never be committed.
Env: PC_HIST_DIR (default: session scratch hist/), PC_HIST_KEY_FILE, PC_HIST_FLOOR (default 182)."""
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

SCR = "/tmp/claude-0/-home-claude/ab9b3f07-215a-50c7-96a2-d84b6c4f2d08/scratchpad"
H = os.environ.get("PC_HIST_DIR", os.path.join(SCR, "hist"))
KEYF = os.environ.get("PC_HIST_KEY_FILE", os.path.join(SCR, "secrets", "hist_odds_key"))
LEDGER = os.path.join(H, "ledger_research.jsonl")
FLOOR = int(os.environ.get("PC_HIST_FLOOR", "182"))
BASE = "https://api.the-odds-api.com/v4/historical/sports/icehockey_nhl"


class Stop(Exception):
    pass


def _key():
    with open(KEYF) as f:
        return f.read().strip()


def redact(s):
    return re.sub(r"apiKey=[^&\s]+", "apiKey=REDACTED", str(s))


def remaining():
    """Last remaining-credits value seen in either ledger (research or DS)."""
    best = None
    for lf in (os.path.join(H, "ledger.jsonl"), LEDGER):
        if not os.path.exists(lf):
            continue
        for line in open(lf):
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("remaining") not in (None, ""):
                v = int(float(r["remaining"]))
                best = v if best is None else min(best, v)
    return best


def get(path, params, cache_file, expect_cost):
    if os.path.exists(cache_file):
        try:
            return json.load(open(cache_file))
        except ValueError:
            pass
    rem = remaining()
    if rem is not None and rem - expect_cost < FLOOR:
        raise Stop("remaining %s - %d < floor %d" % (rem, expect_cost, FLOOR))
    os.makedirs(os.path.dirname(cache_file), exist_ok=True)
    q = dict(params)
    q["apiKey"] = _key()
    url = BASE + path + "?" + urllib.parse.urlencode(q, safe=",:")
    for attempt in range(2):
        status, hdr, body, err = None, {}, None, None
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "pc-research/1"}), timeout=60) as r:
                status, hdr, body = r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            status, hdr = e.code, dict(e.headers or {})
            try:
                body = e.read()
            except Exception:
                body = None
        except Exception as e:
            err = redact(repr(e))
        hl = {k.lower(): v for k, v in hdr.items()}
        rec = {"t": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "path": redact(path),
               "markets": params.get("markets"), "cache": os.path.relpath(cache_file, H), "date": params.get("date"),
               "status": status, "last": hl.get("x-requests-last"), "remaining": hl.get("x-requests-remaining"),
               "used": hl.get("x-requests-used"), "err": err}
        with open(LEDGER, "a") as f:
            f.write(json.dumps(rec) + "\n")
        if status == 200 and body is not None:
            js = json.loads(body)
            with open(cache_file, "w") as f:
                json.dump(js, f)
            time.sleep(0.2)
            return js
        if status in (429, 500, 502, 503, 504) or err:
            time.sleep(3)
            continue
        if status in (401, 403):
            raise Stop("key refused (%s)" % status)
        with open(cache_file, "w") as f:
            json.dump({"_status": status, "_body": (body or b"")[:300].decode("utf-8", "replace")}, f)
        return None
    return None
