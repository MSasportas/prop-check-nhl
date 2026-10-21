"""ODDS_API_KEYS_2: a second secret appended after ODDS_API_KEYS (daily check 2026-10-21)."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import odds  # noqa: E402

VARS = ("ODDS_API_KEYS", "ODDS_API_KEYS_2")


class SecondSecret(unittest.TestCase):
    def setUp(self):
        self.saved = {k: os.environ.get(k) for k in VARS}

    def tearDown(self):
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_second_secret_goes_after_first(self):
        os.environ["ODDS_API_KEYS"] = "aaaa1111,bbbb2222"
        os.environ["ODDS_API_KEYS_2"] = " cccc3333\n"
        self.assertEqual(odds.load_keys(), ["aaaa1111", "bbbb2222", "cccc3333"])

    def test_second_secret_alone_or_absent(self):
        os.environ.pop("ODDS_API_KEYS", None)
        os.environ["ODDS_API_KEYS_2"] = "cccc3333"
        self.assertEqual(odds.load_keys(), ["cccc3333"])
        os.environ["ODDS_API_KEYS"] = "aaaa1111"
        os.environ.pop("ODDS_API_KEYS_2")
        self.assertEqual(odds.load_keys(), ["aaaa1111"])

    def test_duplicate_kept_once(self):
        os.environ["ODDS_API_KEYS"] = "aaaa1111"
        os.environ["ODDS_API_KEYS_2"] = "aaaa1111,dddd4444"
        self.assertEqual(odds.load_keys(), ["aaaa1111", "dddd4444"])


if __name__ == "__main__":
    unittest.main()
