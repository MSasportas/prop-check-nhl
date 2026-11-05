#!/bin/sh
# Re-score EVERY registered forward hypothesis. The daily Researcher run executes this first (RESEARCH.md).
# Add each new forward scorer here when it is registered. Q14 (points) is scored live by the timer's points watch (data/paper_watch/points/summary.json).
# Q17 needs full git history (git fetch --unshallow or a deep fetch) and is skipped with a note if the clone is shallow.
cd "$(dirname "$0")/../../.." || exit 1
set -e
python3 -I research/code/fwd/score_fwd.py "$PWD"          # Q1a-m, Q2a-b
python3 -I research/code/r9/score_q6.py "$PWD"            # Q6a-c
python3 -I research/code/r10/score_q8.py "$PWD"           # Q8a-c
python3 -I research/code/r11/score_q9.py "$PWD"           # Q9a-c
python3 -I research/code/r12/score_q10.py "$PWD"          # Q10
python3 -I research/code/r13/score_q11.py "$PWD"          # Q11a-b
python3 -I research/code/score_q12.py                      # Q12
python3 -I research/code/q19_pin_steam.py --md             # Q19 + Q13
python3 -I research/code/r14/score_q15.py "$PWD"          # Q15a-b
python3 -I research/code/r15/score_q16.py "$PWD"          # Q16a-b
if [ "$(git rev-parse --is-shallow-repository)" = "false" ]; then python3 -I research/code/r17/score_q17.py "$PWD"; else echo "Q17 skipped: shallow clone"; fi
python3 -I research/code/r18/score_q18.py "$PWD"          # Q18a-b
python3 -I research/code/r19/score_q20.py "$PWD"          # Q20a-b
python3 -I research/code/r20/score_q21.py "$PWD"          # Q21a-b
python3 -I research/code/r21/score_q22.py "$PWD"          # Q22a-b
