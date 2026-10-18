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

## 4. Current rules (v1.0, 2026-10-11). Source of truth: `config/rules.json`
Starting values, set from the model backtest and one live Hard Rock pull. Not back-tested against prices (no free
price history exists; our own odds log, `data/odds/`, is building that).

| Area | Rule |
|---|---|
| Markets picked | Shots on goal (main line) and points, over and under. Saves and anytime goal are logged only (top odds tier). Shots alt, assists, sides, totals: out |
| Chance | Model (per-minute rate over two seasons, recent games weighted, × expected ice time × opponent; calibrated) minus 0.02 uncertainty, minus 0.015 on unders, minus 0.04 on thin-history overs; blended 60% model / 40% Hard Rock's de-vigged price |
| Qualify | Price -200 to +120; chance ≥ 0.56; chance − break-even ≥ 0.02 (lineup confirmed) or 0.03 (early); model − book gap > 0.15 needs lineup confirmed; gap > 0.20 = no pick (assume the book knows) |
| Eligibility | ≥ 10 games of history; thin = < 20 games of history or < 10 with team; missed team's last game → wait for lineup; back from 3+ missed games → sits 2 games; ice time down 2:00+ (last 2 vs last 10) → no over; team stats behind → team excluded and named |
| Ranking | By chance − break-even, then chance, confirmed first. 1 pick per player, 3 per game. First 8 open, rest under More |
| Parlays | One leg per game; legs chance ≥ 0.58, price -200 to +100; combined ≥ 0.34 (2 legs) / 0.20 (3); beat parlay break-even by 0.03; up to 3 a night, counting every parlay shown that night (locked and graded too, not pulled); a leg in 1 parlay only. Price = product of leg prices ("about") |
| Pulls | Out per Daily Faceoff; price past -200 or past +120; line or market gone; chance − break-even < 0; market moved 4+ points against an unconfirmed pick. Parlay with a pulled leg is pulled |
| Grading | When the NHL marks the game OFF. Regulation + OT count, shootout never. No ice time = void; whole-number tie = push. Graded at the worst price shown; parlays at their worst shown snapshot. Flat 1 unit |
| Odds pulls | Allowance = credits left / games left before keys reset on the 1st. Pull A (1 PM, or 3h before first puck) is SHOTS ONLY at every tier (cheapest market). Points and everything else wait for that game's lineups to be confirmed (both teams' Daily Faceoff pages dated today) AND the B window (90 min before that game's puck); retried each cycle until 20 min before puck. If lineups are still unconfirmed at 45 min before puck, points only are pulled as a fallback (so Daily Faceoff being down does not kill points picks), merged with pull C when a live pick needs it. Tiers (credits per game): <1 shots only for the games the budget covers; 1-2 shots all games once; 2-4 shots (A) + points (B, once lineups confirm) plus a re-check 45 min before each game holding a pick (C); 4-7 B is shots + points; 7+ B adds goals + saves (Goal watch). Started games are never pulled. The lineups step now runs before odds so a confirmation is used the same cycle. Unspent credits roll over |
| Safety | A market pauses itself at 50 graded legs if its hit rate is 13+ points under its average break-even or it's at -10 units. No other value changes before 150 graded legs in that market; one change at a time |

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
- **Files:** `index.html` (page; reads `data/slate.json`, `data/record.json`, `data/rules.json`), `data/odds/<date>.json`
  (every price pulled), `data/state/` (stats store, schedule, credits ledger), `fixtures/` (QA pages: `?fixture=NAME`,
  `?now=ISO`), `tests/` (`python -m unittest discover -s tests`, 221 tests; `tests/replay_day.py` replays a day).
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
   free fallback from NHL play-by-play `rosterSpots` ~20-30 min before puck, plus a daily lineup-history file
   (`lineups.json` keeps only today, so the DS can't judge the gap 0.15 rule). Needs a re-pull timing check before shipping.
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
15. Closing-price check is weak: most picks get no price pull after they're shown (13 of 18 "flat"). Week 1: 3 moved
    toward us, 2 against, avg +0.5 pts toward us. Re-pricing every shown pick at C would cost credits; pool is 478
    (allowance ~5.2/game), so not now. Revisit when keys reset Nov 1.

13. **ROI (2026-10-18, 18 singles + 7 parlays):** singles 61% vs 58% needed, +0.96u (+5% ROI); parlays -4.45u. Higher-edge
    picks did not hit more (edge 2-3 pts: 6-3; 3-4.5: 3-3; 4.5+: 2-1), so stake sizing by confidence waits until
    ~100 graded legs show the ranking sorts winners. 20 of 22 picks are unders; model sits 12-19 pts off the book on
    every pick (risk 1 above). Weekly review: track parlays after the fix, and edge-bucket hit rates for sizing.

## 8. Rule-change log
| Date | Change | Why | Sample |
|---|---|---|---|
| 2026-10-18 (weekly) | No value changes. Page-only fixes (Record headline adds parlays, reasons, game-list wording, stale state) | Sample too small for any rule; week 1 calibrated (60.6% stated, 61.1% hit) | Shots 13, points 5 graded legs (need 50 pause / 150 change) |
| 2026-10-18 | Parlay cap and leg-use count every parlay shown that night (bug: only open ones counted, so a new set was built after each lock); a leg in 1 parlay (was 2) | Parlays were 1-6, -4.45u, the whole ROI drag (singles 11-7, +0.96u). Oct 13 showed 6 parlays (cap 3) with Rosen and Pulock in 4 each; the 3 extra all lost (-3u). One missed leg should sink one parlay, not four | 7 graded parlays; exposure cut, not a qualifying change, so the 150-leg rule doesn't apply |
| 2026-10-12 | Lineup-gated pulls: A is shots only at every tier; points/goals/saves only after both teams' lineups are confirmed and inside the B window; fallback points-only at 45 min if unconfirmed; lineups step runs before odds | Customer asked for lineup-gated pulls to save credits (no paying for prices on unconfirmed lineups) | Ops timing, no graded sample needed |
| 2026-10-12 | Pull B now 90 min before each game (was: before the first game, for all games) | Evening games were priced only in the morning until 45 min before puck; picks that appear after lineups confirm would show hours-old prices. Same credits | Ops timing, no graded sample needed |
| 2026-10-11 | v1.0 set (section 4) | First build: Sharp standard from the DS backtest (2024-25 fit, 2025-26 out of sample) and one live Hard Rock pull | Backtest only; 0 graded live legs |

## 9. Session log (newest first, one line each)
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
