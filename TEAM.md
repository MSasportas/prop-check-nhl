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
| Parlays | One leg per game; legs chance ≥ 0.58, price -200 to +100; combined ≥ 0.34 (2 legs) / 0.20 (3); beat parlay break-even by 0.03; up to 3 a night, a leg in at most 2. Price = product of leg prices ("about") |
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
- **Files:** `index.html` (page; reads `data/slate.json`, `data/record.json`, `data/rules.json`), `data/odds/<date>.json`
  (every price pulled), `data/state/` (stats store, schedule, credits ledger), `fixtures/` (QA pages: `?fixture=NAME`,
  `?now=ISO`), `tests/` (`python -m unittest discover -s tests`, 185 tests; `tests/replay_day.py` replays a day).
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
3. `toi_drop_sec` blocked overs for 4 of 16 skaters in the first live game: may be twitchy early season. Review item.
4. Lineup confirmation depends on Daily Faceoff (scrape; reachable from the runner on day 1). If it fails, picks stay
   Early and the page says so. Possible free fallback: NHL play-by-play `rosterSpots` ~20 min before puck (not built).
5. No verified free injury source; no free opponent-adjusted ranks (model uses raw opponent shots/goals allowed).
6. The NHL schedule time is used for lock (it can be ~10 min before actual puck drop): conservative.
7. Name matching: exact, or last name + first initial; unmatched names are listed in `status.json` and skipped.
8. QA minors open: R4 null-price pick renders as "—"; R6 chain recovery depends on the cron. Fixed 2026-10-12
   (QA round 2): R1 days left capped at the 1st; R2 rules sheet; R3 refused keys show "keys_refused"; R5 cycle runs
   `guard_record.py --history` after each pull (a force-pushed rewrite is caught only by a runner that saw the
   old Record, i.e. within one ~50 min run).
9. If a cycle pulled prices but its push failed, that cycle's credits are spent again next cycle. Rare.
10. Regular season only; playoffs say "Only regular-season games are covered."
11. Empty-state sub can promise "Next price check at …" when no keys are set or all are used up (`next_price_read_at`
    still set in run.py). Harmless while keys exist; Builder to clear it for `no_keys`/`all_used_up`. (QA note 2026-10-12)

## 8. Rule-change log
| Date | Change | Why | Sample |
|---|---|---|---|
| 2026-10-12 | Lineup-gated pulls: A is shots only at every tier; points/goals/saves only after both teams' lineups are confirmed and inside the B window; fallback points-only at 45 min if unconfirmed; lineups step runs before odds | Customer asked for lineup-gated pulls to save credits (no paying for prices on unconfirmed lineups) | Ops timing, no graded sample needed |
| 2026-10-12 | Pull B now 90 min before each game (was: before the first game, for all games) | Evening games were priced only in the morning until 45 min before puck; picks that appear after lineups confirm would show hours-old prices. Same credits | Ops timing, no graded sample needed |
| 2026-10-11 | v1.0 set (section 4) | First build: Sharp standard from the DS backtest (2024-25 fit, 2025-26 out of sample) and one live Hard Rock pull | Backtest only; 0 graded live legs |

## 9. Session log (newest first, one line each)
- 2026-10-12 1:45 PM daily check: chain alive (link 4, 3 min old), all steps ok, pull A ran 10 AM (3 games), keys 1,445, tier 4, no unmatched names/excluded teams; nothing to grade (CAR@PHI had no picks; first pick FLA@BUF Vilmanis U1.5 shots locked). Fixed: page said "No picks tonight" while a pick was under Started and evening prices were still due → now "No open picks right now." + earlier-pick and next-check lines. Builder → QA PASS at 380px. 185 tests.
- 2026-10-12: QA round 2 (fresh QA) PASS WITH FIXES (0 blockers, 2 majors: Record history guard, refused keys) → fixed → QA recheck SHIP. First real pull 10:00 AM: 3 games, 96 lines, 6 credits, 0 picks (closest: Kaprizov U3.5 shots -150 at +2.2 pts, needs +3 early / +2 confirmed). Scheduled: daily check 1:43 PM ET, weekly team review Sundays 10:47 AM ET.
- 2026-10-11: First build. Probe confirmed timer, secret, Pages, Daily Faceoff from the runner. Team set the standard,
  built engine + page + timer; QA round 1 FAIL (2 blockers, 3 majors) → fixed → QA PASS. Cron unreliable → chain.
  4 odds keys in pool (1,456 credits). Live Record empty; first real pull due Oct 12 ~10:00 AM (FLA@BUF 1 PM).
