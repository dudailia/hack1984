"""
run_all must stay fast on HOSTILE input. A Reader payload carries web text an attacker controls, and the Gate calls
run_all on it before sending. If any regex or loop is super-linear, an attacker can stall the Gate (and the demo)
just by publishing a page full of whitespace or digits. PR #4 review (Aayush) found one such regex in amounts.py;
these tests push 100k-character worst cases through the WHOLE pipeline, not just one function.

BUDGET (not a fixed wall-clock number, so a slow or busy machine does not make it flaky, PR #4 re-review):
each hostile payload may take at most 25x the time of an ORDINARY payload of the same size measured on the same
machine in the same run, and never less than 3 s. On a laptop the ordinary payload takes ~0.1 s and every hostile case
~0.1 to 0.5 s; the quadratic bug this guards against took over 10 MINUTES, so the margin is huge in both directions.
"""

import time
import unittest

from checks import run_all
from checks.tests.helpers import halyard_session, reader_body, search_body

N = 100_000
FLOOR_S = 3.0
FACTOR = 25


def _time(body, session, kind):
    t = time.monotonic()
    run_all(body, session, kind)
    return time.monotonic() - t


def _budget():
    """FACTOR x the time to check an ordinary 100k-character Reader document on this machine (min FLOOR_S)."""
    ordinary = ("Merchant acquiring revenue grew 7.4% in 2025, according to the survey of payments processors. "
                * (N // 96 + 1))[:N]
    s = halyard_session(public_text_received=[ordinary], queries_sent=["payments growth 2025"])
    base = min(_time(reader_body("payments growth 2025", [("r_01", ordinary)]), s, "reader") for _ in range(2))
    return max(FLOOR_S, FACTOR * base)


BUDGET_S = None  # computed once, in setUpModule

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


def setUpModule():
    global BUDGET_S
    BUDGET_S = _budget()


class TestHostileReaderPayloads(unittest.TestCase):
    def test_each_hostile_document_is_checked_quickly(self):
        for name, text in HOSTILE.items():
            with self.subTest(case=name):
                s = halyard_session(public_text_received=[text], queries_sent=["payments growth 2025"])
                took = _time(reader_body("payments growth 2025", [("r_01", text)]), s, "reader")
                self.assertLess(took, BUDGET_S, "%s took %.2fs (budget %.2fs)" % (name, took, BUDGET_S))

    def test_hostile_search_query_is_checked_quickly(self):
        # A query is capped at 300 chars by shape, but the leak rules run first, on the full string.
        took = _time(search_body("412" + " " * N + "x"), halyard_session(), "search")
        self.assertLess(took, BUDGET_S)


if __name__ == "__main__":
    unittest.main()
