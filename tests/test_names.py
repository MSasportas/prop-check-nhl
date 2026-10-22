import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import names


class TestNames(unittest.TestCase):
    def setUp(self):
        self.m = names.Matcher([
            {"id": 8482475, "first": "Egor", "last": "Chinakhov", "team": "PIT", "pos": "F"},
            {"id": 1, "first": "Sidney", "last": "Crosby", "team": "PIT", "pos": "F"},
            {"id": 2, "first": "Elias", "last": "Pettersson", "team": "VAN", "pos": "F"},
            {"id": 3, "first": "Elias", "last": "Pettersson", "team": "VAN", "pos": "D"},
        ])

    def test_transliteration(self):
        self.assertEqual(self.m.find("Yegor Chinakhov")["id"], 8482475)
        self.assertEqual(self.m.find("Egor Chinakhov")["id"], 8482475)

    def test_unchanged(self):
        self.assertEqual(self.m.find("Sidney Crosby")["id"], 1)
        self.assertEqual(self.m.find("S. Crosby")["id"], 1)
        self.assertIsNone(self.m.find("Elias Pettersson"))   # two of them: never guess
        self.assertIsNone(self.m.find("Seth Jarvis"))


if __name__ == "__main__":
    unittest.main()
