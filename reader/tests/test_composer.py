import unittest

import reader
from reader.tests import fixtures as fx


def runs():
    """Per session: kept claims, sources from docs_read, and the recorded answer."""
    out = {}
    for e in fx.events():
        sid, d = e["session_id"], e["data"]
        if e["type"] == "docs_read" and d["by"] == "reader":
            r = out.setdefault(sid, {"kept": [], "sources": {}})
            for doc in d["docs"]:
                r["sources"][doc["result_id"]] = {"url": doc["url"], "title": doc["title"]}
        elif e["type"] == "reader_claims":
            out.setdefault(sid, {"kept": [], "sources": {}})["kept"].extend(d["kept"])
        elif e["type"] == "answer":
            out[sid]["answer"] = d
    return {sid: r for sid, r in out.items() if "answer" in r}


class ReproduceRecordedAnswers(unittest.TestCase):
    def test_both_recorded_answers_exactly(self):
        recorded = runs()
        self.assertEqual(set(recorded), {"s_dtfake1", "s_dtreal1"})
        for sid, r in recorded.items():
            got = reader.compose(r["answer"]["question"], fx.needs_with_labels(), r["kept"], r["sources"])
            self.assertEqual(got, r["answer"], sid)

    def test_formats_section_10_example(self):
        r = runs()["s_dtreal1"]
        got = reader.compose(r["answer"]["question"], fx.needs_with_labels(), r["kept"], r["sources"])
        peer = got["needs"][1]
        self.assertEqual(peer["headline"], {"value": 4.6, "unit": "multiple", "period": "2025",
                                            "method": "median of 4 companies"})
        self.assertEqual([i["value"] for i in peer["items"]], [3.5, 4.2, 5.0, 6.1])
        self.assertTrue(got["text"].endswith("median EV/revenue 4.6x for 2025 across 4 companies [r_05, r_03, r_06, r_04]."))


class ComposerRules(unittest.TestCase):
    Q = "q?"
    NEEDS = [{"need": "peer", "label": "Peers", "claim_types": ["ev_revenue_multiple"]}]

    def claim(self, subject, value, doc, period="2025"):
        return {"claim_type": "ev_revenue_multiple", "subject": subject, "value": value, "unit": "multiple",
                "period": period, "quote": "%s trades at %sx in %s." % (subject, value, period), "document_id": doc}

    def sources(self, *ids):
        return {i: {"url": "https://%s.example.com" % i, "title": i} for i in ids}

    def test_odd_median(self):
        kept = [self.claim("A", 3.0, "r_01"), self.claim("B", 9.0, "r_02"), self.claim("C", 4.0, "r_03")]
        got = reader.compose(self.Q, self.NEEDS, kept, self.sources("r_01", "r_02", "r_03"))
        self.assertEqual(got["needs"][0]["headline"]["value"], 4.0)
        self.assertEqual(got["needs"][0]["headline"]["method"], "median of 3 companies")

    def test_median_is_exact_decimal(self):
        kept = [self.claim("A", 4.1, "r_01"), self.claim("B", 4.2, "r_02")]
        got = reader.compose(self.Q, self.NEEDS, kept, self.sources("r_01", "r_02"))
        self.assertEqual(got["needs"][0]["headline"]["value"], 4.15)

    def test_single_company_has_no_headline(self):
        got = reader.compose(self.Q, self.NEEDS, [self.claim("A", 3.0, "r_01")], self.sources("r_01"))
        self.assertIsNone(got["needs"][0]["headline"])
        self.assertIn("A trades at 3.0x EV/revenue for 2025 [r_01]", got["text"])

    def test_median_uses_the_most_common_period(self):
        kept = [self.claim("A", 3.0, "r_01"), self.claim("B", 5.0, "r_02"), self.claim("C", 20.0, "r_03", "2024")]
        got = reader.compose(self.Q, self.NEEDS, kept, self.sources("r_01", "r_02", "r_03"))
        self.assertEqual(got["needs"][0]["headline"], {"value": 4.0, "unit": "multiple", "period": "2025",
                                                       "method": "median of 2 companies"})
        self.assertEqual(len(got["needs"][0]["items"]), 3)

    def test_duplicate_company_counted_once(self):
        kept = [self.claim("A", 3.0, "r_01"), self.claim("a", 3.0, "r_02"), self.claim("B", 5.0, "r_03")]
        got = reader.compose(self.Q, self.NEEDS, kept, self.sources("r_01", "r_02", "r_03"))
        self.assertEqual(got["needs"][0]["headline"]["method"], "median of 2 companies")

    def test_claim_without_source_is_skipped(self):
        got = reader.compose(self.Q, self.NEEDS, [self.claim("A", 3.0, "r_01")], {})
        self.assertEqual(got["needs"][0]["status"], "not_found")
        self.assertEqual(got["needs"][0]["items"], [])

    def test_not_found_need(self):
        got = reader.compose(self.Q, self.NEEDS, [], {})
        self.assertEqual(got["needs"], [{"need": "peer", "status": "not_found", "headline": None, "items": []}])
        self.assertEqual(got["text"], "Peers: not found.")

    def test_label_falls_back_to_need_id(self):
        got = reader.compose(self.Q, [{"need": "sector_growth", "claim_types": ["revenue_growth"]}], [], {})
        self.assertEqual(got["text"], "Sector growth: not found.")


if __name__ == "__main__":
    unittest.main()
