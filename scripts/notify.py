"""notify.py: Discord messages to Matt, only when he has something to act on. Never fails or slows a run.

Sends (all plain text, one webhook post each):
  new picks    one message per run for every open pick / parlay not told about before (max 8 lines, then "+N more")
  pulled       one short message for picks he was told about that were pulled before puck drop
  action       odds keys refused / odds pool low or empty (the page's own sentence), once per ET day each
  hello        once, the first time the webhook works
  PAPER      (Gap + Guard paper test, TEAM.md item 21) its own messages, headed "PAPER - do not bet": one batched message
             per cycle for flags not told about, plus one PAPER PULLED line for a flag that was told and then pulled. Own
             state (sent_paper / pulled_paper / paper_sent), own cap of 3 a day that does NOT use the 6 above, same quiet
             hours and 14 s budget, no "Bet only at these prices" footer. Marked only after a 2xx.
Never: no-pick nights, heartbeats, lineup checks, grading, errors. Quiet 12:30 AM to 8:00 AM ET (items are held:
they are still open at 8:00 and go out then). At most 6 messages per ET day. A price move or Early -> Lineup
confirmed never re-notifies.

The webhook URL comes ONLY from the env DISCORD_WEBHOOK_URL (a GitHub secret). It is registered as a secret
(scrubbed from stdout/stderr and every file write), never logged, never put in state, and exception text from the
post is never kept. Unset or empty: this module does nothing.

State: data/state/notified.json = ids and timestamps only.
Test hooks: in PC_NOW / PC_DATA_DIR mode nothing is ever posted to Discord unless PC_DISCORD_FIXTURE_URL (a local
test server) is set; then posts go there (DISCORD_WEBHOOK_URL must still be non-empty).
"""
import json
import os
import urllib.error
import urllib.request

import common

PAGE = "https://msasportas.github.io/prop-check-nhl/"
MAX_PER_DAY = 6
PAPER_MAX_PER_DAY = 3       # paper messages, counted apart from MAX_PER_DAY
PAPER_HEAD = "PAPER - do not bet, nothing is on the page as a bet"
MAX_LINES = 8
QUIET_FROM = (0, 30)        # inclusive
QUIET_TO = (8, 0)           # exclusive
TIMEOUT = 5
BUDGET_SEC = 14             # all posts of one run together
HELLO = ("Prop Check notifications are on. You'll get a message only when there is a bet to place, "
         "when one is pulled, or when odds keys need attention.")
CHECK = "Bet only at these prices or better. If Hard Rock shows worse, skip it."
KEEP_DAYS = 2


def state_path():
    return common.dpath("state", "notified.json")


def _test_mode():
    return bool(os.environ.get("PC_NOW") or os.environ.get("PC_DATA_DIR"))


def endpoint():
    """The URL to post to, or None (do nothing). Registers the secret so it can never be printed or written."""
    hook = (os.environ.get("DISCORD_WEBHOOK_URL") or "").strip()
    if not hook:
        return None
    common.register_secret(hook)
    tail = hook.rstrip("/").rsplit("/", 1)[-1]
    common.register_secret(tail)                              # the token alone, too
    fixture = (os.environ.get("PC_DISCORD_FIXTURE_URL") or "").strip()
    if fixture:
        return fixture
    return None if _test_mode() else hook


def quiet(now):
    hm = (now.hour, now.minute)
    return QUIET_FROM <= hm < QUIET_TO


class Sender:
    """Posts one message. send() is True only after a 2xx. 429 or anything else: False, nothing kept."""

    def __init__(self, url, clock):
        self.url, self.clock = url, clock
        self.t0 = clock()
        self.stop = False                                     # a 429 ends the run's sending

    def send(self, text):
        if self.stop:
            return False
        body = json.dumps({"content": text[:1990], "allowed_mentions": {"parse": []}}).encode("utf-8")
        for attempt in range(2):
            if self.clock() - self.t0 > BUDGET_SEC:
                return False
            try:
                req = urllib.request.Request(self.url, data=body, method="POST", headers={
                    "Content-Type": "application/json", "User-Agent": "prop-check-nhl (notify)"})
                with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                    return 200 <= r.status < 300
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    self.stop = True                          # give up for this cycle (Retry-After not waited on)
                    return False
                if e.code < 500:
                    return False
            except Exception:
                pass
        return False


# ---------------------------------------------------------------- state
def load_state():
    st = common.read_json(state_path())
    if not isinstance(st, dict):
        st = {}
    st.setdefault("picks", {})              # id -> ISO time told
    st.setdefault("parlays", {})
    st.setdefault("pulled", {})             # id -> ISO time the pull was told
    st.setdefault("sent", {})               # ET date -> messages sent that day
    st.setdefault("action", {})             # ET date -> ["refused", "pool"] already told
    st.setdefault("hello", None)
    st.setdefault("sent_paper", {})         # paper flag id -> ISO time told (never the real picks' / parlays' ids)
    st.setdefault("pulled_paper", {})       # paper flag id -> ISO time the pull was told
    st.setdefault("paper_sent", {})         # ET date -> paper messages sent that day (its own cap)
    return st


def _prune(st, today):
    from datetime import date, timedelta
    d0 = date.fromisoformat(today)
    keep = {(d0 - timedelta(days=i)).isoformat() for i in range(KEEP_DAYS)}
    for k in ("picks", "parlays", "pulled", "sent_paper", "pulled_paper"):
        st[k] = {i: t for i, t in st[k].items() if i[:10] in keep}
    for k in ("sent", "action", "paper_sent"):
        st[k] = {d: v for d, v in st[k].items() if d in keep}


# ---------------------------------------------------------------- wording
def _t(iso):
    return common.fmt_time(common.parse_iso(iso)) + " ET"


def _state_label(p):
    return "✅ Lineup confirmed" if p.get("state") == "lineup" else "⏳ Early, lineup not set"


SHORT = {"shots": "shots", "points": "points", "goals": "goals", "saves": "saves"}


def _bet(p):
    """'OVER 1.5 shots' (falls back to the full bet text)."""
    if p.get("side") and p.get("line") is not None and p.get("market") in SHORT:
        return "%s %s %s" % (p["side"].upper(), ("%g" % float(p["line"])), SHORT[p["market"]])
    return p["bet"]


def _game(p):
    if p.get("team") and p.get("opp"):
        return ("%s vs %s" if p.get("home") else "%s @ %s") % (p["team"], p["opp"])
    return ""


def _why(p):
    """The page reason without its first sentence (that one repeats the numbers)."""
    parts = [s.strip() for s in str(p.get("reason") or "").split(". ") if s.strip()]
    why = ". ".join(parts[1:]).rstrip(".")
    if len(why) > 110:
        why = why[:107].rsplit(" ", 1)[0] + "..."
    return why


def pick_line(p):
    """One pick as a short Discord block: the bet on top, then when, then why."""
    when = " · ".join(x for x in (_game(p), _t(p["start"]), _state_label(p)) if x)
    out = ["**%s %s  %s**" % (p["player"], _bet(p), common.fmt_price(p["price"])), when,
           "We say %s%% to hit · price needs %s%%" % (p["p_pct"], p["breakeven_pct"])]
    why = _why(p)
    if why:
        out.append("Why: " + why)
    return "\n".join(out)


def parlay_line(pl, by_id):
    legs = [by_id[l] for l in pl["legs"]]
    out = ["**PARLAY %d legs  about %s**" % (len(legs), common.fmt_price(pl["price"]))]
    out += ["• %s %s (%s)" % (l["player"], _bet(l), common.fmt_price(l["price"])) for l in legs]
    out.append("We say %s%% to hit · price needs %s%% · first game %s" % (
        pl["p_pct"], pl["breakeven_pct"], _t(min(l["start"] for l in legs))))
    return "\n".join(out)


def _open(x, now):
    return (not x.get("pulled")) and (not x.get("graded")) and x.get("state") in ("early", "lineup")


def parlays_on(slate):
    """Rules v2.0 turned parlays off (parlay_cap 0): Discord then never sends a parlay, whatever the slate holds."""
    try:
        cfg = common.rules_for(common.load_config(), slate.get("slate_date"))
        return cfg["values"].get("parlay_cap", 0) > 0
    except Exception:
        return False


def build_new(slate, st, now):
    """-> (text, picks, parlays) for items not yet told about, or None."""
    by_id = {p["id"]: p for p in slate.get("picks", [])}
    new_p = [p for p in slate.get("picks", []) if _open(p, now) and p.get("rank") is not None
             and p["id"] not in st["picks"] and common.parse_iso(p["start"]) > now]
    new_p.sort(key=lambda p: (p["rank"], p["id"]))
    new_l = []
    for pl in (slate.get("parlays", []) if parlays_on(slate) else []):
        if not _open(pl, now) or pl["id"] in st["parlays"] or not all(l in by_id for l in pl["legs"]):
            continue
        if all(common.parse_iso(by_id[l]["start"]) > now for l in pl["legs"]):
            new_l.append(pl)
    if not new_p and not new_l:
        return None
    blocks = [pick_line(p) for p in new_p] + [parlay_line(pl, by_id) for pl in new_l]
    n = len(blocks)
    head = "🏒 **%d new bet%s · %s**" % (n, "" if n == 1 else "s", now.strftime("%a %b %-d"))
    tail = "%s\n%s" % (CHECK, PAGE)
    shown = []
    for b in blocks[:MAX_LINES]:
        trial = "\n\n".join([head] + shown + [b, "+%d more on the page" % n, tail])
        if len(trial) > 1900:
            break
        shown.append(b)
    parts = [head] + shown
    if n > len(shown):
        parts.append("+%d more on the page" % (n - len(shown)))
    text = "\n\n".join(parts + [tail])
    return text, new_p, new_l


def build_pulled(slate, st, now):
    by_id = {p["id"]: p for p in slate.get("picks", [])}
    items = []
    for p in slate.get("picks", []):
        if p.get("pulled") and p["id"] in st["picks"] and p["id"] not in st["pulled"] \
                and common.parse_iso(p["start"]) > now:
            items.append(("picks", p["id"], "%s %s (%s)" % (p["player"], _bet(p), p["pulled"]["reason"])))
    for pl in slate.get("parlays", []):
        if pl.get("pulled") and pl["id"] in st["parlays"] and pl["id"] not in st["pulled"] \
                and all(l in by_id for l in pl["legs"]) \
                and min(common.parse_iso(by_id[l]["start"]) for l in pl["legs"]) > now:
            nm = " + ".join(by_id[l]["player"] for l in pl["legs"])
            items.append(("parlays", pl["id"], "Parlay %s (%s)" % (nm, pl["pulled"]["reason"])))
    if not items:
        return None
    text = "❌ **Pulled. Don't bet these:**\n" + "\n".join("• " + s for _, _, s in items[:MAX_LINES])
    if len(items) > MAX_LINES:
        text += "\n+%d more pulled on the page" % (len(items) - MAX_LINES)
    return text + "\n" + PAGE, items


def _paper_summary(slate_date):
    s = common.read_json(common.dpath("paper", "summary.json"))
    if isinstance(s, dict) and s.get("slate") == slate_date and s.get("active"):
        return s
    return None


def paper_line(x):
    """One paper flag as a short block (no bet instruction anywhere)."""
    when = " · ".join(y for y in (x["game"], _t(x["start"]), "✅ " + x["settled"] if x["settled"] != "Early" else "⏳ Early") if y)
    return "\n".join(["**%s %s  %s**" % (x["player"], x["bet"], common.fmt_price(x["price"])), when,
                      "Gap %+.1f%% vs %d books · guard ok (final %.1f%%)" % (x["gap_pct"], x["n_books"], x["final_p_pct"])])


def build_paper(summary, st, now):
    """-> (text, new_flags, pulled_flags) or None. Only flags of games still ahead; a flag already pulled before it was
    told about is never told. Header says PAPER and that nothing is a bet; there is no 'bet at these prices' footer."""
    flags = [x for x in (summary.get("tonight") or {}).get("flags", []) if common.parse_iso(x["start"]) > now]
    new = [x for x in flags if x["id"] not in st["sent_paper"] and not x.get("pulled")]
    pulled = [x for x in flags if x.get("pulled") and x["id"] in st["sent_paper"] and x["id"] not in st["pulled_paper"]]
    if not new and not pulled:
        return None
    parts = [PAPER_HEAD]
    if new:
        parts.append("%d paper flag%s" % (len(new), "" if len(new) == 1 else "s"))
        parts += [paper_line(x) for x in new[:MAX_LINES]]
        if len(new) > MAX_LINES:
            parts.append("+%d more on the page" % (len(new) - MAX_LINES))
    if pulled:
        parts.append("PULLED PAPER")
        parts += ["• %s %s (%s)" % (x["player"], x["bet"], x["pulled"]["reason"]) for x in pulled[:MAX_LINES]]
    parts.append(PAGE)
    return "\n\n".join(parts), new, pulled


def build_actions(slate, st, today):
    """Things only Matt can do: [(code, text)] not yet told today."""
    told = set(st["action"].get(today, []))
    s = slate.get("status") or {}
    out = []
    keys = [b["text"] for b in slate.get("banners", [])
            if isinstance(b, dict) and b.get("level") in ("warn", "stop")
            and ("odds keys" in str(b.get("text", "")).lower() or "odds pulls" in str(b.get("text", "")).lower())]
    if s.get("prices_state") == "keys_refused":
        import odds
        out.append(("refused", odds.KEYS_REFUSED_TEXT))
    elif keys:
        out.append(("pool", keys[0]))
    return [(c, t) for c, t in out if c not in told]


# ---------------------------------------------------------------- the entry point
def notify(slate=None, sender=None):
    """Called at the end of a run. Returns the number of messages sent. Raises nothing."""
    try:
        return _notify(slate, sender)
    except BaseException as e:                                 # never fail or stop the run; keep nothing from e
        if isinstance(e, (KeyboardInterrupt, SystemExit)):
            raise
        return 0


def _notify(slate, sender):
    url = endpoint()
    if not url:
        return 0
    now = common.now()
    if quiet(now):
        return 0
    if slate is None:
        slate = common.read_json(common.dpath("slate.json"))
    real = isinstance(slate, dict) and slate.get("slate_date") == common.slate_date(now)
    paper = _paper_summary(common.slate_date(now))
    if not real and not paper:
        return 0                                               # old slate: say nothing about it
    sender = sender or Sender(url, __import__("time").monotonic)
    st = load_state()
    before = json.dumps(st, sort_keys=True)
    today = now.date().isoformat()
    _prune(st, common.slate_date(now))
    sent = [0]
    stamp = common.iso(now)

    def post(text, mark):
        if st["sent"].get(today, 0) >= MAX_PER_DAY:
            return False                                       # over the cap: drop silently
        if not sender.send(text):
            return False                                       # not a 2xx: nothing marked, retried next cycle
        st["sent"][today] = st["sent"].get(today, 0) + 1
        sent[0] += 1
        mark()
        _save(st, before)                                      # written at once after each 2xx: no double send
        return True

    def post_paper(text, mark):
        if st["paper_sent"].get(today, 0) >= PAPER_MAX_PER_DAY:
            return False                                       # its own cap; the real one is untouched
        if not sender.send(text):
            return False
        st["paper_sent"][today] = st["paper_sent"].get(today, 0) + 1
        sent[0] += 1
        mark()
        _save(st, before)
        return True

    def set_hello():
        st["hello"] = stamp
    if not real:
        pass
    elif not st["hello"]:
        post(HELLO, set_hello)
    pulled = build_pulled(slate, st, now) if real else None
    if pulled:
        def mark_pulled():
            for kind, i, _ in pulled[1]:
                st["pulled"][i] = stamp
        post(pulled[0], mark_pulled)
    new = build_new(slate, st, now) if real else None
    if new:
        def mark_new():
            for p in new[1]:
                st["picks"][p["id"]] = stamp
            for pl in new[2]:
                st["parlays"][pl["id"]] = stamp
        post(new[0], mark_new)
    for code, text in (build_actions(slate, st, today) if real else []):
        post("⚠️ **Needs you:** " + text, lambda c=code: st["action"].setdefault(today, []).append(c))
    pp = build_paper(paper, st, now) if paper else None
    if pp:
        def mark_paper():
            for x in pp[1]:
                st["sent_paper"][x["id"]] = stamp
            for x in pp[2]:
                st["pulled_paper"][x["id"]] = stamp
        post_paper(pp[0], mark_paper)
    _save(st, before)
    return sent[0]


def _save(st, before):
    if json.dumps(st, sort_keys=True) != before:
        common.write_json(state_path(), st)
