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
Sharp (betting method, final call) · Data Scientist (data, model, samples, judging the Record) · UX (page) ·
Builder (all code) · QA (tests every change before it goes live, real browser at 380px, hasn't seen the build).
Rule changes: the Data Scientist names the sample first; the Sharp decides; log it in section 8.

## 4. Current rules (v2.0, 2026-10-18; first slate 2026-10-19). Source of truth: `config/rules.json`
Set by the Sharp from the DS edge study (section 7 item 17) on 742 shadow-graded Hard Rock shots lines. Slates up to
2026-10-18 keep v1.0 (`config/rules.json` "previous"; `common.rules_for`), so nothing already shown or on the Record changes.
v1.0 in one line: 60/40 blend, proportional de-vig, -0.02/-0.015/-0.04 adjustments, chance >= 0.56, margin 0.02 confirmed /
0.03 early, gap 0.15 needs lineup, gap 0.20 = pass, 3 per game, parlays on, 4-pt drift pull.

| Area | Rule |
|---|---|
| Markets picked | **Shots on goal only, lines 1.5 and 2.5** (`lines_allowed`), over and under. Saves = 2nd market, logged only (shadow log) until proven (section 7 item 16). Points, goals: logged only / not pulled. 3.5 and everything else: out |
| Chance | Model (per-minute rate over two seasons, recent games weighted, × expected ice time × opponent; calibrated), blended **70% model / 30% Hard Rock**. Hard Rock's chance = **all hold on the over** (`devig: over_hold`): fair under = the under price's own break-even, fair over = 1 − that. No uncertainty, under or thin-over adjustments (all 0) |
| Qualify | Price -200 to +120; **edge = chance − posted break-even, 0 ≤ edge < 0.05** (`edge_cap`). Same bar early or lineup confirmed. No minimum chance, no news-gap or too-good rule |
| Eligibility | ≥ 10 games of history; missed team's last game → wait for confirmed lineup; back from 3+ missed games → sits 2 games; team stats behind → team excluded and named. Ice time down 2:00+ (last 2 vs last 10) → no over (`toi_drop_sec` 120, unchanged from v1.0). Daily Faceoff lists him out → pulled |
| Ranking and caps | By edge, best first. 1 per player (his best-edge line), **2 per game, 8 a night** (`max_picks_night`: every single shown that night and not pulled counts). All shown, no More list |
| Parlays | **Off** (`parlay_cap 0`). Page shows "Parlays paused until single picks prove out." Discord sends no parlays |
| Pulls | Out per Daily Faceoff; price past -200 or past +120; line or market gone; chance below break-even; **at a new price, edge ≥ 0.05**. No drift pull |
| Grading | When the NHL marks the game OFF. Regulation + OT count, shootout never. No ice time = void; whole-number tie = push. Graded at the worst price shown; parlays at their worst shown snapshot. Flat 1 unit |
| Odds pulls | **Pull C (45 min before puck, shots): every unstarted game at tier 3+ (closing price for the shadow log); at tier 2, or when today's remaining budget is under 3 credits per game still ahead, only games holding a live pick.** **2026-10-18: points are no longer pulled at any tier.** B = shots re-price (+ saves at tier 3, + goals at tier 4), C = shots only, fallback at 45 min = shots. Older text below still says points: read it as shots. Allowance = credits left / games left before keys reset on the 1st. Pull A (1 PM, or 3h before first puck) is SHOTS ONLY at every tier (cheapest market). Points and everything else wait for that game's lineups to be confirmed (both teams' Daily Faceoff pages dated today) AND the B window (90 min before that game's puck); retried each cycle until 20 min before puck. If lineups are still unconfirmed at 45 min before puck, points only are pulled as a fallback (so Daily Faceoff being down does not kill points picks), merged with pull C when a live pick needs it. Tiers (credits per game): <1 shots only for the games the budget covers; 1-2 shots all games once; 2-4 shots (A) + points (B, once lineups confirm) plus a re-check 45 min before each game holding a pick (C); 4-7 B is shots + points; 7+ B adds goals + saves (Goal watch). Started games are never pulled. The lineups step now runs before odds so a confirmation is used the same cycle. Unspent credits roll over |
| Safety | A market pauses itself at 50 graded legs if its hit rate is 13+ points under its average break-even or it's at -10 units (page picks). **Model, blend and qualify changes are judged on the shadow log** (every two-way line graded at the posted price), not on page picks alone; the 150-graded-legs rule now counts shadow-graded lines. One change at a time, forward only |

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
- **Files:** `index.html` (page; reads `data/slate.json`, `data/record.json`, `data/rules.json`), `data/odds/<date>.json`
  (every price pulled), `data/shadow/` (shadow log), `data/state/` (stats store, schedule, credits ledger, lineup history,
  market menu), `fixtures/` (QA pages: `?fixture=NAME`, `?now=ISO`), `tests/` (`python -m unittest discover -s tests`,
  259 tests; `tests/replay_day.py` replays a day).
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

## 8. Rule-change log
| Date | Change | Why | Sample |
|---|---|---|---|
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
