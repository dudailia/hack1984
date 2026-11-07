import datetime
import unittest

from planner import prompt

TYPED = [{"need": "sector_growth", "found": True, "values": [
    {"claim_type": "revenue_growth", "value": 9.8, "unit": "percent", "period": "2025-2030", "result_id": "r_01"}]}]


class TestPrompt(unittest.TestCase):
    def test_date_in_system(self):
        for today in (datetime.date(2026, 11, 7), "2026-11-07"):
            s = prompt.system_prompt(today)
            self.assertTrue(s.startswith("Today is 2026-11-07."), s[:40])

    def test_bad_date(self):
        for today in ("Nov 7", "2026-13-01", "", None, 20261107, datetime.datetime(2026, 11, 7)):
            with self.assertRaises(ValueError):
                prompt.system_prompt(today)

    def test_rules(self):
        s = prompt.system_prompt("2026-11-07").lower()
        for phrase in ("buyer", "price", "codename", "person", "sector", "public peers", "3 to 8 words",
                       "most recent", "reference number", "ref:", "code", " id"):
            self.assertIn(phrase, s)
        self.assertIn("never copy", s)

    def test_messages(self):
        m = prompt.build_messages("MEMO TEXT", "QUESTION TEXT", "2026-11-07", TYPED)
        self.assertEqual([x["role"] for x in m], ["system", "user"])
        self.assertIn("Today is 2026-11-07.", m[0]["content"])
        u = m[1]["content"]
        self.assertIn("MEMO TEXT", u)
        self.assertIn("QUESTION TEXT", u)
        self.assertIn('"value":9.8', u)
        self.assertIn('"result_id":"r_01"', u)

    def test_no_typed(self):
        u = prompt.user_prompt("m", "q", [])
        self.assertIn("none yet", u.lower())


if __name__ == "__main__":
    unittest.main()
