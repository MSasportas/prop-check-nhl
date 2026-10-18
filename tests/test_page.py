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


def page_array(name):
    with open(PAGE, encoding="utf-8") as f:
        src = f.read()
    m = re.search(r"^var %s = \[.*?^\];$" % re.escape(name), src, re.S | re.M)
    if not m:
        raise AssertionError("var %s not found in index.html" % name)
    return m.group(0)


class RulesSheet(unittest.TestCase):
    """The 'How picks are made' sheet must say what the rules in force say (v2.0 from 2026-10-19)."""

    def render(self, array, values):
        js = "\n".join([page_function(n) for n in ("isObj", "arr", "num", "str", "odds", "slot")] + [
            "var S = {rules: {values: %s}};" % json.dumps(values),
            "function ruleVal(k) { return S.rules.values[k]; }",
            "function h(tag, o) { return {miss: /miss/.test(o['class']), text: o.text}; }",
            page_array(array),
            "var out = %s.map(function (s) { var re = /\\{([a-z0-9_.]+)\\|([a-z]+)\\}/g, miss = 0;"
            " var t = s.replace(re, function (_, k, kind) { var x = slot(k, kind); if (x.miss) miss++; return x.text; });"
            " return {t: t, miss: miss}; });" % array,
            "console.log(JSON.stringify(out));"])
        return run_js(js)

    def test_v2_sheet_is_complete_and_has_no_v1_rules(self):
        cfg = helpers.common.load_config()
        out = self.render("RULES", cfg["values"])
        self.assertEqual([o["t"] for o in out if o["miss"]], [], "every number comes from rules.json")
        text = " ".join(o["t"] for o in out)
        self.assertIn("Shots on goal only, at the 1.5 and 2.5 lines.", text)
        self.assertIn("model (70%) with that Hard Rock chance (30%)", text)
        self.assertIn("by 0 to just under 5 points", text)
        self.assertIn("2 per game and 8 a night", text)
        self.assertIn("Parlays are paused until single picks prove out.", text)
        src = page_array("RULES")
        for gone in ("uncertainty", "under_penalty", "thin_over_penalty", "news_gap", "too_good", "drift_pull",
                     "parlay_", "min_p", "margin_"):
            self.assertNotIn("{" + gone, src)

    def test_v1_sheet_still_renders_for_the_v1_slate(self):
        cfg = helpers.common.rules_for(helpers.common.load_config(), "2026-10-18")
        self.assertEqual(cfg["version"], "1.0")
        out = self.render("RULES_V1", cfg["values"])
        self.assertEqual([o["t"] for o in out if o["miss"]], [])

    def test_page_render_loop_accepts_dotted_keys(self):
        """The page's own placeholder regex (not a copy) must match every placeholder in RULES, dotted ones too."""
        import re
        with open(PAGE, encoding="utf-8") as f:
            src = f.read()
        m = re.search(r"var li = h\('li'\), re = /(.+?)/g", src)
        self.assertIsNotNone(m)
        page_re = re.compile(m.group(1).replace("\\{", "\\{"))
        holders = re.findall(r"\{[^{}|]+\|[a-z]+\}", page_array("RULES"))
        self.assertTrue(any("." in h for h in holders))
        for h in holders:
            self.assertIsNotNone(page_re.fullmatch(h), h)

    def test_parlay_paused_line(self):
        with open(PAGE, encoding="utf-8") as f:
            src = f.read()
        self.assertIn("num(ruleVal('parlay_cap')) === 0", src)
        self.assertIn("'Parlays paused until single picks prove out.'", src)


if __name__ == "__main__":
    unittest.main()
