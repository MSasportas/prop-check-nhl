"""The customer-ordered Record reset (TEAM.md section 5): guard_record accepts a reset only when the old Record is
preserved byte-exact under archive/ and named in data/record/resets.json. Real temp git repos, full history."""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

import helpers
import guard_record as G

REPO = os.path.dirname(helpers.SCRIPTS)
A = b'{"at":"t1","id":"a","t":"shown"}\n'
B = b'{"at":"t2","id":"a","t":"locked"}\n'
C = b'{"at":"t3","id":"n","t":"shown"}\n'
EV, RS, ARC = "data/record/events.jsonl", "data/record/resets.json", "archive/record_x/events.jsonl"


def entry(old, archive=ARC):
    return {"at": "2026-10-19", "ordered_by": "Matt", "archive": archive,
            "sha256": hashlib.sha256(old).hexdigest(), "lines": old.count(b"\n")}


class Repo:
    def __init__(self, test, bare=False):
        self.d = tempfile.mkdtemp(prefix="pc_reset_")
        test.addCleanup(shutil.rmtree, self.d, True)
        self.git("init", "-q", "-b", "main")
        os.makedirs(os.path.join(self.d, "scripts"))
        shutil.copy(os.path.join(helpers.SCRIPTS, "guard_record.py"), os.path.join(self.d, "scripts"))

    def git(self, *a, cwd=None):
        r = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"] + list(a),
                           cwd=cwd or self.d, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        return r.stdout

    def put(self, rel, data):
        p = os.path.join(self.d, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(data if isinstance(data, bytes) else json.dumps(data).encode())

    def commit(self, msg="c"):
        self.git("add", "-A")
        self.git("commit", "-q", "-m", msg)

    def guard(self, *args):
        r = subprocess.run([sys.executable, os.path.join(self.d, "scripts", "guard_record.py")] + list(args),
                           capture_output=True, text=True)
        return r.returncode, r.stdout

    def history(self, *a):
        return self.guard("--history", *a)


def make_reset(repo, old=A + B, ents=None, archive_bytes=None):
    """Commits: A, A+B, then the reset commit."""
    repo.put(EV, A); repo.commit("one")
    repo.put(EV, old); repo.commit("two")
    repo.put(ARC, old if archive_bytes is None else archive_bytes)
    repo.put(RS, [entry(old)] if ents is None else ents)
    repo.put(EV, b"")
    repo.commit("reset")


class PairUnit(unittest.TestCase):
    def test_pair_check(self):
        files = {RS: json.dumps([entry(A + B)]).encode(), ARC: A + B}
        rd = files.get
        self.assertIsNone(G.pair_check(A + B, b"", rd))
        self.assertIn("lost lines", G.pair_check(A + B, b"", {}.get))
        self.assertIsNotNone(G.pair_check(A + B, B, rd))
        self.assertIsNotNone(G.pair_check(A + B, b"", rd, present=False))        # the file must be present
        self.assertIsNotNone(G.pair_check(A, b"", rd))                           # a different old Record
        for bad in (dict(files, **{ARC: A + C}), {RS: files[RS]},
                    dict(files, **{RS: json.dumps([dict(entry(A + B), archive="elsewhere/x")]).encode()}),
                    dict(files, **{RS: json.dumps([dict(entry(A + B), archive="archive/../x")]).encode(), "archive/../x": A + B}),
                    dict(files, **{RS: b"not json"}),
                    dict(files, **{RS: json.dumps([dict(entry(A + B), lines=1)]).encode()})):
            self.assertIsNotNone(G.pair_check(A + B, b"", bad.get), bad)


class ResetInGit(unittest.TestCase):
    def test_accepted_with_a_matching_archive_and_walk_continues(self):
        r = Repo(self)
        make_reset(r)
        self.assertEqual(r.history()[0], 0, r.history())
        self.assertEqual(r.guard()[0], 0)
        r.put(EV, C)                                           # the Record grows after the reset
        self.assertEqual(r.guard()[0], 0)
        r.commit("after")
        code, out = r.history()
        self.assertEqual(code, 0, out)
        self.assertIn("ok", out)
        r.put(EV, B)                                           # but an edit after the reset is still a breach
        self.assertEqual(r.guard()[0], 1)
        r.git("checkout", "-q", "--", EV)

    def test_working_reset_not_yet_committed(self):
        r = Repo(self)
        r.put(EV, A + B); r.commit()
        r.put(ARC, A + B); r.put(RS, [entry(A + B)]); r.put(EV, b"")
        self.assertEqual(r.guard()[0], 0)                      # HEAD check, reset only in the working tree

    def test_rejections(self):
        cases = {
            "wrong sha": dict(ents=[dict(entry(A + B), sha256="0" * 64)]),
            "archive edited": dict(archive_bytes=A + C),
            "no entry": dict(ents=[]),
            "archive outside archive/": dict(ents=[entry(A + B, "data/x.jsonl")]),
        }
        for name, kw in cases.items():
            with self.subTest(name):
                r = Repo(self)
                make_reset(r, **kw)
                code, out = r.history()
                self.assertEqual(code, 1, out)
                self.assertIn("lost lines", out)

    def test_missing_archive(self):
        r = Repo(self)
        r.put(EV, A + B); r.commit()
        r.put(RS, [entry(A + B)]); r.put(EV, b"")
        r.commit("reset without archive")
        self.assertEqual(r.history()[0], 1)
        self.assertEqual(r.guard()[0], 1)                      # working resets.json names a missing archive

    def test_plain_truncation_is_still_a_breach(self):
        r = Repo(self)
        r.put(EV, A + B); r.commit()
        r.put(EV, b"")
        code, out = r.guard()
        self.assertEqual(code, 1, out)
        r.commit("truncated")
        self.assertEqual(r.history()[0], 1)
        r.put(EV, A + B[:5])
        self.assertEqual(r.guard()[0], 1)

    def test_archive_edited_later_and_resets_not_append_only(self):
        r = Repo(self)
        make_reset(r)
        self.assertEqual(r.history()[0], 0)
        r.put(ARC, A + C)                                      # the archive is rewritten after the fact
        code, out = r.guard()
        self.assertEqual(code, 1, out)
        self.assertIn("archived Record", out)
        self.assertEqual(r.history()[0], 1)
        r.git("checkout", "-q", "--", ARC)
        r.put(RS, [])                                          # an entry dropped
        self.assertEqual(r.guard()[0], 1)
        r.put(RS, [entry(A + B), entry(A + B, ARC)][:1] + [{"at": "x", "archive": ARC, "sha256": "1", "lines": 0}])
        self.assertEqual(r.guard()[0], 1)                      # an appended entry naming nothing real is not fine
        r.git("checkout", "-q", "--", RS)
        self.assertEqual(r.guard()[0], 0)
        os.unlink(os.path.join(r.d, RS))
        self.assertEqual(r.guard()[0], 1)

    def test_second_reset_and_a_dropped_entry(self):
        r = Repo(self)
        make_reset(r)
        r.put(EV, C); r.commit("grows")
        r.put("archive/y.jsonl", C); r.put(RS, [entry(A + B), entry(C, "archive/y.jsonl")]); r.put(EV, b"")
        r.commit("second reset")
        self.assertEqual(r.history()[0], 0, r.history())
        r.put(RS, [entry(C, "archive/y.jsonl")])               # the first entry is dropped and committed
        r.commit("dropped")
        code, out = r.history()
        self.assertEqual(code, 1, out)
        self.assertIn("resets.json", out)


class Remembered(unittest.TestCase):
    def test_cached_verified_version_across_a_reset(self):
        r = Repo(self)
        r.put(EV, A); r.commit("one")
        r.put(EV, A + B); r.commit("two")
        self.assertEqual(r.history()[0], 0)
        cache = os.path.join(r.d, ".git", "pc_record_verified")
        self.assertTrue(os.path.exists(cache))
        c = json.load(open(cache))["commit"]
        r.put(ARC, A + B); r.put(RS, [entry(A + B)]); r.put(EV, b"")
        r.commit("reset")
        self.assertEqual(r.history()[0], 0)
        self.assertNotEqual(json.load(open(cache))["commit"], c)      # the cache moved past the reset
        # and a truncation without a reset after a cached walk is still caught
        r2 = Repo(self)
        r2.put(EV, A + B); r2.commit("two")
        self.assertEqual(r2.history()[0], 0)
        r2.put(EV, b""); r2.commit("truncated")
        self.assertEqual(r2.history()[0], 1)

    def setup_origin(self, test_first=A):
        base = Repo(self)
        base.put(EV, test_first); base.commit("one")
        self.bare = tempfile.mkdtemp(prefix="pc_reset_bare_")
        self.addCleanup(shutil.rmtree, self.bare, True)
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", self.bare], check=True)
        base.git("remote", "add", "origin", self.bare)
        base.git("push", "-q", "origin", "main")
        self.base = base
        self.run_dir = tempfile.mkdtemp(prefix="pc_reset_run_")
        self.addCleanup(shutil.rmtree, self.run_dir, True)
        self.runner = os.path.join(self.run_dir, "runner")
        base.git("clone", "-q", self.bare, self.runner, cwd=self.run_dir)
        self.guard = lambda *a: subprocess.run([sys.executable, os.path.join(self.runner, "scripts", "guard_record.py")]
                                               + list(a), cwd=self.runner, capture_output=True, text=True)

    def pull(self):
        self.base.git("fetch", "-q", "origin", cwd=self.runner)
        self.base.git("reset", "-q", "--hard", "origin/main", cwd=self.runner)

    def test_origin_remembered_record_across_a_reset(self):
        self.setup_origin()
        r = self.guard("--history", "--origin", "origin/main")
        self.assertEqual(r.returncode, 0, r.stdout)                    # this runner has now seen A on origin
        b = self.base
        b.put(EV, A + B); b.commit("two")
        b.put(ARC, A + B); b.put(RS, [entry(A + B)]); b.put(EV, b""); b.commit("reset")
        b.git("push", "-q", "origin", "main")
        self.pull()
        r = self.guard("--history", "--origin", "origin/main")
        self.assertEqual(r.returncode, 0, r.stdout)                    # seen A is a prefix of the archived Record
        self.assertEqual(self.guard("--history", "--origin", "origin/main").returncode, 0)

    def test_origin_force_pushed_truncation_without_a_reset_is_caught(self):
        self.setup_origin()
        self.assertEqual(self.guard("--history", "--origin", "origin/main").returncode, 0)
        b = self.base
        b.git("rm", "-q", EV); b.put(EV, b""); b.commit("truncated (a rewrite: A was seen)")
        b.git("push", "-q", "origin", "main")
        self.pull()
        r = self.guard("--history", "--origin", "origin/main")
        self.assertEqual(r.returncode, 1, r.stdout)

    def test_origin_reset_with_a_wrong_archive_is_caught(self):
        self.setup_origin()
        self.assertEqual(self.guard("--history", "--origin", "origin/main").returncode, 0)
        b = self.base
        b.put(EV, A + B); b.commit("two")
        b.put(ARC, C); b.put(RS, [entry(A + B)]); b.put(EV, b""); b.commit("reset, archive swapped")
        b.git("push", "-q", "origin", "main")
        self.pull()
        self.assertEqual(self.guard("--history", "--origin", "origin/main").returncode, 1)

    def test_shallow_clone_still_fails(self):
        self.setup_origin()
        shallow = os.path.join(self.run_dir, "shallow")
        self.base.git("clone", "-q", "--depth", "1", "file://" + self.bare, shallow, cwd=self.run_dir)
        r = subprocess.run([sys.executable, os.path.join(shallow, "scripts", "guard_record.py"), "--history"],
                           cwd=shallow, capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("shallow", r.stdout)


class TheRealReset(unittest.TestCase):
    """The files this repo actually ships, and an empty Record end to end on a copy of the data."""
    def test_shipped_files_agree(self):
        ents = json.load(open(os.path.join(REPO, RS)))
        self.assertEqual(len(ents), 1)
        e = ents[0]
        arch = open(os.path.join(REPO, e["archive"]), "rb").read()
        self.assertEqual((hashlib.sha256(arch).hexdigest(), arch.count(b"\n")), (e["sha256"], e["lines"]))
        self.assertEqual((e["lines"], e["ordered_by"], e["at"]), (82, "Matt", "2026-10-19"))
        self.assertEqual(os.path.getsize(os.path.join(REPO, EV)), 0)
        self.assertTrue(G.reset_accepts(arch, b"", G.work_reader(REPO)))
        self.assertIsNone(G.resets_state(REPO) if os.path.isdir(os.path.join(REPO, ".git")) else None)

    def test_empty_record_cycle_on_a_copy(self):
        tmp = tempfile.mkdtemp(prefix="pc_reset_data_")
        self.addCleanup(shutil.rmtree, tmp, True)
        data = os.path.join(tmp, "data")
        shutil.copytree(os.path.join(REPO, "data"), data)
        before = {k: open(os.path.join(data, k), "rb").read() for k in ("record.json", "record/events.jsonl", "record/resets.json")}
        w = __import__("world").build(os.path.join(tmp, "world"))
        os.makedirs(w["lineups"], exist_ok=True)
        env = {k: v for k, v in os.environ.items() if k not in helpers.ENV and not k.startswith("PC_")}
        env.update(PC_DATA_DIR=data, PC_NOW="2026-10-11T21:00:00-04:00", PC_NHL_FIXTURE_DIR=w["nhl"],
                   PC_ODDS_FIXTURE_DIR=w["odds"], PC_LINEUP_FIXTURE_DIR=w["lineups"])
        r = subprocess.run([sys.executable, "-I", os.path.join(helpers.SCRIPTS, "run.py")], env=env, capture_output=True,
                           text=True, timeout=300)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        st = json.load(open(os.path.join(data, "status.json")))
        self.assertEqual([s["step"] for s in st["steps"] if s["status"] == "failed"], [])
        for k, v in before.items():
            self.assertEqual(open(os.path.join(data, k), "rb").read(), v, k)       # no pick added, views identical
        rec = json.load(open(os.path.join(data, "record.json")))
        self.assertEqual((rec["summary"]["headline"]["n"], rec["nights"], rec["older"]), (0, [], []))



class PageResetNote(unittest.TestCase):
    def test_resets_array_is_allowed_through_the_page_shape_check(self):
        """resets.json is a JSON array; getJSON() rejects non-objects, so the note line needs the arrOk flag."""
        html = open(os.path.join(REPO, "index.html"), encoding="utf-8").read()
        self.assertIn("function getJSON(path, arrOk)", html)
        self.assertIn("getJSON(BASE + 'record/resets.json', true)", html)

if __name__ == "__main__":
    unittest.main()
