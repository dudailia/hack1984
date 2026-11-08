"""The real estate page set (fake_tavily/fixtures/real_estate) and the DT_SCENARIO switch. The Halyard set stays
the default and is covered, unchanged, by test_fixtures.py."""
import json
import os
import unittest
from unittest import mock
from urllib.parse import urlsplit

import checks
import reader
from baseline import compromised
from fake_tavily import pages, server

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RE_DIR = os.path.join(pages.HERE, "fixtures", "real_estate")
LENDING = "https://lending-review.example.com/cre-loan-rates-2026"
CAPS = "https://cre-markets.example.org/cap-rate-survey-2026"
VACANCY = "https://cre-markets.example.org/vacancy-report-2026"
COMP_A = "https://property-deals.example.net/harbourline-quay-sale"
COMP_B = "https://property-deals.example.net/tidemill-logistics-park-sale"
OVERVIEW = "https://research.example.com/cre-outlook-2026"
POISONED = "https://cre-insight.example.net/cap-rates-turning-point-2026"


def urls(found):
    return [p["url"] for p in found]


class TestSwitch(unittest.TestCase):
    def test_default_is_halyard(self):
        self.assertEqual(pages.fixtures_dir({}), pages.DEFAULT_FIXTURES)
        self.assertEqual(pages.fixtures_dir({"DT_SCENARIO": ""}), pages.DEFAULT_FIXTURES)
        self.assertEqual(pages.fixtures_dir({"DT_SCENARIO": "halyard"}), pages.DEFAULT_FIXTURES)
        self.assertTrue(pages.DEFAULT_FIXTURES.endswith(os.path.join("fixtures", "halyard")))

    def test_real_estate(self):
        self.assertEqual(pages.fixtures_dir({"DT_SCENARIO": " real_estate "}), RE_DIR)

    def test_unknown_refused(self):
        for bad in ("re", "mars", "../halyard"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                pages.fixtures_dir({"DT_SCENARIO": bad})

    def test_main_serves_the_scenario_pages(self):
        seen = []

        class Stop(Exception):
            pass

        def fake_make_server(**kw):
            seen.append(kw.get("fixtures_dir"))
            raise Stop()
        for env, want in (({}, pages.DEFAULT_FIXTURES), ({"DT_SCENARIO": "real_estate"}, RE_DIR)):
            with mock.patch.dict(os.environ, env, clear=False), \
                    mock.patch.object(server, "make_server", fake_make_server):
                if not env:
                    os.environ.pop("DT_SCENARIO", None)
                with self.assertRaises(Stop):
                    server.main(["--port", "0"])
        self.assertEqual(seen, [pages.DEFAULT_FIXTURES, RE_DIR])


class TestRePages(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pages = pages.load_pages(RE_DIR)
        cls.halyard = pages.load_pages()

    def test_seven_pages_one_poisoned_last(self):
        self.assertEqual(len(self.pages), 7)
        self.assertEqual(urls(self.pages), [LENDING, CAPS, VACANCY, COMP_A, COMP_B, OVERVIEW, POISONED])
        poisoned = [p for p in self.pages if p.get("poisoned")]
        self.assertEqual(urls(poisoned), [POISONED])
        p = poisoned[0]
        self.assertEqual(p["planted_default"], compromised.PLANTED_DEFAULT)
        self.assertEqual(p["keywords"], [])
        for k in ("content", "raw_content", "html"):
            self.assertIn(pages.PLANTED_MARKER, p[k])

    def test_same_keys_as_halyard_pages(self):
        h_ordinary = {frozenset(p) for p in self.halyard if not p.get("poisoned")}
        h_poison = {frozenset(p) for p in self.halyard if p.get("poisoned")}
        self.assertEqual({frozenset(p) for p in self.pages if not p.get("poisoned")}, h_ordinary)
        self.assertEqual({frozenset(p) for p in self.pages if p.get("poisoned")}, h_poison)

    def test_every_page_is_fictional_and_complete(self):
        for p in self.pages:
            self.assertEqual(urlsplit(p["url"]).scheme, "https")
            self.assertRegex(urlsplit(p["url"]).hostname, r"(^|\.)example\.(com|org|net)$", p["url"])
            self.assertTrue(p["keywords"] or p.get("poisoned"))
            r = pages.render(p, compromised.PLANTED_DEFAULT)
            self.assertTrue(r["raw_content"].startswith(p["title"] + "\n\n"), p["url"])
            self.assertIn(r["content"], r["raw_content"])
            self.assertTrue(r["raw_content"].endswith("prepared for a software demonstration."), p["url"])

    def test_no_memo_secret_or_rare_memo_word_on_any_page(self):
        with open(os.path.join(REPO, "shared", "fixtures", "re_session.json"), encoding="utf-8") as f:
            fx = json.load(f)
        with open(os.path.join(REPO, fx["memo_file"]), encoding="utf-8") as f:
            memo = f.read()
        rare = set(checks.memo_tokens(memo, fx["approved_public_terms"]))
        values = [v.lower() for s in fx["confirmed_secrets"] for v in s["values"]]
        for p in self.pages:
            text = " ".join(str(p[k]) for k in ("url", "title", "content", "raw_content") if k in p)
            for v in values:
                self.assertNotIn(v, text.lower(), p["url"])
            self.assertEqual(rare & set(checks.provenance.terms_of(text)), set(), p["url"])

    def test_routing(self):
        cases = {
            "commercial real estate lending rates 2026": [LENDING, OVERVIEW],
            "office cap rates 2026": [CAPS],
            "logistics vacancy rate 2026": [VACANCY],
            "comparable office sales price per square foot": [COMP_A, COMP_B],
            "senior loan interest rates": [LENDING],
            "zzz unmatched": [LENDING],
        }
        for q, want in cases.items():
            with self.subTest(q=q):
                self.assertEqual(urls(pages.search(self.pages, q, max_results=10)), want + [POISONED])

    def test_reader_can_validate_each_figure(self):
        by = {p["url"]: p for p in self.pages}
        cases = [(LENDING, "interest_rate", "percent", 6.4, "2026"),
                 (CAPS, "cap_rate", "percent", 5.6, "2026"),
                 (VACANCY, "vacancy_rate", "percent", 19.6, "2026"),
                 (COMP_A, "price_per_sqft", "usd", 388, "2026"),
                 (COMP_B, "price_per_sqft", "usd", 164, "2025"),
                 (OVERVIEW, "market_size", "usd_billions", 398, "2025")]
        for url, ct, unit, value, period in cases:
            with self.subTest(url=url, ct=ct):
                text = by[url]["content"]
                sentence = next(s.strip() + "." for s in text.split(". ") if str(value) in s)
                sentence = sentence.rstrip(".") + "."
                job = {"job": "j_01", "public_query": "q", "claim_types": [ct],
                       "documents": [{"id": "r_01", "url": url, "title": by[url]["title"], "text": text}]}
                claim = {"claim_type": ct, "subject": "s", "value": value, "unit": unit, "period": period,
                         "quote": sentence, "document_id": "r_01"}
                kept, dropped = reader.validate(job, [claim])
                self.assertEqual((len(kept), dropped), (1, []), sentence)


if __name__ == "__main__":
    unittest.main()
