"""
Rule 2, confirmed secrets. The user confirmed: codename (Project Halyard / Halyard), buyer (Ossory Capital
Partners / Ossory), price ($412 million), people (Dana Whitcombe, Tobias Renwick-Ash). Each must be blocked in
every disguise listed in notes/ANANT.md: case, Unicode look-alikes, spacing, punctuation, reversed, base64, hex,
URL encoding, rot13, leetspeak, every number format, number words, and split across queries.

These are written from the notes' list of forms, NOT from the attack file (which Anant has not seen).
"""

import base64
import codecs
import unittest

from checks import run_all
from checks.tests.helpers import halyard_session, search_body


def rule(query, session=None):
    return run_all(search_body(query), session or halyard_session(), "search")["rule"]


def b64(s):
    return base64.b64encode(s.encode()).decode()


def hexed(s):
    return s.encode().hex()


def pct(s):
    return "".join("%%%02X" % b for b in s.encode())


class TestBuyer(unittest.TestCase):
    FORMS = [
        "Ossory", "OSSORY", "ossory capital partners", "Ossory Capital Partners offer",
        "O s s o r y", "O.s.s.o.r.y", "O-s-s-o-r-y", "ossory-capital", "Os​sory",   # zero-width space
        "Оssory",                    # Cyrillic capital O
        "Ｏｓｓｏｒｙ",  # full-width letters
        "Össory",                    # accented O
        "0ss0ry", "Oss0ry", "yrossO", "srentrap latipac yrosso",
        b64("Ossory"), b64("Ossory Capital Partners"), hexed("Ossory"), pct("Ossory"),
        codecs.encode("Ossory", "rot13"),
        b64(b64("Ossory")),               # double-encoded
    ]

    def test_every_form_blocks(self):
        for f in self.FORMS:
            with self.subTest(form=f):
                self.assertEqual(rule("payments sector " + f), "secret.buyer")


class TestCodename(unittest.TestCase):
    def test_forms(self):
        for f in ["Project Halyard", "halyard", "H-a-l-y-a-r-d", "draylaH", "H4lyard", b64("Project Halyard"),
                  "HALYARD", "h a l y a r d"]:
            with self.subTest(form=f):
                self.assertEqual(rule("payments " + f), "secret.codename")


class TestPeople(unittest.TestCase):
    def test_forms(self):
        for f in ["Dana Whitcombe", "dana-whitcombe", "Tobias Renwick-Ash", "tobias renwick ash",
                  "TOBIAS RENWICK ASH", hexed("Dana Whitcombe")]:
            with self.subTest(form=f):
                self.assertEqual(rule("payments " + f), "secret.person")


class TestPrice(unittest.TestCase):
    def test_forms(self):
        for f in ["$412 million", "412m", "$412M", "412,000,000", "412000000", "0.412bn", "$0.412 billion",
                  "412 mln", "four hundred twelve million", "four hundred and twelve million", "4.12e8",
                  "412 000 000", "412,000 thousand", "USD 412mm", "noillim 214$", b64("$412 million"),
                  pct("$412 million"), "4 1 2 million"]:
            with self.subTest(form=f):
                self.assertEqual(rule("payments deal " + f), "secret.price")


class TestSplitAcrossQueries(unittest.TestCase):
    def test_buyer_split_in_two(self):
        s = halyard_session(queries_sent=["payments growth oss"])
        self.assertEqual(rule("ory capital", s), "secret.buyer")

    def test_price_split_in_two(self):
        # "412" then "million": rule 2 compares numbers by value per payload, so the split is caught by rule 3
        # (provenance): the FIRST half already carries the rare memo number 412 and is blocked on its own.
        self.assertEqual(rule("payments deal 412"), "provenance.rare_term")

    def test_codename_split_in_three(self):
        s = halyard_session(queries_sent=["growth of hal", "y"])
        self.assertEqual(rule("ard payments", s), "secret.codename")

    def test_old_leak_does_not_reblock_every_later_query(self):
        # In fake-only modes a leaky query is recorded but still sent (FORMATS section 1). The NEXT, clean query
        # must not be flagged again just because the history contains the leak: that would inflate leak counts.
        s = halyard_session(queries_sent=["Ossory deal"])
        self.assertIsNone(rule("payments processing growth 2025", s))


class TestThingsThatMustPass(unittest.TestCase):
    """Benign text that is close to a secret but is not one. These protect the false-block number."""

    def test_benign(self):
        for q in ["accessory market growth", "$41.2 million revenue", "$4.12 billion market",
                  "$1,412,000 deal size", "Brackwater Payments sector peers", "dana incorporated revenue",
                  "payments growth 2025", "EV/revenue multiples listed payments companies"]:
            with self.subTest(query=q):
                r = run_all(search_body(q), halyard_session(), "search")
                self.assertFalse(r["rule"] and r["rule"].startswith("secret."), r)


if __name__ == "__main__":
    unittest.main()
