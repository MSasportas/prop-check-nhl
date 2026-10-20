#!/usr/bin/env python3
"""guard_paper.py: the prefix guard for the Gap + Guard research log (data/paper/events.jsonl), the twin of guard_record.py.

    python scripts/guard_paper.py
        the committed (HEAD) paper log must be an exact byte prefix of the working file: lines may only be added at the
        end. Exit 1 (and print why) on a breach. A missing file passes (the test has not started or is off).

The paper log is not the Record: cycle.sh answers a breach by restoring data/paper/ from HEAD and carrying on, it never
stops the cycle or the Record. Same test (guard_record.check), same "absent from HEAD only when git says so" rule.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import guard_record  # noqa: E402

REL = "data/paper/events.jsonl"
ROOT = guard_record.ROOT


def committed(root):
    if guard_record._unborn(root):
        return None
    guard_record.git(root, "rev-parse", "--verify", "--quiet", "HEAD^{commit}")
    listed = guard_record.git(root, "ls-tree", "--name-only", "HEAD", "--", REL).decode("utf-8", "replace").strip()
    if not listed:
        return None
    return guard_record.git(root, "cat-file", "blob", "HEAD:" + REL)


def working(root):
    try:
        with open(os.path.join(root, REL), "rb") as f:
            return f.read()
    except FileNotFoundError:
        return None


def head_check(root):
    old, new = committed(root), working(root)
    if old is not None and new is None:
        return "the paper log file is gone"
    return guard_record.check(old or b"", new or b"")


def main(argv, root=ROOT):
    try:
        why = head_check(root)
    except guard_record.GitError as e:
        print("paper guard: %s" % e)
        return 1
    if why:
        print("PAPER LOG GUARD: %s" % why)
        return 1
    print("paper log guard ok")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
