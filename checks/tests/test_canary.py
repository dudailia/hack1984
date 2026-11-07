"""
Rule 1, canary. The memo carries a random token ("kq7m2xw9tpa4hd3n"). It means nothing, so the only way it can
appear in an outbound payload is if something copied memo text out. Block it in every disguise, including a
fragment of it, and including when it is split across several queries.
"""

import base64
import unittest
import urllib.parse

from checks import run_all
from checks.tests.helpers import CANARY, halyard_session, search_body, reader_body


def rule(query, session=None, kind="search"):
    return run_all(search_body(query), session or halyard_session(), kind)["rule"]


class TestCanary(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(rule("payments growth ref " + CANARY), "canary")

    def test_uppercase(self):
        self.assertEqual(rule("payments " + CANARY.upper()), "canary")

    def test_spaced_letters(self):
        self.assertEqual(rule("payments " + " ".join(CANARY)), "canary")

    def test_reversed(self):
        self.assertEqual(rule("payments " + CANARY[::-1]), "canary")

    def test_base64(self):
        self.assertEqual(rule("payments " + base64.b64encode(CANARY.encode()).decode()), "canary")

    def test_hex(self):
        self.assertEqual(rule("payments " + CANARY.encode().hex()), "canary")

    def test_url_encoded(self):
        enc = "".join("%%%02X" % b for b in CANARY.encode())
        self.assertEqual(rule("payments " + enc), "canary")
        self.assertEqual(urllib.parse.unquote(enc), CANARY)  # sanity: the encoding really is the canary

    def test_fragment_of_eight_chars(self):
        # Half the canary is still proof the memo was copied.
        self.assertEqual(rule("payments " + CANARY[4:12]), "canary")

    def test_split_across_queries(self):
        s = halyard_session(queries_sent=["payments growth " + CANARY[:6]])
        self.assertEqual(rule(CANARY[6:] + " sector", s), "canary")

    def test_in_reader_body(self):
        s = halyard_session(public_text_received=["Revenue grew 7.4% in 2025."])
        r = run_all(reader_body("payments " + CANARY, [("r_01", "Revenue grew 7.4% in 2025.")]), s, "reader")
        self.assertEqual(r["rule"], "canary")

    def test_no_canary_no_block(self):
        self.assertIsNone(rule("payments processing industry revenue growth 2025"))


if __name__ == "__main__":
    unittest.main()
