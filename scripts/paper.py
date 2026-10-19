"""paper.py: the Gap + Guard PAPER test (TEAM.md section 7 item 21). Nothing here is a bet.

A flag is a Hard Rock shots line (1.5 / 2.5) whose price beats the other books' consensus by enough (STEP 1, the gap) and
that our model does not contradict (STEP 2, the guard: the model can only veto, never create). Flags are logged, frozen at the
price of their first qualifying read, followed to the 45-minute read (CLV) and graded at the frozen price, flat 1 unit.
Whether the idea works is judged on Nov 2 (section 7 item 21).

Everything is in EV% = fair_prob x Hard Rock decimal payout - 1, on unrounded floats, every threshold inclusive (>=).
  STEP 1 (gap) passes iff ALL: (a) EV of Hard Rock's price against the market fair >= gap_ev (+3.0%); (b) >= books_min (4)
    OTHER books priced the same player / line with both sides (Pinnacle is one of them); (c) market fair = median of those
    books' proportionally de-vigged fair probability for the side (even count: mean of the two middle values); (d) Pinnacle
    present with both sides AND Pinnacle's own fair EV on Hard Rock's price >= 0.0% (sign check only); (e) line 1.5 or 2.5;
    (f) Hard Rock price -200 .. +120. A book counts only if it returned fresh, two-sided prices with a sane hold
    (shadow.other_lines: the same rule as the shadow log's consensus).
  STEP 2 (guard): final = market_weight x market_fair + model_weight x calibrated model chance for the side, where the
    calibrated model = raw model chance of the over + a FROZEN additive offset per line (config ops.paper.thresholds.offsets;
    refit once from the 2025-26 Hard Rock shots lines, model from prior games only); under = 1 - over. Passes iff
    final x decimal - 1 >= final_ev (+2.0%).
Reads: only pull B (90 min) and pull C (45 min) reads can flag. Pull A (the 1 PM read) is baseline / context only. A read with
no "others" key (Hard Rock-only retry) is skipped entirely. Later reads can only PULL a flag (never re-price it).
Files (all under data/paper/, never under data/record/): events.jsonl (append-only: flag, veto, capped, pull, close, grade),
summary.json (derived, for the page and Discord), cursor.json (last read processed per game, derived). This module must never
import record's append functions or write under data/record/ (tests hash data/record/ around the step).
A failure here never fails a run (run.py wraps it as a soft step).
"""
import json
import os
import random
from datetime import datetime, timedelta

import common
import goalies
import guard_record
import lineups
import odds
import sched
import shadow

EPS = 1e-9
VERSION = 1
MARKET = "shots"
NOTE = "PAPER TEST - not bets. Nothing here is on the page as a bet, in the Record or in the picks."
SUMMARY_NIGHTS = 7


# ---------------------------------------------------------------- paths and the append-only log
def pdir():
    return common.dpath("paper")


def events_path():
    return os.path.join(pdir(), "events.jsonl")


def summary_path():
    return os.path.join(pdir(), "summary.json")


def cursor_path():
    return os.path.join(pdir(), "cursor.json")


def read_raw():
    try:
        with open(events_path(), "rb") as f:
            return f.read()
    except FileNotFoundError:
        return b""


def parse(raw):
    out = []
    for line in raw.decode("utf-8").splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out


def read_events():
    return parse(read_raw())


def append(events):
    """Append events to the paper log. Append-only: the old bytes must be an exact prefix of the new ones (checked
    here with the same test the Record guard uses), then one atomic write."""
    if not events:
        return 0
    old = read_raw()
    add = "".join(common.dumps(e, False) + "\n" for e in events).encode("utf-8")
    new = old + add
    why = guard_record.check(old, new)
    if why:
        raise RuntimeError("paper log guard: " + why)
    common.write_bytes(events_path(), new)
    return len(events)


# ---------------------------------------------------------------- the arithmetic (pure)
def fmt_line(line):
    return "%g" % line


def ev(prob, price):
    """EV per unit staked of a Hard Rock American price at a fair probability."""
    return prob * odds.decimal(price) - 1.0


def median(xs):
    return shadow._median(list(xs))


def side_fair(fair_over, side):
    return fair_over if side == "over" else 1.0 - fair_over


def inside_gate(price, T):
    d = odds.decimal(price)
    return odds.decimal(T["price_gate"]) - EPS <= d <= odds.decimal(T["max_price"]) + EPS


def calibrated_over(raw_over, line, T):
    off = (T.get("offsets") or {}).get(fmt_line(line))
    if off is None:
        return None
    return min(0.999, max(0.001, raw_over + off))


def guard(market_fair, model_side, price, T):
    """Step 2 on numbers: (passes, final probability, final EV). model_side = the CALIBRATED model chance of the side."""
    final = T["market_weight"] * market_fair + T["model_weight"] * model_side
    fe = ev(final, price)
    return fe >= T["final_ev"] - EPS, final, fe


def assess(side, line, price, entry, raw_over_fn, T, guard_anyway=False):
    """Steps 1 and 2 for one side of one line at Hard Rock's `price`.
    entry: shadow.other_lines()'s entry for this player + line (None = no other book has it).
    raw_over_fn: () -> the model's raw chance of the over, or None (only called when step 1 passes).
    guard_anyway: also run step 2 when only the gap line failed (used to judge a flag already alive).
    Returns a dict with every number (unrounded) and `step1`, `guard` (None when step 1 failed or no model)."""
    pairs = (entry or {}).get("pairs") or {}
    fairs = {b: side_fair(odds.fair_two_sided(o, u), side) for b, (o, u) in pairs.items()}
    out = {"side": side, "line": line, "price": price, "n_books": len(fairs), "books": sorted(fairs),
           "market_fair": None, "gap_ev": None, "pin_fair": None, "pin_ev": None, "model_raw_over": None,
           "model_cal_over": None, "model_side": None, "final": None, "final_ev": None, "step1": False,
           "guard": None, "fails": []}
    if fmt_line(line) not in {fmt_line(x) for x in T["lines"]}:
        out["fails"].append("line")
    if not inside_gate(price, T):
        out["fails"].append("price")
    if len(fairs) < T["books_min"]:
        out["fails"].append("books")
    if fairs:
        out["market_fair"] = median(fairs.values())
        out["gap_ev"] = ev(out["market_fair"], price)
        if out["gap_ev"] < T["gap_ev"] - EPS:
            out["fails"].append("gap")
    else:
        out["fails"].append("gap")
    if odds_pin(fairs) is None:
        out["fails"].append("pinnacle")
    else:
        out["pin_fair"] = fairs[shadow.PINNACLE]
        out["pin_ev"] = ev(out["pin_fair"], price)
        if out["pin_ev"] < T["pin_ev_min"] - EPS:
            out["fails"].append("pinnacle")
    out["step1"] = not out["fails"]
    if out["step1"] or (guard_anyway and out["market_fair"] is not None):
        raw = raw_over_fn()
        if raw is not None:
            cal = calibrated_over(raw, line, T)
            if cal is not None:
                ms = side_fair(cal, side)
                ok, final, fe = guard(out["market_fair"], ms, price, T)
                out.update(model_raw_over=raw, model_cal_over=cal, model_side=ms, final=final, final_ev=fe, guard=ok)
    return out


def odds_pin(fairs):
    return fairs.get(shadow.PINNACLE)


# ---------------------------------------------------------------- reads
def minutes_to_puck(f, game):
    return (common.parse_iso(game["start"]) - common.parse_iso(f["at"])).total_seconds() / 60.0


def can_flag(f, game, T):
    """B or C read, taken before puck, that asked other books."""
    return f.get("pull") in T["flag_pulls"] and "others" in f and bool(f.get("book")) and minutes_to_puck(f, game) > 0


def is_close_read(f, game, T):
    """The 45-minute read: pull C, or a B read made inside the 45-minute window (B and C fall due together)."""
    return can_flag(f, game, T) and (f["pull"] == "C" or minutes_to_puck(f, game) <= T["close_min"] + 1)


def view_of(f, v):
    """One read as the paper test sees it: Hard Rock's shots pairs, the other books' entries."""
    mk = (f.get("markets") or {}).get(MARKET)
    at = common.parse_iso(f["at"])
    pairs = None
    if mk is not None:
        pairs = {}
        for k, p in shadow.pairs_of(mk).items():
            p = dict(p)
            p["why"] = odds.check_pair(p["over"], p["under"], mk.get("last_update"), at, v)
            pairs[k] = p
    return {"at": at, "pairs": pairs, "others": shadow.other_lines(f, MARKET, v) or {}}


def market_fair_in(view, pid, line, side):
    entry = view["others"].get((pid, line))
    pairs = (entry or {}).get("pairs") or {}
    if not pairs:
        return None, 0
    return median([side_fair(odds.fair_two_sided(o, u), side) for o, u in pairs.values()]), len(pairs)


def cid(slate, gid, pid, line, side):
    return "%s:%s:%s:%s:%s" % (slate, gid, pid, fmt_line(line), side)


# ---------------------------------------------------------------- folding the log
def fold(events):
    """{id: {"flag"/"veto"/"capped"/"pull"/"close"/"grade": event}} in log order (first of each kind wins)."""
    items = {}
    for e in events:
        it = items.setdefault(e["id"], {})
        it.setdefault(e["t"], e)
    return items


def base_of(it):
    return it.get("flag") or it.get("veto") or it.get("capped")


def settled_level(ls, goalie_state, team, opp, pid):
    st = lineups.player_status(ls or {}, team, pid)
    if st != "in":
        return "Early"
    gt = (goalie_state or {}).get("teams") or {}
    if (gt.get(team) or {}).get("status") == "confirmed" and (gt.get(opp) or {}).get("status") == "confirmed":
        return "Goalie confirmed"
    return "Lineup confirmed"


# ---------------------------------------------------------------- the step
class Paper:
    def __init__(self, now, slate, cfg, inp, sched_cache, games):
        self.now, self.slate, self.cfg, self.inp = now, slate, cfg, inp
        self.sched_cache, self.games = sched_cache or {}, games or []
        self.P = (cfg.get("ops") or {}).get("paper") or {}
        self.T = self.P.get("thresholds") or {}
        self.v = cfg["values"]
        self.events = read_events()
        self.items = fold(self.events)
        self.new = []
        self.ls = (inp.lineup_state if inp is not None else None) or lineups.load(slate)
        self.goalie_state = goalies.load(slate)
        self.notes = []

    # ---- bookkeeping
    def emit(self, e):
        e = dict(e, at=common.iso(self.now), v=VERSION)
        self.new.append(e)
        self.items.setdefault(e["id"], {}).setdefault(e["t"], e)

    def flags_where(self, **kw):
        out = []
        for it in self.items.values():
            fl = it.get("flag")
            if fl and all(fl.get(k) == v for k, v in kw.items()):
                out.append(fl)
        return out

    def model_fn(self, pid, team, g, line):
        opp = g["away"] if team == g["home"] else g["home"]
        home = team == g["home"]

        def run():
            m = self.inp.model(pid, team, opp, home, MARKET, line)
            return None if m is None else m["p_over"]
        return run

    def eligible(self, pid, team):
        """Same footing as the engine: history, not sitting, not out per Daily Faceoff, missed-last needs a lineup."""
        pv = self.inp.player(pid, team)
        if pv["n"] < self.T.get("min_history", 10) or pv["sitting"]:
            return False
        status = lineups.player_status(self.ls, team, pid)
        if status == "out":
            return False
        if pv["missed_last"] and status != "in":
            return False
        return True

    # ---- one read of one game
    def process_game(self, g, reads, cursor):
        gid = str(g["id"])
        last = common.parse_iso(cursor.get(gid)) if cursor.get(gid) else None
        for idx, f in enumerate(reads):
            at = common.parse_iso(f["at"])
            if last is not None and at <= last:
                continue
            if self.P.get("active") and common.paper_active(self.cfg, self.slate) and can_flag(f, g, self.T):
                self.process_read(g, f, reads[:idx])
            cursor[gid] = f["at"]

    def process_read(self, g, f, earlier):
        T, v = self.T, self.v
        view = view_of(f, v)
        if view["pairs"] is None:
            return                                        # this read did not return the shots market
        close = is_close_read(f, g, T)
        read_at = f["at"]
        # (a) later reads may only PULL flags that are still alive
        for fl in list(self.flags_where(game_id=g["id"])):
            it = self.items[fl["id"]]
            if "pull" in it or common.parse_iso(fl["read_at"]) >= view["at"]:
                continue
            reason = self.pull_reason(fl, g, view)
            if reason:
                self.emit({"t": "pull", "id": fl["id"], "read_at": read_at, "reason": reason[0], "detail": reason[1]})
        # (b) candidates: step 1 then step 2, ranked by final EV, capped
        passed, now_ids = [], set()
        for (pid, line), pair in sorted(view["pairs"].items()):
            if pair["over"] is None or pair["under"] is None or pair["why"] is not None:
                continue
            if pair["team"] not in (g["away"], g["home"]) or fmt_line(line) not in {fmt_line(x) for x in T["lines"]}:
                continue
            team = pair["team"]
            entry = view["others"].get((pid, line))
            if not entry or len(entry["pairs"]) < T["books_min"]:
                continue                                  # cheap exit before the model runs
            for side in ("over", "under"):
                i = cid(self.slate, g["id"], pid, line, side)
                it = self.items.get(i, {})
                if "flag" in it or "capped" in it:
                    continue
                a = self.assess_lazy(side, line, pair[side], entry, g, team, pid)
                if a is None or not a["step1"]:
                    continue
                if a["guard"] is None:
                    continue                              # no model for him: the guard cannot run
                if not self.eligible(pid, team):
                    continue
                a.update(id=i, pid=pid, team=team, name=pair["name"])
                if not a["guard"]:
                    if "veto" not in it:
                        self.emit_candidate("veto", a, g, f, view, earlier)
                    continue
                passed.append(a)
        passed.sort(key=lambda a: (-a["final_ev"], a["id"]))
        for a in passed:
            why = self.cap_reason(a, g)
            if why:
                self.emit_candidate("capped", a, g, f, view, earlier, reason=why)
            else:
                self.emit_candidate("flag", a, g, f, view, earlier)
        # (c) the 45-minute read closes every flag / candidate of this game that has no close yet
        if close:
            for i, it in list(self.items.items()):
                b = base_of(it)
                if not b or b["game_id"] != g["id"] or "close" in it or common.parse_iso(b["read_at"]) > view["at"]:
                    continue
                fair, n = market_fair_in(view, b["pid"], b["line"], b["side"])
                first = b["read_at"] == read_at
                clv = None if (fair is None or first) else fair * odds.decimal(b["price"]) - 1.0
                self.emit({"t": "close", "id": i, "game_id": g["id"], "read_at": read_at, "close_fair": fair,
                           "close_books": n, "clv": clv, "first_caught_at_close": first})

    def assess_lazy(self, side, line, price, entry, g, team, pid, guard_anyway=False):
        return assess(side, line, price, entry, self.model_fn(pid, team, g, line), self.T, guard_anyway)

    def cap_reason(self, a, g):
        T = self.T
        mine = self.flags_where(slate=self.slate)
        if sum(1 for x in mine if x["pid"] == a["pid"]) >= T["max_per_player"]:
            return "player"
        if sum(1 for x in mine if x["game_id"] == g["id"]) >= T["max_per_game"]:
            return "game"
        if len(mine) >= T["max_per_night"]:
            return "night"
        return None

    def move_since(self, f, earlier, a):
        """Change in the market fair for this side from the latest earlier read at least `move_min` minutes older."""
        cut = common.parse_iso(f["at"]) - timedelta(minutes=self.T.get("move_min", 25))
        prev = None
        for e in earlier:
            if "others" in e and common.parse_iso(e["at"]) <= cut:
                prev = e
        if prev is None or a["market_fair"] is None:
            return None, None
        fair, n = market_fair_in(view_of(prev, self.v), a["pid"], a["line"], a["side"])
        return (None if fair is None else a["market_fair"] - fair), prev["at"]

    def emit_candidate(self, kind, a, g, f, view, earlier, reason=None):
        move, prev_at = self.move_since(f, earlier, a)
        name = self.inp.display_name(a["pid"], a["name"]) if self.inp is not None else a["name"]
        e = {"t": kind, "id": a["id"], "slate": self.slate, "game_id": g["id"], "pid": a["pid"], "player": name,
             "team": a["team"], "opp": g["away"] if a["team"] == g["home"] else g["home"],
             "home": a["team"] == g["home"], "start": g["start"], "market": MARKET, "line": a["line"],
             "side": a["side"], "read_at": f["at"], "read_pull": f["pull"], "price": a["price"],
             "market_fair": a["market_fair"], "n_books": a["n_books"], "books": a["books"], "pin_fair": a["pin_fair"],
             "pin_ev": a["pin_ev"], "gap_ev": a["gap_ev"], "model_raw_over": a["model_raw_over"],
             "model_cal_over": a["model_cal_over"], "model_side": a["model_side"], "final": a["final"],
             "final_ev": a["final_ev"], "guard": "pass" if a["guard"] else "veto",
             "lineup": lineups.player_status(self.ls, a["team"], a["pid"]),
             "goalie_own": ((self.goalie_state.get("teams") or {}).get(a["team"]) or {}).get("status"),
             "goalie_opp": ((self.goalie_state.get("teams") or {}).get(e_opp(g, a["team"])) or {}).get("status"),
             "settled": settled_level(self.ls, self.goalie_state, a["team"], e_opp(g, a["team"]), a["pid"]),
             "move30": move, "move30_from": prev_at}
        if reason:
            e["cap"] = reason
        self.emit(e)

    # ---- pulls
    def pull_reason(self, fl, g, view):
        """(reason, detail) or None. The flag keeps its frozen price; a read can only take it back."""
        T = self.T
        pair = (view["pairs"] or {}).get((fl["pid"], fl["line"]))
        if pair is None or pair["over"] is None or pair["under"] is None:
            return "line removed", "Hard Rock no longer posts this line"
        if pair["why"] is not None:
            return None                                   # a stale / odd Hard Rock read says nothing
        price = pair[fl["side"]]
        entry = view["others"].get((fl["pid"], fl["line"]))
        n = len((entry or {}).get("pairs") or {})
        a = self.assess_lazy(fl["side"], fl["line"], price, entry, g, fl["team"], fl["pid"], guard_anyway=True)
        # the order is the spec's: price moved + gap under the hysteresis line, books, Pinnacle, the guard
        if price != fl["price"] and a["gap_ev"] is not None and a["gap_ev"] < T["pull_ev"] - EPS:
            return "price moved, gap gone", "gap %+.1f%% at %s" % (100 * a["gap_ev"], common.fmt_price(price))
        if n < T["books_min"]:
            return "fewer than %d books" % T["books_min"], "%d books" % n
        if a["pin_fair"] is None:
            return "Pinnacle gone", "Pinnacle no longer quotes both sides"
        if a["pin_ev"] < T["pin_ev_min"] - EPS:
            return "Pinnacle disagrees", "Pinnacle EV %+.1f%%" % (100 * a["pin_ev"])
        if a["guard"] is False:
            return "model guard fails", "final EV %+.1f%%" % (100 * a["final_ev"])
        return None

    def pull_out(self):
        """A player Daily Faceoff now lists as out (or no longer in the lineup) is pulled, whatever the last read says."""
        for fl in self.flags_where(slate=self.slate):
            it = self.items[fl["id"]]
            g = next((x for x in self.games if x["id"] == fl["game_id"]), None)
            if "pull" in it or g is None or sched.started(g, self.now):
                continue
            if lineups.player_status(self.ls, fl["team"], fl["pid"]) == "out":
                self.emit({"t": "pull", "id": fl["id"], "read_at": None, "reason": "out per Daily Faceoff",
                           "detail": "not in tonight's lineup"})

    # ---- grading (from the shadow log's results)
    def grade(self):
        need = {}
        for i, it in self.items.items():
            b = base_of(it)
            if b and "grade" not in it:
                need.setdefault(b["slate"], []).append((i, b))
        for slate, rows in sorted(need.items()):
            doc = shadow.load(slate)
            by = {shadow.key(r["game_id"], r["market"], r["pid"], r["line"]): r for r in doc["rows"]}
            for i, b in rows:
                r = by.get(shadow.key(b["game_id"], MARKET, b["pid"], b["line"]))
                res = (r or {}).get("result")
                if not res:
                    continue
                w = res.get(b["side"])
                if w not in ("W", "L", "VOID", "PUSH"):
                    continue
                units = odds.decimal(b["price"]) - 1.0 if w == "W" else (-1.0 if w == "L" else 0.0)
                self.emit({"t": "grade", "id": i, "result": w, "units": units, "actual": res.get("actual"),
                           "price": b["price"]})
        return None


def e_opp(g, team):
    return g["away"] if team == g["home"] else g["home"]


# ---------------------------------------------------------------- the derived summary
def _bootstrap_lb(xs, q=0.10, draws=2000, seed=7):
    if not xs:
        return None
    rng = random.Random(seed)
    n = len(xs)
    means = sorted(sum(xs[rng.randrange(n)] for _ in range(n)) / n for _ in range(draws))
    return means[int(q * draws)]


def _stats(xs):
    if not xs:
        return {"n": 0, "mean": None, "lb80": None, "pos_share": None}
    return {"n": len(xs), "mean": sum(xs) / len(xs), "lb80": _bootstrap_lb(xs),
            "pos_share": sum(1 for x in xs if x > 0) / len(xs)}


def view_item(it, ls, goalie_state, now):
    b = base_of(it)
    pull, close, gr = it.get("pull"), it.get("close"), it.get("grade")
    started = common.parse_iso(b["start"]) <= now
    out = {"id": b["id"], "kind": "flag" if "flag" in it else ("veto" if "veto" in it else "capped"),
           "slate": b["slate"], "game_id": b["game_id"], "player": b["player"], "team": b["team"], "opp": b["opp"],
           "game": ("%s vs %s" if b["home"] else "%s @ %s") % (b["team"], b["opp"]), "start": b["start"],
           "side": b["side"], "line": b["line"], "bet": "%s %s shots" % (b["side"].upper(), fmt_line(b["line"])),
           "price": b["price"], "gap_pct": round(100 * b["gap_ev"], 1), "final_pct": round(100 * b["final_ev"], 1),
           "market_fair_pct": round(100 * b["market_fair"], 1), "final_p_pct": round(100 * b["final"], 1),
           "n_books": b["n_books"], "guard": b["guard"], "cap": b.get("cap"), "flagged_at": b["read_at"],
           "read_pull": b["read_pull"], "settled": settled_level(ls, goalie_state, b["team"], b["opp"], b["pid"]),
           "frozen_settled": b["settled"], "move30_pct": None if b.get("move30") is None else round(100 * b["move30"], 1),
           "pulled": None if not pull else {"reason": pull["reason"], "detail": pull.get("detail"), "at": pull["at"]},
           "locked": started, "state": "pulled" if pull else ("locked" if started else "open"),
           "close_fair_pct": None, "clv_pct": None, "result": None, "units": None}
    if close:
        out["close_fair_pct"] = None if close["close_fair"] is None else round(100 * close["close_fair"], 1)
        out["clv_pct"] = None if close["clv"] is None else round(100 * close["clv"], 1)
    if gr:
        out["result"], out["units"] = gr["result"], round(gr["units"], 3)
    return out


def build_summary(now, slate, cfg, events, ls=None, goalie_state=None, nights=()):
    P = (cfg.get("ops") or {}).get("paper") or {}
    items = fold(events)
    ls = ls if ls is not None else lineups.load(slate)
    goalie_state = goalie_state if goalie_state is not None else goalies.load(slate)
    views = [view_item(it, ls, goalie_state, now) for it in items.values() if base_of(it)]
    views.sort(key=lambda x: (x["slate"], -(x["final_pct"] or 0), x["id"]))
    slates = sorted({x["slate"] for x in views}, reverse=True)[:SUMMARY_NIGHTS]
    tonight = [x for x in views if x["slate"] == slate]
    flags = [i for i, it in items.items() if "flag" in it]
    graded = [items[i]["grade"] for i in flags if "grade" in items[i] and items[i]["grade"]["result"] in ("W", "L")]
    probs = [items[i]["flag"]["final"] for i in flags if "grade" in items[i] and items[i]["grade"]["result"] in ("W", "L")]
    wins = sum(1 for g in graded if g["result"] == "W")
    var = sum(p * (1 - p) for p in probs)
    z = (wins - sum(probs)) / var ** 0.5 if var > 0 else None
    clv_gap = [items[i]["close"]["clv"] for i, it in items.items()
               if base_of(it) and "close" in it and it["close"]["clv"] is not None]
    clv_flag = [items[i]["close"]["clv"] for i in flags if "close" in items[i] and items[i]["close"]["clv"] is not None]
    clv_pass = clv_flag
    clv_veto = [it["close"]["clv"] for it in items.values()
                if "veto" in it and "flag" not in it and "close" in it and it["close"]["clv"] is not None]
    nights = sorted(set(nights))
    flag_nights = {items[i]["flag"]["slate"] for i in flags}
    nov2 = {
        "gaps_measured": len(clv_gap), "gaps_logged": sum(1 for it in items.values() if base_of(it)),
        "graded_picks": len(graded), "w": wins, "l": len(graded) - wins,
        "void": sum(1 for i in flags if "grade" in items[i] and items[i]["grade"]["result"] == "VOID"),
        "units": sum(g["units"] for g in graded), "wins_z": z,
        "clv_gaps": _stats(clv_gap), "clv_flags": _stats(clv_flag), "clv_vetoed": _stats(clv_veto),
        "clv_passed_mean": _stats(clv_pass)["mean"], "clv_vetoed_mean": _stats(clv_veto)["mean"],
        "nights": len(nights), "nights_with_flags": len(flag_nights & set(nights)) if nights else len(flag_nights),
        "population_slope": None,
        "judge_on": P.get("judge_on"), "hard_stop": P.get("end"),
    }
    return {"version": VERSION, "note": NOTE, "generated_at": common.iso(now), "slate": slate,
            "active": common.paper_active(cfg, slate), "window": {"start": P.get("start"), "end": P.get("end"),
                                                                  "judge_on": P.get("judge_on")},
            "tonight": {"flags": [x for x in tonight if x["kind"] == "flag"],
                        "vetoes": [x for x in tonight if x["kind"] == "veto"],
                        "capped": [x for x in tonight if x["kind"] == "capped"]},
            "nights": [{"date": s, "flags": [x for x in views if x["slate"] == s and x["kind"] == "flag"],
                        "vetoes": [x for x in views if x["slate"] == s and x["kind"] == "veto"]}
                       for s in slates if s != slate],
            "nov2": nov2}


def write_summary(summary, now, heartbeat_min):
    """summary.json is rewritten only when its content changed (or its stamp is a heartbeat old), so quiet cycles add no
    commit: Pages builds are limited."""
    old = common.read_json(summary_path())
    if isinstance(old, dict):
        same = {k: v for k, v in old.items() if k != "generated_at"} == {k: v for k, v in summary.items() if k != "generated_at"}
        stamp = common.parse_iso(old.get("generated_at")) if old.get("generated_at") else None
        if same and stamp is not None and timedelta(0) <= now - stamp < timedelta(minutes=heartbeat_min):
            return False
    common.write_json(summary_path(), summary)
    return True


def step(now, slate, cfg, inp, sched_cache, games):
    """Called by run.py (soft step, after shadow). Never raises past run.py's wrapper."""
    P = (cfg.get("ops") or {}).get("paper") or {}
    if not P:
        return {"status": "skipped", "note": "no ops.paper in the config"}
    p = Paper(now, slate, cfg, inp, sched_cache, games)
    cursor = common.read_json(cursor_path(), {}) or {}
    cursor.setdefault("reads", {})
    cursor.setdefault("nights", [])
    live = common.paper_active(cfg, slate)
    if live and games and inp is not None:
        odds_doc = common.read_json(odds.odds_path(slate)) or {}
        by_game = {}
        for f in sorted(odds_doc.get("fetches", []), key=lambda x: x["at"]):
            if f.get("game_id") is not None and common.parse_iso(f["at"]) <= now:
                by_game.setdefault(f["game_id"], []).append(f)
        for g in sorted(games, key=lambda x: (x["start"], x["id"])):
            p.process_game(g, by_game.get(g["id"], []), cursor["reads"])
        p.pull_out()
        if slate not in cursor["nights"]:
            cursor["nights"].append(slate)
    p.grade()
    n = append(p.new)
    summary = build_summary(now, slate, cfg, p.events + p.new, p.ls, p.goalie_state, cursor["nights"])
    if live or n or common.read_json(summary_path()) is not None or p.events:
        write_summary(summary, now, P.get("heartbeat_min") or (cfg.get("ops") or {}).get("heartbeat_min") or 20)
    if common.read_json(cursor_path()) != cursor:
        common.write_json(cursor_path(), cursor)
    counts = {}
    for e in p.new:
        counts[e["t"]] = counts.get(e["t"], 0) + 1
    note = ", ".join("%d %s" % (c, t) for t, c in sorted(counts.items())) or "nothing new"
    return {"status": "ok" if live else "skipped", "note": ("paper test: " if live else "paper test off: ") + note}
