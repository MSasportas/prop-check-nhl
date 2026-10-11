#!/usr/bin/env python3
"""guard_record.py: the Record guard. Run before every commit.

The committed data/record/events.jsonl must be an exact prefix of the file in the working tree:
lines may only be added at the end, never changed, removed or reordered. Exit 1 (and print why)
otherwise, so the workflow stops before pushing.

Usage: python scripts/guard_record.py [--old FILE --new FILE]    (the flags are for tests)
"""
import os
import subprocess
import sys

REL = "data/record/events.jsonl"


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


def main(argv):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if "--old" in argv and "--new" in argv:
        old = open(argv[argv.index("--old") + 1], "rb").read()
        new = open(argv[argv.index("--new") + 1], "rb").read()
    else:
        r = subprocess.run(["git", "show", "HEAD:" + REL], cwd=root, capture_output=True)
        old = r.stdout if r.returncode == 0 else b""        # not committed yet: anything is an addition
        try:
            new = open(os.path.join(root, REL), "rb").read()
        except FileNotFoundError:
            new = b""
        if r.returncode == 0 and not os.path.exists(os.path.join(root, REL)):
            print("RECORD GUARD: FAILED: the Record file is gone")
            return 1
    why = check(old, new)
    if why:
        print("RECORD GUARD: FAILED: %s. Nothing will be pushed." % why)
        return 1
    print("RECORD GUARD: ok (%d lines committed, %d now)" % (old.count(b"\n"), new.count(b"\n")))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
