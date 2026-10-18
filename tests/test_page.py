"""The page's QA fixtures and the page's own small rules (index.html), checked without a browser."""
import glob
import json
import os
import re
import shutil
import subprocess
import unittest

import helpers  # noqa: F401  (puts scripts/ on sys.path)
import notify

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, "fixtures")
PAGE = os.path.join(ROOT, "index.html")


def page_function(name):
    """The source of one top-level `function name(...) {...}` in index.html (it ends at a line that is just '}')."""
    with open(PAGE, encoding="utf-8") as f:
        src = f.read()
    m = re.search(r"^function %s\(.*\}$" % re.escape(name), src, re.M)         # a one-line function
    if m and m.group(0).count("{") == m.group(0).count("}"):
        return m.group(0)
    m = re.search(r"^function %s\(.*?^}$" % re.escape(name), src, re.S | re.M)
    if not m:
        raise AssertionError("function %s not found in index.html" % name)
    return m.group(0)


def run_js(code):
    node = shutil.which("node")
    if not node:
        raise unittest.SkipTest("node not installed")
    r = subprocess.run([node, "-e", code], capture_output=True, text=True, timeout=20)
    if r.returncode:
        raise AssertionError(r.stderr)
    return json.loads(r.stdout)


class Fixtures(unittest.TestCase):
    def test_a_leg_is_in_one_parlay_only(self):
        """Rule 2026-10-18: a leg in 1 parlay. The fixtures must not show what the engine can't."""
        paths = sorted(glob.glob(os.path.join(FIX, "*", "slate.json")))
        self.assertGreater(len(paths), 10)
        for p in paths:
            with open(p) as f:
                sl = json.load(f)
            seen = {}
            for par in sl.get("parlays", []):
                for leg in par["legs"]:
                    self.assertNotIn(leg, seen, "%s: %s is in %s and %s" % (p, leg, seen.get(leg), par["id"]))
                    seen[leg] = par["id"]


class PageRules(unittest.TestCase):
    def test_reason_drops_first_sentence_like_discord(self):
        reasons = [
            "66% to clear 3.5 shots; -145 needs 59%. Projects 4.4 shots in 22 min. DAL allow 6% more shots than average.",
            "69% to clear 0.5 points; -160 needs 62%. Projects 1.1 points in 20 min.",
            "62% to stay under 1.5 shots; -140 needs 58%.",
            "",
        ]
        got = run_js(page_function("str") + "\n" + page_function("whyText") +
                     "\nconsole.log(JSON.stringify(%s.map(whyText)))" % json.dumps(reasons))
        for r, g in zip(reasons, got):
            want = notify._why({"reason": r})          # Discord's rule (short reasons: no 110-char cut)
            self.assertEqual(g, want + "." if want else "", r)
        self.assertEqual(got[0], "Projects 4.4 shots in 22 min. DAL allow 6% more shots than average.")

    def test_goalie_last_name(self):
        got = run_js(page_function("str") + "\n" + page_function("lastName") +
                     "\nconsole.log(JSON.stringify(['Joonas Korpisalo', 'Ukko-Pekka Luukkonen', ' Vladar ', ''].map(lastName)))")
        self.assertEqual(got, ["Korpisalo", "Luukkonen", "Vladar", ""])


if __name__ == "__main__":
    unittest.main()
