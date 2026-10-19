# LOG.md: Researcher runs (newest first)

- 2026-10-19 ~12:45 PM ET (Researcher run 3: attack Hard Rock as a retail book). Credits: 1,860 of 2,051 spent (191 left; ledger in
  research/data/hist_addon_2026-10-19_h2h_saves.tgz): 50 featured probes, 1,670 featured moneyline (10 books, 22:30Z on all 167 game
  days = every game's late price + most games' day-ahead price), 140 saves with 10 books (14 games). Scripts: research/code/r3/.
  - S1/S1e stale moneyline vs the other books (late 1,102 games, early 685): Hard Rock sits within 0.5 pts of consensus; EV >= 0 on
    0.1-0.5% of sides; n <= 5 bets per variant. Timing: Hard Rock's early-to-late move copies the market (slope 0.94); no lag.
  - S2 Florida bias: none. FLA +0.12 pts dearer, TBL 0.15 pts cheaper, same overround (4.4%). Fading locals n86 +0.5% [-20,+21].
  - S3 ML calibration: -0.1% n187. S6 back-to-back/rest on the ML: -3.8% n364.
  - S7 saves vs 2-5 other books: 44 of 44 Hard Rock sides EV < 0 (mean -6.6%). Hard Rock saves = market + heavy vig.
  - P1-P6 product-priced same-game parlays: teammates' shots barely correlate (lift x1.03 overs, x0.98 unders), so -10% to -15%.
    The real correlation is goalie saves vs the opposing skaters' shots: P5 (saves Under + opp skater Under) lift x1.21, +4.6% Nov-Feb
    on 1,676 pairs / ~140 games, CI -6.7..+15.7; placebo -11.5%. Pays only if Hard Rock's SGP pays >= 0.95x the product of singles;
    no API shows SGP prices, so it is a lead (Q4), not a candidate. No lockbox look (price unverifiable; ~56 lockbox saves games = no power).
  26 variants (~1.3 false positives expected); all-time 207. Lockbox looks: 1 (unchanged). Process note: S7-probe's registration
  commit landed just after its pull (script error), before any analysis.
  **Verdict: nothing passes; no candidate for the Sharp.** Every Hard Rock market checked (shots, alt shots, points, assists, saves,
  moneyline, team totals, alt totals, BTTS) is the market price plus vig, at every fixed time sampled, with no Florida shading.
  Next: Q4 one in-app SGP price check (saves Under + opp skater Under vs product), Q5 live Hard Rock-vs-9-books on the Q1 feed by read
  time / news window, Q2 lineup-news latency (forward).
- 2026-10-19 ~11:20 AM ET (Researcher run 2, first run). Credits: 1,120 of 3,182 spent (2,062 left; ledger
  hist/ledger_research.jsonl): 150 on 1-game/1-snapshot probes (multi-book shots, points/assists/PPP/goals, team totals/alt
  totals/BTTS, 1 PM and -70 min shots), 970 on Hard Rock alt-shots ladders at -45 for the 104 pre-lockbox games with 1 PM prices
  (97 had ladders; Oct games empty and free). Scripts: research/code/. Ideas (HYPOTHESES.md run 2):
  - R1 Hard Rock vs 8-9 other books (Pinnacle, FD, DK, MGM, Caesars, ESPN, BetRivers, BetOnline): 0 of 100 probed lines had any
    Hard Rock side at or above the others' de-vigged fair, at 1 PM, -70 and -45 min, shots and points/assists, same line or
    cross-line (NB conversion). Hard Rock = market price + ~3.5 pts per side. No bets to test; R5 (sides/totals) skipped for this.
  - R2 calibration refit + model/book stack: best -0.4% n47, -5.4% n188. Book carries the weight; model adds ~nothing.
  - R3 book + pre-game form/TOI/opponent/rest features: -5.6% n1,567 [-9.7, -1.8]; folds Nov -9.7 / Dec -3.9 / Jan +1.8 / Feb -6.9.
  - R4 alt ladder vs NB tails from the main line: every rung -12.3% (n 4,676; NB predicted -12.9%, so the tails are priced as
    modelled plus heavy vig). R4b stale ladder (alt pays more than the main over, same outcome): ~1% of player-games, mean EV vs
    Hard Rock's own fair -0.2%: no mechanical edge (n10 +41% is luck).
  - R6 game script (goal-diff strength): -15.4% n337. R7 teammate absence: -13.6% n235. R10 follow Hard Rock's own 1 PM->-45 move:
    -8.0% n210. R11 saves vs shots props: +2.0% n42, no signal.
  - R8 (post-hoc, found while screening): 1.5 overs at +110 or better +6.4% n293 [-4.8, +17.6] in Nov-Feb incl. the months I looked at;
    n < 300 and CI spans 0, so not frozen and no lockbox look.
  25 variants tested (~1.25 false positives expected); placebo not run because nothing reached n >= 300 with ROI > 0.
  Lockbox looks: 1 (unchanged). **Verdict: nothing passes. No candidate for the Sharp.** Shots main lines, alt ladders, saves and
  derived markets at Hard Rock all look like market price + vig; every model or feature tried so far is worse than or equal to the
  book's own price. The only untested route left is speed on news (forward only).
  Next: Q1 multi-book live pulls at no extra credit (shadow-log Hard Rock vs consensus every pull; catches stale moments),
  Q2 lineup-news latency (PP1 / top-6 promotions, teammate scratches vs an unchanged Hard Rock price), Q3 does consensus keep
  moving after -45 (100-game -5 min pull, 1,000 credits).
- 2026-10-19 (CEO, setup): role created. Starting point: TEAM.md item 20. Lockbox looks used: 1.
