"""
Tests for checks.amounts.parse_amounts: turn every way of writing a number into one canonical value, so
"$412 million", "412m", "412,000,000", "0.412bn" and "four hundred twelve million" all compare equal.
(The module is called amounts.py, not numbers.py, so it never shadows Python's standard `numbers` module.)
"""

import unittest
from decimal import Decimal

from checks.amounts import parse_amounts, canon

D412M = Decimal(412_000_000)


def has_412m(text):
    return D412M in parse_amounts(text)


class TestAmounts(unittest.TestCase):
    def test_all_forms_of_412_million(self):
        forms = [
            "$412 million", "$412M", "412m", "412 mm", "412mn", "412 mln", "412 mil", "USD 412 million",
            "412,000,000", "412000000", "412 000 000", "412.000.000", "412_000_000",
            "0.412bn", "$0.412 billion", "0.412 b", "4.12e8", "412,000 thousand", "412000k",
            "four hundred twelve million", "four hundred and twelve million", "Four-Hundred-Twelve Million",
            "4 1 2 0 0 0 0 0 0",
        ]
        for f in forms:
            with self.subTest(form=f):
                self.assertTrue(has_412m(f), parse_amounts(f))

    def test_near_misses_are_not_412_million(self):
        for f in ["$41.2 million", "$4.12 billion", "412 merchants", "$1,412,000", "412", "2025",
                  "four hundred twelve", "412 thousand"]:
            with self.subTest(form=f):
                self.assertFalse(has_412m(f), parse_amounts(f))

    def test_scale_letter_needs_a_word_boundary(self):
        # "10 merchants" must not read as 10 million ("m" + "erchants").
        self.assertNotIn(Decimal(10_000_000), parse_amounts("10 merchants"))
        self.assertIn(Decimal(10), parse_amounts("10 merchants"))

    def test_number_followed_by_huge_whitespace_is_fast(self):
        # PR #4 review (Aayush): "\s*-?\s*" before the scale word backtracked quadratically, so "412" followed by
        # 100k spaces in an attacker's page (Reader payloads are attacker text) could stall the Gate for minutes.
        import time
        for tail in (" " * 100_000 + "x", "\n" * 100_000, " -" * 50_000, "- " * 50_000):
            t = time.monotonic()
            parse_amounts("412" + tail)
            self.assertLess(time.monotonic() - t, 0.5, repr(tail[:6]))

    def test_scale_still_found_after_short_separators(self):
        for f in ["412 million", "412  million", "412 - million", "412-million", "412\nmillion"]:
            with self.subTest(form=f):
                self.assertTrue(has_412m(f), parse_amounts(f))

    def test_canon(self):
        self.assertEqual(canon(Decimal("412000000.000")), "412000000")
        self.assertEqual(canon(Decimal("4.60")), "4.6")


if __name__ == "__main__":
    unittest.main()
