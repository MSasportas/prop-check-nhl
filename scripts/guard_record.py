#!/usr/bin/env python3
"""guard_record.py: the Record guard. Run before every commit and around every pull.

The Record (data/record/events.jsonl) is append-only: lines may only be added at the end, never changed,
removed or reordered. Exit 1 (and print why) on any breach, so the cycle stops before pushing.

    python scripts/guard_record.py
        the committed (HEAD) Record must be an exact prefix of the working file.
    python scripts/guard_record.py --history [--origin REF]
        every committed version of the Record, oldest first (`git log --reverse -- data/record/events.jsonl`),
        must be a byte-exact prefix of the next one, and the working file must extend the last. This catches
        an edited Record that is already committed (for example pushed to GitHub from outside the timer).
        --origin REF (e.g. origin/main): the Record this checkout last saw at REF must still be a prefix of
        the working file, which catches a force-pushed history that is consistent with itself (within one
        runner's life; a fresh checkout has seen nothing yet). Then REF's Record is remembered.
        Needs full history: a shallow clone FAILS rather than passing on a partial walk.
    python scripts/guard_record.py --remember REF
        after a push: remember REF's Record as the newest one seen on origin (for --origin above).
    python scripts/guard_record.py --old FILE --new FILE     (tests)

One exception, a customer-ordered reset (TEAM.md section 5): a pair (old, new) that fails the prefix rule is
accepted only if new is an empty file and data/record/resets.json (read from the NEWER side) has an entry whose
sha256 equals sha256(old) and whose archive file (under archive/, read from the same side) is byte-identical to old.
resets.json is append-only itself, and every archive it names must still match its sha256 in the working tree.

"File absent from HEAD" passes only when git says the path is truly not in HEAD; any other git error fails.
Speed: the last verified version is remembered in .git/pc_record_verified (never committed), so later checks
in the same checkout only walk the versions added since.
"""
import hashlib
import json
import os
import subprocess
import sys

REL = "data/record/events.jsonl"
RESETS = "data/record/resets.json"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class GitError(Exception):
    pass


def check(old, new):
    """old, new: bytes. Returns None if fine, else a reason."""
    if not new.startswith(old):
        n_old, n_new = old.count(b"\n"), new.count(b"\n")
        if n_new < n_old:
            return "the Record lost lines (%d committed, %d now)" % (n_old, n_new)
        return "a committed Record line was changed"
    if old and not old.endswith(b"\n") and len(new) > len(old):
        return "the committed Record did not end with a newline"
    if new and not new.endswith(b"\n"):
        return "the Record does not end with a newline"
    return None


def git(root, *args):
    r = subprocess.run(["git"] + list(args), cwd=root, capture_output=True)
    if r.returncode != 0:
        raise GitError("git %s failed: %s" % (" ".join(args[:2]), r.stderr.decode("utf-8", "replace").strip()[:200]))
    return r.stdout


def committed(root, rev):
    """The Record's bytes at `rev`, or None when the path is truly absent there (or HEAD has no commit yet:
    a brand-new repository). Any other problem raises."""
    if rev == "HEAD" and _unborn(root):
        return None
    git(root, "rev-parse", "--verify", "--quiet", rev + "^{commit}")          # an unknown revision is an error
    listed = git(root, "ls-tree", "--name-only", rev, "--", REL).decode("utf-8", "replace").strip()
    if not listed:
        return None
    return git(root, "cat-file", "blob", "%s:%s" % (rev, REL))


def _unborn(root):
    """True only for a repository whose current branch has no commit yet."""
    r = subprocess.run(["git", "symbolic-ref", "-q", "HEAD"], cwd=root, capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip():
        return False                                            # detached HEAD (or not a repo): not "unborn"
    ref = r.stdout.strip()
    git(root, "rev-parse", "--git-dir")                         # not a repository at all: raise
    # rev-parse finds a ref even when it points at a missing object (that is damage, caught later), so only a
    # ref that does not exist at all counts as unborn
    return subprocess.run(["git", "rev-parse", "-q", "--verify", ref], cwd=root, capture_output=True).returncode != 0


# ---------------------------------------------------------------- customer-ordered resets
def _entries(raw):
    """resets.json bytes -> list of dict entries, or None when absent/unreadable."""
    if raw is None:
        return None
    try:
        v = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    return v if isinstance(v, list) and all(isinstance(e, dict) for e in v) else None


def _archive_ok(e, reader):
    """The archive bytes an entry names (read from the same side), or None unless they match the entry's sha256."""
    path = e.get("archive")
    if not isinstance(path, str) or not path.startswith("archive/") or ".." in path.split("/") or path.startswith("/"):
        return None
    data = reader(path)
    if data is None or hashlib.sha256(data).hexdigest() != e.get("sha256"):
        return None
    if e.get("lines") != data.count(b"\n"):
        return None
    return data


def reset_accepts(old, new, reader):
    """True when (old -> new) is a recorded reset: new is empty and a reset entry (from the newer side) names an
    archive byte-identical to old."""
    if new != b"":
        return False
    ents = _entries(reader(RESETS))
    if not ents:
        return False
    sha = hashlib.sha256(old).hexdigest()
    return any(e.get("sha256") == sha and _archive_ok(e, reader) == old for e in ents)


def seen_after_reset(seen_n, seen_sha, reader):
    """True when what this runner last saw on origin is a prefix of an archived (reset) Record."""
    for e in _entries(reader(RESETS)) or []:
        arch = _archive_ok(e, reader)
        if arch is not None and len(arch) >= seen_n and hashlib.sha256(arch[:seen_n]).hexdigest() == seen_sha:
            return True
    return False


def pair_check(old, new, reader, present=True):
    """check(), except a recorded reset is fine."""
    why = check(old, new)
    if why and present and reset_accepts(old, new, reader):
        return None
    return why


def resets_prefix(old_raw, new_raw):
    """resets.json is append-only: returns a reason or None."""
    if old_raw is None:
        return None
    o, n = _entries(old_raw), _entries(new_raw)
    if o is None:
        return None if not old_raw.strip() else "resets.json was unreadable and was replaced"
    if n is None or n[:len(o)] != o:
        return "resets.json lost or changed an entry"
    return None


def archives_intact(raw, reader):
    for e in _entries(raw) or []:
        if _archive_ok(e, reader) is None:
            return "the archived Record %s is missing or was changed" % (e.get("archive"),)
    return None


def work_reader(root):
    def read(rel):
        try:
            with open(os.path.join(root, rel), "rb") as f:
                return f.read()
        except OSError:
            return None
    return read


def commit_reader(root, rev):
    def read(rel):
        if not git(root, "ls-tree", "--name-only", rev, "--", rel).strip():
            return None
        return git(root, "cat-file", "blob", "%s:%s" % (rev, rel))
    return read


def resets_state(root):
    """Working resets.json vs HEAD: append-only, and every archive it names intact. Returns a reason or None."""
    rd = work_reader(root)
    work = rd(RESETS)
    head = None if _unborn(root) else commit_reader(root, "HEAD")(RESETS)
    if head is not None and work is None:
        return "resets.json is gone"
    return resets_prefix(head, work) or archives_intact(work, rd)


def working(root):
    try:
        with open(os.path.join(root, REL), "rb") as f:
            return f.read()
    except FileNotFoundError:
        return None


def head_check(root):
    old = committed(root, "HEAD")
    new = working(root)
    if old is not None and new is None:
        return "the Record file is gone", 0, 0
    old, new = old or b"", new or b""
    why = pair_check(old, new, work_reader(root)) or resets_state(root)
    return why, old.count(b"\n"), new.count(b"\n")


def _cache_path(root):
    try:
        gd = git(root, "rev-parse", "--git-dir").decode().strip()
    except GitError:
        return None
    return os.path.join(root, gd, "pc_record_verified")


def _blobs(root, specs):
    """Read many blobs in one git process. specs: list of 'rev:path'. Yields bytes (None = path absent) in order."""
    if not specs:
        return
    p = subprocess.Popen(["git", "cat-file", "--batch"], cwd=root, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    try:
        for s in specs:
            p.stdin.write((s + "\n").encode())
            p.stdin.flush()
            head = p.stdout.readline().decode("utf-8", "replace").split()
            if len(head) == 2 and head[1] == "missing":
                # "missing" means either the path is not in that commit (deleted) or the object is damaged.
                # Only the first is acceptable: confirm with ls-tree, and fail if the path is listed.
                rev, _, path = s.partition(":")
                if git(root, "ls-tree", rev, "--", path).strip():
                    raise GitError("could not read %s (object damaged)" % s)
                yield None
                continue
            if len(head) != 3 or head[1] != "blob":
                raise GitError("could not read %s (%s)" % (s, " ".join(head)))
            size = int(head[2])
            data = p.stdout.read(size)
            p.stdout.read(1)                                    # the newline after each object
            yield data
    finally:
        p.stdin.close()
        p.wait()


def _load_cache(path):
    try:
        with open(path) as f:
            c = json.load(f)
        return c if isinstance(c, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def history_check(root, origin=None):
    """Returns (reason or None, versions walked).
    origin: a ref such as origin/main. The Record this checkout last saw there (length + sha256, kept in the
    cache) must still be a prefix of the working file: origin's history may have been rewritten (force push)
    into one that is consistent with itself. After a clean check, origin's current Record is remembered."""
    if git(root, "rev-parse", "--is-shallow-repository").decode().strip() == "true":
        return "the clone is shallow, so the Record's history cannot be checked (fetch full history)", 0
    commits = [] if _unborn(root) else git(root, "log", "--reverse", "--format=%H", "HEAD", "--", REL).decode().split()
    cache = _cache_path(root)
    c = _load_cache(cache) if cache else {}
    start = commits.index(c["commit"]) if c.get("commit") in commits else 0   # walked before, in HEAD's history
    # a commit that deleted the file is in the log too: it reads as empty, so deleting a non-empty Record
    # fails ("lost lines") and nothing can sneak back in after it
    walk, prev = commits[start:], None
    for h, cur in zip(walk, _blobs(root, ["%s:%s" % (h, REL) for h in walk])):
        cur_present = cur is not None
        cur = cur if cur is not None else b""
        if prev is not None:
            why = pair_check(prev[1], cur, commit_reader(root, h), present=cur_present)
            if why:
                return "%s in commit %s (after %s)" % (why, h[:10], prev[0][:10]), len(walk)
        prev = (h, cur)
    head = committed(root, "HEAD")
    new = working(root)
    if new is None and head:
        return "the Record file is gone", len(walk)
    new = new or b""
    why = pair_check(head or b"", new, work_reader(root))
    if why:
        return why + " (working file vs HEAD)", len(walk)
    why = _resets_history(root)
    if why:
        return why, len(walk)
    seen_n, seen_sha = c.get("seen_len"), c.get("seen_sha")
    if isinstance(seen_n, int) and seen_sha:
        if (len(new) < seen_n or hashlib.sha256(new[:seen_n]).hexdigest() != seen_sha) \
                and not seen_after_reset(seen_n, seen_sha, work_reader(root)):
            return "the Record this runner last saw on origin is no longer a prefix of it (history was rewritten)", \
                len(walk)
    if cache:
        out = {"commit": commits[-1] if commits else None, "seen_len": seen_n, "seen_sha": seen_sha}
        if origin:
            seen = committed(root, origin)
            if seen is not None:
                out.update(seen_len=len(seen), seen_sha=hashlib.sha256(seen).hexdigest())
        try:
            with open(cache, "w") as f:
                json.dump(out, f)
        except OSError:
            pass
    return None, len(walk)


def _resets_history(root):
    """Every committed version of resets.json must extend the one before, and the working file the last; the
    archives it names must be intact in the working tree."""
    commits = [] if _unborn(root) else git(root, "log", "--reverse", "--format=%H", "HEAD", "--", RESETS).decode().split()
    prev = None
    for h, cur in zip(commits, _blobs(root, ["%s:%s" % (h, RESETS) for h in commits])):
        if prev is not None:
            if cur is None:
                return "resets.json was deleted in commit %s" % h[:10]
            why = resets_prefix(prev, cur)
            if why:
                return "%s in commit %s" % (why, h[:10])
        if cur is not None:
            prev = cur
    return resets_state(root)


def remember(root, ref):
    """After a push: remember the Record now at `ref` as the newest one this checkout has seen on origin."""
    cache = _cache_path(root)
    seen = committed(root, ref)
    if cache is None or seen is None:
        return
    c = _load_cache(cache)
    c.update(seen_len=len(seen), seen_sha=hashlib.sha256(seen).hexdigest())
    with open(cache, "w") as f:
        json.dump(c, f)


def main(argv, root=ROOT):
    try:
        if "--remember" in argv:
            i = argv.index("--remember")
            remember(root, argv[i + 1] if i + 1 < len(argv) else "HEAD")
            return 0
        if "--old" in argv and "--new" in argv:
            old = open(argv[argv.index("--old") + 1], "rb").read()
            new = open(argv[argv.index("--new") + 1], "rb").read()
            why, n_old, n_new = check(old, new), old.count(b"\n"), new.count(b"\n")
        elif "--history" in argv:
            i = argv.index("--origin") if "--origin" in argv else -1
            why, n = history_check(root, argv[i + 1] if 0 <= i < len(argv) - 1 else None)
            if why:
                print("RECORD HISTORY: FAILED: %s. Nothing will be pushed." % why)
                return 1
            print("RECORD HISTORY: ok (%d version(s) walked)" % n)
            return 0
        else:
            why, n_old, n_new = head_check(root)
    except GitError as e:
        print("RECORD GUARD: FAILED: %s. Nothing will be pushed." % e)
        return 1
    if why:
        print("RECORD GUARD: FAILED: %s. Nothing will be pushed." % why)
        return 1
    print("RECORD GUARD: ok (%d lines committed, %d now)" % (n_old, n_new))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
