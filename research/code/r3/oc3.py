"""Run-3 historical Odds API client (stdlib). Cache-first, own ledger, hard floor on remaining credits (150).
Key read from a file at call time; never printed, logged or written. Cache lives in session scratch (PC_R3_DIR),
packaged later as research/data/hist_addon_*.tgz with apiKey redacted."""
import json, os, re, time, urllib.error, urllib.parse, urllib.request

SCR = "/tmp/claude-0/-home-claude/ab9b3f07-215a-50c7-96a2-d84b6c4f2d08/scratchpad"
H = os.environ.get("PC_R3_DIR", os.path.join(SCR, "r3pull"))
KEYF = os.path.join(SCR, "secrets", "hist_odds_key")
LEDGER = os.path.join(H, "ledger_r3.jsonl")
FLOOR = 150
BASE = "https://api.the-odds-api.com/v4/historical/sports/icehockey_nhl"
BOOKS = "hardrockbet,hardrockbet_fl,pinnacle,draftkings,fanduel,betmgm,williamhill_us,espnbet,betrivers,fanatics"
os.makedirs(H, exist_ok=True)


class Stop(Exception):
    pass


def redact(s):
    return re.sub(r"apiKey=[^&\s]+", "apiKey=REDACTED", str(s))


def remaining():
    v = None
    if os.path.exists(LEDGER):
        for line in open(LEDGER):
            r = json.loads(line)
            if r.get("remaining") not in (None, ""):
                v = int(float(r["remaining"]))
    return v


def get(path, params, cache_rel, expect_cost):
    cf = os.path.join(H, cache_rel)
    if os.path.exists(cf):
        return json.load(open(cf))
    rem = remaining()
    if rem is not None and rem - expect_cost < FLOOR:
        raise Stop("remaining %s - %d < floor %d" % (rem, expect_cost, FLOOR))
    os.makedirs(os.path.dirname(cf), exist_ok=True)
    q = dict(params)
    q["apiKey"] = open(KEYF).read().strip()
    url = BASE + path + "?" + urllib.parse.urlencode(q, safe=",:")
    for attempt in range(3):
        status, hdr, body, err = None, {}, None, None
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "pc-research/3"}), timeout=60) as r:
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
               "markets": params.get("markets"), "cache": cache_rel, "date": params.get("date"), "status": status,
               "last": hl.get("x-requests-last"), "remaining": hl.get("x-requests-remaining"),
               "used": hl.get("x-requests-used"), "err": err}
        with open(LEDGER, "a") as f:
            f.write(json.dumps(rec) + "\n")
        if status == 200 and body is not None:
            js = json.loads(body)
            json.dump(js, open(cf, "w"))
            time.sleep(0.15)
            return js
        if status in (401, 403):
            raise Stop("key refused (%s)" % status)
        if status in (429, 500, 502, 503, 504) or err:
            time.sleep(3)
            continue
        json.dump({"_status": status, "_body": (body or b"")[:300].decode("utf-8", "replace")}, open(cf, "w"))
        return None
    return None


def featured(date_iso, markets="h2h,totals,spreads", tag=None):
    n = len(markets.split(","))
    return get("/odds", {"date": date_iso, "bookmakers": BOOKS, "markets": markets, "oddsFormat": "american"},
               "feat/%s_%s.json" % (tag or markets.replace(",", "+"), date_iso.replace(":", "")), 10 * n)


def event_odds(eid, date_iso, markets, tag):
    n = len(markets.split(","))
    return get("/events/%s/odds" % eid, {"date": date_iso, "bookmakers": BOOKS, "markets": markets,
               "oddsFormat": "american"}, "ev/%s_%s.json" % (tag, date_iso.replace(":", "")), 10 * n)
