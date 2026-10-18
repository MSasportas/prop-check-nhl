"""odds.py: Hard Rock prices from the-odds-api (bookmaker `hardrockbet`).

What lives here
  keys      read from env ODDS_API_KEYS only. Never printed, never written. A key that is used up or
            refused (401 / 429) is skipped and the next one is tried.
  ledger    data/state/credits.json: what each key has left (by position, never the key) and what we spent.
  plan      allowance = pool credits left / games left before the 1st. The allowance picks a tier, the
            tier decides which pulls (A, B, C) run and which markets they ask for (Sharp standard, section 2).
  pulls     each run asks "which pull is due for which game right now" from the files on disk, fetches
            those games into memory, then writes data/odds/<date>.json once.
  checks    a line is used only if both sides are there, the hold is sane and the price is fresh.

Cost: 1 credit per market RETURNED per game. The events list is free.
With PC_ODDS_FIXTURE_DIR set nothing here touches the network (see _fixture_* below).
"""
import json
import math
import os
import urllib.parse
from datetime import datetime, timedelta

import common
import names
import teams

API = "https://api.the-odds-api.com/v4/sports/icehockey_nhl"
SOURCE = {"ok": 0, "failed": 0}
KEYS_REFUSED_TEXT = "Hard Rock prices are off: the odds keys were refused. New keys are needed."


# ---------------------------------------------------------------- price arithmetic
def break_even(american):
    """-200 -> 0.6667, +120 -> 0.4545"""
    return (-american) / (-american + 100.0) if american < 0 else 100.0 / (american + 100.0)


def decimal(american):
    """-200 -> 1.5, +120 -> 2.2"""
    return 1.0 + (100.0 / -american if american < 0 else american / 100.0)


def american(dec):
    """Decimal price -> American integer (2.65 -> +165, 1.5 -> -200)."""
    if dec >= 2.0:
        return int(round((dec - 1.0) * 100))
    return int(round(-100.0 / (dec - 1.0)))


def fair_two_sided(price_side, price_other):
    """De-vig: our side's share of the two break-evens."""
    a, b = break_even(price_side), break_even(price_other)
    return a / (a + b)


def hold(price_a, price_b):
    return break_even(price_a) + break_even(price_b) - 1.0


# ---------------------------------------------------------------- keys and ledger
def load_keys():
    raw = os.environ.get("ODDS_API_KEYS", "")
    keys = [k.strip() for k in raw.replace("\n", ",").split(",") if k.strip()]
    for k in keys:
        common.register_secret(k)
    return keys


def fixture_dir():
    return os.environ.get("PC_ODDS_FIXTURE_DIR")


def ledger_path():
    return common.dpath("state", "credits.json")


class Pool:
    """The key pool and its ledger. Keys are known only by position (n = 1, 2, ...)."""

    def __init__(self, keys, now):
        self.keys, self.now = keys, now
        self.fixture = bool(fixture_dir())
        led = common.read_json(ledger_path(), {}) or {}
        self.spent = led.get("spent", [])
        saved = led.get("keys", [])
        month = now.strftime("%Y-%m")
        if self.fixture:
            start = (common.read_json(os.path.join(fixture_dir(), "pool.json"), {}) or {}).get("keys", [500])
            self.keys = ["fixture-key-%d" % (i + 1) for i in range(len(start))]
        self.state = []
        for i in range(len(self.keys)):
            s = saved[i] if i < len(saved) and led.get("count") == len(self.keys) else {}
            left = s.get("left")
            if s.get("month") != month:
                left = None                                # keys refill on the 1st: forget last month's count
            if self.fixture and left is None:
                left = start[i]
            status = "ok" if left != 0 else "empty"
            # a key the feed refused (401, not "used up") stays refused this month until it answers again: it is
            # not used for pulls, but the free events call asks it every run (see unknown()), so it recovers
            if s.get("status") == "invalid" and s.get("month") == month and not self.fixture:
                status = "invalid"
            self.state.append({"n": i + 1, "left": left, "status": status,
                               "checked_at": s.get("checked_at") if left is not None or status == "invalid" else None,
                               "month": month})

    # -- facts
    def count(self):
        return len(self.keys)

    # A key's number is UNKNOWN (left is None) until the feed reports it. A refused (401) or rate-limited (429)
    # key stays unknown; it is never counted as 0. Only a feed answer saying "used up" (or 0 left) means 0.
    def unknown(self):
        """How many keys have not reported what they have left."""
        return sum(1 for s in self.state if s["left"] is None or s["status"] == "invalid")

    def known(self):
        """True once at least one key has reported a number."""
        return any(s["left"] is not None and s["status"] != "invalid" for s in self.state)

    def all_used_up(self):
        """True only when EVERY key has reported 0 left."""
        return bool(self.state) and all(s["left"] == 0 for s in self.state)

    def all_refused(self):
        """True when no key can be used because the feed refused them: every key is refused (401) or used up,
        and at least one is refused."""
        return keys_refused(self.state, len(self.state))

    def total_left(self):
        """Credits on keys that have reported a number (refused keys are left out, not counted as 0)."""
        return sum(s["left"] for s in self.state if s["left"] is not None and s["status"] != "invalid")

    def public(self):
        return [{"n": s["n"], "left": s["left"]} for s in self.state]

    def spent_on(self, slate):
        return sum(e["cost"] for e in self.spent if e["date"] == slate)

    # -- bookkeeping
    def note_headers(self, i, headers, slate=None, pull=None, game_id=None, returned=0):
        s = self.state[i]
        try:
            s["left"] = int(float(headers.get("x-requests-remaining")))
        except (TypeError, ValueError):
            if s["left"] is not None and returned:
                s["left"] = max(0, s["left"] - returned)
        try:
            cost = int(float(headers.get("x-requests-last")))
        except (TypeError, ValueError):
            cost = returned
        s["checked_at"] = common.iso(self.now)
        s["status"] = "empty" if s["left"] == 0 else "ok"
        if slate and cost:
            self.spent.append({"at": common.iso(self.now), "date": slate, "pull": pull, "game_id": game_id,
                               "cost": cost, "key": s["n"]})
        return cost

    def save(self):
        keep_from = (self.now - timedelta(days=62)).date().isoformat()
        self.spent = [e for e in self.spent if e["date"] >= keep_from]
        common.write_json(ledger_path(), {"count": len(self.keys), "keys": self.state, "spent": self.spent})

    def candidates(self, need):
        """Key positions worth trying for a request that may cost `need` credits, best first."""
        out = [i for i, s in enumerate(self.state) if s["status"] == "ok" and (s["left"] is None or s["left"] >= need)]
        return out


# ---------------------------------------------------------------- the client
class Client:
    def __init__(self, pool, cfg):
        self.pool, self.cfg = pool, cfg
        self.errors = []                                   # short, key-free notes for status.json

    # -- network
    def _get(self, path, params, need, slate=None, pull=None, game_id=None):
        """Try keys in order until one answers. Returns (json or None, cost)."""
        for i in self.pool.candidates(need):
            q = urllib.parse.urlencode(dict(params, apiKey=self.pool.keys[i]))
            r = common.http_get("%s%s?%s" % (API, path, q), timeout=30)
            if r.ok:
                js = r.json()
                if js is None:
                    self.errors.append("odds feed sent an unreadable answer")
                    SOURCE["failed"] += 1
                    return None, 0
                returned = _markets_returned(js, self.cfg["ops"]["bookmakers"]) if need else 0
                cost = self.pool.note_headers(i, r.headers, slate, pull, game_id, returned)
                SOURCE["ok"] += 1
                return js, cost
            if r.status in (401, 429):
                body = r.text().upper()
                st = self.pool.state[i]
                if "OUT_OF_USAGE" in body or "QUOTA" in body or "USAGE" in body:
                    st["left"], st["status"] = 0, "empty"  # the feed says this key is used up
                elif r.status == 401:
                    st["status"] = "invalid"               # refused: its number is unknown, not 0
                else:
                    st["status"] = "limited"               # 429 rate limit: skip this key for this run
                st["checked_at"] = common.iso(self.pool.now)
                self.errors.append("key %d refused (%d), trying the next" % (i + 1, r.status))
                continue
            if r.status == 422 or r.status == 404:         # event or market not offered: not a feed failure
                SOURCE["ok"] += 1
                return {}, 0
            self.errors.append("odds feed did not answer (%s)" % (r.error or r.status))
            SOURCE["failed"] += 1
            return None, 0
        self.errors.append("every odds key was refused" if self.pool.all_refused() else "no odds key with credits left")
        return None, 0

    # -- fixtures
    def _fixture_json(self, name):
        try:
            with open(os.path.join(fixture_dir(), name), "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return None

    def _fixture_spend(self, cost, slate, pull, game_id):
        for i in self.pool.candidates(cost):
            st = self.pool.state[i]
            st["left"] -= cost
            st["checked_at"] = common.iso(self.pool.now)
            st["status"] = "empty" if st["left"] == 0 else "ok"
            if cost:
                self.pool.spent.append({"at": common.iso(self.pool.now), "date": slate, "pull": pull,
                                        "game_id": game_id, "cost": cost, "key": st["n"]})
            return True
        return False

    # -- public
    def refresh_keys(self, only_unknown=False):
        """Ask the free events endpoint once per key so we know what each key has left.
        only_unknown: ask only keys whose number we do not know yet. Returns the events list (or None)."""
        if self.pool.fixture:
            ev = self._fixture_json("events.json")
            SOURCE["ok" if ev is not None else "failed"] += 1
            if ev is None:
                self.errors.append("odds feed did not answer (fixture has no events.json)")
            return ev
        events = None
        for i in range(self.pool.count()):
            st = self.pool.state[i]
            if only_unknown and st["left"] is not None and st["status"] != "invalid":
                continue
            q = urllib.parse.urlencode({"apiKey": self.pool.keys[i], "dateFormat": "iso"})
            r = common.http_get("%s/events?%s" % (API, q), timeout=30)
            st = self.pool.state[i]
            if r.ok and r.json() is not None:
                self.pool.note_headers(i, r.headers)
                events = events if events is not None else r.json()
                SOURCE["ok"] += 1
            elif r.status in (401, 429):
                body = r.text().upper()
                if "USAGE" in body or "QUOTA" in body:
                    st["left"], st["status"] = 0, "empty"
                else:
                    st["status"] = "invalid" if r.status == 401 else "limited"
                st["checked_at"] = common.iso(self.pool.now)
                self.errors.append("key %d refused (%d)" % (i + 1, r.status))
            else:
                self.errors.append("odds feed did not answer (%s)" % (r.error or r.status))
                SOURCE["failed"] += 1
        return events

    def event_odds(self, event_id, away, home, market_keys, slate, pull, game_id):
        """Prices for one game. Returns (payload or None, cost). None = the feed failed (retry later)."""
        if self.pool.fixture:
            js = self._fixture_json("odds_%s_%s.json" % (away.lower(), home.lower())) or \
                self._fixture_json("odds_%s.json" % event_id)
            if js is None:
                self.errors.append("odds feed did not answer (no fixture for %s at %s)" % (away, home))
                SOURCE["failed"] += 1
                return None, 0
            js = json.loads(json.dumps(js))
            for b in js.get("bookmakers", []):             # the real feed returns only what was asked for
                b["markets"] = [m for m in b.get("markets", []) if m["key"] in market_keys]
            cost = _markets_returned(js, self.cfg["ops"]["bookmakers"])
            if not self._fixture_spend(cost, slate, pull, game_id):
                self.errors.append("no odds key with credits left")
                return None, 0
            SOURCE["ok"] += 1
            return js, cost
        params = {"regions": self.cfg["ops"]["odds_region"], "bookmakers": ",".join(self.cfg["ops"]["bookmakers"]),
                  "markets": ",".join(market_keys), "oddsFormat": "american", "dateFormat": "iso"}
        return self._get("/events/%s/odds" % event_id, params, len(market_keys), slate, pull, game_id)


def _markets_returned(js, books):
    if not isinstance(js, dict):
        return 0
    keys = set()
    for b in js.get("bookmakers", []) or []:
        for m in b.get("markets", []) or []:
            keys.add(m.get("key"))
    return len(keys)


def keys_refused(key_state, key_count):
    """From the ledger's key list: every key is refused (status invalid) or used up (0 left), at least one is
    refused, and the ledger covers every key in use. Then no price can be read until new keys are added."""
    ks = list(key_state or [])
    if not ks or (key_count and len(ks) != key_count):
        return False
    return all(k.get("status") == "invalid" or k.get("left") == 0 for k in ks) and \
        any(k.get("status") == "invalid" for k in ks)


# ---------------------------------------------------------------- the plan (pure functions, easy to test)
def tier_of(allowance, v):
    """0: some games, shots only. 1: shots, all games. 2: + shots pull C and B. 3: + saves (logged). 4: + goals."""
    if allowance < v["tier_shots_all"]:
        return 0
    if allowance < v["tier_points"]:
        return 1
    if allowance < v["tier_second_pull"]:
        return 2
    if allowance < v["tier_top"]:
        return 3
    return 4


def markets_for(tier, pull, live_markets=()):
    """Which markets a pull asks for at a tier. [] = this pull does not run at this tier."""
    if pull == "A":
        return ["shots"]                                   # cheapest market only; points wait for confirmed lineups
    if pull == "B":
        if tier == 2:
            return ["shots"]                               # points picks are off (2026-10-18 focus): shots re-price only
        if tier == 3:
            return ["shots", "saves"]                      # saves: logged to build the second market's sample
        if tier >= 4:
            return ["shots", "saves", "goals"]
        return []
    if pull == "C":
        return sorted(m for m in live_markets if m == "shots") if tier >= 2 else []
    return []


def make_plan(pool_left, games_left, games_today, v):
    allowance = (pool_left / games_left) if games_left else 0.0
    return {"allowance": round(allowance, 4), "tier": tier_of(allowance, v),
            "budget_today": int(math.floor(allowance * games_today + 1e-9)),
            "pool_at_plan": pool_left, "games_left": games_left, "games_today": games_today}


def pull_times(slate, games, v):
    """When A and B fall due today. games: today's games (each with 'start'). Returns dict(A=dt, B=dt, first=dt)."""
    first = min(common.parse_iso(g["start"]) for g in games)
    hh, mm = [int(x) for x in v["pull_a"].split(":")]
    a_clock = datetime.fromisoformat(slate).replace(hour=hh, minute=mm, tzinfo=common.ET)
    a = min(a_clock, first - timedelta(minutes=v["pull_a_before_first_min"]))
    return {"A": a, "B": first - timedelta(minutes=v["pull_b_min"]), "first": first}


def lineups_confirmed(state, games):
    """{game_id: True} for games whose both teams have a Daily Faceoff page dated today (data/state/lineups.json)."""
    teams = (state or {}).get("teams") if isinstance(state, dict) else None
    teams = teams if isinstance(teams, dict) else {}

    def ok(t):
        rec = teams.get(t)
        page = rec.get("page") if isinstance(rec, dict) else None
        return isinstance(page, dict) and page.get("today") is True
    
    return {g["id"]: ok(g["away"]) and ok(g["home"]) for g in games}


def due_pulls(now, games, tier, v, fetched, live_markets, started, retry_min=30, lineups_ok=None):
    """Decide, from what is on disk, which pull each game needs right now.

    games: today's games. fetched: {game_id: [dict(pull, at (datetime), markets asked, returned)]} for every
    read already made today (committed or staged). live_markets: {game_id: set of markets holding a live
    pick}. started: {game_id: bool}.
    A pull is "done" for a game once every market it wants has been RETURNED by a read made at or after the
    pull's due time. A market the book has not posted yet costs nothing to ask for, so it is asked again
    (at most every `retry_min` minutes) until the pull's window closes.
    lineups_ok: {game_id: bool}, both teams' lineups confirmed. Pull B (shots re-price, saves, goals) needs it; if it is
    still False at pull_c_min before puck, B falls back to shots only so Daily Faceoff being down does not
    kill shots picks. Pull A is shots only.
    Returns a list of dict(pull, game, markets) in puck-time order, one per game at most."""
    lineups_ok = lineups_ok or {}
    if not games:
        return []
    t = pull_times(games[0]["date"], games, v)
    out = []
    for g in sorted(games, key=lambda x: (x["start"], x["id"])):
        if started.get(g["id"]):
            continue
        start = common.parse_iso(g["start"])
        left = (start - now).total_seconds() / 60.0
        done = fetched.get(g["id"], [])
        c_due = start - timedelta(minutes=v["pull_c_min"])
        b_due = start - timedelta(minutes=v["pull_b_min"])     # B is per game: pull_b_min before ITS puck

        def need(markets, due_at):
            got = set()
            for f in done:
                if f["at"] >= due_at:
                    got |= set(f["returned"])
            missing = [m for m in markets if m not in got]
            last_try = None
            for f in done:                                 # only asks that included a still-missing market count
                if f["at"] >= due_at and set(missing) & set(f["markets"]):
                    last_try = f["at"] if last_try is None else max(last_try, f["at"])
            if missing and last_try is not None and (now - last_try).total_seconds() / 60.0 < retry_min:
                return []                                  # asked recently and it was not posted: wait
            return missing

        choice = None
        b_markets = markets_for(tier, "B")
        if b_markets and now >= b_due and left >= v["pull_latest_min"]:
            if not lineups_ok.get(g["id"]):
                b_markets = ["shots"] if left <= v["pull_c_min"] else []      # fallback at the 45 minute mark
            m = need(b_markets, b_due) if b_markets else []
            if m and now >= c_due and tier >= 2 and left >= v["pull_c_latest_min"]:
                # B and C fall due together (45 minute mark): one read for both, not two
                m = m + [x for x in need(markets_for(tier, "C", live_markets.get(g["id"], ())), c_due) if x not in m]
            if m:
                choice = ("B", m)
        if choice is None and tier >= 2 and now >= c_due and left >= v["pull_c_latest_min"]:
            m = need(markets_for(tier, "C", live_markets.get(g["id"], ())), c_due)
            if m:
                choice = ("C", m)
        if choice is None and now >= t["A"] and left >= v["pull_latest_min"]:
            m = need(markets_for(tier, "A"), t["A"])
            if m:
                choice = ("A", m)
        if choice:
            out.append({"pull": choice[0], "game": g, "markets": choice[1]})
    return out


def next_read_at(now, games, tier, v, fetched, started, has_budget=True, lineups_ok=None):
    """The next time a price read is expected (for the status sheet). None when none is coming."""
    if not games or not has_budget:
        return None
    slate = games[0]["date"]
    t = pull_times(slate, games, v)
    cands = []
    for g in games:
        if started.get(g["id"]):
            continue
        start = common.parse_iso(g["start"])
        done = fetched.get(g["id"], [])
        if not done and start - timedelta(minutes=v["pull_latest_min"]) >= now:
            cands.append(max(t["A"], now))
        b_due = start - timedelta(minutes=v["pull_b_min"])
        c = start - timedelta(minutes=v["pull_c_min"])
        bm = markets_for(tier, "B")
        if bm and start - timedelta(minutes=v["pull_latest_min"]) >= max(b_due, now):
            got = set()
            for f in done:
                if f["at"] >= b_due:
                    got |= set(f["returned"])
            if set(bm) - got:
                if (lineups_ok or {}).get(g["id"]):
                    cands.append(max(b_due, now))
                elif c > now:                              # unconfirmed: the guaranteed read is the 45 minute fallback
                    cands.append(c)
                elif "shots" not in got:
                    cands.append(now)
        if tier >= 2 and c > now:
            cands.append(c)
    return min(cands) if cands else None


# ---------------------------------------------------------------- matching events and names
def match_events(events, games, hours):
    """Feed events -> NHL game ids by both team names and a start time within `hours`.
    Returns ({game_id: event_id}, [unknown team names])."""
    out, unknown = {}, []
    for e in events or []:
        a, h = teams.abbrev_for(e.get("away_team")), teams.abbrev_for(e.get("home_team"))
        for nm, ab in ((e.get("away_team"), a), (e.get("home_team"), h)):
            if ab is None and nm and nm not in unknown:
                unknown.append(nm)
        if not a or not h:
            continue
        try:
            when = common.parse_iso(e["commence_time"])
        except (KeyError, ValueError, TypeError):
            continue
        for g in games:
            if g["away"] == a and g["home"] == h and \
                    abs((common.parse_iso(g["start"]) - when).total_seconds()) <= hours * 3600:
                out[str(g["id"])] = e["id"]
    return out, unknown


def normalize(payload, game, matcher, requested_keys, pull, at, cost, cfg):
    """One game's raw feed answer -> the record we keep in data/odds/<date>.json (every price, all markets)."""
    key_to_market = {m["feed_key"]: name for name, m in cfg["ops"]["markets"].items()}
    book = None
    for want in cfg["ops"]["bookmakers"]:
        book = next((b for b in (payload or {}).get("bookmakers", []) or [] if b.get("key") == want), None)
        if book:
            break
    out = {"game_id": game["id"], "away": game["away"], "home": game["home"], "pull": pull, "at": common.iso(at),
           "cost": cost, "requested": sorted(key_to_market.get(k, k) for k in requested_keys),
           "book": book.get("key") if book else None, "markets": {}, "unmatched": []}
    for m in (book or {}).get("markets", []) or []:
        name = key_to_market.get(m.get("key"), m.get("key"))
        rows = []
        for o in m.get("outcomes", []) or []:
            who = o.get("description") or ""
            side = (o.get("name") or "").lower()
            if side not in ("over", "under") or o.get("price") is None:
                continue
            p = matcher.find(who) if matcher else None
            if p is None and who not in out["unmatched"]:
                out["unmatched"].append(who)
            try:
                price = int(round(float(o["price"])))
                line = float(o["point"]) if o.get("point") is not None else None
            except (TypeError, ValueError):
                continue
            rows.append({"name": who, "pid": p["id"] if p else None, "team": p["team"] if p else None,
                         "side": side, "line": line, "price": price})
        out["markets"][name] = {"last_update": m.get("last_update"), "outcomes": rows}
    return out


# ---------------------------------------------------------------- feed checks
def check_pair(over, under, last_update, read_at, v):
    """Is this over/under pair usable? Returns None when fine, else a short reason."""
    if over is None or under is None:
        return "one side missing"
    h = hold(over, under)
    if h < v["hold_min"] or h > v["hold_max"]:
        return "hold out of range"
    if is_stale(last_update, read_at, v):
        return "price is stale"
    return None


def is_stale(last_update, read_at, v):
    lu = common.parse_iso(last_update) if last_update else None
    if lu is None:
        return True
    return (read_at - lu).total_seconds() / 60.0 >= v["stale_min"]


def build_view(odds_doc, cfg):
    """Latest known prices per game and market, with the feed checks applied.

    Returns {game_id: {market: view}} where view is
      at            when these prices were read (datetime)
      pull          A | B | C
      gone          True if the newest read that ASKED for this market came back without it
      stale         True if the feed's own last_update was too old at read time
      pairs         {(pid, line): dict(over, under, ok, why, name, team)}   matched players only
      checked/failed  counts for the page
    """
    v = cfg["values"]
    out = {}
    for f in (odds_doc or {}).get("fetches", []):
        at = common.parse_iso(f["at"])
        gv = out.setdefault(f["game_id"], {})
        if f.get("book") is None:
            continue                                        # the book was absent: a feed problem, not news
        for m in f.get("requested", []):
            if m not in f.get("markets", {}):
                prev = gv.get(m)
                gv[m] = {"at": at, "pull": f["pull"], "gone": True, "stale": False,
                         "pairs": {}, "checked": 0, "failed": 0, "prev": prev}
                continue
            mk = f["markets"][m]
            stale = is_stale(mk.get("last_update"), at, v)
            if stale and m in gv and not gv[m].get("gone"):
                gv[m]["stale_read_at"] = at                 # keep the last good read; note the stale one
                continue
            pairs = {}
            for o in mk["outcomes"]:
                if o["pid"] is None or o["line"] is None:
                    continue
                p = pairs.setdefault((o["pid"], o["line"]), {"over": None, "under": None, "name": o["name"],
                                                             "team": o["team"]})
                p[o["side"]] = o["price"]
            failed = 0
            for p in pairs.values():
                p["why"] = check_pair(p["over"], p["under"], mk.get("last_update"), at, v)
                p["ok"] = p["why"] is None
                failed += 0 if p["ok"] else 1
            gv[m] = {"at": at, "pull": f["pull"], "gone": False, "stale": stale, "pairs": pairs,
                     "checked": len(pairs), "failed": failed}
    return out


# ---------------------------------------------------------------- the daily state file and the pull itself
def day_path():
    return common.dpath("state", "odds_day.json")


def odds_path(slate):
    return common.dpath("odds", "%s.json" % slate)


def load_day(slate):
    d = common.read_json(day_path(), {}) or {}
    if d.get("date") != slate:
        d = {"date": slate, "plan": None, "events": {}, "events_at": None, "unknown_teams": [],
             "done": {}, "stage": None, "skipped": {}, "last_fail_at": None, "fail_note": None, "key_count": None}
    for k, dv in (("events", {}), ("done", {}), ("skipped", {}), ("unknown_teams", [])):
        d.setdefault(k, dv)
    return d


def fetched_map(day):
    """{game_id: [{pull, at, markets}]} from committed pulls plus anything staged."""
    out = {}
    stage = (day.get("stage") or {}).get("fetches", [])
    staged = [{"pull": f["pull"], "at": f["at"], "markets": f["requested"], "game_id": f["game_id"],
               "returned": sorted(f["markets"])} for f in stage]
    for src in (day["done"].values(), staged):
        for group in src:
            for f in (group if isinstance(group, list) else [group]):
                out.setdefault(f["game_id"], []).append({"pull": f["pull"], "at": common.parse_iso(f["at"]),
                                                         "markets": f["markets"],
                                                         "returned": f.get("returned", f["markets"])})
    return out


def run_pulls(now, slate, games, sched_left, cfg, rosters_for, live_markets, started, dry_run=False, lineups_ok=None):
    """The whole odds step. Returns a result dict for status.json and the engine.

    games: today's regular-season games. sched_left: (games left this month, game days list).
    rosters_for(game) -> names.Matcher for that game. live_markets: {game_id: set(market)}.
    """
    v, ops = cfg["values"], cfg["ops"]
    keys = load_keys()
    pool = Pool(keys, now)
    client = Client(pool, cfg)
    day = load_day(slate)
    res = {"status": "ok", "note": "", "keys": pool.public(), "pool_left": None, "plan": day.get("plan"),
           "fetched_now": 0, "errors": client.errors, "no_keys": pool.count() == 0}
    if pool.count() == 0:
        res.update(status="skipped", note="no odds keys set")
        _finish(day, pool, res, sched_left, cfg, write=not dry_run)
        return res
    if not games:
        res.update(status="skipped", note="no games today")
        _finish(day, pool, res, sched_left, cfg, write=not dry_run)
        return res

    # 1. know the pool and today's events (free). Once a day, and again if a key was added or a game has no event.
    need_events = day.get("events_at") is None or day.get("key_count") != pool.count()
    only_unknown = False
    if not need_events and pool.unknown():
        need_events, only_unknown = True, True             # a key has not reported yet: ask it again (free)
    missing_event = any(str(g["id"]) not in day["events"] and not started.get(g["id"]) for g in games)
    last_ev = common.parse_iso(day.get("events_at"))
    if missing_event and (last_ev is None or now - last_ev >= timedelta(minutes=30) or now < last_ev):
        need_events = True
    if need_events and not dry_run:
        events = client.refresh_keys(only_unknown=only_unknown and not missing_event)
        if events is not None:
            matched, unknown = match_events(events, games, ops["event_match_hours"])
            day["events"].update(matched)
            day["unknown_teams"] = unknown
            day["events_at"] = common.iso(now)
            day["key_count"] = pool.count()
        else:
            day["last_fail_at"], day["fail_note"] = common.iso(now), "The odds feed did not answer."

    # 2. the plan for today. Made only once a key has reported a number. Fixed once made, except that it is
    #    re-made when the number of keys changes, when it was made on 0 credits and a key now reports credits,
    #    or when a key that had not reported (refused, rate-limited) now has.
    old = day.get("plan")
    replan = old is None or old.get("key_count") != pool.count() or \
        (old.get("pool_at_plan", 0) == 0 and pool.total_left() > 0) or \
        old.get("unknown_keys", 0) > pool.unknown()
    if replan and pool.known():
        spent = pool.spent_on(slate)
        plan = make_plan(pool.total_left() + spent, sched_left[0], len(games), v)
        plan["key_count"] = pool.count()
        plan["unknown_keys"] = pool.unknown()
        plan["made_at"] = common.iso(now)
        if old is not None:
            plan["replaced"] = old.get("made_at")
        day["plan"] = plan
    plan = day.get("plan")
    res["plan"] = plan
    if plan is None:
        day["keys_unread_at"] = common.iso(now)
        if pool.all_refused():                             # a known state, not a run failure (the page says it)
            res.update(status="skipped", note="every odds key was refused")
        else:
            res.update(status="failed" if client.errors else "skipped",
                       note="could not read the odds keys yet")
        _finish(day, pool, res, sched_left, cfg, write=not dry_run)
        return res

    # 3. which pulls are due
    due = due_pulls(now, games, plan["tier"], v, fetched_map(day), live_markets, started,
                    ops.get("empty_retry_min", 30), lineups_ok=lineups_ok)
    key_of = {name: m["feed_key"] for name, m in ops["markets"].items()}
    stage = day.get("stage") or {"since": None, "fetches": []}
    failed_games, no_budget = [], []
    for d in due:
        g = d["game"]
        if dry_run:
            continue
        budget_left = plan["budget_today"] - pool.spent_on(slate)
        if budget_left < len(d["markets"]) or pool.total_left() < len(d["markets"]):
            no_budget.append(g["id"])
            day["skipped"][str(g["id"])] = {"pull": d["pull"], "why": "no budget", "at": common.iso(now)}
            continue
        ev = day["events"].get(str(g["id"]))
        if not ev:
            failed_games.append(g["id"])
            client.errors.append("no feed event for %s at %s" % (g["away"], g["home"]))
            continue
        payload, cost = client.event_odds(ev, g["away"], g["home"], [key_of[m] for m in d["markets"]],
                                          slate, d["pull"], g["id"])
        if payload is None:
            failed_games.append(g["id"])
            continue
        matcher = rosters_for(g)
        stage["fetches"].append(normalize(payload, g, matcher, [key_of[m] for m in d["markets"]],
                                          d["pull"], now, cost, cfg))
        res["fetched_now"] += 1
        day["skipped"].pop(str(g["id"]), None)
        day["stage"] = stage
        pool.save()
        common.write_json(day_path(), day)                 # credits were spent: keep the answer even if we crash

    # 4. commit: one write of the odds file. A pull that failed part-way waits (briefly) for its retry.
    if failed_games:
        day["last_fail_at"] = common.iso(now)
        day["fail_note"] = "The odds feed did not answer."
        if stage["fetches"] and stage.get("since") is None:
            stage["since"] = common.iso(now)
    hold_until = common.parse_iso(stage.get("since")) + timedelta(minutes=ops["stage_hold_min"]) \
        if stage.get("since") else None
    retry_possible = bool(failed_games) and any(
        (common.parse_iso(g["start"]) - now).total_seconds() / 60.0 >= v["pull_c_latest_min"]
        for g in games if g["id"] in failed_games)
    holding = bool(stage["fetches"]) and bool(failed_games) and retry_possible and hold_until and now < hold_until
    if stage["fetches"] and not holding and not dry_run:
        doc = common.read_json(odds_path(slate)) or {"date": slate, "fetches": []}
        have = {(f["game_id"], f["at"], f["pull"]) for f in doc["fetches"]}
        for f in stage["fetches"]:
            if (f["game_id"], f["at"], f["pull"]) not in have:
                doc["fetches"].append(f)
            day["done"].setdefault(str(f["game_id"]), [])
            if not any(x["at"] == f["at"] and x["pull"] == f["pull"] for x in day["done"][str(f["game_id"])]):
                day["done"][str(f["game_id"])].append({"game_id": f["game_id"], "pull": f["pull"], "at": f["at"],
                                                        "markets": f["requested"], "returned": sorted(f["markets"]),
                                                        "cost": f["cost"]})
        common.write_json(odds_path(slate), doc, pretty=False)
        day["stage"] = None
        res["committed"] = True
    elif holding:
        day["stage"] = stage
        res["note"] = "pull incomplete, %d game(s) to retry" % len(failed_games)
    if res["fetched_now"] and not failed_games:
        day["last_fail_at"], day["fail_note"] = None, None
    if failed_games:
        res["status"] = "failed" if not res["fetched_now"] else "ok"
        if pool.all_refused():                             # a known state, not a run failure (the page says it)
            res.update(status="skipped", note="every odds key was refused")
    if not res["note"]:
        bits = []
        if res["fetched_now"]:
            got = sum(1 for f in stage["fetches"][-res["fetched_now"]:] if f["markets"])
            if got:
                bits.append("%d game(s) priced" % got)
            if res["fetched_now"] - got:
                bits.append("%d game(s) not posted yet" % (res["fetched_now"] - got))
        if failed_games:
            bits.append("%d game(s) failed" % len(failed_games))
        if no_budget:
            bits.append("%d game(s) skipped, budget used" % len(no_budget))
        res["note"] = ", ".join(bits) or "no pull due"
    res["failed_games"], res["no_budget"] = failed_games, no_budget
    _finish(day, pool, res, sched_left, cfg, write=not dry_run)
    return res


def _finish(day, pool, res, sched_left, cfg, write=True):
    res["keys"] = pool.public()
    res["pool_left"] = pool.total_left() if pool.known() else None
    res["all_used_up"] = pool.all_used_up()
    res["spent_today"] = pool.spent_on(day["date"])
    res["day"] = day
    if write:
        pool.save()
        common.write_json(day_path(), day)


def used_at(view):
    """When the newest price read that the engine actually USES was made: a read that returned the market,
    was not stale and has at least one line passing the feed checks. None when there is none."""
    best = None
    for gv in (view or {}).values():
        for mv in gv.values():
            if mv.get("gone") or mv.get("stale") or not any(p.get("ok") for p in mv.get("pairs", {}).values()):
                continue
            best = mv["at"] if best is None else max(best, mv["at"])
    return best


def days_to_reset(slate):
    """Days from the slate date up to the 1st of next month, when the keys refill (Oct 31 -> 1)."""
    d = datetime.fromisoformat(slate).date()
    first = (d.replace(day=1) + timedelta(days=32)).replace(day=1)
    return (first - d).days


def pool_summary(pool_left, key_count, plan, sched_days, cfg, spent=(), slate=None):
    """What the page shows about the key pool.
    pulls_left      credits on keys that have reported a number (None until one has)
    game_days_left  game days the pool covers at the basic cost (2 credits a game)
    days_left       pool / average daily spend at the current tier (recent game days; today's budget until
                    there is a history), rounded down, and never more than the days left before the keys
                    refill on the 1st. None when it cannot be worked out.
    low             the allowance is under ops.pool_low_allowance"""
    if pool_left is None:
        return {"pulls_left": None, "keys": key_count, "game_days_left": None, "days_left": None, "low": False}
    per_game = cfg["ops"]["basic_cost_per_game"]
    left, days = pool_left, 0
    for _, n in sched_days:
        if left < per_game * n:
            break
        left -= per_game * n
        days += 1
    by_day = {}
    for e in spent or ():
        if slate is None or e["date"] < slate:
            by_day[e["date"]] = by_day.get(e["date"], 0) + e["cost"]
    recent = [c for d, c in sorted(by_day.items())[-7:] if c > 0]
    avg = (sum(recent) / float(len(recent))) if recent else float((plan or {}).get("budget_today") or 0)
    days_left = int(math.floor(pool_left / avg + 1e-9)) if avg > 0 else None
    if days_left is not None and slate:
        days_left = min(days_left, days_to_reset(slate))      # the keys refill on the 1st: never "more" than that
    low = bool(plan) and plan["allowance"] < cfg["ops"]["pool_low_allowance"]
    return {"pulls_left": pool_left, "keys": key_count, "game_days_left": days, "days_left": days_left, "low": low}
