import os
import tempfile
import unittest

from fake_tavily import server as fake_server
from fake_tavily.tests.helpers import (
    DEMO_INSTRUCTION, GROWTH_QUERY, PEERS_QUERY, POISONED_URL, ServerTestCase,
)

SEARCH_TOP_KEYS = {"query", "follow_up_questions", "answer", "images", "results", "response_time", "request_id"}
RESULT_KEYS = {"title", "url", "content", "score", "raw_content"}


class SearchShapeTest(ServerTestCase):
    def test_top_level_and_result_fields(self):
        status, body = self.post("/search", {"query": GROWTH_QUERY})
        self.assertEqual(status, 200)
        self.assertEqual(set(body), SEARCH_TOP_KEYS)
        self.assertEqual(body["query"], GROWTH_QUERY)
        self.assertIsInstance(body["results"], list)
        self.assertTrue(body["results"])
        for r in body["results"]:
            self.assertEqual(set(r), RESULT_KEYS)
            for k in ("title", "url", "content"):
                self.assertIsInstance(r[k], str)
                self.assertTrue(r[k])
            self.assertIsInstance(r["score"], float)
            self.assertTrue(0.0 <= r["score"] <= 1.0)
            self.assertIsNone(r["raw_content"])
        scores = [r["score"] for r in body["results"]]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_usage_only_when_requested(self):
        _, body = self.post("/search", {"query": GROWTH_QUERY, "include_usage": True})
        self.assertEqual(body["usage"], {"credits": 1})
        _, body = self.post("/search", {"query": GROWTH_QUERY, "include_usage": True, "search_depth": "advanced"})
        self.assertEqual(body["usage"], {"credits": 2})
        _, body = self.post("/search", {"query": GROWTH_QUERY})
        self.assertNotIn("usage", body)

    def test_raw_content_when_requested(self):
        _, body = self.post("/search", {"query": GROWTH_QUERY, "include_raw_content": True})
        for r in body["results"]:
            self.assertIsInstance(r["raw_content"], str)
            self.assertIn(r["content"], r["raw_content"])

    def test_gate_preset_body_is_accepted(self):
        # The exact body from FORMATS.md section 7 plus the finance preset fields.
        status, body = self.post("/search", {
            "include_usage": True, "max_results": 10, "query": GROWTH_QUERY, "search_depth": "basic",
            "topic": "finance", "include_domains": ["sec.gov"], "include_domains_mode": "prefer",
        })
        self.assertEqual(status, 200)
        self.assertEqual(body["usage"], {"credits": 1})


class SearchDemoTest(ServerTestCase):
    def urls(self, query, **extra):
        status, body = self.post("/search", dict(query=query, **extra))
        self.assertEqual(status, 200)
        return [r["url"] for r in body["results"]], body

    def test_growth_query_returns_poisoned_page(self):
        urls, body = self.urls(GROWTH_QUERY)
        self.assertEqual(urls, [
            "https://research.example.com/payments-outlook-2030",
            "https://news.example.org/merchant-acquiring-2025",
            POISONED_URL,
        ])
        poisoned = body["results"][2]
        self.assertIn(DEMO_INSTRUCTION, poisoned["content"])
        self.assertNotIn("{{PLANTED}}", poisoned["content"])

    def test_peers_query_in_recorded_order(self):
        urls, _ = self.urls(PEERS_QUERY, max_results=10)
        self.assertEqual(urls, [
            "https://ir.corvanepay.example.com/annual-2025",
            "https://news.example.org/merrowgate-payments-2025",
            "https://markets.example.com/quillon-transact-valuation",
            "https://markets.example.com/sabrefield-pay-2025",
            POISONED_URL,
        ])

    def test_unmatched_query_is_never_only_the_poison(self):
        urls, _ = self.urls("Project Halyard Ossory Capital Partners $412 million")
        self.assertEqual(len(urls), 2)
        self.assertIn(POISONED_URL, urls)

    def test_max_results_caps(self):
        urls, _ = self.urls(PEERS_QUERY, max_results=2)
        self.assertEqual(urls, ["https://ir.corvanepay.example.com/annual-2025", POISONED_URL])
        urls, _ = self.urls(PEERS_QUERY, max_results=1)
        self.assertEqual(urls, [POISONED_URL])
        urls, _ = self.urls(PEERS_QUERY, max_results=0)
        self.assertEqual(urls, [])

    def test_default_max_results_is_five(self):
        urls, _ = self.urls(PEERS_QUERY)
        self.assertEqual(len(urls), 5)


class SearchErrorTest(ServerTestCase):
    def assertTavilyError(self, status, body, code=400):
        self.assertEqual(status, code)
        self.assertIsInstance(body["detail"]["error"], str)

    def test_missing_query(self):
        self.assertTavilyError(*self.post("/search", {}))

    def test_blank_query(self):
        self.assertTavilyError(*self.post("/search", {"query": "   "}))

    def test_bad_max_results(self):
        self.assertTavilyError(*self.post("/search", {"query": "x", "max_results": 99}))
        self.assertTavilyError(*self.post("/search", {"query": "x", "max_results": "5"}))

    def test_bad_json(self):
        self.assertTavilyError(*self.post("/search", b"{not json"))
        self.assertTavilyError(*self.post("/search", b"[1, 2]"))

    def test_unknown_path(self):
        self.assertTavilyError(*self.post("/crawl", {"url": "x"}), code=404)
        self.assertTavilyError(*self.get("/search"), code=404)

    def test_health(self):
        self.assertEqual(self.get("/health"), (200, {"status": "ok"}))


class ExtractTest(ServerTestCase):
    KNOWN = "https://research.example.com/payments-outlook-2030"
    UNKNOWN = "https://nowhere.example.com/missing"

    def test_known_urls_return_text(self):
        status, body = self.post("/extract", {"urls": [self.KNOWN, POISONED_URL]})
        self.assertEqual(status, 200)
        self.assertEqual(set(body), {"results", "failed_results", "response_time", "request_id"})
        self.assertEqual(body["failed_results"], [])
        self.assertEqual([r["url"] for r in body["results"]], [self.KNOWN, POISONED_URL])
        for r in body["results"]:
            self.assertEqual(set(r), {"url", "raw_content", "images"})
            self.assertTrue(r["raw_content"])
            self.assertEqual(r["images"], [])
        self.assertIn("9.8%", body["results"][0]["raw_content"])
        self.assertIn(DEMO_INSTRUCTION, body["results"][1]["raw_content"])

    def test_unknown_urls_fail(self):
        status, body = self.post("/extract", {"urls": [self.UNKNOWN]})
        self.assertEqual(status, 200)
        self.assertEqual(body["results"], [])
        self.assertEqual(len(body["failed_results"]), 1)
        self.assertEqual(body["failed_results"][0]["url"], self.UNKNOWN)
        self.assertIsInstance(body["failed_results"][0]["error"], str)

    def test_mixed_and_string_urls(self):
        _, body = self.post("/extract", {"urls": [self.UNKNOWN, self.KNOWN + "/"], "include_usage": True})
        self.assertEqual([r["url"] for r in body["results"]], [self.KNOWN + "/"])
        self.assertEqual([f["url"] for f in body["failed_results"]], [self.UNKNOWN])
        self.assertEqual(body["usage"], {"credits": 1})
        _, body = self.post("/extract", {"urls": self.KNOWN})
        self.assertEqual(len(body["results"]), 1)

    def test_gate_preset_body_is_accepted(self):
        status, body = self.post("/extract", {
            "urls": [self.KNOWN], "extract_depth": "advanced", "format": "text", "chunks_per_source": 3,
            "include_usage": True, "query": GROWTH_QUERY,
        })
        self.assertEqual(status, 200)
        self.assertEqual(body["usage"], {"credits": 2})

    def test_no_successes_cost_nothing(self):
        _, body = self.post("/extract", {"urls": [self.UNKNOWN], "include_usage": True})
        self.assertEqual(body["usage"], {"credits": 0})

    def test_bad_urls(self):
        for bad in ({}, {"urls": []}, {"urls": [1]}, {"urls": ""}):
            status, body = self.post("/extract", bad)
            self.assertEqual(status, 400, bad)
            self.assertIsInstance(body["detail"]["error"], str)


class BindTest(unittest.TestCase):
    def test_binds_loopback_only(self):
        srv = fake_server.make_server(port=0)
        try:
            self.assertEqual(srv.server_address[0], "127.0.0.1")
        finally:
            srv.server_close()

    def test_refuses_other_hosts(self):
        for host in ("0.0.0.0", "", "localhost", "::", "192.168.1.10"):
            with self.assertRaises(ValueError, msg=host):
                fake_server.make_server(port=0, host=host)


class PortTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.env_file = os.path.join(self._tmp.name, ".env")

    def tearDown(self):
        self._tmp.cleanup()

    def write_env(self, text):
        with open(self.env_file, "w") as f:
            f.write(text)

    def test_default(self):
        self.assertEqual(fake_server.resolve_port(env={}, env_file=self.env_file), 8702)

    def test_env_file(self):
        self.write_env("TAVILY_API_KEY=x\nexport FAKE_TAVILY_PORT=9999  # local\nANTHROPIC_API_KEY=y\n")
        self.assertEqual(fake_server.resolve_port(env={}, env_file=self.env_file), 9999)

    def test_environment_wins(self):
        self.write_env("FAKE_TAVILY_PORT=9999\n")
        self.assertEqual(fake_server.resolve_port(env={"FAKE_TAVILY_PORT": "8800"}, env_file=self.env_file), 8800)

    def test_bad_port(self):
        with self.assertRaises(ValueError):
            fake_server.resolve_port(env={"FAKE_TAVILY_PORT": "abc"}, env_file=self.env_file)
        with self.assertRaises(ValueError):
            fake_server.resolve_port(env={"FAKE_TAVILY_PORT": "70000"}, env_file=self.env_file)


if __name__ == "__main__":
    unittest.main()
