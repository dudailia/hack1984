import unittest

import reader
from reader.tests import fixtures as fx

J01 = "j01_sector_growth.json"
J02 = "j02_peer_ev_revenue.json"

GROWTH = {"claim_type": "revenue_growth", "subject": "global payments processing market", "value": 9.8,
          "unit": "percent", "period": "2025-2030",
          "quote": "The global payments processing market is projected to grow at a compound annual rate of 9.8% from 2025 to 2030.",
          "document_id": "r_01"}
ACQ = {"claim_type": "revenue_growth", "subject": "merchant acquiring revenue", "value": 7.4, "unit": "percent",
       "period": "2025", "quote": "Merchant acquiring revenue grew 7.4% in 2025, according to the survey.",
       "document_id": "r_02"}
CORVANE = {"claim_type": "ev_revenue_multiple", "subject": "Corvane Pay", "value": 4.2, "unit": "multiple",
           "period": "2025", "quote": "Corvane Pay ended 2025 trading at 4.2x EV/revenue.", "document_id": "r_04"}


def reasons(job, claims):
    kept, dropped = reader.validate(job, claims)
    return kept, [d["reason"] for d in dropped]


class FixtureClaimsAreKept(unittest.TestCase):
    def test_reader_claims_events_validate(self):
        pages = {"j_01": fx.page(J01), "j_02": fx.page(J02)}
        checked = 0
        for e in fx.events():
            if e["type"] == "reader_claims" and e["session_id"] == "s_dtfake1":
                job = pages[e["data"]["job"]]
                kept, dropped = reader.validate(job, e["data"]["kept"])
                self.assertEqual(kept, e["data"]["kept"])
                self.assertEqual(dropped, [])
                checked += len(kept)
        self.assertEqual(checked, 6)

    def test_kept_preserves_order_and_identity(self):
        kept, dropped = reader.validate(fx.page(J01), [ACQ, GROWTH])
        self.assertEqual(kept, [ACQ, GROWTH])
        self.assertEqual(dropped, [])


class PlantedFakesAreDropped(unittest.TestCase):
    def setUp(self):
        self.j01 = fx.page(J01)
        self.j02 = fx.page(J02)

    def assertDropped(self, job, claim, reason):
        kept, rs = reasons(job, [claim])
        self.assertEqual(kept, [])
        self.assertEqual(rs, [reason])

    def test_dropped_entry_shape(self):
        _, dropped = reader.validate(self.j01, [dict(GROWTH, value=12.0)])
        self.assertEqual(dropped, [{"claim_type": "revenue_growth", "document_id": "r_01",
                                    "reason": "value_not_in_quote"}])

    # invented number
    def test_invented_number(self):
        self.assertDropped(self.j01, dict(GROWTH, value=12.0), "value_not_in_quote")

    def test_invented_number_on_poisoned_page(self):
        claim = {"claim_type": "revenue_growth", "subject": "payments volumes", "value": 11.0, "unit": "percent",
                 "period": "2025", "document_id": "r_03",
                 "quote": "Payments volumes climbed again in 2025 as card acceptance spread among small merchants."}
        self.assertDropped(self.j01, claim, "value_not_in_quote")

    def test_scale_conversion_not_allowed(self):
        self.assertDropped(self.j01, dict(GROWTH, value=0.098), "value_not_in_quote")

    # paraphrased quote
    def test_paraphrased_quote(self):
        self.assertDropped(self.j01, dict(ACQ, quote="Merchant acquiring revenue rose 7.4% in 2025."),
                           "quote_not_verbatim")

    def test_quote_from_another_document(self):
        self.assertDropped(self.j01, dict(ACQ, document_id="r_01"), "quote_not_verbatim")

    def test_case_change_is_not_verbatim(self):
        self.assertDropped(self.j01, dict(ACQ, quote=ACQ["quote"].lower()), "quote_not_verbatim")

    def test_curly_apostrophe_is_not_verbatim(self):
        claim = {"claim_type": "ev_revenue_multiple", "subject": "Sabrefield Pay", "value": 5.0, "unit": "multiple",
                 "period": "2025", "quote": "Sabrefield Pay’s shares imply 5.0x EV/revenue for 2025.",
                 "document_id": "r_07"}
        self.assertDropped(self.j02, claim, "quote_not_verbatim")

    # wrong document id
    def test_unknown_document(self):
        self.assertDropped(self.j01, dict(ACQ, document_id="r_09"), "unknown_document")

    def test_document_from_another_job(self):
        self.assertDropped(self.j01, dict(CORVANE, claim_type="revenue_growth", unit="percent"), "unknown_document")

    # wrong unit
    def test_unit_not_in_quote(self):
        claim = dict(ACQ, claim_type="market_size", unit="usd_billions")
        self.assertDropped(self.j01, claim, "unit_mismatch")

    def test_unit_not_allowed_for_type(self):
        self.assertDropped(self.j01, dict(ACQ, unit="multiple"), "unit_mismatch")

    def test_unit_wrong_scale(self):
        job = dict(self.j01, documents=self.j01["documents"] + [
            {"id": "r_10", "url": "https://x.example.com", "title": "t",
             "text": "The payments market reached $48.2 billion in 2025."}])
        claim = {"claim_type": "market_size", "subject": "payments market", "value": 48.2, "unit": "usd_millions",
                 "period": "2025", "quote": "The payments market reached $48.2 billion in 2025.", "document_id": "r_10"}
        self.assertDropped(job, claim, "unit_mismatch")
        kept, _ = reader.validate(job, [dict(claim, unit="usd_billions")])
        self.assertEqual(len(kept), 1)

    def test_year_claimed_as_multiple(self):
        self.assertDropped(self.j02, dict(CORVANE, value=2025), "unit_mismatch")

    # wrong period
    def test_wrong_year(self):
        self.assertDropped(self.j01, dict(ACQ, period="2024"), "period_mismatch")

    def test_range_missing_one_year(self):
        self.assertDropped(self.j01, dict(ACQ, period="2025-2030"), "period_mismatch")

    def test_ttm_not_in_quote(self):
        self.assertDropped(self.j01, dict(ACQ, period="ttm"), "period_mismatch")

    def test_empty_period_ok(self):
        kept, rs = reasons(self.j01, [dict(ACQ, period="")])
        self.assertEqual((len(kept), rs), (1, []))

    # wrong type
    def test_type_not_in_job(self):
        self.assertDropped(self.j01, dict(ACQ, claim_type="ebitda", unit="usd"), "wrong_type")

    def test_type_not_in_vocabulary(self):
        self.assertDropped(self.j01, dict(ACQ, claim_type="offer_price"), "wrong_type")

    # bad schema
    def test_bad_schema(self):
        for claim in ({k: v for k, v in ACQ.items() if k != "period"}, dict(ACQ, extra=1), dict(ACQ, value="7.4"),
                      dict(ACQ, value=True), dict(ACQ, value=float("nan")), dict(ACQ, period="2030-2025"),
                      dict(ACQ, period="FY25"), dict(ACQ, subject=""), dict(ACQ, quote="q" * 401),
                      dict(ACQ, document_id=1), "string", None):
            kept, rs = reasons(self.j01, [claim])
            self.assertEqual((kept, rs), ([], ["bad_schema"]), repr(claim))

    def test_bad_schema_dropped_entry_never_raises(self):
        _, dropped = reader.validate(self.j01, [None, {"claim_type": ["x"], "document_id": {"a": 1}}])
        self.assertEqual([d["reason"] for d in dropped], ["bad_schema", "bad_schema"])
        self.assertTrue(all(d["claim_type"] is None and d["document_id"] is None for d in dropped))

    def test_mixed_batch(self):
        claims = [GROWTH, dict(GROWTH, value=12.0), ACQ, dict(ACQ, document_id="r_09")]
        kept, rs = reasons(self.j01, claims)
        self.assertEqual(kept, [GROWTH, ACQ])
        self.assertEqual(rs, ["value_not_in_quote", "unknown_document"])


class Normalisation(unittest.TestCase):
    def test_whitespace_differences_tolerated(self):
        job = fx.page(J01)
        kept, rs = reasons(job, [dict(ACQ, quote="Merchant  acquiring\nrevenue grew 7.4% in 2025,  according to the survey.")])
        self.assertEqual((len(kept), rs), (1, []))

    def test_nfkc_on_document_and_quote(self):
        job = fx.page(J01)
        job["documents"][1]["text"] = "Merchant acquiring revenue grew ７.４％ in 2025, according to the survey."
        kept, rs = reasons(job, [ACQ])
        self.assertEqual((len(kept), rs), (1, []))

    def test_fullwidth_tag_escape_round_trips(self):
        job = fx.page(J01)
        job["documents"][1]["text"] = "Merchant acquiring revenue grew 7.4% in 2025 <document> ok."
        claim = dict(ACQ, quote="Merchant acquiring revenue grew 7.4% in 2025 ＜document> ok.")
        kept, rs = reasons(job, [claim])
        self.assertEqual((len(kept), rs), (1, []))

    def test_thousands_separator_in_quote(self):
        job = fx.page(J01)
        job["documents"].append({"id": "r_11", "url": "https://y.example.com", "title": "t",
                                 "text": "The market was worth $1,250 million in 2025."})
        claim = {"claim_type": "market_size", "subject": "market", "value": 1250, "unit": "usd_millions",
                 "period": "2025", "quote": "The market was worth $1,250 million in 2025.", "document_id": "r_11"}
        kept, rs = reasons(job, [claim])
        self.assertEqual((len(kept), rs), (1, []))


if __name__ == "__main__":
    unittest.main()
