# RESEARCH.md: the Researcher's job and rules

Read TEAM.md first (sections 4, 7 items 17-20), then this file, then research/HYPOTHESES.md and research/LOG.md.
Update HYPOTHESES.md and LOG.md last, then add one line to TEAM.md section 9.

## The job
**Scope (Matt, 2026-10-19: SHOTS ON GOAL ONLY; 2026-10-28: PLAYER POINTS ADDED, saves dropped, see TEAM.md item 28).** Shots stays the live market; points is research-only and gets the same daily run on the forward data in `data/paper_watch/points/`, `data/shadow/` (market points) and `data/odds/`. Original scope text follows. **SHOTS ON GOAL ONLY.** Find the edge in Hard Rock shots on goal props (main lines, over
and under). Do not test other markets. Try different IDEAS (models, features, player types, timing, structure, price
selection) on the saved historical shots data and the live shadow log. No new historical pulls (191 credits left; ask
the CEO only if an idea truly needs one).
Find a rule that beats Hard Rock (Florida) at its posted prices, in a market Matt can bet: player props first
(shots, saves, points, assists, PP points, goals, alt lines), sides and totals allowed. No leg worse than -200.
Every run: come up with NEW ideas (models, features, markets, timing, de-vig, structure), test them honestly,
and report. Don't re-run ideas already in HYPOTHESES.md unless the change is stated and counted as a new variant.
The aim is ROI, but a false edge costs Matt real money: the bar below never moves to make a deadline.

## Data (nothing here may be paid for twice)
- **Historical Hard Rock odds 2025-26** (bought 2026-10-19): `research/data/hist_2025-26_hardrock.tgz` in this repo
  (Matt's choice: everything in one repo). `tar -xzf` it into a scratch folder, never into the repo. Contents:
  `raw/odds/` (every API response: events lists + shots at -45 min for all 1,311 games, saves -45 for 233 games,
  shots 1 PM for 144 games), `raw/research/` (alt-shot ladders at -45 for 97 games; multi-market/multi-book probes),
  `work/` (`shots45_lines.jsonl` 18,383 lines with prices, results and the production model's prior-only p_over;
  `shots45_feat.jsonl` same plus features; `saves45_lines.jsonl`; `shots13_lines.jsonl`), `code/` (pull, build,
  walk-forward, lockbox, placebo scripts), `research/` (derived features), ledgers, `PLAN.md`, `results.md`.
  Add new historical pulls as a NEW tgz in research/data/ (never rewrite an old one). Never commit any key.
- **Live 2026-27**: `data/odds/` (every Hard Rock read), `data/shadow/` (every line, open/close, model p, context,
  results), `data/state/lineup_history/`. This is the forward test that no history can replace.
- **Free**: NHL APIs (api-web.nhle.com, api.nhle.com/stats/rest), MoneyPuck downloads (non-commercial, credit them).
- **More historical odds** need a key Matt holds; it is not in GitHub secrets. Ask the CEO (a chat) for pulls.
  Prices: 10 credits per market per game snapshot (props); featured markets (h2h/totals/spreads) 10 per market per
  snapshot for ALL games at once.

## Rules (contamination = failure)
1. **Register first.** Before testing, add the hypothesis to HYPOTHESES.md (id, exact rule, data, metric) and commit.
2. **No leakage.** Every input to a projection comes from data dated strictly before the game. No closing price,
   result, later stat, or lineup not known at bet time. Prices: bet at the snapshot price you would have had.
3. **Walk-forward.** Fit on months up to m, score m+1, rolling (Nov 2025 -> Feb 2026). Report every fold.
4. **Lockbox** = games Mar 1 - Apr 2026. Only a FROZEN candidate that is positive walk-forward with n >= 300 may
   look, once. Each look is logged (LOG.md, count). Looks so far: 2 (2026-10-19 v2+B2B +2.4% noise; 2026-10-21 LB2 T5 movers -7.5%, p 0.85).
   Pass on the lockbox needs one-sided p < 0.05 / (number of lockbox looks so far, including this one).
5. **Count everything.** Every variant tried counts. Report expected false positives and a shuffle placebo.
6. **Grading** like the Record: 1u flat at the posted price; regulation + OT; no ice time = void; tie = push.
   Clustered (by game) bootstrap intervals.
7. **No product changes.** You never edit scripts/, config/, index.html or data/. You write research/ only.

## Promotion (who decides)
A candidate that passes walk-forward AND the lockbox goes to the Sharp with: rule, n, ROI, CI, folds, placebo,
lockbox p. The Sharp may put it live (CEO ships through Builder + QA) with kill gates on the live Record and the
shadow log (kill at ROI <= -5% after 300 forward bets or open-to-close movement against us at t <= -2).
Untestable-in-history ideas (e.g. reacting to lineup or goalie news before Hard Rock moves) are registered and
judged forward on the shadow log only.

## Report (end of every run, LOG.md entry, newest first)
Date/time, ideas tested (ids), best result per idea with n/ROI/CI, lockbox looks used, verdict, and the next
3 ideas queued. One line per idea; plain words.
