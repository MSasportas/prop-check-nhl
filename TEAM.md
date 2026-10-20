# TEAM.md: Prop Check NHL operating doc

Read this first in every session. Update it last. It replaces the old roadmap, spec and briefs.

Live page: https://msasportas.github.io/prop-check-nhl/ · Repo: MSasportas/prop-check-nhl (public)

## 1. The product
Every NHL game day: every leg that qualifies at a real Hard Rock (`hardrockbet`) price, ranked best first, each
with the price, our chance vs the price's break-even and a one-line reason, plus 2-3 leg parlays from the top legs.
The page updates through the day; each pick shows how settled it is (Early / Lineup confirmed / Locked), and
pulled picks stay visible with the reason. Dark, phone first (~380px). The Record is the scoreboard.

**Customer facts (fixed):** Matt; Hard Rock Florida only; no leg worse than -200 (plus money fine); parlays 2-3 legs;
player props are the core (sides/totals allowed); bets any time from morning to puck drop.
**Fixed:** the Record. Every pick and parlay exactly as shown, graded after the game at the posted price,
append-only, pulled picks kept and marked. Nothing edited or dropped. It is the only reporting Matt wants.
**Come to Matt only for:** more odds keys, paying for something, a GitHub setting we can't reach. Exact taps, one
short message.

## 2. How we are judged
1. Picks hit, at the price posted (a -200 leg must hit 66.7%+). An empty night beats picks that miss.
2. Always current; anything missing or stale is said plainly on the page.
3. A usable set of picks most nights.
4. Readable on a phone in seconds.

## 3. The team (subagents run by the CEO; any chat in the project is the CEO)
Sharp (betting method, final call) · Data Scientist (data, model, samples, judging the Record) · **Researcher (new 2026-10-19: tests new hypotheses every day to find an edge; rules in research/RESEARCH.md; writes research/ only)** · UX (page) ·
Builder (all code) · QA (tests every change before it goes live, real browser at 380px, hasn't seen the build).
Rule changes: the Data Scientist names the sample first; the Sharp decides; log it in section 8.

## 4. Current rules (v3.1, 2026-10-20; first slate 2026-10-20). Source of truth: `config/rules.json` (`ops.gap_guard`)
There is ONE rule: Gap + Guard. Hard Rock's price must beat the other books' middle price by a margin (the gap), and our
model must not disagree (the guard). The v1.0 and v2.0 engines, the "previous" rules block, `rules_for`, the pause and the
paper mode are gone; they are not options. History of why: section 7 items 17-21 and section 8. All EV% below = fair
probability x Hard Rock decimal payout - 1, on unrounded numbers; every threshold is inclusive.

| Area | Rule |
|---|---|
| Markets | **Hard Rock shots on goal only, lines 1.5 and 2.5, over and under.** Everything else (points, goals, saves, 3.5) is not picked. Saves stay in the shadow log only |
| Step 1: the gap | All of: Hard Rock EV vs the market fair >= **+3.0%**; >= **4 other books** priced the same player, line and side with both sides quoted (Pinnacle counts and must be one; each read fresh, hold 0-15%); **market fair = median** of the books' proportionally de-vigged fair chance (even count: mean of the middle two); Pinnacle present with both sides and Pinnacle-fair EV on Hard Rock's price >= 0.0% (sign check only); Hard Rock price -200 to +120 |
| Step 2: the guard | final = 0.8 x market fair + 0.2 x (model chance + frozen offset on the over: 1.5 +0.0179, 2.5 +0.0158; under = 1 - over). Passes iff final EV >= **+2.0%**. The model can only veto, never create. No model for the player = no pick. Offsets are frozen: changing them needs the DS to name the sample and the Sharp to log it in section 8 |
| Which reads can pick | Only the 90-minute (B) and 45-minute (C) reads that carry `others` (the other books). The 1 PM (A) read is a baseline only. A read with no other books is skipped |
| The pick | The **first passing read** makes the pick and **freezes its price** there. That price is shown on the page and in Discord and is what is graded: flat 1 unit, regulation + OT, void if no ice time. Later prices never change it (better or worse) |
| Eligibility | >= 10 games of history; missed his team's last game -> waits for a confirmed lineup; back from 3+ missed games -> sits 2 games; team stats behind -> team excluded and named; Daily Faceoff lists him out -> never picked. Settled level shown: Early / Lineup confirmed / Goalie confirmed |
| Pulls | Later reads only PULL: Hard Rock's price changed and step-1 EV < **+1.5%**; fewer than 4 books; Pinnacle gone or sign flipped; step 2 fails; line removed; Daily Faceoff lists him out (every run). A pulled pick stays on the page and in the Record marked pulled, and is still graded at its frozen price (counted under "Pulled", not in the headline). No pulls after puck drop |
| Caps | 1 side per player (best final EV). **No per-game or nightly cap (v3.1, 2026-10-20, Matt): every qualifying leg is shown, ranked by final EV, and graded on the Record** (`max_per_game`/`max_per_night` = null = off). Locked at puck drop (NHL schedule time) |
| Parlays | **Not offered** (no evidence). Page and Discord say so; Record keeps the old parlay shapes only so the archived Record still reads |
| Grading | When the NHL marks the game OFF. Regulation + OT count, shootout never. No ice time = void. Graded at the price shown. Flat 1 unit |
| Odds pulls | Shots only at every tier. Pull A 1 PM (or 3h before first puck), **B 90 min before each game (not lineup-gated)**, **C 45 min before each game, every game** (tier floor 3 when the allowance is >= 3). About 3 credits per game. Started games are never pulled. Allowance = credits left / game days before keys reset on the 1st |
| Safety | New picks stop by themselves if the Record reaches **-10 units** (`ops.safety_pause`), with the reason on the page; picks already shown are still looked after. Also no new picks while team stats are behind or Gap + Guard itself fails (a failed step, shown on the page). Never silent |
| Research log | `data/paper/` (flags, vetoes, capped, pulls, closes, grades, `summary.json`) is kept as the **Gap + Guard research log**: every candidate including the vetoed, capped and close ones, with closing fair and CLV. It is internal, append-only (`guard_paper.py`; a breach restores it from HEAD and the cycle carries on) and is where picks come from, but it is not the Record |
| Checkpoint | 2026-11-02: the DS reads the research log (CLV of measured gaps, graded results). Nothing switches off by itself except the -10 unit safety. A rule change goes through section 8 |

## 5. How it runs
- `scripts/run.py` is the only entry point; each run decides what's due: stats build, slate, odds pull A/B/C,
  lineup check (Daily Faceoff, within 3h of puck), re-evaluate picks, lock at puck drop, grade finished games,
  rebuild `data/record.json`, write `data/status.json`. Safe to run twice; writes are atomic. Stdlib Python 3.12.
- **Timer:** GitHub's cron barely fires for this repo (once in ~4 hours on day 1), so `.github/workflows/run.yml` is a
  self-dispatching chain: each run loops `scripts/loop.sh` ~50 minutes (`scripts/cycle.sh` every 10 min from
  8 AM to 3 AM ET, every 30 min otherwise) and then starts the next run via workflow_dispatch. Hourly cron and any
  push to scripts/, config/ or .github/workflows/ (re)start it. Commits only when data changed (heartbeat every
  20 min) to stay under Pages' ~10 builds/hour. Off switch: commit `config/stop_timer`. Details: section 7 risks.
- **Is it alive?** `git pull` and read `data/status.json`: `finished_at` should be < 30 min old (8 AM-3 AM ET);
  `runner.chain_link` increments each hand-over; `steps` show what ran; `keys` show credits per key (never keys).
  Chats can't see Actions history, Secrets or the live link; the public Actions page can be read with WebFetch:
  https://github.com/MSasportas/prop-check-nhl/actions
- **Restart a dead chain:** push any commit touching `scripts/`, `config/` or `.github/workflows/`.
- **Record guard:** every cycle runs `scripts/guard_record.py --history` after pulling and again just before pushing:
  every committed version of `data/record/events.jsonl` must be a byte-exact prefix of the next. If not, the cycle
  pushes NOTHING and the page soon says "Updates have stopped". Repair: a fix commit on top does not clear it (the
  edited version stays in history); only a force-push that removes the bad commit(s) does, restoring the last good
  log. `python scripts/run.py --rebuild-record` regenerates the derived Record views. Only the timer writes
  `data/record/`. No chat ever edits it.
- **Customer-ordered reset (only exception to append-only):** a reset is accepted by `guard_record.py` only when the old
  Record is preserved byte-exact in the repo. `data/record/resets.json` (append-only list) has an entry
  `{at, ordered_by, archive, sha256, lines}`; the archive file lives under `archive/` and is never rewritten. A
  (old -> new) pair that fails the prefix rule passes iff new is an empty file AND resets.json (read from the newer side:
  the working file, or that commit's tree) has an entry whose sha256 equals sha256(old) AND the archive it names, read from
  the same side, is byte-identical to old. The same rule applies in the HEAD check, the `--history` walk (including the
  cached `.git/pc_record_verified` path) and the `--origin` remembered-Record check (a remembered Record that is a prefix of
  an archived one is fine). Every run also requires: resets.json only ever gains entries (checked across all commits), and
  every archive it names still matches its sha256 in the working tree. Anything else (plain truncation, wrong sha, missing
  or edited archive, shallow clone) is the same breach as before. First use: 2026-10-19, archive `archive/record_2026-10-19/`
  (events.jsonl byte-exact, 82 lines, plus the old record.json view). The page shows one line on the Record view when
  resets.json exists. **Future resets need Matt's explicit order**; no one else may add a resets.json entry.
- **Odds keys:** GitHub secret `ODDS_API_KEYS` (comma-separated). Never in the repo, page or logs. Rotates when a key
  is out or refused; a refused key is "unknown", not empty. Page warns when the pool is low.
- **Discord notifications:** `scripts/notify.py`, called at the end of `run.py` (never fails or slows a run: 5 s
  timeout, one retry, whole run capped at 14 s). Webhook = GitHub secret `DISCORD_WEBHOOK` (the script reads it from env `DISCORD_WEBHOOK_URL`), passed to the loop step
  in `run.yml` like `ODDS_API_KEYS`; env only, scrubbed from stdout/files, never in state; unset or empty = does
  nothing. Sends only: NEW PICKS (one batched message per cycle, 8 lines then "+N more"; parlays included; each pick
  once, a price move or Early -> Lineup confirmed never repeats), PULLED (only picks already notified, before puck),
  ACTION NEEDED (keys refused, pool low/empty: the page's sentence, once per ET day each), a one-time hello. Never
  no-pick nights, heartbeats, grading, errors. Quiet 12:30-8:00 AM ET (held items go out at 8 if still ahead). Max 6
  messages per ET day. Message format (2026-10-18): bold bet line, game · time · lineup state, "We say X% to hit · price
  needs Y%", "Why:" (page reason minus its first sentence), parlays as bulleted legs, footer "Bet only at these
  prices or better", link last and never cut (blocks dropped to fit under 1,900 chars). State `data/state/notified.json` (ids and timestamps only; marked only after a 2xx; 429/5xx =
  retry next cycle). Tests: `PC_DISCORD_FIXTURE_URL` posts to a local server; in `PC_NOW`/`PC_DATA_DIR` mode nothing
  ever reaches Discord without it. Matt adds the secret: repo Settings > Secrets and variables > Actions > New
  repository secret, name `DISCORD_WEBHOOK`, value = the Discord channel webhook URL.
- **Game list status (2026-10-18):** each unstarted game on the page shows, per team, lineup (confirmed / not set / not checked
  yet, from `data/state/lineups.json`) and the starting goalie (confirmed / expected / not posted, from `scripts/goalies.py`,
  Daily Faceoff starting-goalies page, one read per cycle, `data/state/goalies.json`, written only when it changes). Display
  only, no pick depends on it. Verified live 2026-10-18 (status ok, real names on the page). Page text: `lineup later` /
  `lineup not out` / `✅ lineup`, then `G <Last> ✅` / `G <Last> (likely)` / `G not posted`.
- **Team logs (2026-10-18, item 17; internal: never on the page, the Record or Discord; "soft" steps in `run.py`, a
  failure shows as `warn` in status.json steps and never fails the run):**
  `shadow` (after grade) -> `data/shadow/<slate>.json` (`scripts/shadow.py`): one row per game x market x player x line for
  every two-way line in `data/odds/`; `open` = first pre-puck read, `close` = last pre-puck read (prices, de-vigged fair
  over, the engine's own model chance of the over before blend, blended chance each side, lineup + goalie state), `ctx`
  (home, team/opp, position, history, thin, back-to-back, rest days, TOI last 5 / season, start), `result` (boxscore as
  grade.py reads it; W/L/PUSH/VOID per side). Open/close never written after puck. Saves rows use `model.goalie_prob`
  (team-level, assumes that goalie starts). Backfill: `scripts/shadow_backfill.py FROM TO` (model from prior games only;
  check: 13/13 Record shots picks match). Done for Oct 12-17; run it for Oct 18 once final.
  `lineup_history` (after lineups) -> `data/state/lineup_history/<slate>.json`: per team, first page dated today
  (`first_today_at`) and last page before puck, incl. Daily Faceoff units (`groups`: f1-f4, d1-d3, pp1/pp2, pk, g; kept
  by `lineups.parse_page` from Oct 18 on). Written only on change. Backfill from git: `scripts/lineup_backfill.py`
  (needs full history; done Oct 12-17, no `groups` in those).
  `market_menu` (after odds) -> `data/state/market_menu.json`: once per ISO week, one event-markets call (~1 credit,
  ledger pull `M`) listing every market key Hard Rock posts for NHL, first/last seen. Skips if budget is tight.
  **Other books (2026-10-19, Researcher Q1):** every price read asks `bookmakers=hardrockbet` + `ops.consensus_books` (9: DK,
  FD, MGM, Caesars, ESPN, BetRivers, Fanatics, Pinnacle, BetOnline; max 9 so the list stays <= 10 = one billed region = same
  credits as Hard Rock alone; ledger uses the feed's `x-requests-last`, fallback = markets returned x regions, never x books).
  Hard Rock stays THE book: a fetch's `markets` is Hard Rock exactly as before; other books sit under `others`
  {book: {market: {last_update, outcomes}}} (pid-matched like Hard Rock; no `others` key = Hard Rock-only read). Engine, page,
  Record and status read `markets` only (byte-for-byte test: `tests/test_consensus.py`). Cost catch: a market only another
  book has IS billed, so a retry of a market Hard Rock had not posted asks Hard Rock only (max ~1 extra credit per game-market
  per day, e.g. saves at B). Shadow rows (open/close) add `cons_books`, `cons_stale_books`, `cons_fair_over_med/_mean`
  (proportional de-vig), `pin_fair_over`, `hr_vs_consensus` (HR proportional fair over - median), `best_over/_under` + `_book`;
  close adds `cons_move` and `stale` (HR prices unchanged since the previous read while the median moved >= 0.03); each stale
  read is kept in the row's `stale_events`. Market menu stays Hard Rock only.
- **Doc fix (2026-10-19):** in the "Other books (2026-10-19, Researcher Q1)" bullet and the Files bullet: it says "9 books" / "9 other books".
  We ASK for 9 (`ops.consensus_books`, max 9 so the list stays <= 10 = one billed region), but only 6 books actually return data
  for NHL shots: fanduel, betonlineag, draftkings, betmgm, espnbet, pinnacle. williamhill_us (Caesars), betrivers and fanatics
  return nothing. Any "9 books" in docs means "asked", never "counted". Paper counts only books that returned fresh two-sided prices.
- **Gap + Guard (live from 2026-10-20).** `scripts/paper.py` is the single source of the maths and writes the research log
  (`data/paper/`); `scripts/engine.py` turns each flag into a Record `shown` event (`pick.gg_id` = the flag id) with the
  price frozen, then looks after it (state, pull, lock). Spec: section 4. Config `ops.gap_guard` {active, live_from
  "2026-10-20", checkpoint "2026-11-02", thresholds}; nothing is shown or appended for a slate before `live_from`
  (`common.gap_guard_active`, enforced in both paper.py and engine.py). `data/rules.json` carries the page's numbers under
  `values.gap_guard` (never the frozen offsets).
- Research log files and guard: unchanged from the old paper bullet (events.jsonl, summary.json, cursor.json; `guard_paper.py` in
  `cycle.sh`; `paper.py` never imports `record`). Event types: flag, veto, capped, pull, close, grade.
- `--explain` prints, for each unstarted game's latest 90/45-minute read, every shots side with books, market fair, gap EV,
  final EV and the first reason it did not pass ("PASSES BOTH CHECKS" for the ones that do). Writes nothing.
- Page: each pick shows player, bet, Hard Rock price (frozen, with its read time and "bet at this price or better"), gap vs
  market with the books count and market fair, "Model agrees · We say X% · price needs Y%", the settled chip (Early / Lineup
  confirmed / Goalie confirmed, or Locked) and time to puck. Empty state: "No picks yet today" plus the next read time and
  the real reason ("108 lines read, none cleared both checks."). Stale and low-credit warnings unchanged. The paper section, the
  paused banner and the goal-watch list are gone. One rules sheet (the 9 lines in `RULES` in index.html), numbers from rules.json.
- **Discord (v3.0, replaces the older Discord and PAPER wording in this section):** cycle, 8 blocks then "+N more"; each pick once), PULLED (only picks already notified, before puck), ACTION NEEDED (keys refused, pool low/empty, once per ET day each), a one-time hello. NEW PICK block = bold bet line `**P. Name OVER 1.5 shots +100**`, `CAR @ PHI · 7:00 PM ET · ⏳ Early` (or `✅ Lineup confirmed`), `Gap +5.7% vs market, we say 53%, price needs 50%`; footer "Bet only at this price or better. If Hard Rock shows worse, skip it." and the link last, never cut. Never: no-pick nights, heartbeats, grading, errors, vetoes. Quiet 12:30-8:00 AM ET (held items go out at 8 if still ahead). Max 6 messages per ET day. Delete "parlays included", "Why:" and "Bet only at these prices or better". State `notified.json` keys: picks, pulled, sent, action, hello.
- Tests: `python -m unittest discover -s tests`, 322 tests (`tests/test_live_picks.py` end to end; `tests/test_paper.py` research-log maths; `tests/fixtures/paper_oct19/` = real Oct 19 reads). Fixtures: `python3 fixtures/make_fixtures.py`.

- **Files:** `index.html` (page; reads `data/slate.json`, `data/record.json`, `data/rules.json`), `data/odds/<date>.json`
  (every price pulled: Hard Rock in `markets`, 9 other books in `others`; ~10x bigger: ~1.5 MB on a 16-game night, ~2.5-3 MB
  with C on every game, ~250 MB a season in the working tree; git-compressed ~60 KB/day. Gzip/rotate old days before ~Dec:
  Pages' 1 GB site limit and full-history checkout), `data/shadow/` (shadow log), `data/state/` (stats store, schedule,
  credits ledger, lineup history, market menu), `fixtures/` (QA pages: `?fixture=NAME`, `?now=ISO`), `tests/`
  (`python -m unittest discover -s tests`, 282 tests; `tests/replay_day.py` replays a day).
- **Debug:** `python scripts/run.py --explain` shows why each line did or didn't qualify. Test env vars: `PC_NOW`,
  `PC_DATA_DIR`, `PC_ODDS_FIXTURE_DIR`, `PC_LINEUP_FIXTURE_DIR`, `PC_NHL_FIXTURE_DIR`. Never test against the live data/.

## 6. Reviews (scheduled tasks; each reads this file first and updates it last)
- **Daily check, 1:43 PM ET:** is the chain alive, did pull A run, any failed steps, unmatched names, excluded teams,
  grading done for last night; fix what's broken; no rule changes.
- **Weekly team review, Sundays 10:47 AM ET:** full team (Sharp, Data Scientist, UX, Builder, QA) on the Record and
  the odds log: pick volume, closing-price check, calibration by bucket; ship agreed fixes through QA; log changes.

## 7. Known gaps and risks
1. **Edge vs the book is unproven.** The model is calibrated (backtest 2025-26: stated 70-75% hit 72.1%), but at
   -200-or-better prices the book's fair chance is under ~63%, so a pick needs the model to beat the book by ~11-15
   points. On the first live game (CAR@PHI, Oct 11) 0 of 64 sides qualified. Expect empty or thin nights. Judge
   criterion 3 against criterion 1 at the first weekly review using `data/odds/` (how many lines came close, and
   did prices move toward our side). Don't loosen without the sample rule.
2. **Timer chain:** holds one runner around the clock (~1,440 min/day, free on public repos). GitHub's terms
   discourage disproportionate/always-on use; moderate risk. If the chain dies and the cron doesn't fire, the
   page says "Updates have stopped" until a push. Safer variant needs Matt: an outside scheduler (e.g. cron-job.org)
   calling workflow_dispatch with a fine-grained token, one cycle per run. Revisit if cron starts firing reliably.
3. ~~`toi_drop_sec` twitchy~~ Closed 2026-10-18: it removed 84 over sides in week 1 and 0 would otherwise have qualified.
4. **Lineup confirmation depends on Daily Faceoff, and it often never confirms (top build item).** Oct 17: 14 teams
   (incl. CBJ, CHI, PIT, VGK) never got a page dated today by 20 min before puck, so 2 of 4 qualifying sides stayed
   Early and missed the 0.03 bar, and 1 more (gap > 0.15) needed a confirmed lineup. Lost picks, not a bug. Next build:
   free fallback from NHL play-by-play `rosterSpots` ~20-30 min before puck. Needs a re-pull timing check before shipping.
   Daily lineup-history file: built 2026-10-18 (section 5, team logs), backfilled Oct 12-17.
5. No verified free injury source; no free opponent-adjusted ranks (model uses raw opponent shots/goals allowed).
6. The NHL schedule time is used for lock (it can be ~10 min before actual puck drop): conservative.
7. Name matching: exact, or last name + first initial; unmatched names are listed in `status.json` and skipped.
8. QA minors open: R4 null-price pick renders as "—"; R6 chain recovery depends on the cron. Fixed 2026-10-12
   (QA round 2): R1 days left capped at the 1st; R2 rules sheet; R3 refused keys show "keys_refused"; R5 cycle runs
   `guard_record.py --history` after each pull (a force-pushed rewrite is caught only by a runner that saw the
   old Record, i.e. within one ~50 min run).
9a. **Closing read budget (fixed 2026-10-20):** C for every game used to need 3 credits per unstarted game left in today's budget,
   ignoring A/B already paid, so Oct 19's 7 PM games got no C. Now `odds.c_for_every_game` counts only B + C still owed.
   Open minors: it does not count a pull A still owed (Hard Rock posts late; can only under-reserve, never overspend);
   `scripts/market_menu.py` still uses a flat 3 per game reserve.
9. If a cycle pulled prices but its push failed, that cycle's credits are spent again next cycle. Rare.
10. Discord: `notified.json` lives in the repo, so a cycle that fails after sending (run/push failure resets data/ to
   origin) can re-send that cycle's batch once. Rare, accepted. A webhook deleted in Discord gives 404: silently
   retried each cycle, no alert. Quiet hours also hold hello and action messages.
11. Regular season only; playoffs say "Only regular-season games are covered."
12. ~~Empty state promised "Next price check" with no keys~~ Fixed 2026-10-18 (run.py, 2 tests).

14. Late night, the "Not covered tonight: … (stats behind)" banner names teams whose game is already final. Misleading,
    minor; UX/Builder ticket. Also open (QA minors): strip wraps to 2 lines when records are long; one-sentence reason
    would show no reason (engine never makes one).
15. (2026-10-18: pull C now runs for every game at tier 3+ when the budget allows (live picks only at tier 2), so every shots line gets a close ~45 min out; the shadow log
    measures CLV on every line.) Closing-price check is weak: most picks get no price pull after they're shown (13 of 18 "flat"). Week 1: 3 moved
    toward us, 2 against, avg +0.5 pts toward us. Re-pricing every shown pick at C would cost credits; pool is 478
    (allowance ~5.2/game), so not now. Revisit when keys reset Nov 1.

16. **Market focus tickets (2026-10-18), in order.** (a) DONE 2026-10-18 (`scripts/odds.py` `markets_for`, tests updated, 221 pass; no QA browser pass needed, no page change): points no longer
    pulled; B pulls shots + saves at tier 3. Still open: re-price every shown pick (item 15). (b) Saves
    model: needs goalie game logs (NHL stats API, free; skater/team files hold none) plus team shots-against; use
    `scripts/goalies.py` for the confirmed starter. Saves needs only the goalie confirmed, not the full lineup, so it
    dodges item 4. Log saves lines every game from pull B so the sample builds (only 33 two-way lines so far). (c) Shots:
    keep the lineup fallback (item 4) top priority, it is what costs shots picks. (d) Re-check at the first weekly review
    after 50 graded shots legs: is the second market earning its credits; if not, shots alone.
    Evidence behind the choice (Oct 12-18 odds log, Hard Rock): shots 1,233 two-way lines, 4 lines (1.5/2.5/3.5), hold ~7.6%,
    8-5 +0.82u, under 1.5 5-2 +1.96u, under 3.5 1-2 -1.44u (priced near -200). Points 924 lines, 94% on the 0.5 line,
    hold ~7.1%, 3-2 -0.14u, and it needs confirmed lineups (power-play units), the thing that fails most. Goals: one-sided
    prices, no de-vig, high hold. Not in our feed or log, so unverified: assists, blocks, PP points, alt shots, sides, totals.
    Saves as #2 is a judgment, not a result: 0 graded legs. Status 2026-10-18: saves lines now go to the shadow log every
    pull B with the existing team-level `goalie_prob` (no new saves model yet; Oct 12-17 backfill has 33 graded saves lines).
    Tools research (2026-10-18): no new source needed for saves. The NHL stats API we already use returns goalie game rows
    (`api.nhle.com/stats/rest/en/goalie/summary?isGame=true`: saves, shotsAgainst, gamesStarted, timeOnIce; tested live) and the
    boxscore has a `starter` flag. Optional later: MoneyPuck free downloads (shot-level xG, goalie games; non-commercial, credit
    MoneyPuck anywhere shown, no scraping beyond listed files) for shot quality. Skip: paid odds/stat APIs, public repos (none
    beat what we have, mostly xG/R packages). RotoGrinders mirrors Daily Faceoff lines + PP units: a possible lineup fallback,
    terms and JS-vs-HTML unchecked.

13. **ROI (2026-10-18, 18 singles + 7 parlays):** singles 61% vs 58% needed, +0.96u (+5% ROI); parlays -4.45u. Higher-edge
    picks did not hit more (edge 2-3 pts: 6-3; 3-4.5: 3-3; 4.5+: 2-1), so stake sizing by confidence waits until
    ~100 graded legs show the ranking sorts winners. 20 of 22 picks are unders; model sits 12-19 pts off the book on
    every pick (risk 1 above). Weekly review: track parlays after the fix, and edge-bucket hit rates for sizing.

17. **Edge study (team meeting 2026-10-18, DS + Sharp). Read before any rule change.** Shadow-graded 742 two-way Hard Rock shots
    lines Oct 12-17 (48 games), model rebuilt with only prior games (matches the Record on all 13 picks). Six nights = leads, not results.
    - Hard Rock puts the vig on the over: all overs 46.2% hit, -13.8% ROI; all unders 53.8%, +0.2%. Hold ~7.9%. No blind rule clears break-even.
    - Model has some real information (ranks players better than the book on every line; regression weight 0.68, CI 0.01-1.36;
      log loss 0.6852 vs book 0.6903, CI includes 0). But hit rate does NOT rise with the gap: gap 0-0.03: -5.7% ROI (n 254);
      **0.03-0.10: ~+12% (n 355, CI +1.6 to +23, found after looking = hypothesis)**; 0.10+: -6 to -20% (n 100). Current rules only
      bet gaps ~0.135+, the zone that lost. Early unders can never qualify (0.03 early bar needs gap > 0.15, which needs a lineup).
    - Prices move toward the model: +0.58 pts avg on 347 re-read lines, larger with larger gaps (16.5% of the gap). Real, but
      Hard Rock's own close is over-biased, so it is not proof of profit.
    - The 12-19 pt gap on every pick is mostly built in by the filter (0.6 blend + vig + margins), and it bets a 7.9%-hold book is
      wrong by 15 pts, almost always on the under: treat as a red flag (likely level bias), not insight.
    - Saves: 33 lines, model worse than book. Nothing to say yet.
    - Lineup history is rebuildable from git history of `lineups.json` (161 versions): 78/100 team-games got a page dated that day,
      61 by 20 min before puck. Regulars (last 3 games, steady TOI) missed 0.8% (a miss is a void, not a loss).
    - Time to detect a 3-pt edge: Record picks only ~750 nights; **model's side on every line ~15-20 nights**; CLV 3-5 nights (already seen).
    **Plan (Sharp's gates):** (1) Shadow log: every night grade the model's side on every two-way shots line priced -200 to +120,
    by gap band and side, at posted price, internal file only (never the Record). (2) Closing shots pull ~20-25 min before puck
    for every game (~1 credit each), CLV on every line. (3) Daily lineup-history file. (4) Fit the blend weight from shadow log loss.
    **Gates:** edge = best blend weight on the model >= 0.3 and beats book log loss on >= 1,000 lines; no edge = weight <= 0.1.
    Go = mean CLV > 0 (t >= 2) and ROI >= 0. **Kill rule: at 100 graded shots picks or Nov 30, if CLV <= 0 and ROI <= 0, shots go
    logged-only and the page says "no proven edge".** No value change until the shadow sample decides (gap band, de-vig on the over,
    blend weight are the candidates). Traps (not now): early-regulars rule, staking by edge, extra re-prices, threshold tuning on 13 picks.
    **Status 2026-10-18 (Builder):** plan items 1-3 built (section 5, team logs): shadow log live each cycle + backfilled
    Oct 12-17 (751 shots, 33 saves, 850 points lines; shots results and model match the DS study exactly), C for every
    game, lineup history. Plus a weekly Hard Rock market menu. Item 4 (fit the blend weight) is the DS's, from `data/shadow/`.
    The DS method is ported to `scripts/shadow_backfill.py`.
18. **Rules v2.0 forward gates (Sharp, 2026-10-18).** Judged on the shadow log (the v2.0 bet on every line, not only page picks).
    - **Kill** = ROI <= -5% at 300 shadow bets, or <= 0% at 600, or open-to-close CLV < 0 at t <= -2 → page back to logged-only
      (50-leg pause stays on page picks).
    - **Confirm (~Oct 30):** 400 shadow bets ROI > 0 and mean CLV >= 0 → keep, consider 10/night.
    - **Strongly profitable (~mid-Nov):** 1,000 shadow bets ROI >= +5% with 90% lower bound > 0 → revisit parlays and edge cap.
    - **Stop doing:** proportional de-vig, gaps >= 0.05, 3.5 line, re-slicing Oct 12-17 (frozen; new variants forward only),
      mid-test value changes.
    - Builder replay (approximate: engine rules on every Oct 12-17 Hard Rock read, lineups unknown, missed-last-game players
      left out): 42 shown (6, 9, 4, 10, 4, 9 a night), 8 pulled, 21-13, +3.24u (+9.5% on 34 graded). In-sample, not evidence.

19. **Historical backtest, PRE-REGISTERED 2026-10-19 9:31 AM ET (commit 79d745c), before any historical price was looked at.** Matt gave a
    historical-odds key (The Odds API, 20,000 credits; held only in session scratch, never in the repo, secrets, page or logs).
    Probe: Hard Rock 2025-26 NHL shots props exist (10 credits per market per game snapshot). Model params were fit on 2024-25
    and the v2.0 rules on Oct 2026 lines, so the 2025-26 season is out of sample for both.
    - **Frozen hypotheses** (exact current code/config, no tuning): H1 v2.0 as in config; H2 rule A (no edge cap, lines 1.5/2.5/3.5,
      no caps); H3 v1.0 (expect a loss); H4 blind unders 1.5+2.5 in -200..+120 (baseline); H5 model vs over-hold-de-vigged book log loss.
    - **Prices:** primary = Hard Rock snapshot 45 min before puck (our pull C); secondary = 1 PM ET snapshot (our pull A) for a
      sample, for CLV. Graded 1u flat at that price; regulation + OT, no shootout; no ice time = void.
    - **No leakage:** model state for each game built only from games strictly before that date; no closing price, result, lineup
      or later stat used in a projection; stat corrections ignored. No historical lineups exist, so v2's early bar is the honest test.
    - **Primary success:** H1 full-season ROI >= +3% with 90% lower bound > 0 (game-clustered bootstrap), and positive in at least
      4 of 6 months. **Fail:** H1 ROI <= 0: v2 goes back to logged-only on the page and the edge question restarts.
    - **New ideas** (anything: subsets, home/away, rest, saves models, de-vig/blend variants): walk-forward only. Fit on months
      up to m, test on m+1, rolling. **Lockbox:** Mar 1-Apr 2026 games are not scored for any new idea until its rule is frozen
      and logged here. Count every variant tried; report the multiple-testing view.
    - **Budget:** max 18,000 credits, 2,000 kept in reserve. Order: shots at -45 min for all 2025-26 regular-season games;
      then saves at -45 min for a sample; then 1 PM shots for a sample (CLV). Raw historical data stays in session scratch (not
      committed); summaries and the scripts' method go in this file.

20. **Backtest result (2026-10-19): v2.0 FAILS the pre-registered bar. Picks are PAUSED (`ops.pause.active`).** 16,818 credits;
    1,287 of 1,312 2025-26 games with Hard Rock shots, 18,383 two-way lines, 0.7% names unmatched (two Elias Petterssons on VAN;
    Chinakhov spelling, also live). Production engine read-only, prior-game rows only; 6 lines checked by hand; replica = engine picks.
    | Hypothesis | n | ROI | 90% CI | months > 0 |
    |---|---|---|---|---|
| 2026-10-20 (CEO, Matt; Builder) | **v3.1: per-game (2) and nightly (3) caps removed.** Every leg that passes Gap + Guard is shown, ranked by final EV, in the Record and Discord. 1 side per player stays (you can't bet both sides). Page rules sheet reworded | Matt: "The limits I don't like. At the very least they should track all picks even if they exceed the limit." The product spec is every qualifying leg, ranked; the caps were exposure limits, not evidence-based | No picks shown under v3.0 yet (first live slate tonight); Nov 2 checkpoint now judges every passing leg |
    | H1 v2.0 uncapped / capped (live caps) | 3,918 / 1,198 | -2.7% / -6.1% | -5.2..-0.2 / -10.3..-1.9 | 1/7, 2/7 |
    | H2 rule A | 4,774 | -1.4% | -3.5..+0.8 | 2/7 |
    | H4 blind unders 1.5+2.5 | 13,427 | -6.3% | -7.7..-4.9 | 0/7 |
    - H5 log loss: proportional book 0.6814 < model 0.6832 < over-hold book 0.6836. The model is WORSE than Hard Rock (CI +0.0005..+0.0032).
      Model leans under by 1.5-2.5 pts on listed lines (1.5: says 53.2% over, actual 55.0%). That lean is where "under edges" came from.
    - Over-hold was NOT structural: share of hold on the over 0.52 for the season (Oct .45, Nov .58, Dec .38, Jan .29, Feb .33, Mar .80, Apr .75).
      Oct 2026's week was noise. Proportional de-vig is the better book estimate.
    - Hard Rock prices are sticky: 81% of lines unchanged 1 PM to -45 min; 2.9% of the model-book gap closes (t 2.0): real, ~1/20 of the vig.
    - Placebo: shuffled model -5.2% vs real -2.7% (p 0.02): the model has a little information, not enough to beat ~7% hold.
    - Walk-forward Nov-Feb, 11 idea families / 156 variants (rest/B2B, opp suppression, lines, TOI trend, PP role, edge band, price band,
      fitted blend, saves): every family negative out of sample; best -0.2%. Fitted blend gives the model ~0.1-0.4 weight.
      Frozen candidate (v2 + team on a B2B), lockbox Mar-Apr: n 268, +2.4%, CI -6.8..+11.4 = noise.
    - Saves (406 lines): model worse than book; walk-forward -4% to -14%.
    **Decision (pre-registered fail rule, CEO 2026-10-19 ~11 AM, before any v2 pick was shown):** no new picks in any market; page
    says "No picks for now: no proven edge." Odds pulls and the shadow log keep running (forward test of the one untested angle:
    Hard Rock's slow prices around lineup/goalie news). Item 18 gates are moot while paused.
    **Before picks return:** a new rule must be (1) pre-registered here, (2) positive walk-forward AND on a lockbox in history where
    testable, (3) then forward on the shadow log. Fix first: refit calibration on 2025-26 listed lines (removes the under lean),
    proportional de-vig, blend weight fitted walk-forward. Do not spend more historical credits re-slicing shots main lines.
    Historical key: 3,182 credits left (session scratch only). Raw data and scripts were in session scratch (not committed).
21. **Gap + Guard (LIVE since slate 2026-10-20; was a paper test).** STATUS 2026-10-19: Matt ordered "there should only be one
    version, the gap + model part". The CEO unpaused it as THE engine: real picks on the page, in the Record and in Discord from the first
    slate it covers (2026-10-20). Parlays stay off. v1.0/v2.0 code and rules removed (section 8). Hypothesis, not proven edge:
    the checkpoint is 2026-11-02 and the -10 unit safety pause protects the Record meanwhile. Keep the idea, frozen offsets and the Nov 2
    go / stop bullets below as written (they now judge a live rule: "GO" = keep, "STOP" = the Sharp pauses new picks via `ops.gap_guard.active`
    and logs it in section 8; the "hard stop Nov 23" and "paper only until Nov 2" wording is obsolete).
    Original item text (history):
21. **Gap + Guard PAPER test (Sharp final spec 2026-10-19 ~7 PM; Builder shipped, QA SHIP WITH FIXES (1 minor fixed), pushed 2026-10-19 evening).** Idea: Hard Rock's price sometimes lags the other books'
    consensus; buy only when the gap is >= +3.0% EV with Pinnacle agreeing, and let our model veto. Hypothesis, not evidence. Paper only until Nov 2.
    - **Frozen model offsets (do not change mid-test).** Refit once from the 2025-26 historical bundle (`research/data/hist_2025-26_hardrock.tgz`,
      `work/shots45_lines.jsonl`): Hard Rock shots lines at -45 min, production model from prior games only (`p_over` = engine `model_p_over`, raw,
      before blend), eligible = ok pair, >= 10 games, not sitting, not missed last game, result OK. Offset = actual over rate - mean model over:
      **1.5: +0.0179** (9,892 lines, actual 54.95% vs model 53.16%, SE 0.5 pt; reproduces item 20's "+1.8 pts") and **2.5: +0.0158** (6,610 lines,
      46.04% vs 44.45%, SE 0.6 pt). In-sample on the whole season (a one-number bias correction, not a rule); by month the 1.5 offset ran
      +0.5 to +3.8 pts.
    - **Nov 2 go / stop (CLV-based; ROI is reported, not judged).** Measured gap = a step-1 candidate (flag, veto or capped) with a CLV value.
      GO needs ALL: >= 30 measured gaps; >= 10 graded picks (W/L only); mean CLV >= +2.0% with 80% bootstrap lower bound > 0; >= 60% of CLV
      values positive; picks on >= 50% of nights; population slope > 0 (computed by the DS from `data/shadow/`, `summary.json` leaves it null);
      vetoed gaps do worse than passed ones (else drop the model guard). STOP if ANY: mean CLV <= 0 at >= 25 measured gaps; units <= -8; wins
      z < -2 against the sum of the flags' final probabilities; population slope <= 0 at >= 1,000 lines. Otherwise extend in 7-night blocks;
      hard stop Nov 23: STOP if N < 30. `summary.json` -> `nov2` holds gaps_measured, graded_picks, w/l/void, units, wins_z, CLV stats
      (n, mean, lb80, pos_share) for all measured gaps (headline), flags only and vetoed only, nights, nights_with_flags.
    - Open: no model for a player = no flag (not a veto); `toi_drop` is not applied (spec silent); the night cap is first-come within a read order
      by start time, ranked by final EV only inside one game's read; the page shows only the plain list (UX restyle pending); when the allowance is
      under 3 credits a game pull C runs only for games with a live pick (none while paused), so there is no close and no CLV on those nights.

## 8. Rule-change log
| Date | Change | Why | Sample |
|---|---|---|---|
| 2026-10-19 (CEO, Matt's order; Builder) | **One engine: Gap + Guard goes live as the only rule (v3.0), first slate 2026-10-20.** Real picks on the page, in the Record and in Discord (NEW PICK / PULLED). Removed: v1.0 and v2.0 selection code, the "previous" rules block, `rules_for`, `ops.pause` / pause banner / "no proven edge" text, `ops.paper` and paper mode (page section, Discord PAPER messages), parlays and goal watch UI. Parlays stay off. Kept: frozen offsets, the research log in `data/paper/`, the -10 unit safety pause (`ops.safety_pause`) | Matt: "Unpause ... There is no more 'old' version. There should only be one version which is the gap + model part." Gap + Guard is the only angle with a mechanism (Hard Rock lags the other books); v2.0 failed its pre-registered bar (item 20) | Item 21; Oct 19 replay on the real reads: Killorn O1.5 +100 shown at the 90-minute read, Michkov O1.5 -120 vetoed |
| 2026-10-19 (Builder) | Pick price is frozen at the flag read; the Record gets no `price` events for these picks; engine ranks by rounded final EV (4 dp) so the rank is stable between runs; research log is graded in a second soft step `gg_grade` after the shadow step so a finished game is graded in the same run | Keeps the page, the Record and the log on the same price and avoids a one-run lag | Tests |
| 2026-10-19 | **Record reset.** Record restarted empty; old Record archived at `archive/record_2026-10-19/` (18 singles 11-7 61% +0.96u, 7 parlays 1-6 -4.45u; Oct 12-18, 82 lines). Guard now accepts a reset only with a matching archive (`data/record/resets.json`) | Matt's order: "Restart all records and tracking. Everything starts fresh" (scope: Record + paper; odds, shadow logs, credits ledger untouched) | Record is empty until picks resume |
| 2026-10-20 | **Paper test starts** (`ops.paper`): Gap + Guard flags, vetoes, CLV and grades logged to `data/paper/`, Discord PAPER pings, page section "Paper test (not bets)". Pull B = shots only at every tier >= 1 and not lineup-gated, pull C = shots on every game, while paper is active. No pick, parlay or Record change; picks stay paused | Matt approved the paper path after the 2026-10-19 Gap + Guard review (Sharp, DS, Builder, QA all GO WITH CHANGES; final GO for PAPER ONLY). Model offsets frozen (item 21) | Nov 2 go/stop in item 21; ~3 credits/game |
| 2026-10-19 | Picks paused (`ops.pause.active`), page says no proven edge; v2.0 values kept but unused | Pre-registered fail rule: 2025-26 backtest H1 -2.7% (capped -6.1%), model worse than book | 18,383 historical Hard Rock lines (item 20) |
| 2026-10-18 (Sharp) | **Rules v2.0** from slate 2026-10-19: over-hold de-vig; blend 70/30; no adjustments; qualify 0 <= edge < 0.05, same bar early/confirmed; no min chance, news-gap, too-good or drift rules; shots 1.5 and 2.5 only; 2 per game, 8 a night by edge; pull at a new price if edge >= 0.05; parlays off. Shadow-graded lines now count as the sample for model/blend/qualify changes | DS edge study + Sharp ruling (section 7 items 17-18): Hard Rock puts the vig on the over; gaps 0.03-0.10 won, 0.10+ lost, and v1.0 only bet ~0.135+ | 742 shadow lines; discovery +19.1% (n 150) / check +12.8% (n 83); forward gates in section 7 item 18 |
| 2026-10-18 (QA fix) | Pull C for every game only at tier 3+ with today's budget >= 3 credits per game ahead; otherwise live picks only | Tier 2 cannot afford a closing read on every game | Ops |
| 2026-10-18 (team, item 17) | Pull C (shots, 45 min before puck) for every unstarted game at tier 2+, not only games with a live pick | Closing price on every line for the shadow log / CLV gate. ~1 credit a game; tier 3 is now up to 4 a game (A 1, B 2, C 1) against an allowance of ~5.2 | Ops, no graded sample needed; no qualifying value changed |
| 2026-10-18 (Matt) | Scope: shots only for picks (points `picks:false`); saves is the 2nd market, logged only until proven | Customer asked for at most 2 markets and to be elite at them. Customer-directed scope, not a data-driven value change; the 150-leg rule is about values. Points had 5 graded legs (3-2) so nothing is lost on evidence | Shots 13, points 5 graded legs; 1,233 shots and 924 points two-way lines in the odds log |
| 2026-10-18 (weekly) | No value changes. Page-only fixes (Record headline adds parlays, reasons, game-list wording, stale state) | Sample too small for any rule; week 1 calibrated (60.6% stated, 61.1% hit) | Shots 13, points 5 graded legs (need 50 pause / 150 change) |
| 2026-10-18 | Parlay cap and leg-use count every parlay shown that night (bug: only open ones counted, so a new set was built after each lock); a leg in 1 parlay (was 2) | Parlays were 1-6, -4.45u, the whole ROI drag (singles 11-7, +0.96u). Oct 13 showed 6 parlays (cap 3) with Rosen and Pulock in 4 each; the 3 extra all lost (-3u). One missed leg should sink one parlay, not four | 7 graded parlays; exposure cut, not a qualifying change, so the 150-leg rule doesn't apply |
| 2026-10-12 | Lineup-gated pulls: A is shots only at every tier; points/goals/saves only after both teams' lineups are confirmed and inside the B window; fallback points-only at 45 min if unconfirmed; lineups step runs before odds | Customer asked for lineup-gated pulls to save credits (no paying for prices on unconfirmed lineups) | Ops timing, no graded sample needed |
| 2026-10-12 | Pull B now 90 min before each game (was: before the first game, for all games) | Evening games were priced only in the morning until 45 min before puck; picks that appear after lineups confirm would show hours-old prices. Same credits | Ops timing, no graded sample needed |
| 2026-10-11 | v1.0 set (section 4) | First build: Sharp standard from the DS backtest (2024-25 fit, 2025-26 out of sample) and one live Hard Rock pull | Backtest only; 0 graded live legs |

## 9. Session log (newest first, one line each)
- 2026-10-20 ~5:25 PM (Matt: dislikes the limits, track every pick): v3.1 removes the 2/game and 3/night caps before tonight's first 5:30 PM read; 1 per player kept. paper.py treats a null cap as off; tests updated (322 pass); fixtures regenerated; rules sheet checked at 380px in Chromium (no overflow, no errors). Done by the CEO directly (no time for a separate Builder/QA round before the 5:30 read); weekly review to re-check.
- 2026-10-20 1:45 PM daily check: chain alive (link 138, Actions runs ok), all steps/sources ok, pull A ran 1 PM (11 games), keys 384 (key 4 empty), tier 3, budget 50 (11 used); unmatched: Elias Pettersson (two on VAN, known); no excluded teams. Nothing to grade (Record empty since reset, live from today); Oct 19 shadow graded. Fixed: C-for-every-game reserve over-counted (Oct 19 7 PM games got no C; tonight's margin was 1 credit) -> counts only B + C still owed. Builder -> QA SHIP (no page change), 322 tests.
- 2026-10-20 ~8:30 AM Researcher run 6 (daily, shots): N1-N5 registered before testing (team coherence of Hard Rock lines, within-team share, starting goalies, vig placement, home/road, close-game OT); 18 variants, best N2 +3.2% n230 / N1 +0.7% n110, nothing positive with n >= 300, no lockbox look (still 1); forward Q1a +7.2% n13 (1 night). Nothing passed.
- 2026-10-19 ~11:55 PM Researcher run 5 (extra, live consensus night 1, shots): Q1a-m + Q2a-b registered before scoring; research/code/fwd/score_fwd.py re-scores them on all nights daily. Night 1: 64 of 66 lines had consensus (median 5 books); Hard Rock at/above consensus fair on 13 lines (mostly plus-money unders, up to +5.7%); Q1 X=0 6-4 +1.7u on 10 graded = noise (bar n >= 300); 0 stale events, Q2 0 bets. Ops: 7 PM games got no 45-min C read on Oct 19.
- 2026-10-19 Builder (Matt: one version only, the gap + model part): Gap + Guard is now THE engine (v3.0). `engine.py` rebuilt on the research log
  (`paper.py` stays the single source of the maths); picks go to the page, the Record (`shown` with `gg_id`, price frozen) and Discord; old
  v1/v2 engine, rules sheets, pause, paper section, PAPER messages, parlays and goal watch removed; `gg_grade` step added; fixtures regenerated.
  319 tests pass (369 before: 4 test files / 61 tests of the removed engine deleted, 28 more tests of removed features deleted or rewritten inside other files, 38 new tests added incl. 29 in test_live_picks.py). Record untouched (still empty;
  guard and resets.json unchanged). Not pushed by the Builder. First live slate 2026-10-20: nothing is shown or appended for 2026-10-19 or earlier.
- 2026-10-19 ~8:30 PM (Matt: "Restart all records and tracking. Everything starts fresh"; scope chosen: Record + paper): old Record archived byte-exact at archive/record_2026-10-19/ and restarted empty; guard accepts only a reset with a matching archive (data/record/resets.json); paper log was already empty; odds, shadow logs and credits untouched. QA SHIP WITH FIXES (note rendering fixed), 369 tests, real 780-commit history walk passes. Future resets need Matt's explicit order.
- 2026-10-19 ~8 PM (Matt: "let's do it"): Gap + Guard PAPER shipped to main after QA (SHIP WITH FIXES). Paper window 2026-10-20 to 2026-11-23, judged Nov 2; picks stay paused; first paper flags possible from the 90-min reads on Oct 20. Open: page section not checked in a real browser; NHL Savant visual pass dropped by Matt; UX restyle of the paper section pending.
- 2026-10-19 Builder (Gap + Guard PAPER, Matt approved): built `scripts/paper.py`, `guard_paper.py`, `ops.paper`, odds plan (B shots-only not lineup-gated, C every game), Discord PAPER, page section; 353 tests pass (282 + 71). Oct 19 replay on the real reads: Killorn O1.5 +100 flagged at the 90-minute read (market 52.9%, +5.7% EV), Michkov O1.5 -120 vetoed (+3.7% gap, final EV +1.9%). QA: 353 tests pass, Oct 19 replay + Record-hash + timer-guard checks pass, page layout at 380px NOT browser-verified (no browser in session).
- 2026-10-19 ~7 PM Gap + Guard review (review + prototype only; no code, rule, timer or Record change): Sharp, Data Scientist, Builder, QA all GO WITH CHANGES; every objection resolved; final = GO for PAPER ONLY. Pinned: gap/guard in EV%, 4+ books incl. Pinnacle (Pinnacle = sign check only), flag on 90/45-min reads only, model offsets refit and frozen, B shots-only and not lineup-gated, paper log and PAPER pings fully separate from the Record. Nov 2 go/stop is CLV-based (N >= 30, extend to Nov 23). Not live until Builder ships it and QA passes it.
- 2026-10-19 ~2:50 PM Researcher run 4 (shots on goal only, resumed after a restart; K1-K12 registered before testing): arena, moneyline game script, player residual, VMR shape, last-game, price bands, LightGBM, top-k, attempts, PP change, opp blocks, shift-chart linemates; 46 variants (all-time 253), none positive with n >= 300, no lockbox look (still 1). Nothing passes; history exhausted for shots with free data; next = live news/timing (Q2, Q5, opening-line drift).
- 2026-10-19 12:50 PM (Matt): Researcher scope is shots on goal only; new ideas on saved data, no more historical credits. RESEARCH.md updated; run 4 started.
- 2026-10-19 12:45 PM Researcher run 3 (retail-book angles): S1-S3/S6 moneyline vs 9 books + Florida bias, S7 saves vs books, P1-P6 correlated parlays; 26 variants, nothing passes: Hard Rock ML within 0.5 pts of consensus, no FLA/TBL shading, saves -6.6% EV on every side; only lead = saves Under + opp skater Under SGP (+4.6%, CI spans 0, needs Hard Rock SGP >= 0.95x product; queued Q4). 1,860 hist credits (191 left); raw in research/data/hist_addon_2026-10-19_h2h_saves.tgz.
- 2026-10-19 12:30 PM (Matt, twice: everything in the current repo): historical bundle committed as research/data/hist_2025-26_hardrock.tgz (6 MB; scanned, no key). Matt was told The Odds API terms forbid offering its data as downloadable files (risk: key revoked) and chose this anyway; same applies to data/odds. Researcher runs now load from the repo.
- 2026-10-19 noon: Q1 live (QA PASS, 282 tests): every odds read asks Hard Rock + 9 books (same credits); shadow log has consensus, hr_vs_consensus, stale flags. Open: gzip/rotate data/odds before ~Dec (1.5-3 MB/day). Probe (10 hist credits): `hardrockbet_fl` returned no shots props for TOR Oct 17 (only `hardrockbet` did), so keep `hardrockbet`; recheck if FL prices ever appear. Extra Researcher run tonight 11:47 PM on night 1 of consensus data. Hist key 2,051 credits left.
- 2026-10-19 Builder (Q1, CEO approved): every odds read also asks 9 other books (same credits, one region); `others` in data/odds, consensus + stale fields in the shadow log; Hard Rock picks/page/Record byte-for-byte unchanged (test). 282 tests. Local commit for QA, not pushed.
- 2026-10-19 Researcher run 2: R1-R11 (25 variants), nothing passes; Hard Rock = market + ~3.5 pts/side, never beat 8-9 other books' consensus; 1,120 hist credits (2,062 left); next Q1 multi-book live pulls. NOT saved: the new alt-ladder/probe pulls (1.8 MB) — the Project is out of room; they live only in session scratch until Matt frees space or adds a private repo.
- 2026-10-19 11 AM (Matt: save historical data; hire a Researcher; find an edge): historical odds bundle saved privately as Project doc data/nhl_hist_2025-26_hardrock.tar.gz.b64.txt (round-trip checksum ok; not in this public repo). Researcher role created (research/RESEARCH.md, HYPOTHESES.md, LOG.md); first run now, then a daily scheduled run.
- 2026-10-19 (Matt: historical key, backtest with best practice): pre-registered, DS backtested 2025-26 (16,818 credits). v2.0 failed; picks paused before the first v2 pick. Pause = `ops.pause` in config + `common.picks_paused`; tests set PC_PAUSE_OFF=1 (test_pause.py turns it on). 263 tests. Dry cycle on a copy: empty state 'paused', Record unchanged; page and rules sheet checked at 380px.
- 2026-10-18 7 PM: v2.0 + shadow live, chain ok (7:00 PM run all steps ok). First market menu: Hard Rock NHL lists h2h, spreads, totals (+alts, periods, 3-way, OT, team totals, BTTS, odd/even) and player shots, alt shots, points, assists, PP points, goals (+alt, first), total saves, goals against, shutouts. No blocked shots. Weekly reviews check item 18 gates every Sunday (confirm gate ~Oct 30).
- 2026-10-18 evening (Matt: whatever it takes, find a strongly profitable edge): DS subset hunt (680 slices, none survive; rule A survives placebo p=0.01), Sharp ruled v2.0 (over-hold de-vig, 0.7 blend, edge 0-0.05, 1.5/2.5 only, 2/game, 8/night, parlays paused) live from slate Oct 19. Builder shipped shadow log, C on every game, lineup history, market menu, v2.0. QA: shadow PASS WITH FIXES (fixed), v2.0 PASS WITH FIXES (rules sheet dotted placeholder, fixed + page-regex test). 260 tests. Open: rulesv2 fixture still has v1-style picks; sheet says pull 'at a new price' but code pulls any time below break-even (code is the safer one).
- 2026-10-18 Builder (rules v2.0 + QA fixes): v2.0 in `config/rules.json` with v1.0 kept as "previous" for slates <= Oct 18 (`common.rules_for`); engine: over-hold de-vig, edge cap (entry + pull at a new price), line filter, 2/game, 8/night, best-edge line per player, optional rules (null = off); parlays off on page (one line) and Discord; rules sheet rewritten (v1 text kept for a v1.x rules.json); fixture `rulesv2`. QA fixes: shadow step 60 s budget, boxscores shared with grade per run (quick 10 s reads), previous-slate fetch cap 4; C every game only at tier 3+ with budget. Shadow adds `fair_over_oh` and `rules`. 259 tests pass. Local commit for QA, not pushed.
- 2026-10-18 Builder (item 17 build): shadow log (`scripts/shadow.py`, soft step after grade) + backfill Oct 12-17 (check 13/13 Record shots picks match), pull C for every game at tier 2+, lineup history (+ git backfill Oct 12-17), weekly market menu (~1 credit). 242 tests pass. Committed locally for QA, not pushed. Oct 18 shadow backfill to run once final.
- 2026-10-18 team meeting (Matt: find an edge, then prove it profitable): DS shadow-graded 742 shots lines, Sharp set gates and kill rule. Findings and plan in section 7 item 17. No code or rule changed this meeting; build waits for Matt's go.
- 2026-10-18 (Matt: hyper-specialize in 1-2 markets): reviewed every market we can see at Hard Rock. Decision: shots only for picks now, goalie saves as #2 (log, build, prove). Points picks off in `config/rules.json`; 221 tests pass. Then shipped item 16(a): planner stops pulling points, B pulls shots + saves, 221 tests pass. Not done: no saves model yet. No pick changes to the Record.
- 2026-10-18 1:44 PM daily check: chain alive (link 69, finished 1:40 PM, Actions runs all success; one cron run cancelled by the chain, normal), all steps/sources ok, pull A ran 1:00 PM (2 games, 34 lines, 0 picks, next check 5:15 PM), keys 476 (key 4 at 18), tier 3, no unmatched names/excluded teams. Oct 17's 1 pick graded (W); all 25 shown picks/parlays graded; record guard ok (82 lines). 221 tests pass. Nothing to fix.
- 2026-10-18 weekly review: DS (Record thru Oct 17): singles 11-7 61% vs 57.7% BE +0.96u (shots U 7-5 +0.11, points U 2-2 -0.49); parlays 1-6 -4.45u (all before the cap fix); calibration ok (stated 60.6%, hit 61.1%, n=18); edge doesn't sort winners; 1 zero-pick night (Oct 14); 19 sides within 1 pt of qualifying. Sharp: no value changes (shots 13 / points 5 graded legs vs 50 pause / 150 change). Shipped (QA SHIP at 380px): strip shows singles + parlays, Record "All bets", reasons show the real why (first sentence dropped, 3 lines), short Record table under 30, shorter game-list status, stale state hides New/Since and says "old price", fixtures one-parlay-per-leg, gap 12. Oct 17 1-of-4 = Daily Faceoff never confirmed (gap 4). Health: chain link 65 alive, all sources ok, keys 478, grading complete. 221 tests.
- 2026-10-18 (Matt): game list now shows lineup + goalie status per team. QA PASS at 380px. Goalie scrape untested against the live site.
- 2026-10-18 (Matt: Discord hard to read; hit rate fine but ROI low): Record read: singles +0.96u, parlays -4.45u. Fixed parlay cap bug (all-night count), leg in 1 parlay, rewrote Discord message. QA PASS. 212 tests.
- 2026-10-13 morning check: all 3 picks + 1 parlay graded end to end after final (picks 2W-1L +0.68u, parlay L), graded at worst shown price, record.json = rebuild, history guard ok (12 versions, needs unshallow in a fresh sandbox). 5 AM rollover ok, 16-game slate set, pull A not yet due. First-session list complete.
- 2026-10-12 evening check: chain ok, no failed steps, Record 12 lines, record.json matches rebuild. 3 picks + 1 parlay shown and locked (Vilmanis U1.5 shots graded; Vukovic-type U3.5 and U1.5 shots + parlay awaiting final). Same day shipped: pull B per game, lineup-gated pulls (45-min fallback), own-team highlight on cards, Discord notifications (hello sent; picks shown before the webhook were not notified). 208 tests. Morning check set for grading + 5 AM rollover.
- 2026-10-12 1:45 PM daily check: chain alive (link 4, 3 min old), all steps ok, pull A ran 10 AM (3 games), keys 1,445, tier 4, no unmatched names/excluded teams; nothing to grade (CAR@PHI had no picks; first pick FLA@BUF Vilmanis U1.5 shots locked). Fixed: page said "No picks tonight" while a pick was under Started and evening prices were still due → now "No open picks right now." + earlier-pick and next-check lines. Builder → QA PASS at 380px. 185 tests.
- 2026-10-12: QA round 2 (fresh QA) PASS WITH FIXES (0 blockers, 2 majors: Record history guard, refused keys) → fixed → QA recheck SHIP. First real pull 10:00 AM: 3 games, 96 lines, 6 credits, 0 picks (closest: Kaprizov U3.5 shots -150 at +2.2 pts, needs +3 early / +2 confirmed). Scheduled: daily check 1:43 PM ET, weekly team review Sundays 10:47 AM ET.
- 2026-10-11: First build. Probe confirmed timer, secret, Pages, Daily Faceoff from the runner. Team set the standard,
  built engine + page + timer; QA round 1 FAIL (2 blockers, 3 majors) → fixed → QA PASS. Cron unreliable → chain.
  4 odds keys in pool (1,456 credits). Live Record empty; first real pull due Oct 12 ~10:00 AM (FLA@BUF 1 PM).


## Obsolete wording (v3.0 note, 2026-10-19)
Gap + Guard is the only live engine. Anywhere this file still says v1.0/v2.0 rules, picks paused, paper mode, parlays on, goal watch, or `ops.pause` / `ops.paper`, it is history; section 4 is the rule.