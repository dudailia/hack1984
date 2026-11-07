"""
run_all must stay fast on HOSTILE input. A Reader payload carries web text an attacker controls, and the Gate calls
run_all on it before sending. If any regex or loop is super-linear, an attacker can stall the Gate (and the demo)
just by publishing a page full of whitespace or digits. PR #4 review (Aayush) found one such regex in amounts.py;
these tests push 100k-character worst cases through the WHOLE pipeline, not just one function.

Budget: 3 seconds per payload on a laptop (a normal 100 KB Reader body takes about 0.2 s).
"""

import time
import unittest

from checks import run_all
from checks.tests.helpers import halyard_session, reader_body, search_body

N = 100_000
BUDGET_S = 3.0

HOSTILE = {
    "number then spaces": "412" + " " * N + "x",
    "many numbers each followed by spaces": ("412" + " " * 1000) * 100,
    "number then dashes and spaces": "412" + " -" * (N // 2),
    "spaced single digits": "1 " * (N // 2),
    "long digit run": "4" * N,
    "dotted thousands run": "1" + ".000" * (N // 4),
    "comma thousands run": "1" + ",000" * (N // 4),
    "hex-looking run": "4f" * (N // 2),
    "hex pairs with separators": "4f " * (N // 3),
    "base64-looking run": "QUJD" * (N // 4),
    "percent escapes": "%41" * (N // 3),
    "number words": "four hundred " * (N // 13),
    "letters only": "a" * N,
}


class TestHostileReaderPayloads(unittest.TestCase):
    def test_each_hostile_document_is_checked_quickly(self):
        for name, text in HOSTILE.items():
            with self.subTest(case=name):
                s = halyard_session(public_text_received=[text], queries_sent=["payments growth 2025"])
                body = reader_body("payments growth 2025", [("r_01", text)])
                t = time.monotonic()
                run_all(body, s, "reader")
                self.assertLess(time.monotonic() - t, BUDGET_S, name)

    def test_hostile_search_query_is_checked_quickly(self):
        # A query is capped at 300 chars by shape, but the leak rules run first, on the full string.
        t = time.monotonic()
        run_all(search_body("412" + " " * N + "x"), halyard_session(), "search")
        self.assertLess(time.monotonic() - t, BUDGET_S)


if __name__ == "__main__":
    unittest.main()
