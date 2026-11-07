import unittest
from decimal import Decimal

from reader import numbers as n


def values(text):
    return [v for v, _, _ in n.find_numbers(text)]


class Normalize(unittest.TestCase):
    def test_whitespace_collapsed(self):
        self.assertEqual(n.normalize("  grew\n 7.4%\t in  2025 "), "grew 7.4% in 2025")

    def test_nfkc(self):
        self.assertEqual(n.normalize("grew ７.４％"), "grew 7.4%")


class FindNumbers(unittest.TestCase):
    def test_simple(self):
        self.assertEqual(values("grew 7.4% in 2025"), [Decimal("7.4"), Decimal("2025")])

    def test_thousands_separators_removed(self):
        self.assertEqual(values("revenue of $1,234,500 last year"), [Decimal("1234500")])

    def test_range_is_two_positive_years(self):
        self.assertEqual(values("from 2025-2030"), [Decimal("2025"), Decimal("2030")])

    def test_negative(self):
        self.assertEqual(values("revenue fell -2.5% in 2024"), [Decimal("-2.5"), Decimal("2024")])

    def test_no_numbers_inside_words(self):
        self.assertEqual(values("Q3 results for FY were strong"), [])

    def test_trailing_period_not_decimal(self):
        self.assertEqual(values("It was 6.1x in 2025."), [Decimal("6.1"), Decimal("2025")])

    def test_spans(self):
        text = "at 4.2x EV/revenue"
        [(v, s, e)] = n.find_numbers(text)
        self.assertEqual(text[s:e], "4.2")


class UnitConsistent(unittest.TestCase):
    def check(self, text, unit, value):
        for v, s, e in n.find_numbers(text):
            if v == Decimal(value):
                return n.unit_consistent(text, s, e, unit)
        raise AssertionError("value not found")

    def test_percent(self):
        self.assertTrue(self.check("grew 7.4% in 2025", "percent", "7.4"))
        self.assertTrue(self.check("grew 7.4 percent in 2025", "percent", "7.4"))
        self.assertFalse(self.check("grew 7.4% in 2025", "percent", "2025"))

    def test_multiple(self):
        self.assertTrue(self.check("trading at 4.2x EV/revenue", "multiple", "4.2"))
        self.assertTrue(self.check("trading at 4.2 times revenue", "multiple", "4.2"))
        self.assertTrue(self.check("an EV/revenue multiple of 4.2", "multiple", "4.2"))
        self.assertFalse(self.check("EV/revenue multiple was 6.1x in 2025", "multiple", "2025"))
        self.assertFalse(self.check("grew 7.4% in 2025", "multiple", "7.4"))

    def test_millions_and_billions(self):
        self.assertTrue(self.check("revenue of $412 million", "usd_millions", "412"))
        self.assertTrue(self.check("revenue of $412m", "usd_millions", "412"))
        self.assertTrue(self.check("revenue of USD 412mn", "usd_millions", "412"))
        self.assertTrue(self.check("a market of $48.2 billion", "usd_billions", "48.2"))
        self.assertTrue(self.check("a market of $48.2bn", "usd_billions", "48.2"))
        self.assertFalse(self.check("a market of $48.2 billion", "usd_millions", "48.2"))
        self.assertFalse(self.check("12 months of data", "usd_millions", "12"))

    def test_usd(self):
        self.assertTrue(self.check("EBITDA of $250,000", "usd", "250000"))
        self.assertFalse(self.check("EBITDA of $250 million", "usd", "250"))
        self.assertFalse(self.check("EBITDA of 250,000", "usd", "250000"))

    def test_count_and_year(self):
        self.assertTrue(self.check("It employs 1,200 people", "count", "1200"))
        self.assertFalse(self.check("It grew 12% last year", "count", "12"))
        self.assertTrue(self.check("founded in 2004", "year", "2004"))


class PeriodInQuote(unittest.TestCase):
    def test_empty_period(self):
        self.assertTrue(n.period_in("anything", ""))

    def test_year(self):
        self.assertTrue(n.period_in("grew 7.4% in 2025", "2025"))
        self.assertTrue(n.period_in("FY2025 revenue", "2025"))
        self.assertFalse(n.period_in("grew 7.4% in 2025", "2024"))
        self.assertFalse(n.period_in("grew 7.4% in 20251", "2025"))

    def test_range_needs_both_years(self):
        self.assertTrue(n.period_in("from 2025 to 2030", "2025-2030"))
        self.assertFalse(n.period_in("in 2025", "2025-2030"))

    def test_ttm(self):
        for text in ("on a TTM basis", "LTM revenue", "over the trailing twelve months"):
            self.assertTrue(n.period_in(text, "ttm"), text)
        self.assertFalse(n.period_in("in 2025", "ttm"))


if __name__ == "__main__":
    unittest.main()
