"""
Rule 3, provenance. The confirmed-secrets list only covers what the user remembered to confirm. Provenance is
the safety net: a RARE word or number from the memo (not ordinary English, not an approved public term) may only
leave if the web already showed it to us this session. It is checked across the whole session, so a rare word
split over several queries is caught too.
"""

import unittest

from checks import memo_tokens, run_all
from checks.tests.helpers import MEMO, halyard_session, search_body


def no_secrets_session(**kw):
    """A session where the user confirmed NOTHING, so only provenance stands between the memo and the web."""
    return halyard_session(confirmed_secrets=[], **kw)


def rule(query, session):
    return run_all(search_body(query), session, "search")["rule"]


class TestMemoTokens(unittest.TestCase):
    def setUp(self):
        self.toks = set(memo_tokens(MEMO, ["Brackwater Payments", "payments processing", "payments"]))

    def test_rare_words_and_numbers_are_in(self):
        for t in ["halyard", "ossory", "whitcombe", "tobias", "renwick", "dana", "412", "412000000",
                  "kq7m2xw9tpa4hd3n"]:
            self.assertIn(t, self.toks)

    def test_ordinary_and_approved_words_are_out(self):
        for t in ["payments", "brackwater", "processing", "sector", "revenue", "project", "confidential",
                  "capital", "partners", "price", "million", "november", "16", "the", "management", "listed"]:
            self.assertNotIn(t, self.toks)

    def test_deterministic_and_sorted(self):
        a = memo_tokens(MEMO, ["Brackwater Payments"])
        self.assertEqual(a, sorted(a))
        self.assertEqual(a, memo_tokens(MEMO, ["Brackwater Payments"]))


class TestProvenanceRule(unittest.TestCase):
    def test_unconfirmed_rare_word_blocks(self):
        self.assertEqual(rule("Halyard payments growth", no_secrets_session()), "provenance.rare_term")

    def test_partial_name_not_on_confirmed_list_blocks(self):
        # "Renwick" alone is not a confirmed value ("Tobias Renwick-Ash" is), so rule 2 misses it; rule 3 must not.
        self.assertEqual(rule("Renwick payments", halyard_session()), "provenance.rare_term")

    def test_rare_number_blocks(self):
        self.assertEqual(rule("412 merchants payments", no_secrets_session()), "provenance.rare_term")

    def test_rare_amount_in_another_format_blocks(self):
        self.assertEqual(rule("payments deals 412,000,000", no_secrets_session()), "provenance.rare_term")

    def test_spaced_rare_word_blocks(self):
        self.assertEqual(rule("R e n w i c k payments", halyard_session()), "provenance.rare_term")

    def test_split_rare_word_blocks(self):
        s = halyard_session(queries_sent=["payments renw"])
        self.assertEqual(rule("ick growth", s), "provenance.split")

    def test_seen_in_public_text_is_allowed(self):
        # Once the web itself showed "Renwick", repeating it reveals nothing new about the memo.
        s = halyard_session(public_text_received=["The Renwick index of payments fell."])
        self.assertIsNone(rule("Renwick index payments", s))

    def test_approved_target_name_passes(self):
        # notes/BENIGN.md question 30: the target name is user-approved and must pass.
        self.assertIsNone(rule("What is Brackwater Payments' sector, and who are its listed peers?",
                               halyard_session()))

    def test_ordinary_memo_words_pass(self):
        self.assertIsNone(rule("listed payments companies EV/revenue sector growth November", halyard_session()))


if __name__ == "__main__":
    unittest.main()
