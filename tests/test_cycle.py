"""The timer's shell scripts (cycle.sh, loop.sh, dispatch_next.sh) against a throwaway git repo:
a bare "origin" plays GitHub, a clone plays the runner, a second clone plays someone else pushing.
Everything is offline: the NHL, odds and lineup sources read the made-up league's files."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

import helpers
import test_record_grade
import world

REPO = os.path.dirname(helpers.SCRIPTS)
HAVE = shutil.which("git") and shutil.which("bash") and shutil.which("timeout")


@unittest.skipUnless(HAVE, "needs git, bash and timeout")
class Cycle(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="pc_cycle_")
        self.w = world.build(os.path.join(self.tmp, "world"))
        os.makedirs(self.w["lineups"], exist_ok=True)
        self.origin = os.path.join(self.tmp, "origin.git")
        self.runner = os.path.join(self.tmp, "runner")
        self.other = os.path.join(self.tmp, "other")
        self.git(self.tmp, "init", "-q", "--bare", "-b", "main", self.origin)
        self.git(self.tmp, "clone", "-q", self.origin, self.runner)
        for d in ("scripts", "config"):
            shutil.copytree(os.path.join(REPO, d), os.path.join(self.runner, d),
                            ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copy(os.path.join(REPO, ".gitignore"), self.runner)
        os.makedirs(os.path.join(self.runner, "data", "record"))
        shutil.copytree(os.path.join(self.w["data"], "state"), os.path.join(self.runner, "data", "state"))
        open(os.path.join(self.runner, "data", "record", "events.jsonl"), "w").close()
        with open(os.path.join(self.runner, "README.md"), "w") as f:
            f.write("test\n")
        self.git(self.runner, "checkout", "-q", "-b", "main")
        self.git(self.runner, "add", "-A")
        self.git(self.runner, "commit", "-q", "-m", "init")
        self.git(self.runner, "push", "-q", "origin", "main")
        self.git(self.tmp, "clone", "-q", "-b", "main", self.origin, self.other)
        self.env = {k: v for k, v in os.environ.items() if k not in helpers.ENV and not k.startswith("PC_")}
        self.env.update(PC_NHL_FIXTURE_DIR=self.w["nhl"], PC_ODDS_FIXTURE_DIR=self.w["odds"],
                        PC_LINEUP_FIXTURE_DIR=self.w["lineups"], PC_PYTHON=sys.executable, GITHUB_REF_NAME="main",
                        PC_RUNNER_EVENT="workflow_dispatch", PC_RUNNER_RUN_ID="4242", PC_RUNNER_LINK="7",
                        PC_RUNNER_CHAIN_STARTED="2026-10-11T08:00:00-04:00", PC_RUNNER_ITERATION="1",
                        GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ---- helpers
    def git(self, cwd, *args):
        r = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false",
                            "-c", "init.defaultBranch=main"] + list(args), cwd=cwd, capture_output=True, text=True)
        if r.returncode:
            raise AssertionError("git %s failed: %s" % (" ".join(args), r.stderr))
        return r.stdout

    def script(self, name, now, args=(), **extra):
        env = dict(self.env, PC_NOW="2026-10-11T%s:00-04:00" % now, **extra)
        return subprocess.run(["bash", os.path.join(self.runner, "scripts", name)] + list(args),
                              env=env, capture_output=True, text=True, timeout=300)

    def cycle(self, now, **extra):
        return self.script("cycle.sh", now, **extra)

    def subjects(self):
        return self.git(self.origin, "log", "--format=%s", "main").splitlines()

    def origin_file(self, path):
        r = subprocess.run(["git", "show", "main:" + path], cwd=self.origin, capture_output=True, text=True)
        return r.stdout if r.returncode == 0 else None

    def other_push(self, path, text, msg):
        self.git(self.other, "pull", "-q", "--rebase", "origin", "main")
        full = os.path.join(self.other, path)
        os.makedirs(os.path.dirname(full) or self.other, exist_ok=True)
        with open(full, "w") as f:
            f.write(text)
        self.git(self.other, "add", "-A")
        self.git(self.other, "commit", "-q", "-m", msg)
        self.git(self.other, "push", "-q", "origin", "main")

    def clean(self):
        return self.git(self.runner, "status", "--porcelain", "--untracked-files=all", "data") == ""

    # ---- the cases
    def test_changed_commits_unchanged_does_not(self):
        r = self.cycle("09:00")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(self.subjects()[0].startswith("run: "))
        st = json.loads(self.origin_file("data/status.json"))
        self.assertEqual(st["runner"], {"event": "workflow_dispatch", "run_id": "4242", "iteration": 1, "chain_link": 7,
                                        "chain_started_at": "2026-10-11T08:00:00-04:00", "run_started_at": None})
        n = len(self.subjects())
        r = self.cycle("09:05", PC_RUNNER_ITERATION="2")          # nothing new, heartbeat not due, runner block ignored
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("nothing changed, nothing pushed", r.stdout)
        self.assertEqual(len(self.subjects()), n)
        self.assertTrue(self.clean())
        r = self.cycle("09:21", PC_RUNNER_ITERATION="3")          # heartbeat due: one commit, runner block refreshed
        self.assertEqual(len(self.subjects()), n + 1)
        self.assertEqual(json.loads(self.origin_file("data/status.json"))["runner"]["iteration"], 3)

    def test_edited_record_is_blocked_and_the_failure_is_published(self):
        # a full, already graded pick from an earlier night (so the engine has nothing to do with it)
        ev = test_record_grade.shown("x", slate="2026-10-01", at="2026-10-01T13:02:00-04:00",
                                     start="2026-10-01T19:00:00-04:00")
        gr = {"t": "graded", "id": "x", "at": "2026-10-01T23:00:00-04:00", "result": "W", "actual": 3,
              "actual_text": "had 3", "price": -120, "units": 0.8333}
        lines = os.path.join(self.tmp, "lines.jsonl")
        with open(lines, "w") as f:
            for e in (ev, gr):
                f.write(json.dumps(e, separators=(",", ":"), sort_keys=True) + "\n")
        add = "%s scripts/run.py && cat %s >> data/record/events.jsonl" % (sys.executable, lines)
        r = self.cycle("09:00", CYCLE_RUN_CMD=add)                # appending is fine
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        good = self.origin_file("data/record/events.jsonl")
        self.assertEqual(good.count("\n"), 2)
        edit = "%s scripts/run.py && sed -i 's/had 3/had 2/' data/record/events.jsonl" % sys.executable
        r = self.cycle("09:10", CYCLE_RUN_CMD=edit)
        self.assertEqual(r.returncode, 1)
        self.assertIn("RECORD GUARD: FAILED", r.stdout)
        self.assertEqual(self.subjects()[0], "run failed: record guard")
        self.assertEqual(self.origin_file("data/record/events.jsonl"), good, "the edited Record never reaches origin")
        st = json.loads(self.origin_file("data/status.json"))
        self.assertEqual((st["ok"], st["failed_step"]), (False, "record guard"))
        self.assertEqual(st["runner"]["run_id"], "4242")
        sl = json.loads(self.origin_file("data/slate.json"))
        self.assertTrue(sl["banners"][0]["text"].startswith("The last update failed at 9:10 AM (record guard)."))
        self.assertTrue(self.clean())
        r = self.cycle("09:20")                                   # the next good cycle clears the failure
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(json.loads(self.origin_file("data/status.json"))["ok"])
        self.assertEqual(self.origin_file("data/record/events.jsonl"), good)

    # ---- QA round 2, M1: the Record's history on origin
    def two_good_lines(self):
        ev = test_record_grade.shown("x", slate="2026-10-01", at="2026-10-01T13:02:00-04:00",
                                     start="2026-10-01T19:00:00-04:00")
        gr = {"t": "graded", "id": "x", "at": "2026-10-01T23:00:00-04:00", "result": "W", "actual": 3,
              "actual_text": "had 3", "price": -120, "units": 0.8333}
        lines = os.path.join(self.tmp, "lines.jsonl")
        with open(lines, "w") as f:
            for e in (ev, gr):
                f.write(json.dumps(e, separators=(",", ":"), sort_keys=True) + "\n")
        r = self.cycle("09:00", CYCLE_RUN_CMD="%s scripts/run.py && cat %s >> data/record/events.jsonl"
                       % (sys.executable, lines))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("RECORD HISTORY: ok", r.stdout)
        return self.origin_file("data/record/events.jsonl")

    def outside_edit(self, cwd=None):
        cwd = cwd or self.other
        return ("cd %s && git pull -q --rebase origin main && sed -i 's/had 3/had 2/' data/record/events.jsonl && "
                "git commit -qam 'edited outside the timer' && git push -q origin main" % cwd)

    def test_record_edited_on_origin_stops_the_cycle_and_nothing_is_pushed(self):
        self.two_good_lines()
        subprocess.run(["bash", "-c", self.outside_edit()], env=self.env, check=True, capture_output=True)
        top = self.git(self.origin, "rev-parse", "main")
        r = self.cycle("09:10")
        self.assertEqual(r.returncode, 1)
        self.assertIn("RECORD HISTORY: FAILED: a committed Record line was changed", r.stdout)
        self.assertIn("FAILED at: record history", r.stdout)
        self.assertEqual(self.git(self.origin, "rev-parse", "main"), top, "nothing pushed, not even a failure note")
        r = self.cycle("09:20")                                   # and it stays stopped
        self.assertEqual(r.returncode, 1)
        self.assertEqual(self.git(self.origin, "rev-parse", "main"), top)

    def test_record_edited_on_origin_during_the_run_is_caught_before_the_push(self):
        self.two_good_lines()
        cmd = "%s scripts/run.py && (%s)" % (sys.executable, self.outside_edit())
        r = self.cycle("09:21", CYCLE_RUN_CMD=cmd)                # heartbeat due: the runner has a commit to push
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        out = r.stdout
        self.assertLess(out.index("RECORD HISTORY: ok"), out.index("RECORD HISTORY: FAILED"), out)   # caught at push
        self.assertEqual(self.subjects()[0], "edited outside the timer", "the runner pushed nothing on top")

    def test_force_pushed_rewrite_is_caught_by_the_same_runner(self):
        good = self.two_good_lines()
        # someone rewrites history so it is consistent with itself: the edited lines appear as if first written
        cmd = ("cd %s && git fetch -q origin && git reset -q --hard origin/main~1 && "
               "git show origin/main:data/record/events.jsonl | sed 's/had 3/had 2/' > data/record/events.jsonl && "
               "git add -A && git commit -qm 'rewritten' && git push -q -f origin HEAD:main" % self.other)
        subprocess.run(["bash", "-c", cmd], env=self.env, check=True, capture_output=True)
        self.assertNotEqual(self.origin_file("data/record/events.jsonl"), good)
        top = self.git(self.origin, "rev-parse", "main")
        r = self.cycle("09:10")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("history was rewritten", r.stdout)
        self.assertEqual(self.git(self.origin, "rev-parse", "main"), top)

    def test_workflow_checks_out_full_history(self):
        with open(os.path.join(REPO, ".github", "workflows", "run.yml")) as f:
            wf = f.read()
        self.assertIn("fetch-depth: 0", wf)

    def test_run_crash_and_run_timeout_publish_a_failure(self):
        self.cycle("09:00")
        r = self.cycle("09:10", CYCLE_RUN_CMD="echo half > data/slate.json; exit 3")
        self.assertEqual(r.returncode, 1)
        self.assertEqual(self.subjects()[0], "run failed: run")
        self.assertNotEqual(self.origin_file("data/slate.json").strip(), "half")
        r = self.cycle("09:20", CYCLE_RUN_CMD="sleep 30", CYCLE_RUN_TIMEOUT="2")
        self.assertEqual(r.returncode, 1)
        self.assertIn("did not finish within 2 seconds", r.stdout)
        self.assertEqual(json.loads(self.origin_file("data/status.json"))["failed_step"], "run")

    def test_someone_else_pushed_before_and_during_the_cycle(self):
        self.cycle("09:00")
        self.other_push("README.md", "before\n", "human edit before")
        during = ("%s scripts/run.py && cd %s && printf 'during\\n' > README.md && git add -A && "
                  "git commit -q -m 'human edit during' && git push -q origin main" % (sys.executable, self.other))
        r = self.cycle("09:30", CYCLE_RUN_CMD=during)             # forces the push to rebase first
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.subjects()[:3][1:], ["human edit during", "human edit before"])
        self.assertTrue(self.subjects()[0].startswith("run: "))
        self.assertEqual(self.origin_file("README.md"), "during\n")

    def test_loop_carries_on_after_a_failed_cycle(self):
        counter = os.path.join(self.tmp, "n")
        cmd = ("n=$(cat %s 2>/dev/null || echo 0); n=$((n+1)); echo $n > %s; "
               "if [ $n -eq 2 ]; then exit 1; fi; %s scripts/run.py" % (counter, counter, sys.executable))
        r = self.script("loop.sh", "09:00", LOOP_MAX_ITER="3", LOOP_SLEEP="0", CYCLE_RUN_CMD=cmd)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("=== cycle 2 failed; the loop carries on", r.stdout)
        self.assertIn("=== cycle 3 ", r.stdout)
        self.assertIn("=== stop: 3 cycles done", r.stdout)
        s = self.subjects()
        self.assertEqual(s[1], "run failed: run")
        self.assertTrue(s[0].startswith("run: "), s)               # cycle 3 recovered (status back to ok)
        st = json.loads(self.origin_file("data/status.json"))
        self.assertEqual((st["ok"], st["runner"]["iteration"]), (True, 3))

    def test_loop_stops_for_new_code_and_for_the_off_switch(self):
        cmd = ("%s scripts/run.py && cd %s && git pull -q --rebase origin main && echo '# x' >> scripts/teams.py && "
               "git commit -qam 'code change' && git push -q origin main" % (sys.executable, self.other))
        r = self.script("loop.sh", "09:00", LOOP_MAX_ITER="5", LOOP_SLEEP="0", CYCLE_RUN_CMD=cmd)
        self.assertIn("=== stop: new code on main", r.stdout)
        self.assertNotIn("=== cycle 2", r.stdout)
        self.other_push("config/stop_timer", "off\n", "stop the timer")
        r = self.script("loop.sh", "09:30", LOOP_MAX_ITER="5", LOOP_SLEEP="0")
        self.assertIn("config/stop_timer is set: no cycles", r.stdout)
        self.assertNotIn("=== cycle 1", r.stdout)

    def test_loop_stops_when_time_is_up(self):
        r = self.script("loop.sh", "09:00", LOOP_SECONDS="5", LOOP_SLEEP="10")
        self.assertIn("=== stop: time is up, handing over", r.stdout)
        self.assertNotIn("=== cycle 2", r.stdout)

    def test_cadence(self):
        for clock, want in (("07:23:10", 410), ("08:00:00", 600), ("02:55:00", 300), ("03:00:00", 1800),
                            ("23:59:30", 30), ("12:34:56", 304)):
            r = subprocess.run(["bash", os.path.join(REPO, "scripts", "loop.sh"), "--next-sleep", clock],
                               capture_output=True, text=True)
            self.assertEqual(int(r.stdout), want, clock)

    def test_dispatch_next(self):
        bin_dir = os.path.join(self.tmp, "bin")
        os.makedirs(bin_dir)
        calls = os.path.join(self.tmp, "gh_calls")
        fails = os.path.join(self.tmp, "gh_fail")
        with open(os.path.join(bin_dir, "gh"), "w") as f:     # a fake gh: logs its arguments, fails on request
            f.write("#!/bin/sh\necho \"$@\" >> %s\n[ -f %s ] && exit 1\nexit 0\n" % (calls, fails))
        os.chmod(os.path.join(bin_dir, "gh"), 0o755)
        env = dict(PATH=bin_dir + os.pathsep + self.env["PATH"], DISPATCH_BACKOFF="0", GH_TOKEN="ghs_SECRETTOKEN123")
        r = self.script("dispatch_next.sh", "09:00", **env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        with open(calls) as f:
            self.assertEqual(f.read().strip(), "workflow run run.yml --ref main -f chain_link=8 "
                                               "-f chain_started_at=2026-10-11T08:00:00-04:00")
        self.assertNotIn("SECRET", r.stdout + r.stderr)
        open(fails, "w").close()                                   # GitHub refuses 4 times
        os.unlink(calls)
        r = self.script("dispatch_next.sh", "09:00", **env)
        self.assertEqual(r.returncode, 1)
        with open(calls) as f:
            self.assertEqual(len(f.read().splitlines()), 4)
        self.assertIn("the hourly schedule will restart the chain", r.stdout)
        os.unlink(fails)
        os.unlink(calls)
        self.other_push("config/stop_timer", "off\n", "stop")
        r = self.script("dispatch_next.sh", "09:00", **env)
        self.assertEqual(r.returncode, 0)
        self.assertFalse(os.path.exists(calls), "the off switch means no next run")


if __name__ == "__main__":
    unittest.main()
