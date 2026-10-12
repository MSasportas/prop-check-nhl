#!/usr/bin/env bash
# cycle.sh: ONE timer cycle. The workflow runs it in a loop (scripts/loop.sh); a single manual run is the same code.
#
#   1. sync     bring the checkout up to date with origin (pull --rebase; if that fails, reset to origin)
#   2. run      python scripts/run.py (it decides what is due); killed after CYCLE_RUN_TIMEOUT seconds
#   3. guard    the committed Record must be an exact prefix of the new one
#   4. publish  commit data/ and push, only if something changed (rebase and retry up to 3 times)
# If 2, 3 or 4 fails: throw away everything this cycle produced, write only the failure note
# (scripts/fail_status.py) onto the last good state, push that, and exit 1. The caller carries on.
#
# Never prints a key: the keys exist only in the ODDS_API_KEYS environment variable, which run.py scrubs.
# Settings (environment): GITHUB_REF_NAME (branch, default main), PC_PYTHON (default python3),
# CYCLE_RUN_TIMEOUT (default 420), CYCLE_RUN_CMD (tests only: replaces step 2).
set -u
cd "$(dirname "$0")/.."
BRANCH="${GITHUB_REF_NAME:-main}"
PY="${PC_PYTHON:-python3}"
RUN_TIMEOUT="${CYCLE_RUN_TIMEOUT:-420}"

say() { echo "[cycle $(TZ=America/New_York date '+%-I:%M:%S %p')] $*"; }

git config user.name "prop-check-bot"
git config user.email "bot@users.noreply.github.com"

reset_to_origin() {
  git rebase --abort >/dev/null 2>&1 || true
  git fetch -q origin "$BRANCH" || return 1
  git reset -q --hard "origin/$BRANCH"
  git clean -fdq data
}

fail() {   # $1 = the step that failed
  say "FAILED at: $1. Publishing only the failure note."
  if ! reset_to_origin; then
    say "could not reach origin to publish the failure note"
    return 1
  fi
  "$PY" scripts/fail_status.py "$1"
  git add data/status.json data/slate.json 2>/dev/null
  if ! git diff --cached --quiet; then
    git commit -q -m "run failed: $1"
    for attempt in 1 2 3; do
      if git pull -q --rebase origin "$BRANCH" && git push -q origin "HEAD:$BRANCH"; then
        say "failure note pushed"
        return 1
      fi
      git rebase --abort >/dev/null 2>&1 || true
      sleep $((attempt * 5))
    done
    say "failure note could not be pushed"
  fi
  return 1
}

# 1. sync
if ! git pull -q --rebase origin "$BRANCH"; then
  say "pull --rebase failed; resetting to origin"
  reset_to_origin || { say "origin not reachable; skipping this cycle"; exit 1; }
fi

# 2. run
if [ -n "${CYCLE_RUN_CMD:-}" ]; then
  timeout "$RUN_TIMEOUT" bash -c "$CYCLE_RUN_CMD"
else
  timeout "$RUN_TIMEOUT" "$PY" scripts/run.py
fi
rc=$?
if [ $rc -ne 0 ]; then
  [ $rc -eq 124 ] && say "run.py did not finish within $RUN_TIMEOUT seconds"
  fail "run"; exit 1
fi

# 3. guard
"$PY" scripts/guard_record.py || { fail "record guard"; exit 1; }

# 4. publish
git add -A data
if git diff --cached --quiet; then
  say "nothing changed, nothing pushed"
  exit 0
fi
git commit -q -m "run: $(TZ=America/New_York date '+%Y-%m-%d %-I:%M %p ET')"
for attempt in 1 2 3; do
  if git pull -q --rebase origin "$BRANCH" && git push -q origin "HEAD:$BRANCH"; then
    say "pushed $(git rev-parse --short HEAD)"
    exit 0
  fi
  git rebase --abort >/dev/null 2>&1 || true
  sleep $((attempt * 5))
done
fail "push"; exit 1
