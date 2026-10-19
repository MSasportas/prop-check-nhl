# LOG.md: Researcher runs (newest first)

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
