# HYPOTHESES.md: every idea, registered before it is tested

| id | date | rule (exact) | data | result | status |
|---|---|---|---|---|---|
| H1 | 2026-10-19 | v2.0 as config (over-hold de-vig, 0.7 blend, edge 0-0.05, 1.5/2.5, caps) | 2025-26 shots -45 | -2.7% n3918 (capped -6.1%) | failed |
| H2 | 2026-10-19 | rule A (over-hold, 0.7 blend, edge >= 0, all lines) | same | -1.4% n4774 | failed |
| H3 | 2026-10-19 | v1.0 | same | n3 | n/a |
| H4 | 2026-10-19 | blind unders 1.5+2.5, -200..+120 | same | -6.3% n13427 | failed |
| H5 | 2026-10-19 | model vs book log loss | same | model worse (0.6832 vs 0.6814) | failed |
| WF1-11 | 2026-10-19 | 11 families / 156 variants: rest/B2B, opp suppression, line subsets, TOI trend, PP role, edge band, price band, fitted blend, saves (2 models) | walk-forward Nov-Feb | all negative, best -0.2% | failed |
| LB1 | 2026-10-19 | v2 + team on back-to-back (frozen) | lockbox Mar-Apr | +2.4% n268, CI -6.8..+11.4 | noise (lockbox look #1) |

## Run 2 (Researcher, 2026-10-19). Registered before any of these were tested.
Common to all: Hard Rock posted price at the -45 min snapshot (5-min grid, as item 19), price >= -200 (plus money any),
1u flat, regulation + OT, void no TOI, push on tie, game-clustered bootstrap. BE = break-even of the Hard Rock price.
Walk-forward test months Nov, Dec, Jan, Feb (train = all earlier months incl. Oct); lockbox Mar 1+ untouched until frozen.

| id | date | rule (exact) | data | result | status |
|---|---|---|---|---|---|
| R1 | 2026-10-19 | **Hard Rock vs other books (stale/off-market line), shots.** Same snapshot, same player, same line. Each other book with both sides: proportional de-vig. Consensus fair = mean over other books. Primary: >= 2 other books, bet the Hard Rock side with consensus fair - BE >= 0.02. No model. Variants (counted): T in {0, .01, .02, .03, .04} x min books {1, 2} x consensus {mean, median} = 20; walk-forward picks the variant with the best train ROI (min n 50) | new pull: player_shots_on_goal, up to 10 books incl. hardrockbet, -45 min, stratified game sample | no bets possible: 0 of 100 probed lines had any HR side at or above consensus fair (see R1-probe) | dropped (untestable) |
| R2 | 2026-10-19 | **Model flaws fixed, then edge.** Walk-forward logistic on every listed two-way line: logit P(over) = a_line + b*logit(proportional-de-vig book) + c*logit(model p_over). Bet side with p - BE >= T, T in {.01,.02,.03} (3 variants) | shots45_lines (existing) | best T=.03 -0.4% n47; T=.01 -5.4% n188 (bets only in Nov); book weight 0.66-0.91, model 0.13-0.47; log loss = book | failed |
| R3 | 2026-10-19 | **Market-implied residuals.** Walk-forward L2 logistic: logit P(over) = a_line + b*logit(prop book) + features known before the game: L5 and L10 SOG mean minus line, season-to-date SOG/game minus line, L10 over-rate at this line, TOI L5 minus season, position, home, team B2B, opponent SOG-against L10, book price band. Bet side with p - BE >= T, T in {.01,.02,.03} (3 variants). Plus a residual table by each feature (descriptive, train months only) | shots45_lines + NHL boxscores (existing) | T=.01 -5.6% n1567 [-9.7,-1.8]; .02 -5.9% n906; .03 -8.5% n500; features add nothing (log loss worse than book 3 of 4 months) | failed |
| R4 | 2026-10-19 | **Hard Rock alt shots ladder vs its own main line.** Fit each player's SOG distribution (negative binomial, dispersion fitted on training months) to the main line's proportional-de-vig fair over; price every alt rung (X+); bet a rung whose model-from-main-line fair - BE >= T, T in {.02,.04} (2 variants). No player model | new pull: player_shots_alternate (only if the probe shows Hard Rock posts it historically) | all 4,676 rungs -12.3% (NB model predicted -12.9%: tails priced as modelled, heavy vig); T=.02 -47% n9, T=.04 n4 | failed |
| R5 | 2026-10-19 | **Sides/totals: Hard Rock vs other books.** As R1 on h2h and totals (same line), one snapshot per game day before the first game; consensus = mean proportional de-vig of other books; bet HR side with consensus - BE >= T, T in {.01,.02,.03} (3 variants per market) | new pull: featured markets, only if credits remain after R1 | not pulled: probe shows HR at or worse than the field on team totals, alt totals, BTTS | dropped |
| R6 | 2026-10-19 | **Game script (shots).** Walk-forward L2 logistic: logit P(over) = a_line + b*logit(prop book) + c*strength diff + d*strength diff x is-D, strength diff = team minus opponent goal differential per game in 2025-26 games before the date (0 if < 5 games). Bet side with p - BE >= T, T in {.01,.02,.03} (3 variants). If walk-forward ROI > 0, R6b repeats it with Hard Rock's moneyline (featured h2h, paid) | shots45 + boxscores | T=.01 -15.4% n337; .02 -14.5% n169; .03 -19.3% n81 | failed |
| R7 | 2026-10-19 | **Teammate absence (shots).** Same logistic with c*absent_sog = sum of 2025-26 SOG/game of teammates who played >= 5 of the team's last 10 games but not its last game (knowable pre-game), and d*absent_sog x player's own SOG share. T in {.01,.02,.03} (3 variants) | shots45 + boxscores | T=.01 -13.6% n235; .02 -13.9% n186; .03 -9.6% n139 | failed |
| R8 | 2026-10-19 | **1.5 overs at plus money (low-volume shooters' tails).** Found while screening R4 (looked at Oct-Feb outcomes: 1.5 lines with fair over < .44 hit 2+ at 47.9%, n 144), so Nov-Feb is NOT clean for it. Rule: bet over 1.5 when Hard Rock over price >= +100. Variants: price >= +100 / >= +110 / >= +120 (3). Clean test = lockbox only, once, if Nov-Feb ROI > 0 with n >= 300 | shots45 | >=+100 +0.0% n780; >=+110 +6.4% n293 [-4.8,+17.6] (in-sample, n<300); >=+120 +11% n77 | not a candidate (post-hoc, n<300, CI spans 0) |
| R1-probe | 2026-10-19 | R1 frequency check (prices only, no results): Hard Rock vs 8-9 other books (Pinnacle, FD, DK, MGM, Caesars, ESPN, BetRivers, BetOnline) on 4 snapshots (1 PM x2, -70 min, -45 min), shots 62 lines + points/assists 38 lines: **0 lines where any Hard Rock side beats the other books' de-vigged consensus (T = 0)**; best -0.014. Hard Rock copies the market and keeps ~3.5 pts per side. R1 untestable (no bets) and structurally empty at these times; R5 (featured) not pulled for the same reason (team totals/alt totals/BTTS probe: Hard Rock worse than the field on longshots) | probe pulls | 0 bets | dropped |
| R4b | 2026-10-19 | **Stale alt ladder.** Same -45 snapshot: when Hard Rock's alt rung at the main line's own point pays MORE than the main over (alt price > main over price), bet that alt rung. Variant R4b2: in that case also bet every higher rung with EV >= 0 under NB tails from the main fair (r fitted on training months). 2 variants. Probe example: Forsling main O1.5 +120, alt 1.5 +145 | new pull: player_shots_alternate, HR only, the 104 pre-lockbox games that have 1 PM prices | ~1% of player-games (13 of 1,348); test n10 +40.8% [-2.5,+95.6] = luck: mean EV vs HR main fair -0.2%; R4b2 -21.8% n18 | failed (no mechanical edge) |
| R10 | 2026-10-19 | **Follow Hard Rock's own move (under-reaction to news).** Lines with a 1 PM and a -45 price at the same point: if proportional fair over moved by >= d between 1 PM and -45, bet the side it moved toward at the -45 price. d in {0.005, 0.02, 0.04} (3 variants). Same-point line changes (1.5 -> 2.5) counted as a move toward the over/under by line direction, bet at the new line | shots13 + shots45 (existing, 104 pre-lockbox games) | d=.005 -8.0% n210; .02 -14.1% n76; .04 -11.3% n25 | failed |
| R11 | 2026-10-19 | **Saves vs the shots props (cross-market, no player model).** Implied shots against = sum over the opponent's listed skaters of NB mean (r 20) solved from each Hard Rock shots line's proportional fair, scaled by a ratio fitted on training months (team SOG / listed sum). Walk-forward logistic: logit P(saves over) = a + b*logit(saves book fair) + c*(scaled implied SA - saves line)/sqrt(line). Bet side with p - BE >= T, T in {.01,.02,.03} (3 variants) | saves45 + shots45 (existing) | T=.01 +2.0% n42 [-24,+27]; .02 n6; feature weight ~0 and flips sign | failed (no signal, n tiny) |

Run 2 count: 25 variants tested (R2 3, R3 3, R4 2, R4b 2, R6 3, R7 3, R8 3, R10 3, R11 3; R1's 20 had no bets, R5 not pulled).
Expected false positives at 5%: ~1.25. Positives seen: R4b n10, R8 +6.4% n293 (post-hoc), R11 n42: all n < 300, CIs span 0.
Cumulative variants all runs: 181. Lockbox looks: still 1.

## Run 3 (Researcher, 2026-10-19 PM). Registered before any of these were tested.
Brief: stop polishing the shots model; attack Hard Rock as a retail book (market-vs-market, local bias, structure, timing).
Probes before registering (prices only, no results, 50 credits): featured h2h/totals/spreads, 10 books, 2025-11-18 22:30Z and
2025-12-09 17:00Z. Findings that shaped the pull: `hardrockbet_fl` returns nothing historically (only `hardrockbet`); Hard Rock has
no h2h_3_way or 1st-period totals historically (probe 641); at 17:00Z next-day games have no Hard Rock price, at 22:30Z most do,
so one 22:30Z snapshot per game day gives every game a LATE price (same-day games, ~0.5-4.5 h before puck) and an EARLY price
(next-day games, ~24-28 h before). Pull: featured h2h, 10 books (hardrockbet + pinnacle, draftkings, fanduel, betmgm,
williamhill_us, espnbet, betrivers, fanatics), 22:30Z every game day Oct 7 - Apr 16 (~1,650 credits).
Common: consensus fair = mean of proportional de-vig fair over the OTHER books with both sides at that snapshot (>= 3 books);
Pinnacle fair = Pinnacle alone de-vigged. EV = fair x decimal(Hard Rock price) - 1. Hard Rock price must be >= -200. h2h graded
on the final result incl. OT/shootout (NHL final score). 1u flat, game-clustered bootstrap. Walk-forward folds Nov, Dec, Jan, Feb
reported per variant; lockbox (Mar 1+) only for a frozen variant positive Nov-Feb with n >= 300, once.

| id | date | rule (exact) | data | result | status |
|---|---|---|---|---|---|
| S1 | 2026-10-19 | **Moneyline stale vs the market, LATE price.** Same-day games (puck 0.25-6 h after the snapshot). Bet the Hard Rock side whose EV >= T. T in {0, .01, .02} x fair in {consensus, Pinnacle} (6 variants) | featured h2h pull | | registered |
| S1e | 2026-10-19 | **Same, EARLY price (timing).** Next-day games (puck 18-34 h after the snapshot), same 6 variants. Plus descriptive: does Hard Rock's early-to-late move lag the consensus move (regress HR late-early on consensus late-early)? | same | | registered |
| S2 | 2026-10-19 | **Florida local bias.** Descriptive: d = Hard Rock fair(team) - consensus fair(team), late price, for FLA and TBL sides vs every other team (game-clustered CI). Bets: S2a every FLA/TBL opponent ML at Hard Rock (late, >= -200); S2b same only when that price's EV vs consensus >= -0.01 (2 variants). n ~150 games, so it can never reach the n >= 300 lockbox bar alone: a shading finding would go forward-only | same | | registered |
| S3 | 2026-10-19 | **Moneyline calibration (favourite-longshot) at Hard Rock.** Walk-forward logistic: logit P(win) = a + b*logit(consensus fair) + c*home, fit on months before m; bet Hard Rock side with p - BE >= T, T in {.01, .02, .03} (3 variants) | same | | registered |
| P1 | 2026-10-19 | **Correlated parlays (structure), same-team shots overs.** Every pair of teammates' two-way shots OVER lines at the -45 snapshot (each leg >= -200), parlay paid at the PRODUCT of Hard Rock decimal prices (what a product-priced parlay would pay). Report ROI, joint hit vs product of fair (lift), and the break-even same-game-parlay price. No fitting | shots45 (existing) | | registered |
| P2 | 2026-10-19 | Same, teammates' UNDER pairs | shots45 | | registered |
| P3 | 2026-10-19 | Same, OVER pairs from opposing teams (same game) | shots45 | | registered |
| P4 | 2026-10-19 | Goalie saves OVER + each opposing skater's shots OVER (same game, -45) | saves45 + shots45 | | registered |
| P5 | 2026-10-19 | Goalie saves UNDER + each opposing skater's shots UNDER | saves45 + shots45 | | registered |
| P6 | 2026-10-19 | 3-leg same-team shots OVERS (every triple) | shots45 | | registered |

Run 3 variants registered: S1 6, S1e 6, S2 2, S3 3, P1-P6 6 = 23 (all-time 181 -> 204 if all run).

## Queued (not yet tested)
| id | rule idea | data | status |
|---|---|---|---|
| Q1 | Multi-book live pulls at no extra credit (a `bookmakers=` list of up to 10 costs the same as Hard Rock alone): shadow-log Hard Rock vs consensus at every pull; forward rule = bet a Hard Rock side whose price beats the other books' de-vigged consensus by >= 0 (none did in 4 historical snapshots, so this tests news latency only) | live feed (Builder change, CEO call) | queued |
| Q2 | Lineup-news latency: when Daily Faceoff moves a player up (top-6 / PP1) or a top-shooting teammate is out, and Hard Rock's price has not changed since, bet the over (shots) | data/state/lineup_history groups + data/odds | queued (forward only) |
| Q3 | Hard Rock -45 price vs other books' close (-5 min): does the consensus keep moving after -45, and is the direction predictable from features at -45? | historical pull, 10 credits/game, sample 100 games | queued |
