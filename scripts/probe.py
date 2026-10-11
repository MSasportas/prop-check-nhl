"""First-run probe: confirms the timer, the secret, Pages and outside hosts. Never prints or writes a key."""
import json, os, urllib.request, urllib.error, datetime

def get(url, timeout=25, headers=None):
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), b""
    except Exception as e:
        return 0, {}, str(type(e).__name__).encode()

out = {"ranAt": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
       "event": os.environ.get("GITHUB_EVENT_NAME", ""), "runId": os.environ.get("GITHUB_RUN_ID", "")}
keys = [k.strip() for k in os.environ.get("ODDS_API_KEYS", "").replace("\n", ",").split(",") if k.strip()]
out["keys"] = []
for i, k in enumerate(keys):
    st, h, _ = get("https://api.the-odds-api.com/v4/sports/?apiKey=" + k)
    low = {a.lower(): b for a, b in h.items()}
    out["keys"].append({"n": i + 1, "status": st, "left": low.get("x-requests-remaining"), "used": low.get("x-requests-used")})
hosts = {}
for name, url in {
    "nhl_web": "https://api-web.nhle.com/v1/schedule/now",
    "nhl_stats": "https://api.nhle.com/stats/rest/en/team",
    "dailyfaceoff_goalies": "https://www.dailyfaceoff.com/starting-goalies",
    "dailyfaceoff_lines": "https://www.dailyfaceoff.com/teams/florida-panthers/line-combinations",
    "pages": "https://msasportas.github.io/prop-check-nhl/status/probe.json",
    "pages_root": "https://msasportas.github.io/prop-check-nhl/",
}.items():
    st, h, body = get(url)
    hosts[name] = {"status": st, "bytes": len(body), "nextData": b"__NEXT_DATA__" in body}
out["hosts"] = hosts
os.makedirs("status", exist_ok=True)
json.dump(out, open("status/probe.json", "w"), indent=1)
print(json.dumps({k: v for k, v in out.items()}, indent=1))

# One-off: save a trimmed structure sample of Daily Faceoff pages so the parser can be written and tested.
import re
def trim(x, depth=0):
    if isinstance(x, dict): return {k: trim(v, depth + 1) for k, v in list(x.items())[:60]}
    if isinstance(x, list): return [trim(v, depth + 1) for v in x[:(40 if depth < 4 else 4)]]
    if isinstance(x, str): return x[:160]
    return x
for name, url in {"df_goalies": "https://www.dailyfaceoff.com/starting-goalies",
                  "df_lines": "https://www.dailyfaceoff.com/teams/philadelphia-flyers/line-combinations"}.items():
    st, h, body = get(url)
    m = re.search(rb'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', body, re.S)
    if m:
        try:
            json.dump(trim(json.loads(m.group(1)).get("props", {}).get("pageProps", {})), open("status/%s_sample.json" % name, "w"), indent=1)
        except Exception as e:
            print(name, "parse failed", type(e).__name__)
