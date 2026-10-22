# LOG.md: Researcher runs (newest first)

- 2026-10-22 ~8:10 AM ET (Researcher run 8, daily; SHOTS ON GOAL ONLY). No key used, no historical odds pull. U1-U5 registered and pushed
  (902c4a0) before any test ran. Free NHL stats REST logs refetched to scratch (r6/fetch6.py; lockbox months not fetched). Script
  research/code/r8/u8.py, output u8_results.txt. 10,405 graded Nov-Feb lines.
  - U1 template prices (lines posted at Hard Rock's most common default price pairs = untouched by a trader?): -15.3% n147. No.
  - U2 start time (matinee / late West-coast games): logistic -9.0% n119; matinee UNDERS -6.8% n1,141 [-12.1,-1.5]. Priced in.
  - U3 opponent positional allowance (does the opponent give its shots to defensemen or forwards?): -10.6% n194; weight ~0.
  - U4 division games: -13.0% n178. Division games lean slightly over (stable small weight) but nowhere near the hold.
  - U5 player vs this opponent ("he owns this team"): logistic -7.3% n171; fading the "owner" +8.5% n50 [-12.5,+29.8] (tiny n).
  - Forward re-score (score_fwd.py, nights Oct 19-21; Oct 21 = 2 games): Q1a (Hard Rock >= consensus fair) +7.4% n90 [-8,+24] p .23;
    Q1f (4+ books) +13.8% n70 p .14; Q1k Pinnacle +3.0% n74; mean CLV ~= EV (+2.9%). Q2a/b 0 bets. Too small (bar n >= 300, p < 0.0033).
  17 variants (~0.85 false positives expected); all-time historical 309. Lockbox looks: 2 (unchanged; next needs p < 0.0167). Forward 15.
  **Verdict: nothing passed; no candidate for the Sharp.** Start time, divisions, opponent positional mix, head-to-head history and
  default-price lines are all inside Hard Rock's price; the book's own fair keeps weight ~1.0 and nothing moves it 3.5 pts.
  Next: (1) Q6, registered with a clean start date before looking: Q1a split by read (A vs B/C) and by side (unders), scored from the
  first night after registration; (2) Q7 returners' overs forward (needs a missed-games field per live shadow line: derive in research
  code from NHL boxscores + data/shadow); (3) a frozen stack of the small STABLE weights seen so far (K9 attempts, N1 team gap, N3 skew,
  U4 division) walk-forward, stated as using already-seen features, lockbox only if n >= 300 and positive.
- 2026-10-21 ~8:15 AM ET (Researcher run 7, daily; SHOTS ON GOAL ONLY). No key used, no historical odds pull. T1-T5 registered and pushed
  (810c48b) before any test ran; LB2 frozen and pushed (9da1bcb) before the lockbox was looked at. Free NHL stats REST logs refetched to
  scratch (r6/fetch6.py; Mar-Apr logs only after LB2 was frozen, r7/fetch_lb.py). Script research/code/r7/t7.py, output t7_results.txt.
  10,405 graded Nov-Feb lines.
  - T1 return from absence (UNDER on players back from missed games): -13.0% n161 / -21.8% n95. The logistic found the opposite:
    returners go OVER (T1c T=.03 +23.3% n84, all 4 folds positive, p .0085 before correction, ~0.18 after 21 variants, n < 300). Lead only:
    queued as Q7, forward only (history now seen).
  - T2 star tax (unders on last season's top-25/50 scorers): -5.5% n1,038 / -7.7% n2,077. No retail shading of stars.
  - T3 time-zone travel (unders after a 2+ zone trip within 2 days): +1.5% n498 [-5.8,+8.0] / east +0.5% n256; logistic -9.4%. Noise.
  - T4 big-slate calibration: -11.1% n363 (Nov only). Hard Rock is not sloppier on 10+ game nights.
  - T5 new team (book anchoring to last season for movers): T=.01 +1.8% n405 [-5.8,+9.3], folds -10.3/+25.2/+6.8/+22.7; T=.02 +15.9% n148.
    Placebo 0/200 >= real. Frozen as LB2 -> **lockbox look #2: -7.5% n179 [-18.6,+4.3], p 0.85. Failed.**
  - Forward re-score (score_fwd.py, nights Oct 19-20, 6 games + 13 games): Q1a +5.5% n82 [-13,+23], Q1f +12.8% n65, Q1k Pinnacle +3.4%
    n70, Q1m -1.4% n8; mean CLV ~= EV (+2.6%). Q2a/b 0 bets. Oct 20: 117 of 1,096 side-reads at/above consensus (10.7%), 5 stale events.
    Too small to judge (bar n >= 300, p < 0.0033).
  21 variants (~1.05 false positives expected); all-time historical 292. Lockbox looks: 2 (next needs p < 0.0167). Forward variants 15.
  **Verdict: nothing passed; no candidate for the Sharp.** The one variant that reached the lockbox (movers) was negative there.
  Next: (1) Q7 returners' overs, forward (needs a missed-games field on live shadow lines; ask the DS/Builder via the CEO, or derive from
  data/state/lineup_history and NHL boxscores in research code); (2) Q6 Q1 split by read (A vs B/C) and unders, registered with a clean
  start date; (3) T5 movers and T3 travel re-checked forward on the shadow log only if Q1's consensus feed shows Hard Rock lagging those spots.
- 2026-10-20 ~8:30 AM ET (Researcher run 6, daily; SHOTS ON GOAL ONLY). No key used, no historical odds pull. N1-N5 registered and pushed
  (ae64445) before any test ran. Free NHL stats REST per-game logs (skater, team, goalie; 2024-25 + 2025-26 through Feb 28 only, lockbox
  never fetched). Scripts: research/code/r6/ (fetch6.py, n6.py; output n6_results.txt). 12,952 pre-lockbox two-way lines.
  - N1 team coherence (do Hard Rock's player lines add up to the team's expected shots?): best T=.02 +0.7% n110 [-12.8,+13.8]; T=.01
    -5.4% n259. The gap has a real, stable positive weight, but it is far too small to clear ~3.5 pts of hold per side.
  - N1b within-team share vs history: -4.4% n109; weight ~0. N2 starting goalies (opp save %, backups): best T=.02 +3.2% n230
    [-5.7,+11.4], T=.01 -6.1% n519. N3 vig placement (skew/hold, a better de-vig): -9.6% n204; skew is a real calibration fix but loses.
  - N4 player home/road split: -9.9% n211, weight 0. N5 close game -> OT: 0 bets, weight 0.
  - As in run 4, the walk-forward logistics bet almost only in November (Oct-only training); from December nothing moves P past BE.
  - Forward (score_fwd.py, all nights to date = 2026-10-19 only; Oct 20 not played yet): all 13 Q1a bets now graded 7-6 +0.9u (+7.2%);
    Q1f +12.2% n11; Q1k Pinnacle +0.3% n14; Q1m 1-1; Q2a/b 0 bets. Too small to judge (bar n >= 300).
  18 variants (~0.9 false positives expected); none positive with n >= 300, so no placebo and no lockbox look. All-time historical 271;
  forward 15. Lockbox looks: 1 (unchanged).
  **Verdict: nothing passed; no candidate for the Sharp.** Team-level coherence, goalies, de-vig shape, home/road and OT chance are all
  already in Hard Rock's price to within its hold. Free-data features on main-line shots are exhausted; the live consensus feed is the
  only live route.
  Next: (1) daily forward re-score (Q1/Q2) as nights land; (2) Q6 A-read vs B/C split and an unders-only split, registered from a
  clean start date before looking once ~2 weeks are in; (3) N1 gap as a guard input for Gap + Guard picks (descriptive only on the live
  shadow log first: does a Gap pick with a negative team-coherence gap hit less?).
- 2026-10-19 ~11:55 PM ET (Researcher run 5, extra: night 1 of the live 9-book consensus; SHOTS ONLY; forward tests). No key used,
  no historical pull. Registered Q1a-m (13 variants) + Q2a-b (2) and pushed (0c0ce82) BEFORE any EV or result was computed; then
  built research/code/fwd/score_fwd.py, which re-scores every registered forward variant on ALL nights to date (output
  research/fwd/scores.md + .json). Forward bar fixed in HYPOTHESES.md: n >= 300 graded, ROI > 0, one-sided p < 0.0033, CLV > 0.
  - Night 1 = 4 games, 66 Hard Rock shots lines, 143 line-reads; 141 reads (64 lines) had a consensus (median 5 books).
  - Hard Rock at or better than the consensus fair on a side: 15 of 282 side-reads, 13 distinct lines (20% of lines), up to +5.7%
    EV (median side -8.2%, 90th pct -1.6%, 99th +3.6%). History said 0 of 100; difference = median of ~5 live books vs a mean of
    8-9 then, and/or one night's luck. 11 of the 15 were UNDERS at plus money. Hard Rock hold on these lines 9.4%.
  - Q1 (bet when Hard Rock beats consensus fair by >= X), graded so far (PIT@UTA's 3 bets not final at 11:40 PM): X=0 6-4 +1.7u
    (+17%, CI -26..+46); X=.01 +8% n7; X=.02 +26% n6; X=.03 -39% n3; X=.05 0-1. Pinnacle-only X=0 7-4 +3.0u n11. Gap lookalike
    1-1. CLV ~= EV (prices barely moved between reads). 4 games of results: noise, not evidence.
  - Stale events (Hard Rock frozen while consensus moved >= 3 pts): 0. Goalies: all 8 confirmed by the 2 PM check. Lineups: 4
    Daily Faceoff group changes (PHI 6:40 PM, PIT 8:50 PM), only Rakell had a Hard Rock line and no read came after the news before
    puck, so Q2 had 0 bets and no latency could be timed. 6 of the 13 Q1a bets came from the 1 PM read (before lineups/goalies).
  - Ops note for the CEO (not research): the two 7 PM games (ANA@NYR, COL@PHI) got B (5:30) but no 45-min C read (no 6:10 run;
    6:00 then 6:20). Gap + Guard only picks at B/C, so a missing C is a missed chance.
  15 forward variants (all-time historical still 253). Lockbox looks: 1 (unchanged).
  **Verdict: nothing passes; too small to judge (n 13 at best vs 300 needed).** First live sign that Hard Rock sometimes sits at or
  above the market on shots (mostly plus-money unders), which history never showed; needs weeks.
  Next: (1) daily run: `git fetch --unshallow origin` then `python3 -I research/code/fwd/score_fwd.py .`, append the table line;
  (2) Q6 split Q1 by read (A vs B/C) and by side (unders) once ~2 weeks are in, register any split before looking;
  (3) Q5 / Q2 latency as news events land between reads.
- 2026-10-19 ~2:50 PM ET (Researcher run 4, SHOTS ON GOAL ONLY; resumed after a session restart at 2:34 PM). Registrations K1-K9
  were written ~12:55-1:15 PM and committed (a96d06a) before any test ran; K10-K12 were registered and pushed (00b9a4b) after K1-K9
  ran and before K10-K12 were built. No odds key used, no historical odds pulled. Free NHL data only (team/skater logs, realtime
  attempts/blocks, TOI/PP TOI, and 2025-26 shift charts for the 945 pre-lockbox games). Scripts: research/code/r4/ (feats4.py,
  k_tests.py, k7.py, k_own.py, fetch_rest.py, fetch_shifts.py). Script fixes to match the registration before scoring: one-sided
  lines skipped (2 of 18,383), K1r on every line (the draft script had limited it to 1.5/2.5).
  - K1 arena scorekeeper: logistic -13.7% n153; road overs in top-5 arenas -1.7% n747, road unders bottom-5 -5.8% n832. Arena
    effect does not persist across seasons (corr 0.11).
  - K2 moneyline game script: 0 bets (no side within 1 pt of an edge). K3 player residual history: -12.6% n240.
  - K4 distribution shape (VMR): -10.2% n287. K5 last-game overreaction: +0.0% n246 [-8.7,+9.0]; rules -9.1% n616 / -2.8% n1,024.
  - K6 price-band rules (plus-money overs/unders): -6.7% to -10.6% on 1,390-4,563 bets, every fold negative; selector -8.9%.
  - K7 LightGBM on book + 24 prior-only features: no better than the book (Nov worse, Dec-Feb equal); -11.0% n76. K8 top-k -8% to -9%.
  - K9 attempts surplus -14.3% n237 (weight real and positive, too small). K10 PP TOI change -7.7% n534. K11 opp block rate
    -13.2% n235. K12 shift-chart linemate change -7.2% n369.
  46 variants (~2.3 false positives expected); none positive with n >= 300, so no placebo and no lockbox look. All-time 253.
  Lockbox looks: 1 (unchanged).
  **Verdict: nothing passes; no candidate for the Sharp.** On 12,877 pre-lockbox Hard Rock shots lines, no free pre-game
  information (arena, game script, player history, shape, form, attempts, PP role, opponent blocks, linemates, boosted trees)
  moves the probability past Hard Rock's ~3.5-pt-per-side hold. History is exhausted for main-line shots with free data; what is
  left is timing/news, which only the live feed can test.
  Next: (1) Q2 lineup/PP1 news latency on the live shadow log (Hard Rock shots prices are sticky: 81% unchanged 1 PM to -45);
  (2) Q5 Hard Rock vs the 9-book consensus on live shots reads by read time and news window; (3) first-posted Hard Rock shots line
  vs the -45 price on the live feed (history only had 1 PM and -45): does the opening number drift predictably?
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
