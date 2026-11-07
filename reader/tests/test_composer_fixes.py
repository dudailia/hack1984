"""Composer fixes: forecast tense, aggregates kept out of the peer median, one value per company, no repeated ids."""
import datetime
import re
import unittest

import reader

TODAY = datetime.date(2026, 11, 7)
GROWTH = [{"need": "sector_growth", "label": "Sector growth", "claim_types": ["revenue_growth", "market_size"]}]
PEERS = [{"need": "peer_ev_revenue", "label": "Peers", "claim_types": ["ev_revenue_multiple"]}]


def src(*ids):
    return {i: {"url": "https://%s.example.com" % i, "title": i} for i in ids}


def growth(subject, value, period, quote, doc="r_01"):
    return {"claim_type": "revenue_growth", "subject": subject, "value": value, "unit": "percent", "period": period,
            "quote": quote, "document_id": doc}


def multiple(subject, value, doc, quote=None, period="2025"):
    return {"claim_type": "ev_revenue_multiple", "subject": subject, "value": value, "unit": "multiple",
            "period": period, "quote": quote or "%s trades at %sx EV/revenue in %s." % (subject, value, period),
            "document_id": doc}


def cites(text):
    return [re.findall(r"r_\d+", c) for c in re.findall(r"\[([^\]]*)\]", text)]


class TenseTest(unittest.TestCase):
    def text(self, claim, today=TODAY):
        return reader.compose("q", GROWTH, [claim], src(claim["document_id"]), today=today)["text"]

    def test_future_range_without_forecast_word(self):
        t = self.text(growth("global payments market", 9.8, "2025-2030",
                             "The global payments market grows at a 9.8% CAGR from 2025 to 2030."))
        self.assertIn("is projected to grow 9.8% a year from 2025 to 2030", t)
        self.assertNotIn("grew", t)

    def test_future_single_year(self):
        t = self.text(growth("merchant acquiring revenue", 6, "2027", "Merchant acquiring revenue rises 6% in 2027."))
        self.assertIn("is projected to grow 6% in 2027", t)
        self.assertNotIn("grew", t)

    def test_forecast_words_with_a_past_or_current_period(self):
        for quote in ("Revenue is projected to rise 5% in 2025.", "Revenue is expected to rise 5% in 2025.",
                      "Analysts forecast 5% growth in 2025.", "Revenue will grow 5% in 2025.",
                      "The 2025 forecast is 5% growth.", "Revenue growth was forecasted at 5% in 2025."):
            with self.subTest(quote=quote):
                t = self.text(growth("revenue", 5, "2025", quote))
                self.assertIn("is projected to grow 5% in 2025", t)
                self.assertNotIn("grew", t)

    def test_past_stays_past(self):
        t = self.text(growth("merchant acquiring revenue", 7.4, "2025",
                             "Merchant acquiring revenue grew 7.4% in 2025, according to the survey."))
        self.assertIn("merchant acquiring revenue grew 7.4% in 2025", t)
        t = self.text(growth("card volumes", 5, "2019-2024", "Card volumes grew 5% a year from 2019 to 2024."))
        self.assertIn("card volumes grew 5% a year from 2019 to 2024", t)

    def test_depends_on_today(self):
        c = growth("global payments market", 9.8, "2025-2030",
                   "The global payments market grows at a 9.8% CAGR from 2025 to 2030.")
        self.assertIn("is projected to grow", self.text(c, datetime.date(2026, 1, 1)))
        self.assertIn("grew 9.8% a year from 2025 to 2030", self.text(c, datetime.date(2031, 1, 1)))

    def test_default_today_is_the_system_date(self):
        c = growth("global payments market", 9.8, "2025-2999", "The market grows 9.8% a year from 2025 to 2999.")
        self.assertIn("is projected to grow", reader.compose("q", GROWTH, [c], src("r_01"))["text"])


class AggregateTest(unittest.TestCase):
    def compose(self, kept):
        ids = sorted({c["document_id"] for c in kept})
        return reader.compose("q", PEERS, kept, src(*ids), today=TODAY)

    def test_aggregate_subject_is_context_not_a_company(self):
        kept = [multiple("Corvane Pay", 3.0, "r_01"), multiple("Quillon Transact", 5.0, "r_02"),
                multiple("payments companies median", 4.6, "r_03",
                         "Listed payments companies trade at a median 4.6x EV/revenue in 2025.")]
        out = self.compose(kept)
        need = out["needs"][0]
        self.assertEqual(need["headline"], {"value": 4.0, "unit": "multiple", "period": "2025",
                                            "method": "median of 2 companies"})
        self.assertIn("across 2 companies [r_01, r_02]", out["text"])
        self.assertIn("context: payments companies median 4.6x EV/revenue for 2025 [r_03]", out["text"])
        self.assertEqual(len(need["items"]), 3, "the aggregate is still shown, with its quote and source")

    def test_each_aggregate_word(self):
        for subject in ("sector average", "peer mean", "payments index", "payments sector", "industry",
                        "listed payments companies", "Median of peers", "AVERAGE"):
            with self.subTest(subject=subject):
                kept = [multiple("Corvane Pay", 3.0, "r_01"), multiple("Quillon Transact", 5.0, "r_02"),
                        multiple(subject, 9.0, "r_03", "The figure is 9.0x EV/revenue in 2025.")]
                out = self.compose(kept)
                self.assertEqual(out["needs"][0]["headline"]["method"], "median of 2 companies")
                self.assertEqual(out["needs"][0]["headline"]["value"], 4.0)

    def test_aggregate_in_the_quote_only(self):
        kept = [multiple("Corvane Pay", 3.0, "r_01"), multiple("Quillon Transact", 5.0, "r_02"),
                multiple("Sabrefield Pay", 9.0, "r_03", "Sabrefield Pay trades at 9.0x, far above the sector median.")]
        out = self.compose(kept)
        self.assertEqual(out["needs"][0]["headline"]["method"], "median of 2 companies")
        self.assertIn("context: Sabrefield Pay 9.0x EV/revenue for 2025 [r_03]", out["text"])

    def test_company_names_containing_the_words_are_companies(self):
        kept = [multiple("Indexa Pay", 3.0, "r_01"), multiple("Sectorial Payments", 5.0, "r_02")]
        self.assertEqual(self.compose(kept)["needs"][0]["headline"]["method"], "median of 2 companies")

    def test_one_company_and_aggregates_has_no_headline(self):
        kept = [multiple("Corvane Pay", 3.0, "r_01"), multiple("sector median", 4.6, "r_02")]
        out = self.compose(kept)
        self.assertIsNone(out["needs"][0]["headline"])
        self.assertNotIn("across", out["text"])

    def test_growth_need_keeps_sector_facts(self):
        c = growth("payments sector", 5, "2025", "The payments sector grew 5% in 2025.")
        t = reader.compose("q", GROWTH, [c], src("r_01"), today=TODAY)["text"]
        self.assertIn("payments sector grew 5% in 2025 [r_01]", t)
        self.assertNotIn("context", t)


class PerCompanyDedupeTest(unittest.TestCase):
    def compose(self, kept):
        ids = sorted({c["document_id"] for c in kept})
        return reader.compose("q", PEERS, kept, src(*ids), today=TODAY)

    def test_one_value_per_company(self):
        kept = [multiple("Corvane Pay", 4.2, "r_03"), multiple("Corvane Pay Inc.", 4.4, "r_09"),
                multiple("Quillon Transact", 3.5, "r_05")]
        out = self.compose(kept)
        need = out["needs"][0]
        self.assertEqual(need["headline"]["method"], "median of 2 companies")
        self.assertEqual(need["headline"]["value"], 3.85)
        self.assertEqual(sorted(i["value"] for i in need["items"]), [3.5, 4.2])

    def test_normalised_names(self):
        for other in ("CORVANE PAY, INC.", "Corvane Pay plc", "Corvane Pay's", "Corvane", "corvane  pay ltd",
                      "Corvane Pay Holdings", "Corvane Pay Corp."):
            with self.subTest(other=other):
                kept = [multiple("Corvane Pay", 4.2, "r_03"), multiple(other, 4.9, "r_09"),
                        multiple("Quillon Transact", 3.5, "r_05")]
                self.assertEqual(self.compose(kept)["needs"][0]["headline"]["method"], "median of 2 companies")

    def test_different_companies_with_a_shared_first_word_stay_apart(self):
        kept = [multiple("Corvane Pay", 4.2, "r_03"), multiple("Corvane Lending", 2.0, "r_04"),
                multiple("Quillon Transact", 3.5, "r_05")]
        self.assertEqual(self.compose(kept)["needs"][0]["headline"]["method"], "median of 3 companies")

    def test_aggregate_never_swallows_a_company(self):
        kept = [multiple("payments companies median", 4.6, "r_01",
                         "Listed payments companies trade at a median 4.6x EV/revenue in 2025."),
                multiple("Payments", 3.0, "r_02"), multiple("Quillon Transact", 5.0, "r_03")]
        need = self.compose(kept)["needs"][0]
        self.assertEqual(len(need["items"]), 3)
        self.assertEqual(need["headline"]["method"], "median of 2 companies")

    def test_other_period_is_another_fact(self):
        kept = [multiple("Corvane Pay", 4.2, "r_03"), multiple("Corvane Pay", 3.9, "r_04", period="2024"),
                multiple("Quillon Transact", 3.5, "r_05")]
        need = self.compose(kept)["needs"][0]
        self.assertEqual(len(need["items"]), 3)
        self.assertEqual(need["headline"]["method"], "median of 2 companies")

    def test_reproduce_aayush_two_items_from_r22_plus_an_aggregate(self):
        aggregate = multiple("listed payments companies", 4.6, "r_23",
                             "Listed payments companies trade at a median 4.6x EV/revenue in 2025.")
        # same company twice on r_22: one company, so no median at all
        same = [multiple("Corvane Pay", 4.2, "r_22", "Corvane Pay trades at 4.2x EV/revenue in 2025."),
                multiple("Corvane Pay Inc.", 4.4, "r_22", "Corvane Pay Inc. shares imply 4.4x EV/revenue in 2025."),
                aggregate]
        out = self.compose(same)
        self.assertNotIn("across 3 companies", out["text"])
        self.assertIsNone(out["needs"][0]["headline"])
        # two different companies on r_22: two companies, r_22 cited once
        two = [multiple("Corvane Pay", 4.2, "r_22", "Corvane Pay trades at 4.2x EV/revenue in 2025."),
               multiple("Quillon Transact", 3.5, "r_22", "Quillon Transact trades at 3.5x EV/revenue in 2025."),
               aggregate]
        out = self.compose(two)
        self.assertNotIn("across 3 companies", out["text"])
        self.assertIn("median EV/revenue 3.85x for 2025 across 2 companies [r_22]", out["text"])
        for ids in cites(out["text"]):
            self.assertEqual(len(ids), len(set(ids)), out["text"])

    def test_no_citation_list_repeats_an_id(self):
        kept = [multiple("A Pay", 3.0, "r_01"), multiple("B Pay", 4.0, "r_01"), multiple("C Pay", 5.0, "r_02"),
                multiple("D Pay", 6.0, "r_02")]
        out = self.compose(kept)
        self.assertIn("across 4 companies [r_01, r_02]", out["text"])
        for ids in cites(out["text"]):
            self.assertEqual(len(ids), len(set(ids)))


class ReviewGapsTest(unittest.TestCase):
    """Review of PR #18: more aggregate wordings, and a leading article in a company name."""

    def compose(self, kept):
        ids = sorted({c["document_id"] for c in kept})
        return reader.compose("q", PEERS, kept, src(*ids), today=TODAY)

    def two_and(self, extra):
        kept = [multiple("Corvane Pay", 3.0, "r_01"), multiple("Quillon Transact", 5.0, "r_02"), extra]
        return self.compose(kept)["needs"][0]["headline"]

    def test_more_aggregate_subjects(self):
        for subject in ("payments peers", "peer group", "listed comps", "comparables", "S&P 500 payments benchmark",
                        "payments composite", "fintech basket", "peer cohort", "coverage universe", "payments ETF",
                        "payments market", "payments segment"):
            with self.subTest(subject=subject):
                h = self.two_and(multiple(subject, 9.0, "r_03", "The figure is 9.0x EV/revenue in 2025."))
                self.assertEqual((h["method"], h["value"]), ("median of 2 companies", 4.0))

    def test_peers_in_the_quote_only(self):
        h = self.two_and(multiple("Sabrefield Pay", 9.0, "r_03", "Listed peers trade at 9.0x EV/revenue in 2025."))
        self.assertEqual(h["method"], "median of 2 companies")

    def test_market_in_a_quote_is_still_a_company(self):
        h = self.two_and(multiple("Sabrefield Pay", 9.0, "r_03",
                                  "Sabrefield Pay trades at 9.0x EV/revenue in 2025 at its market value."))
        self.assertEqual(h["method"], "median of 3 companies")

    def test_names_containing_the_new_words_are_companies(self):
        for subject in ("Peerless Pay", "Marketa", "Basketo Payments"):
            with self.subTest(subject=subject):
                self.assertEqual(self.two_and(multiple(subject, 9.0, "r_03"))["method"], "median of 3 companies")

    def test_withheld_subject_is_not_a_company(self):
        out = self.compose([multiple("Corvane Pay", 3.0, "r_01"), multiple("Quillon Transact", 5.0, "r_02"),
                            multiple("Fund 7", 9.0, "r_03", "The figure is 9.0x EV/revenue in 2025.")])
        self.assertEqual(out["needs"][0]["headline"]["method"], "median of 2 companies")
        self.assertIn("context: [subject withheld] 9.0x EV/revenue for 2025 [r_03]", out["text"])

    def test_leading_article_is_the_same_company(self):
        kept = [multiple("the Corvane Pay", 3.5, "r_01"), multiple("Corvane Pay", 4.5, "r_02"),
                multiple("Quillon Transact", 5.0, "r_03")]
        self.assertEqual(self.compose(kept)["needs"][0]["headline"]["method"], "median of 2 companies")


if __name__ == "__main__":
    unittest.main()
