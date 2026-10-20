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
    def test_fixtures_show_only_what_the_engine_can_make(self):
        """One engine: Gap + Guard singles, flat 1u, no parlays, no goal watch, shots only. The page's QA fixtures say so too."""
        paths = sorted(glob.glob(os.path.join(FIX, "*", "slate.json")))
        self.assertGreater(len(paths), 10)
        for p in paths:
            with open(p) as f:
                sl = json.load(f)
            self.assertEqual(sl.get("parlays"), [], p)
            self.assertNotIn("goal_watch", sl, p)
            for pk in sl["picks"]:
                for k in ("gap_pct", "market_fair_pct", "n_books", "guard", "settled", "price", "bet", "reason", "start"):
                    self.assertIn(k, pk, "%s: %s has no %s" % (p, pk["id"], k))
                self.assertEqual(pk["market"], "shots", p)
                if "/long/" not in p:                                  # the layout-stress fixture has a +1000 price on purpose
                    self.assertGreaterEqual(pk["price"], -200, p)
                    self.assertLessEqual(pk["price"], 120, p)
        with open(os.path.join(FIX, "normal", "rules.json")) as f:
            rules = json.load(f)
        self.assertEqual(rules["version"], helpers.common.load_config()["version"])


class PageRules(unittest.TestCase):
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

    def rules_values(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("make_fixtures", os.path.join(FIX, "make_fixtures.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.rules_doc()["values"]

    def test_the_sheet_is_complete_and_is_the_one_rule(self):
        out = self.render("RULES", self.rules_values())
        self.assertEqual([o["t"] for o in out if o["miss"]], [], "every number comes from rules.json")
        text = " ".join(o["t"] for o in out)
        self.assertIn("Hard Rock shots on goal at the 1.5 and 2.5 lines", text)
        self.assertIn("At least 4 of them", text)
        self.assertIn("by at least 3%", text)
        self.assertIn("80% the other books' chance with 20% our model's chance", text)
        self.assertIn("by at least 2%", text)
        self.assertIn("The first 90 or 45 minute read that passes both steps becomes the pick, and its price is frozen", text)
        self.assertIn("No more than 1 per player, 2 per game and 3 a night", text)
        self.assertIn("Parlays are not offered", text)
        self.assertIn("-10 units", text)
        src = page_array("RULES")
        for gone in ("uncertainty", "under_penalty", "thin_over_penalty", "news_gap", "too_good", "drift_pull",
                     "parlay_", "min_p", "margin_", "paper", "previous"):
            self.assertNotIn("{" + gone, src)
        with open(PAGE, encoding="utf-8") as f:
            self.assertNotIn("RULES_V1", f.read())

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

    def test_the_old_engine_is_gone_from_the_page(self):
        with open(PAGE, encoding="utf-8") as f:
            src = f.read()
        for gone in ("Paper test", "paper test", "no proven edge", "Picks are paused", "Parlays paused until", "goal_watch",
                     "RULES_V1", "paperSection", "S.slate.paper"):
            self.assertNotIn(gone, src, gone)
        self.assertIn("Parlays are not offered", src)

    def test_a_pick_card_says_what_matt_needs(self):
        """Gap, market fair + books, guard verdict, our chance vs the price, settled level, time to puck, frozen price."""
        with open(PAGE, encoding="utf-8") as f:
            src = f.read()
        card = page_function("pickCard")
        for want in ("p.gap_pct", "' vs market'", "p.n_books", "p.market_fair_pct", "gd.verdict === 'agrees'", "'Model agrees",
                     "'We say '", "price needs", "settledChip(p)", "toPuck(", "bet at this price or better", "p.reason"):
            self.assertIn(want, card, want)
        self.assertIn("puck dropped", page_function("toPuck"))
        self.assertIn("to puck", page_function("toPuck"))


if __name__ == "__main__":
    unittest.main()
