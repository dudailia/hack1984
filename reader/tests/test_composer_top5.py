"""Composer growth section: at most 5 growth facts, actual figures before projections, latest period first within
each group, expense subjects excluded.

Fixture: 8 validated growth facts, 6 about revenue or volume and 2 about expenses. The expense facts have the
latest period, so a cap alone would show them first; they must be excluded, not just pushed down. All fictional.
"""
import datetime
import unittest

import reader

TODAY = datetime.date(2026, 11, 7)
GROWTH = [{"need": "sector_growth", "label": "Sector growth", "claim_types": ["revenue_growth"]}]


def fact(doc, subject, value, period, quote):
    return {"claim_type": "revenue_growth", "subject": subject, "value": value, "unit": "percent", "period": period,
            "quote": quote, "document_id": doc}


EIGHT = [
    fact("r_01", "merchant acquiring revenue", 7.4, "2025", "Merchant acquiring revenue grew 7.4% in 2025."),
    fact("r_02", "card volumes", 5, "2019-2024", "Card volumes grew 5% a year from 2019 to 2024."),
    fact("r_03", "Operating expense", 9, "2026", "Operating expense growth was 9% in 2026."),
    fact("r_04", "payments processing revenue", 6.1, "2023", "Payments processing revenue grew 6.1% in 2023."),
    fact("r_05", "global payments market", 9.8, "2025-2030",
         "The global payments market is projected to grow at a 9.8% CAGR from 2025 to 2030."),
    fact("r_06", "Card processing costs", 4.2, "2026", "Card processing costs rose 4.2% in 2026."),
    fact("r_07", "acquirer revenue", 8.3, "2024", "Acquirer revenue grew 8.3% in 2024."),
    fact("r_08", "cross-border volumes", 11.5, "2022", "Cross-border volumes grew 11.5% in 2022."),
]
PROJECTION_2026 = fact("r_09", "issuer processing revenue", 6.5, "2026",
                       "Issuer processing revenue is expected to grow 6.5% in 2026.")
SOURCES = {f["document_id"]: {"url": "https://%s.example.com" % f["document_id"], "title": f["document_id"]}
           for f in EIGHT}


def compose(facts, today=TODAY):
    return reader.compose("payments sector growth", GROWTH, facts, SOURCES, today=today)


class GrowthTopFiveTest(unittest.TestCase):
    def setUp(self):
        self.out = compose(EIGHT)
        self.items = self.out["needs"][0]["items"]

    def test_at_most_five_actuals_first_latest_first_without_expenses(self):
        self.assertEqual([(i["subject"], i["period"]) for i in self.items], [
            ("merchant acquiring revenue", "2025"),
            ("acquirer revenue", "2024"),
            ("card volumes", "2019-2024"),
            ("payments processing revenue", "2023"),
            ("cross-border volumes", "2022"),
        ], "five actuals fill the section; the 2025-2030 projection is sixth and cut")

    def test_projections_after_actuals_latest_first(self):
        facts = [f for f in EIGHT if f["document_id"] in ("r_02", "r_05", "r_07")] + [PROJECTION_2026]
        sources = dict(SOURCES, r_09={"url": "https://r_09.example.com", "title": "r_09"})
        items = reader.compose("q", GROWTH, facts, sources, today=TODAY)["needs"][0]["items"]
        self.assertEqual([(i["period"], i["value"]) for i in items],
                         [("2024", 8.3), ("2019-2024", 5), ("2025-2030", 9.8), ("2026", 6.5)])

    def test_text_matches_the_items(self):
        text = self.out["text"]
        order = ["7.4%", "8.3%", "5%", "6.1%", "11.5%"]
        positions = [text.index(v) for v in order]
        self.assertEqual(positions, sorted(positions), text)
        for absent in ("9.8", "Operating expense", "costs", "r_03", "r_05", "r_06"):
            self.assertNotIn(absent, text)

    def test_numbers_are_the_validated_values(self):
        by_doc = {f["document_id"]: f["value"] for f in EIGHT}
        for i in self.items:
            self.assertEqual(i["value"], by_doc[i["source"]["result_id"]])

    def test_expense_words(self):
        for subject in ("Operating expense", "operating expenses", "Opex", "marketing spending", "Card processing costs",
                        "cost of revenue", "Total COST"):
            with self.subTest(subject=subject):
                out = compose([fact("r_01", subject, 9, "2025", "%s grew 9%% in 2025." % subject)])
                self.assertEqual(out["needs"][0]["items"], [])
                self.assertEqual(out["needs"][0]["status"], "not_found")
                self.assertEqual(out["text"], "Sector growth: not found.")

    def test_similar_words_are_not_expenses(self):
        for subject in ("Costco revenue", "spendable income", "expensive card segment"):
            with self.subTest(subject=subject):
                out = compose([fact("r_01", subject, 9, "2025", "%s grew 9%% in 2025." % subject)])
                self.assertEqual(len(out["needs"][0]["items"]), 1)

    def test_five_or_fewer_are_all_shown(self):
        revenue = [f for f in EIGHT if f["document_id"] in ("r_01", "r_02", "r_04")]
        self.assertEqual([i["period"] for i in compose(revenue)["needs"][0]["items"]], ["2025", "2019-2024", "2023"])

    def test_other_needs_are_not_capped(self):
        peers = [{"need": "peers", "label": "Peers", "claim_types": ["ev_revenue_multiple"]}]
        claims = [{"claim_type": "ev_revenue_multiple", "subject": "Company %s" % c, "value": 2 + n,
                   "unit": "multiple", "period": "2025", "quote": "Company %s trades at %dx EV/revenue." % (c, 2 + n),
                   "document_id": "r_%02d" % (n + 1)} for n, c in enumerate("ABCDEFG")]
        srcs = {c["document_id"]: {"url": "u", "title": "t"} for c in claims}
        out = reader.compose("q", peers, claims, srcs, today=TODAY)
        self.assertEqual(len(out["needs"][0]["items"]), 7)


if __name__ == "__main__":
    unittest.main()
