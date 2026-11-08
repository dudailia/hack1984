"""The real estate claim types (FORMATS §1): cap_rate, vacancy_rate, interest_rate (percent) and price_per_sqft
(usd). Existing units only, so the number rules are the existing ones; the composer words them as levels, never as
growth. Halyard behaviour is covered, unchanged, by the other composer tests."""
import unittest

import reader
from reader.schema import CLAIM_UNITS

TODAY = __import__("datetime").date(2026, 11, 8)


def job(text, types):
    return {"job": "j_01", "public_query": "office cap rates 2026", "claim_types": types,
            "documents": [{"id": "r_01", "url": "https://x.example.com", "title": "t", "text": text}]}


def claim(ctype, unit, value, quote, period="2025", subject="US industrial", doc="r_01"):
    return {"claim_type": ctype, "subject": subject, "value": value, "unit": unit, "period": period,
            "quote": quote, "document_id": doc}


def sources(*ids):
    return {i: {"url": "https://%s.example.com" % i, "title": i} for i in ids}


class TestSchema(unittest.TestCase):
    def test_units(self):
        self.assertEqual(CLAIM_UNITS["cap_rate"], ("percent",))
        self.assertEqual(CLAIM_UNITS["vacancy_rate"], ("percent",))
        self.assertEqual(CLAIM_UNITS["interest_rate"], ("percent",))
        self.assertEqual(CLAIM_UNITS["price_per_sqft"], ("usd",))
        self.assertEqual(len(CLAIM_UNITS), 12)


class TestValidate(unittest.TestCase):
    def kept(self, text, types, c):
        kept, dropped = reader.validate(job(text, types), [c])
        return kept, dropped

    def test_cap_rate_percent_kept(self):
        q = "US industrial cap rates averaged 5.4% in 2025."
        kept, _ = self.kept(q, ["cap_rate"], claim("cap_rate", "percent", 5.4, q))
        self.assertEqual(len(kept), 1)

    def test_vacancy_and_interest_kept(self):
        q = "National office vacancy reached 19.8 percent in 2025, while new loans priced at 6.25% in 2025."
        kept, dropped = reader.validate(job(q, ["vacancy_rate", "interest_rate"]), [
            claim("vacancy_rate", "percent", 19.8, q, subject="US office"),
            claim("interest_rate", "percent", 6.25, q, subject="new commercial real estate loans")])
        self.assertEqual((len(kept), dropped), (2, []))

    def test_price_per_sqft_kept(self):
        q = "Comparable waterfront offices sold for $425 per square foot in 2025."
        kept, _ = self.kept(q, ["price_per_sqft"], claim("price_per_sqft", "usd", 425, q))
        self.assertEqual(len(kept), 1)

    def test_wrong_unit_dropped(self):
        q = "US industrial cap rates averaged 5.4% in 2025."
        kept, dropped = self.kept(q, ["cap_rate"], claim("cap_rate", "usd", 5.4, q))
        self.assertEqual(kept, [])
        self.assertEqual(len(dropped), 1)

    def test_type_not_in_job_dropped(self):
        q = "US industrial cap rates averaged 5.4% in 2025."
        kept, _ = self.kept(q, ["vacancy_rate"], claim("cap_rate", "percent", 5.4, q))
        self.assertEqual(kept, [])

    def test_request_lists_the_new_types(self):
        body = reader.build_request(job("x", ["price_per_sqft", "cap_rate"]))
        text = str(body)
        self.assertIn("cap_rate: percent", text)
        self.assertIn("price_per_sqft: usd", text)


class TestComposer(unittest.TestCase):
    def compose(self, needs, kept, ids=("r_01", "r_02", "r_03")):
        return reader.compose("q?", needs, kept, sources(*ids), today=TODAY)

    def test_rates_are_levels_not_growth(self):
        kept = [claim("cap_rate", "percent", 5.4, "US industrial cap rates averaged 5.4% in 2025."),
                claim("vacancy_rate", "percent", 7.1, "US industrial vacancy was 7.1% in 2025.", doc="r_02"),
                claim("interest_rate", "percent", 6.25, "New CRE loans priced at 6.25% in 2025.",
                      subject="new commercial real estate loans", doc="r_03")]
        out = self.compose([{"need": "re_cap_rates", "claim_types": ["cap_rate", "vacancy_rate"],
                             "label": "Cap rates and vacancy"},
                            {"need": "re_lending_rates", "claim_types": ["interest_rate"],
                             "label": "CRE lending rates"}], kept)
        t = out["text"]
        self.assertIn("US industrial (cap rate): 5.4% for 2025 [r_01]", t)
        self.assertIn("US industrial (vacancy): 7.1% for 2025 [r_02]", t)
        self.assertIn("new commercial real estate loans (interest rate): 6.25% for 2025 [r_03]", t)
        self.assertNotIn("grew", t)
        self.assertNotIn("projected", t)
        self.assertTrue(t.startswith("Cap rates and vacancy: "), t)
        self.assertIsNone(out["needs"][0]["headline"])

    def test_label_not_repeated_when_the_subject_says_it(self):
        kept = [claim("cap_rate", "percent", 5.4, "Manhattan Class A office cap rates were 5.4% in 2025.",
                      subject="Manhattan Class A office cap rate")]
        t = self.compose([{"need": "re_cap_rates", "claim_types": ["cap_rate"]}], kept)["text"]
        self.assertIn("Manhattan Class A office cap rate: 5.4% for 2025", t)
        self.assertNotIn("(cap rate)", t)

    def test_price_per_sqft(self):
        kept = [claim("price_per_sqft", "usd", 425, "Comparable offices sold for $425 per square foot in 2025.",
                      subject="comparable waterfront office sales")]
        t = self.compose([{"need": "re_comps", "claim_types": ["price_per_sqft"], "label": "Comparable sales"}],
                         kept)["text"]
        self.assertEqual(t, "Comparable sales: comparable waterfront office sales: $425 per sq ft for 2025 [r_01].")

    def test_markets_are_not_merged_like_companies(self):
        # "office" and "office Manhattan" would be one company for multiples; for rates they are two markets
        kept = [claim("cap_rate", "percent", 6.1, "US office cap rates were 6.1% in 2025.", subject="US office"),
                claim("cap_rate", "percent", 5.4, "US office Manhattan cap rates were 5.4% in 2025.",
                      subject="US office Manhattan", doc="r_02")]
        out = self.compose([{"need": "re_cap_rates", "claim_types": ["cap_rate"]}], kept)
        self.assertEqual(len(out["needs"][0]["items"]), 2)

    def test_cost_subject_is_kept_for_levels(self):
        kept = [claim("price_per_sqft", "usd", 180, "Bulk warehouses cost $180 per square foot to build in 2025.",
                      subject="bulk warehouse construction cost")]
        out = self.compose([{"need": "re_comps", "claim_types": ["price_per_sqft"]}], kept)
        self.assertEqual(out["needs"][0]["status"], "found")


if __name__ == "__main__":
    unittest.main()
