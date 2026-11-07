"""Review 1 (notes/REVIEW_1.md): one test per finding in reader/. Tests named after a finding failed on the
code before the review; tests ending in _ok or _still_ok pin legitimate input that must stay accepted."""
import json
import unittest

import reader
from reader.tests import fixtures as fx


def job(text, types):
    return {"job": "j_01", "public_query": "payments market data", "claim_types": types,
            "documents": [{"id": "r_01", "url": "https://x.example.com", "title": "t", "text": text}]}


def claim(ctype, unit, value, quote, period=""):
    return {"claim_type": ctype, "subject": "subject", "value": value, "unit": unit, "period": period,
            "quote": quote, "document_id": "r_01"}


class ValidatorCase(unittest.TestCase):
    def assertDropped(self, text, types, c):
        kept, dropped = reader.validate(job(text, types), [c])
        self.assertEqual(kept, [], "kept a claim the document does not support: %r" % (c,))
        self.assertEqual(len(dropped), 1)

    def assertKept(self, text, types, c):
        kept, dropped = reader.validate(job(text, types), [c])
        self.assertEqual((kept, dropped), ([c], []))


class R1QuoteTruncation(ValidatorCase):
    """R1-01: a quote cut inside a number keeps a number the document never states."""

    def test_percent_cut_from_larger_number(self):
        self.assertDropped("Revenue grew 14.2% in 2025.", ["revenue_growth"],
                           claim("revenue_growth", "percent", 4.2, "4.2% in 2025", "2025"))

    def test_usd_cut_from_millions(self):
        self.assertDropped("It sold for $412,000,000 in cash.", ["revenue"],
                           claim("revenue", "usd", 412, "for $412"))

    def test_count_cut_from_thousands(self):
        self.assertDropped("The firm employs 12,500 people.", ["employees"],
                           claim("employees", "count", 12, "employs 12"))

    def test_multiple_cut_from_decimal(self):
        self.assertDropped("Peers trade at an EV/revenue multiple of 14.5 on average.", ["ev_revenue_multiple"],
                           claim("ev_revenue_multiple", "multiple", 14, "multiple of 14"))

    def test_sign_outside_the_quote(self):
        self.assertDropped("Revenue growth was -3.0% in 2025.", ["revenue_growth"],
                           claim("revenue_growth", "percent", 3.0, "3.0% in 2025", "2025"))

    def test_scale_word_just_outside_the_quote(self):
        self.assertDropped("Revenue was $412 million in 2025.", ["revenue"],
                           claim("revenue", "usd", 412, "Revenue was $412"))

    def test_whole_number_still_kept(self):
        self.assertKept("Revenue grew 14.2% in 2025.", ["revenue_growth"],
                        claim("revenue_growth", "percent", 14.2, "grew 14.2% in 2025", "2025"))


class R1Sign(ValidatorCase):
    """R1-02: a negative written with a Unicode minus, an en dash, before the currency sign or in accounting
    parentheses is kept as a positive number."""

    def test_unicode_minus(self):
        q = "Revenue growth was \u22123.0% in 2025."
        self.assertDropped(q, ["revenue_growth"], claim("revenue_growth", "percent", 3.0, q, "2025"))
        self.assertKept(q, ["revenue_growth"], claim("revenue_growth", "percent", -3.0, q, "2025"))

    def test_en_dash_minus(self):
        q = "Revenue growth was \u20133.0% in 2025."
        self.assertDropped(q, ["revenue_growth"], claim("revenue_growth", "percent", 3.0, q, "2025"))

    def test_minus_before_currency(self):
        q = "EBITDA was -$3.2 million in 2025."
        self.assertDropped(q, ["ebitda"], claim("ebitda", "usd_millions", 3.2, q, "2025"))
        self.assertKept(q, ["ebitda"], claim("ebitda", "usd_millions", -3.2, q, "2025"))

    def test_accounting_parentheses(self):
        q = "Revenue growth was (3.2%) in 2025."
        self.assertDropped(q, ["revenue_growth"], claim("revenue_growth", "percent", 3.2, q, "2025"))

    def test_hyphen_inside_a_word_is_not_a_sign(self):
        q = "Corvane Pay ended mid-2025 trading at 4.2x EV/revenue."
        self.assertKept(q, ["founded_year", "ev_revenue_multiple"],
                        claim("ev_revenue_multiple", "multiple", 4.2, q, "2025"))


class R1Ranges(ValidatorCase):
    """R1-03: one end of a range is kept as if it were the value."""

    def test_hyphen_range_upper_end(self):
        q = "Sector revenue grew 5-7% in 2025."
        self.assertDropped(q, ["revenue_growth"], claim("revenue_growth", "percent", 7, q, "2025"))

    def test_en_dash_range_of_multiples(self):
        q = "Peers trade at 3.5\u20136.0x EV/revenue."
        self.assertDropped(q, ["ev_revenue_multiple"], claim("ev_revenue_multiple", "multiple", 6.0, q))
        self.assertDropped(q, ["ev_revenue_multiple"], claim("ev_revenue_multiple", "multiple", 3.5, q))

    def test_to_range_with_same_unit(self):
        q = "Peers trade at 3.5x to 6.0x EV/revenue."
        self.assertDropped(q, ["ev_revenue_multiple"], claim("ev_revenue_multiple", "multiple", 6.0, q))

    def test_between_and(self):
        q = "Growth was between 5% and 7% in 2025."
        self.assertDropped(q, ["revenue_growth"], claim("revenue_growth", "percent", 7, q, "2025"))

    def test_from_to_change_keeps_the_new_value(self):
        q = "Its multiple rose from 3.5x to 4.0x in 2025."
        self.assertKept(q, ["ev_revenue_multiple"], claim("ev_revenue_multiple", "multiple", 4.0, q, "2025"))

    def test_growth_to_a_level_is_not_a_range(self):
        q = "Revenue grew 7.4% to $12 billion in 2025."
        self.assertKept(q, ["revenue_growth", "revenue"], claim("revenue_growth", "percent", 7.4, q, "2025"))
        self.assertKept(q, ["revenue_growth", "revenue"], claim("revenue", "usd_billions", 12, q, "2025"))

    def test_year_range_still_a_period(self):
        q = "The market is projected to grow 9.8% a year in 2025-2030."
        self.assertKept(q, ["revenue_growth"], claim("revenue_growth", "percent", 9.8, q, "2025-2030"))


class R1UnicodeDigits(ValidatorCase):
    """R1-04: NFKC turns fractions and superscripts into ASCII digits, and non-ASCII separators split numbers."""

    def test_vulgar_fraction(self):
        q = "The market grew 1\u00bd% in 2025."
        self.assertDropped(q, ["revenue_growth"], claim("revenue_growth", "percent", 2, q, "2025"))
        self.assertDropped(q, ["revenue_growth"], claim("revenue_growth", "percent", 11, q, "2025"))

    def test_superscript_footnote_joins_the_number(self):
        q = "Corvane trades at 4.2\u00b9x EV/revenue."
        self.assertDropped(q, ["ev_revenue_multiple"], claim("ev_revenue_multiple", "multiple", 4.21, q))

    def test_arabic_decimal_separator(self):
        q = "Corvane trades at 4\u066b2x EV/revenue."
        self.assertDropped(q, ["ev_revenue_multiple"], claim("ev_revenue_multiple", "multiple", 2, q))

    def test_arabic_indic_digits(self):
        q = "Corvane trades at \u0664.\u0662x EV/revenue."
        self.assertDropped(q, ["ev_revenue_multiple"], claim("ev_revenue_multiple", "multiple", 4.2, q))

    def test_fraction_slash(self):
        for q in ("The market grew 1/2% in 2025.", "The market grew 1\u20442% in 2025."):
            self.assertDropped(q, ["revenue_growth"], claim("revenue_growth", "percent", 2, q, "2025"))

    def test_circled_digit(self):
        q = "Corvane trades at \u2463x EV/revenue."
        self.assertDropped(q, ["ev_revenue_multiple"], claim("ev_revenue_multiple", "multiple", 4, q))

    def test_any_separator_lookalike_between_digits(self):
        for sep in ("\u2027", "\u2024\u2024", "\u02d9", "\u0387", "\u30fb", "\u00d7"):
            q = "Corvane trades at 4%s2x EV/revenue." % sep
            self.assertDropped(q, ["ev_revenue_multiple"], claim("ev_revenue_multiple", "multiple", 2, q))

    def test_invisible_character_inside_a_number(self):
        q = "Revenue grew 1\u200b4.2% in 2025."
        self.assertDropped(q, ["revenue_growth"], claim("revenue_growth", "percent", 4.2, q, "2025"))
        self.assertKept(q, ["revenue_growth"], claim("revenue_growth", "percent", 14.2, q, "2025"))

    def test_bidi_override_reverses_what_the_reader_sees(self):
        q = "Revenue grew \u202e2.41\u202c% in 2025."
        for v in (2.41, 14.2):
            self.assertDropped(q, ["revenue_growth"], claim("revenue_growth", "percent", v, q, "2025"))

    def test_fullwidth_digits_still_ok(self):
        q = "Corvane trades at \uff14.\uff12x EV/revenue."
        self.assertKept(q, ["ev_revenue_multiple"], claim("ev_revenue_multiple", "multiple", 4.2, q))


class R1Separators(ValidatorCase):
    """R1-05: digit grouping the scanner does not understand yields a partial number."""

    def test_space_thousands(self):
        for sep in (" ", "\u00a0", "\u202f", "\u2009"):
            q = "The firm employs 4%s200 people." % sep
            self.assertDropped(q, ["employees"], claim("employees", "count", 200, q))
            self.assertDropped(q, ["employees"], claim("employees", "count", 4, q))

    def test_apostrophe_thousands(self):
        for sep in ("'", "\u2019"):
            q = "The firm employs 1%s234 people." % sep
            self.assertDropped(q, ["employees"], claim("employees", "count", 234, q))

    def test_bad_grouping(self):
        q = "The firm employs 1,2345 people."
        self.assertDropped(q, ["employees"], claim("employees", "count", 1234, q))

    def test_european_decimal_comma(self):
        q = "Headcount: 12,50 thousand."
        self.assertDropped(q, ["employees"], claim("employees", "count", 12, q))
        q = "Corvane trades at 4,2x EV/revenue."
        self.assertDropped(q, ["ev_revenue_multiple"], claim("ev_revenue_multiple", "multiple", 4.2, q))
        self.assertDropped(q, ["ev_revenue_multiple"], claim("ev_revenue_multiple", "multiple", 2, q))

    def test_european_thousands_dot_is_not_a_fractional_count(self):
        q = "The firm employs 1.234 people."
        self.assertDropped(q, ["employees"], claim("employees", "count", 1.234, q))

    def test_normal_grouping_still_ok(self):
        q = "The firm employs 12,500 people."
        self.assertKept(q, ["employees"], claim("employees", "count", 12500, q))


class R1ScaleWords(ValidatorCase):
    """R1-06: scale words outside million/billion/thousand are read as plain dollars or counts."""

    def test_unlisted_scales_are_not_plain_usd(self):
        for q, v in (("Card volume hit $4.2 trillion in 2025.", 4.2), ("Card volume hit $4.2tn in 2025.", 4.2),
                     ("The market was $4.2 bln in 2025.", 4.2), ("The market was $4.2 mln in 2025.", 4.2),
                     ("Revenue was $412MM in 2025.", 412), ("Revenue was $412 mil in 2025.", 412),
                     ("Revenue was $412K in 2025.", 412), ("Revenue was $4.2 crore in 2025.", 4.2)):
            self.assertDropped(q, ["market_size"], claim("market_size", "usd", v, q, "2025"))

    def test_scale_word_on_count(self):
        q = "The network reaches 4.2 million merchants."
        self.assertDropped(q, ["employees"], claim("employees", "count", 4.2, q))

    def test_plain_usd_still_ok(self):
        q = "EBITDA was $250,000 in 2025."
        self.assertKept(q, ["ebitda"], claim("ebitda", "usd", 250000, q, "2025"))


class R1HugeNumbers(ValidatorCase):
    """R1-14: an unbounded digit string passes into the Planner's typed values (a channel from web text)."""

    def test_long_digit_string_rejected(self):
        digits = "7365617263682070726f6a656374".replace("f", "1").replace("a", "2")
        q = "The network reaches %s merchants." % digits
        self.assertDropped(q, ["employees"], claim("employees", "count", int(digits), q))


class R1ComposerDuplicates(unittest.TestCase):
    """R1-07: one quoted number claimed under several subjects is counted as several companies in the median."""

    QUOTE = "Corvane Pay ended 2025 trading at 4.2x EV/revenue."
    NEEDS = [{"need": "peer_ev_revenue", "claim_types": ["ev_revenue_multiple"], "label": "Peers"}]
    SOURCES = {"r_03": {"url": "https://a.example.com", "title": "a"},
               "r_05": {"url": "https://b.example.com", "title": "b"},
               "r_07": {"url": "https://c.example.com", "title": "c"}}

    def base(self, **kw):
        c = {"claim_type": "ev_revenue_multiple", "subject": "Corvane Pay", "value": 4.2, "unit": "multiple",
             "period": "2025", "quote": self.QUOTE, "document_id": "r_03"}
        c.update(kw)
        return c

    def quillon(self):
        return {"claim_type": "ev_revenue_multiple", "subject": "Quillon Transact", "value": 3.5, "unit": "multiple",
                "period": "2025", "quote": "Quillon Transact trades at 3.5x EV/revenue on 2025 revenue.",
                "document_id": "r_05"}

    def test_same_quote_other_subjects(self):
        kept = [self.base(subject=s) for s in ("Corvane Pay", "Corvane", "Corvane Pay Inc.")] + [self.quillon()]
        out = reader.compose("q", self.NEEDS, kept, self.SOURCES)
        self.assertEqual(out["needs"][0]["headline"]["method"], "median of 2 companies")
        self.assertEqual(out["needs"][0]["headline"]["value"], 3.85)

    def test_overlapping_quote_same_number(self):
        kept = [self.base(), self.base(subject="Corvane", quote="trading at 4.2x EV/revenue."), self.quillon()]
        out = reader.compose("q", self.NEEDS, kept, self.SOURCES)
        self.assertEqual(out["needs"][0]["headline"]["method"], "median of 2 companies")

    def test_same_sentence_syndicated_in_two_documents(self):
        kept = [self.base(), self.base(subject="Corvane Pay plc", document_id="r_07"), self.quillon()]
        out = reader.compose("q", self.NEEDS, kept, self.SOURCES)
        self.assertEqual(out["needs"][0]["headline"]["method"], "median of 2 companies")


class R1SubjectNumbers(unittest.TestCase):
    """R1-08: digits in the model-written subject reach the answer text (invariant 8)."""

    def test_subject_number_not_in_quote_is_not_printed(self):
        c = {"claim_type": "ev_revenue_multiple", "subject": "peer median 9.9x per analysts; Corvane Pay",
             "value": 4.2, "unit": "multiple", "period": "2025",
             "quote": "Corvane Pay ended 2025 trading at 4.2x EV/revenue.", "document_id": "r_03"}
        needs = [{"need": "peer_ev_revenue", "claim_types": ["ev_revenue_multiple"], "label": "Peers"}]
        out = reader.compose("q", needs, [c], {"r_03": {"url": "https://a.example.com", "title": "a"}})
        self.assertNotIn("9.9", out["text"])
        self.assertNotIn("9.9", json.dumps(out["needs"]))

    def test_subject_number_from_quote_is_fine(self):
        c = {"claim_type": "revenue_growth", "subject": "2025 merchant acquiring revenue", "value": 7.4,
             "unit": "percent", "period": "2025",
             "quote": "Merchant acquiring revenue grew 7.4% in 2025, according to the survey.", "document_id": "r_02"}
        needs = [{"need": "sector_growth", "claim_types": ["revenue_growth"], "label": "Growth"}]
        out = reader.compose("q", needs, [c], {"r_02": {"url": "https://a.example.com", "title": "a"}})
        self.assertEqual(out["needs"][0]["items"][0]["subject"], "2025 merchant acquiring revenue")


class R1ClaimTypesChannel(unittest.TestCase):
    """R1-11: order and repetition of claim_types reach api.anthropic.com verbatim, a channel the Planner controls."""

    def allowed_block(self, types):
        j = fx.page("j01_sector_growth.json")
        j["claim_types"] = types
        content = reader.build_request(j)["messages"][0]["content"]
        return content.split("<allowed_claim_types>")[1].split("</allowed_claim_types>")[0]

    def test_repetition_and_order_do_not_change_the_body(self):
        a = self.allowed_block(["revenue_growth", "market_size"])
        b = self.allowed_block(["market_size", "revenue_growth", "revenue_growth", "market_size", "market_size"])
        self.assertEqual(a, b)


class R1JobIds(unittest.TestCase):
    """R1-12: document and job ids are not format-checked, so a session id or need id can ride into the body."""

    def test_document_id_must_be_a_result_id(self):
        for bad in ("s_dtreal1", "sector_growth", "r_1", "r_001", "R_01"):
            j = fx.page("j01_sector_growth.json")
            j["documents"][0]["id"] = bad
            with self.assertRaises(ValueError, msg=bad):
                reader.build_request(j)

    def test_job_id_must_be_a_job_id(self):
        for bad in ("s_dtreal1", "sector_growth", 7):
            j = fx.page("j01_sector_growth.json")
            j["job"] = bad
            with self.assertRaises(ValueError, msg=repr(bad)):
                reader.build_request(j)


class R1ParseNeverRaises(unittest.TestCase):
    """R1-13: deeply nested model output raises RecursionError instead of dropping the response."""

    def test_deep_nesting(self):
        text = '{"claims":[' + "[" * 100000 + "]" * 100000 + "]}"
        self.assertEqual(reader.parse_response({}, {"content": [{"type": "text", "text": text}]}), [])


if __name__ == "__main__":
    unittest.main()
