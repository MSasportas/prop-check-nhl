# LOG.md: Researcher runs (newest first)

- 2026-10-29 ~8:15 AM ET (Researcher run 14, daily; SHOTS ON GOAL ONLY). No key used, no historical odds pull. BB1-BB3 + forward Q15a-b registered
  and pushed (399b42c) before any test ran. Free NHL stats REST skater per-game logs fetched to scratch (r14/fetch14.py; Feb 28 cut-off,
  lockbox not fetched). Script research/code/r14/bb14.py, output bb14_results.txt. 10,413 graded Nov-Feb lines.
  - BB1 team bounce-back after a bad game (lost by 3+, outshot): best T=.02 -14.7% n92; OVER after a 3+ goal loss -3.0% n1,953 [-6.6,+0.4],
    p .92. Small stable weight: a team that outshot its last opponent leans over (+0.05..0.08 std), far below the hold.
  - BB2 streak vs his own Hard Rock number (3+ straight overs/unders): -19.4% n120 to -60% n16; UNDER after 3+ straight overs -3.7% n1,401.
  - BB3 road trip / homecoming: best T=.02 -4.7% n98; UNDER on the 4th+ straight road game -9.3% n963 [-14.5,-4.1], every fold negative.
  - Forward re-score (score_fwd.py + Q6/Q8/Q9/Q10/Q11 scorers, 10 nights Oct 19-28; clone unshallowed): Q1a (Hard Rock >= consensus fair)
    +9.6% n354 [+1,+18] p .025, n now past 300 but p misses its bar (.0033): not a pass; Q1b (EV >= 1%) +14.8% n258 p .001; Q1c (EV >= 2%)
    +18.2% n188 [+9,+28] p .001; Q1k Pinnacle +10.4% n274; Q1m +28.2% n36; mean CLV ~= EV (+2.4..4.2%). Q6a (1 PM) +12.2% n112, Q6b (B/C)
    +9.9% n89, Q6c (unders) +17.0% n165. Q8a-c +17.9% n17 / -5.5% n28 / +20.7% n72. Q9a-c +24.7% n57 / +4.2% n34 / +0.2% n11. Q10 +14.4% n29.
    Q11a (both goalies confirmed) +8.9% n57 p .22; Q11b (not both) +22.3% n131 p .003. Q2a/b 0 bets. Q15a-b (Q1c at 1 PM vs at B/C) start
    tonight, 0 bets. Oct 28 (2 nights' worth of games at 1 PM only) pulled Q1c from +20.4% to +18.2%: still strong, but shrinking toward Q1a.
  - Points (Q12-Q14) not scored: this task's prompt is shots only; RESEARCH.md says points also runs daily, so the CEO should either widen
    this task's prompt or give points its own run.
  12 variants (~0.6 false positives expected); all-time historical 392; forward 29. Lockbox looks: 2 (unchanged; next needs p < 0.0167).
  **Verdict: nothing passed; no candidate for the Sharp.** Bounce-backs, over/under streaks and road-trip length are all inside Hard Rock's
  price; history with free data stays exhausted (392 variants). Q1a is the first forward test past n 300 and it does NOT clear its bar
  (p .025 vs .0033); Q1b/Q1c (the stricter EV cuts) are the live leads, ~300 by about Nov 4-7.
  Next: (1) Q1b to n >= 300 (~Nov 2) and Q1c (~Nov 6), judged at the forward bar, CLV checked; (2) Q15a vs Q15b from tonight: if the edge sits
  at the 1 PM read the product cannot use it yet (CEO decision on an earlier read); (3) a forward test of Q1c on Pinnacle-present lines only
  vs Pinnacle-absent, registered before looking.
- 2026-10-28 ~8:10 AM ET (Researcher run 13, daily; SHOTS ON GOAL ONLY). No key used, no historical odds pull. AA1-AA4 + forward Q11a-b registered
  and pushed (9bc8805) before any test ran. Free NHL stats REST skater + goalie per-game logs fetched to scratch (r13/fetch13.py; Feb 28
  cut-off, lockbox not fetched). Script research/code/r13/aa13.py, output aa13_results.txt. 10,413 graded Nov-Feb lines.
  - AA1 player fatigue load (minutes in the last 3 days, 3rd game in 4 nights, heavy last game): best T=.03 -11.8% n238; UNDER on a
    player's 3rd game in 4 nights -7.3% n2,116 [-10.7,-3.8], every fold negative. Tired legs are not an under at Hard Rock's price.
  - AA2 board depth (how many Hard Rock lines the team/game has = trader attention): -14.1% n211 to -25.9% n71; weight ~0.
  - AA3 own goalie (weak/backup own goalie -> trailing -> more shots): -3.3% n1,094 to -4.0% n1,204 (Nov only); OVER when his team starts
    its backup -7.6% n4,036 [-9.9,-5.3]. The weight even points the other way (backup -> slightly fewer shots).
  - AA4 position calibration (book too extreme/flat on defensemen): -8.8% n274; D x book weight -0.03..-0.05 every fold (real, tiny).
  - Forward re-score (score_fwd.py, 9 nights Oct 19-27; clone unshallowed): Q1a (Hard Rock >= consensus fair) +9.0% n332 [-0,+18] p .053;
    Q1b (EV >= 1%) +15.3% n241 [+6,+24] p .0025; Q1c (EV >= 2%) +20.4% n177 [+11,+30] p < .001; Q1k Pinnacle +10.2% n254; Q1m +31.9%
    n35; mean CLV ~= EV (+2.5..4.1%). Q6a (1 PM) +14.9% n98, Q6b (B/C) +5.0% n81, Q6c (unders) +16.3% n147. Q8a-c +42.6% n13 / -21.6% n22
    / +19.8% n60. Q9a-c +20.3% n45 / +1.4% n28 / +31.2% n7. Q10 returners' overs +15.8% n27. Q2a/b 0 bets.
    New Q11 (Q1c by goalie status at the read): both goalies confirmed +10.6% n53 p .20; NOT both confirmed +24.6% n124 [+13,+37] p .002
    (78 of the 124 from the 1 PM read). Fits the idea that Hard Rock's edge-sides appear before news, but n is far below 300.
    Nothing has n >= 300 with p under its bar yet (Q1a n332 has p .053 vs .0033).
  14 variants (~0.7 false positives expected); all-time historical 380; forward 27. Lockbox looks: 2 (unchanged; next needs p < 0.0167).
  **Verdict: nothing passed; no candidate for the Sharp.** Player fatigue, board depth, own-goalie score effects and position calibration
  are all inside Hard Rock's price. History with free data stays exhausted (380 variants). The live Q1 gap keeps strengthening: Q1c
  +20.4% on 177 bets with CLV matching EV; at ~20 bets/night it reaches n 300 around Nov 3-4.
  Next: (1) Q1c to n >= 300 (~Nov 4), then the Sharp decision is a forward-bar call, not a lockbox one; (2) Q11 split keeps running
  (does the gap live mostly at the 1 PM read before goalies? the product picks only at B/C); (3) a forward Q1c-at-1-PM-only variant
  if the Sharp would consider moving picks earlier, registered before looking further.
- 2026-10-27 ~8:15 AM ET (Researcher run 12, daily; SHOTS ON GOAL ONLY). No key used, no historical odds pull. Z1-Z4 + forward Q10 registered
  and pushed (3100297) before any test ran. Free NHL stats REST skater summary + realtime logs fetched to scratch (r12/fetch12.py; Feb 28
  cut-off, lockbox not fetched). Script research/code/r12/z12.py, output z12_results.txt. 10,413 graded Nov-Feb lines.
  - Z1 team-level shot form (team's last-5 shots vs its season; opponent's last-5 shots allowed): best T=.03 -12.4% n247; fixed OVER rule
    -3.8% n758 [-9.6,+1.8], p .87. Hard Rock already folds team form into each player's number.
  - Z2 accuracy luck (recent shots-on-target rate above his norm should regress): best T=.02 -2.8% n90; UNDER on the luckiest -4.3% n505
    [-11.2,+3.0]. Recent accuracy partly carries over; nothing to fade.
  - Z3 role instability (ice-time swings): -9.7% n353 to -11.7% n168; weight ~0. The book is no worse on volatile-role players.
  - Z4 stuck line (same integer line 4+ straight games while his volume drifts): -11.0% n223; fixed rule -9.6% n1,716, every fold -8..-11.
    Hard Rock moves the price instead of the line, and does it well.
  - Forward re-score (score_fwd.py, 8 nights Oct 19-26; clone unshallowed first so Q2 lineup events count): Q1a (Hard Rock >= consensus
    fair) +8.8% n269 [-1,+19] p .07; Q1b (EV >= 1%) +12.7% n192 p .024; Q1c (EV >= 2%) +15.6% n140 [+4,+27] p .022; Q1k Pinnacle +9.2%
    n206; Q1m +25.1% n29; mean CLV ~= EV. Q6a (1 PM) +16.5% n65, Q6b (B/C) +3.3% n51, Q6c (unders) +17.4% n94. Q8a-c n6/n4/n22, Q9a-c
    n10/n5/n2 (1-2 nights). Q2a/b 0 bets. Q10 returners' overs (new, all shadow nights Oct 12-26): +20.3% n26, p .14. All too small
    (bar n >= 300 and p < .0020).
  15 variants (~0.75 false positives expected); all-time historical 366; forward 25. Lockbox looks: 2 (unchanged; next needs p < 0.0167).
  **Verdict: nothing passed; no candidate for the Sharp.** Team shot form, shooting-accuracy luck, ice-time volatility and stuck lines are
  all inside Hard Rock's price. History with free data stays exhausted (366 variants); the live Q1 gap (Hard Rock at or above the other
  books' fair price) is still the only lead and is trending the right way (Q1c p .022 at n140), but needs ~2 more weeks for n 300.
  Next: (1) Q1c run to n >= 300 (about Nov 10 at this pace) and check CLV stays ~EV; (2) Q10 forward, ~2 bets per night (slow, judge by
  season end); (3) a forward test of Q1c split by goalie status at read time (both goalies confirmed vs not), registered before looking.
- 2026-10-26 ~8:10 AM ET (Researcher run 11, daily; SHOTS ON GOAL ONLY). No key used, no historical odds pull. Y1-Y4 + forward Q9a-c registered
  and pushed (55727c6) before any test ran. Free NHL stats REST skater logs fetched to scratch (r11/fetch11.py; Feb 28 cut-off, lockbox not
  fetched). Script research/code/r11/y11.py, output y11_results.txt. 10,413 graded Nov-Feb lines.
  - Y1 opponent's missing regulars (D and F who usually play but sat the opponent's last game): best T=.02 -6.7% n149; OVER vs an opponent
    missing 20+ min of D -3.0% n2,025 [-6.3,+0.7], p .92. Hard Rock prices short-handed opponents.
  - Y2 schedule-strength-adjusted form (recent raw shots deflated by tough defenses): -11.6% n230; weight ~0.
  - Y3 first Hard Rock postings (call-ups/new names the book has least attention on): -9.9% n209; UNDER on first lines -16.1% n93.
  - Y4 line-specific calibration (is the fair too steep at the tails of 1.5/2.5/3.5?): -8.0% n145; tails a touch extreme, far below the hold.
  - Forward re-score (score_fwd.py, 7 nights Oct 19-25): Q1a (Hard Rock >= consensus fair) +7.3% n252 [-2,+17] p .10; Q1b (EV >= 1%)
    +10.8% n180 p .048; Q1c (EV >= 2%) +15.9% n132 [+3,+28] p .03; Q1k Pinnacle +8.0% n192; Q1m +23.4% n28; mean CLV ~= EV. Q6a (1 PM)
    +10.0% n60, Q6b (B/C) +2.4% n39, Q6c (unders) +12.7% n78. Q8a-c n3/n2/n10 (1 night). Q9a-c start tonight. Q2a/b 0 bets.
    All too small (bar n >= 300 and p < .0021-.0033).
  14 variants (~0.7 false positives expected); all-time historical 351; forward 24. Lockbox looks: 2 (unchanged; next needs p < 0.0167).
  **Verdict: nothing passed; no candidate for the Sharp.** Opponent injuries, schedule-adjusted form, new-name attention and tail calibration
  are all inside Hard Rock's price. Main-line shots history with free data is exhausted 351 variants deep; the live Q1 gap is the only lead.
  Next: (1) Q9a-c forward from tonight (`python3 -I research/code/r11/score_q9.py .` after score_fwd.py); (2) Q7 returners' overs forward
  (missed-games field per live shadow line from NHL boxscores; register a start date); (3) Q1c by read time vs news (goalie confirmation
  window), registered forward before looking.
- 2026-10-25 ~8:05 AM ET (Researcher run 10, daily; SHOTS ON GOAL ONLY). No key used, no historical odds pull. X1-X3 + forward Q8a-c registered
  and pushed (8077cba) before any test ran. Free NHL stats REST skater logs fetched to scratch (r10/fetch10.py; Feb 28 cut-off, lockbox not
  fetched). Script research/code/r10/x10.py, output x10_results.txt. 10,405 graded Nov-Feb lines.
  - X1 book chasing its own number (Hard Rock moves a player's number after a big/small game): best T=.02 +2.1% n96 [-13.9,+18.2], T=.01
    -6.2% n199; fade-the-raise rule -1.9% n99. Hard Rock's moves overshoot a hair (small stable negative weight), not enough to beat the hold.
  - X2 public nights (Saturday/Fri/Sun): -8.2% n732; Saturday UNDERS -9.9% n2,588, every fold negative. No weekend shading.
  - X3 prior-season anchor (book over-trusting the new season early): -15.5% n163; weight small and stable, far below the hold.
  - Forward re-score (score_fwd.py, 6 nights Oct 19-24): Q1a (Hard Rock >= consensus fair) +7.3% n237 [-2,+18] p .12; Q1c (EV >= 2%)
    +13.4% n124 [+0,+26] p .048; Q1k Pinnacle +5.4% n178; Q1m gap lookalike +23.4% n28; mean CLV ~= EV. Q6a (1 PM read) +8.2% n55,
    Q6b (B/C) +5.3% n29, Q6c (unders) +15.1% n68. Q2a/b 0 bets. Q8a-c (Q1a by book count) start tonight. All too small (n >= 300, p < .0024).
  11 variants (~0.55 false positives expected); all-time historical 337; forward 21. Lockbox looks: 2 (unchanged; next needs p < 0.0167).
  **Verdict: nothing passed; no candidate for the Sharp.** Hard Rock's own line moves, weekend public money and last-season anchoring are
  all inside its price. The live Hard Rock-vs-consensus test (Q1) stays the only lead; it is positive 6 nights in but far from the bar.
  Next: (1) Q8a-c forward from tonight (`python3 -I research/code/r10/score_q8.py .` after score_fwd.py); (2) Q7 returners' overs forward
  (needs a missed-games field per live shadow line, derived in research code from NHL boxscores; register a start date first); (3) a
  forward Q1 split by line (1.5 vs 2.5 vs 3.5, 3.5 live since Oct 23), registered before looking.
- 2026-10-23 ~8:04 AM ET (Researcher run 9, daily; SHOTS ON GOAL ONLY). No key used, no historical odds pull. W1-W5 + forward Q6a-c registered
  and pushed (fa577da) before any test ran. Free NHL stats REST logs fetched to scratch (r9/fetch9.py: team summary, skater summary, team
  powerplay, skater timeonice + realtime; Feb 28 cut-off, lockbox not fetched). Script research/code/r9/w9.py, output w9_results.txt.
  10,405 graded Nov-Feb lines.
  - W1 penalty environment x PP role (PP specialists vs opponents that take lots of penalties): -3.4% n301 [-11.4,+4.4] best; weight ~0.
  - W2 hot shooter (goal streaks / shooting luck; public chases goals): -13.1% n190; UNDER after 3+ goals in 3 games -4.8% n714. No shading.
  - W3 new to the league (374 rookie lines): -3.5% n128 to -9.6% n419. Hard Rock prices rookies as well as vets.
  - W4 rematch (same opponent within 3 days, anchoring to the last game): -15.1% n240; fixed rule -21.3% n21.
  - W5 frozen stack of earlier small stable weights (skew/hold, division, attempts): beats the book's log loss every month Dec-Feb (a real
    calibration fix) but bets still lose: -4.6% n615 [-10.8,+1.2], folds -11.0/-6.4/-7.8/+18.7.
  - Forward re-score (score_fwd.py, nights Oct 19-22): Q1a (Hard Rock >= consensus fair) +7.4% n153 [-5,+20] p .16; Q1f (4+ books) +9.1%
    n121; Q1k Pinnacle +11.8% n118 [-2,+27] p .08; mean CLV ~= EV. Q2a/b 0 bets. Q6a-c 0 bets (start tonight). Too small (n >= 300, p < .0033).
  17 variants (~0.85 false positives expected); all-time historical 326; forward 18. Lockbox looks: 2 (unchanged; next needs p < 0.0167).
  **Verdict: nothing passed; no candidate for the Sharp.** Penalty/PP environment, hot hands, rookies, rematches and a stack of every small
  stable weight seen so far are all inside Hard Rock's price; the stack improves calibration but not by the ~3.5 pts per side of hold.
  Next: (1) Q6a-c forward from tonight (A-read vs B/C, unders) via `python3 -I research/code/r9/score_q6.py .` after score_fwd.py;
  (2) Q7 returners' overs forward (derive missed games per live shadow line from NHL boxscores in research code, register a start date);
  (3) live-only idea: does Q1a's edge concentrate in lines where only Hard Rock and 1-3 books post (thin market) vs 6+ books? register
  as a forward split before looking at results by book count.
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
