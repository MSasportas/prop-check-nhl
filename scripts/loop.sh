#!/usr/bin/env bash
# loop.sh: runs scripts/cycle.sh again and again for about LOOP_SECONDS (default 3000 = 50 minutes), then exits
# so the workflow can hand over to the next run. One failed cycle never ends the loop.
#
# Cadence (Eastern): every 10 minutes on the :00 :10 :20 ... marks from 8:00 AM to 3:00 AM, every 30 minutes
# (:00 / :30) from 3:00 AM to 8:00 AM. The loop stops early when the code on origin changed, so the next run
# picks up the new scripts / config / workflow, or when the file config/stop_timer exists (the off switch).
#
# Exports for run.py's status.json "runner" block: PC_RUNNER_EVENT, PC_RUNNER_RUN_ID, PC_RUNNER_LINK,
# PC_RUNNER_CHAIN_STARTED, PC_RUNNER_RUN_STARTED, PC_RUNNER_ITERATION.
# Tests: LOOP_MAX_ITER (stop after N cycles), LOOP_SLEEP (fixed seconds instead of the cadence),
#        `loop.sh --next-sleep HH:MM:SS` prints the cadence sleep for an Eastern clock time.
set -u
cd "$(dirname "$0")/.."

next_sleep() {   # $1 = Eastern clock "HH:MM:SS" -> seconds to the next mark
  local h m s now step
  IFS=: read -r h m s <<< "$1"
  h=$((10#$h)); m=$((10#$m)); s=$((10#$s))
  now=$((h * 3600 + m * 60 + s))
  if [ $h -ge 3 ] && [ $h -lt 8 ]; then step=1800; else step=600; fi
  echo $(( (now / step + 1) * step - now ))
}

if [ "${1:-}" = "--next-sleep" ]; then next_sleep "$2"; exit 0; fi

BRANCH="${GITHUB_REF_NAME:-main}"
LOOP_SECONDS="${LOOP_SECONDS:-3000}"
START=$(date +%s)
export PC_RUNNER_RUN_STARTED="$(TZ=America/New_York date '+%Y-%m-%dT%H:%M:%S%:z')"
export PC_RUNNER_CHAIN_STARTED="${PC_RUNNER_CHAIN_STARTED:-$PC_RUNNER_RUN_STARTED}"
# hand the chain's start time to the workflow's next step (dispatch_next.sh) when running on GitHub
[ -n "${GITHUB_ENV:-}" ] && echo "PC_CHAIN_STARTED_FINAL=$PC_RUNNER_CHAIN_STARTED" >> "$GITHUB_ENV"
code_id() { git rev-parse "origin/$BRANCH:scripts" "origin/$BRANCH:config" "origin/$BRANCH:.github" 2>/dev/null | tr '\n' ' '; }
git fetch -q origin "$BRANCH" 2>/dev/null
CODE="$(code_id)"

if git cat-file -e "origin/$BRANCH:config/stop_timer" 2>/dev/null; then echo "=== config/stop_timer is set: no cycles"; exit 0; fi

i=0
while :; do
  i=$((i + 1))
  export PC_RUNNER_ITERATION=$i
  echo "=== cycle $i (run ${PC_RUNNER_RUN_ID:-local}, link ${PC_RUNNER_LINK:-?})"
  bash scripts/cycle.sh || echo "=== cycle $i failed; the loop carries on"
  if [ -n "${LOOP_MAX_ITER:-}" ] && [ $i -ge "$LOOP_MAX_ITER" ]; then echo "=== stop: $i cycles done"; break; fi
  if git cat-file -e "origin/$BRANCH:config/stop_timer" 2>/dev/null; then echo "=== stop: config/stop_timer is set"; break; fi
  if [ "$(code_id)" != "$CODE" ]; then echo "=== stop: new code on $BRANCH, handing over to a fresh run"; break; fi
  if [ -n "${LOOP_SLEEP:-}" ]; then wait_s=$LOOP_SLEEP; else wait_s=$(next_sleep "$(TZ=America/New_York date +%H:%M:%S)"); fi
  if [ $(( $(date +%s) + wait_s - START )) -gt "$LOOP_SECONDS" ]; then echo "=== stop: time is up, handing over"; break; fi
  echo "=== sleeping ${wait_s}s"
  sleep "$wait_s"
done
exit 0
