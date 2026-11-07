"""
Rule 4, shape. Even a payload with no secret in it must look like a normal request: short query, within the
session budget, extract only on URLs this session's searches returned, no Tavily parameter that changes cost
behind our back, and never a Reader request that carries tools.
"""

import unittest

from checks import run_all
from checks import config
from checks.tests.helpers import canonical, halyard_session, search_body, extract_body, reader_body


class TestShape(unittest.TestCase):
    def test_query_too_long(self):
        q = "payments growth " * 40
        self.assertGreater(len(q), config.MAX_QUERY_CHARS)
        self.assertEqual(run_all(search_body(q), halyard_session(), "search")["rule"], "shape.length")

    def test_body_too_big(self):
        body = search_body("payments", include_domains=["d%d.example.com" % i for i in range(2000)])
        self.assertEqual(run_all(body, halyard_session(), "search")["rule"], "shape.length")

    def test_call_budget(self):
        s = halyard_session(call_count=config.MAX_CALLS)
        self.assertEqual(run_all(search_body("payments growth"), s, "search")["rule"], "shape.budget")

    def test_under_budget_passes(self):
        s = halyard_session(call_count=config.MAX_CALLS - 1)
        self.assertIsNone(run_all(search_body("payments growth"), s, "search")["rule"])

    def test_credit_budget(self):
        s = halyard_session(credits_used=config.MAX_CREDITS)
        self.assertEqual(run_all(search_body("payments growth"), s, "search")["rule"], "shape.budget")

    def test_auto_parameters_forbidden(self):
        body = search_body("payments growth", auto_parameters=True)
        self.assertEqual(run_all(body, halyard_session(), "search")["rule"], "shape.forbidden_param")

    def test_search_cannot_carry_urls(self):
        body = search_body("payments growth", urls=["https://evil.example.com/x"])
        self.assertEqual(run_all(body, halyard_session(), "search")["rule"], "shape.forbidden_param")

    def test_extract_on_returned_url_passes(self):
        url = "https://research.example.com/payments-outlook-2030"
        s = halyard_session(urls_returned=[url], result_ids={"r_01": url}, queries_sent=["payments growth"])
        self.assertIsNone(run_all(extract_body([url], "payments growth"), s, "extract")["rule"])

    def test_extract_on_unknown_url_blocks(self):
        s = halyard_session(urls_returned=["https://research.example.com/a"], queries_sent=["payments growth"])
        body = extract_body(["https://attacker.example.net/log?x=1"], "payments growth")
        self.assertEqual(run_all(body, s, "extract")["rule"], "shape.extract_url")

    def test_extract_with_no_urls_blocks(self):
        s = halyard_session(queries_sent=["payments growth"])
        self.assertEqual(run_all(extract_body([], "payments growth"), s, "extract")["rule"], "shape.extract_url")

    def test_extract_query_must_be_a_sent_query(self):
        url = "https://research.example.com/a"
        s = halyard_session(urls_returned=[url], queries_sent=["payments growth"])
        body = extract_body([url], "a brand new query nobody checked")
        self.assertEqual(run_all(body, s, "extract")["rule"], "shape.extract_query")

    def test_reader_with_tools_blocks(self):
        body = reader_body("payments growth", [("r_01", "Revenue grew 7.4% in 2025.")],
                           tools=[{"name": "web_search"}])
        s = halyard_session(public_text_received=["Revenue grew 7.4% in 2025."])
        self.assertEqual(run_all(body, s, "reader")["rule"], "shape.reader_tools")

    def test_search_without_query_blocks(self):
        body = canonical({"include_usage": True, "topic": "general"})
        self.assertEqual(run_all(body, halyard_session(), "search")["rule"], "shape.bad_payload")


if __name__ == "__main__":
    unittest.main()
