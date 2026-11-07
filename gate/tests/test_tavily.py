import json
import os
import tempfile
import unittest

from gate import tavily
from gate.ledger import Ledger
from gate.pipeline import Pipeline
from gate.session import SessionStore
from gate.tests.test_canonical import PAYLOAD
from gate.canonical import canonical_json

ALLOW = {"decision": "allow", "rule": None, "detail": None}


def tavily_reply(n, start=0, credits=1):
    body = {"query": "q", "results": [
        {"id": f"tavily-internal-{start + i}", "url": f"https://ex{start + i}.example.com/a",
         "title": f"Title {start + i}", "content": f"Content {start + i}", "score": 0.9, "raw_content": None}
        for i in range(n)], "response_time": 1.2, "request_id": "req-xyz"}
    if credits is not None:
        body["usage"] = {"credits": credits}
    return 200, json.dumps(body).encode()


class TestPresets(unittest.TestCase):
    def test_general_matches_section7_bytes(self):
        b = tavily.search_body("payments processing industry revenue growth 2025", "general")
        self.assertEqual(canonical_json(b), PAYLOAD)

    def test_news_and_finance(self):
        n = tavily.search_body("q", "news")
        self.assertEqual(n["topic"], "news")
        f = tavily.search_body("q", "finance")
        self.assertEqual(f["topic"], "finance")
        self.assertEqual(f["include_domains"][0], "sec.gov")
        self.assertEqual(f["include_domains_mode"], "prefer")
        for b in (n, f):
            self.assertEqual((b["search_depth"], b["max_results"], b["include_usage"]), ("basic", 10, True))

    def test_never_auto_parameters(self):
        for p in tavily.SEARCH_PRESETS:
            b = tavily.search_body("q", p)
            self.assertNotIn("auto_parameters", b)
            self.assertEqual(b["search_depth"], "basic")

    def test_unknown_preset(self):
        with self.assertRaises(ValueError):
            tavily.search_body("q", "advanced")

    def test_presets_not_mutable_through_bodies(self):
        b = tavily.search_body("q", "finance")
        b["include_domains"].append("evil.com")
        self.assertNotIn("evil.com", tavily.search_body("q", "finance")["include_domains"])


class TestParse(unittest.TestCase):
    def test_parse(self):
        results, credits = tavily.parse_search(tavily_reply(2)[1])
        self.assertEqual(credits, 1)
        self.assertEqual(results[0], {"url": "https://ex0.example.com/a", "title": "Title 0", "content": "Content 0"})

    def test_missing_usage(self):
        self.assertIsNone(tavily.parse_search(tavily_reply(1, credits=None)[1])[1])

    def test_float_credits(self):
        self.assertEqual(tavily.parse_search(tavily_reply(1, credits=2.0)[1])[1], 2)

    def test_bad_entries_skipped(self):
        body = json.dumps({"results": [{"url": 5}, "x", {"url": "https://ok.example.com", "title": None}]}).encode()
        results, _ = tavily.parse_search(body)
        self.assertEqual(results, [{"url": "https://ok.example.com", "title": "", "content": ""}])


class TestSearch(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.led = Ledger(os.path.join(self.dir.name, "t.db"))
        self.store = SessionStore(self.led, memo_tokens_fn=lambda m: [])
        self.calls = []
        self.replies = []

    def tearDown(self):
        self.led.close()
        self.dir.cleanup()

    def transport(self, dest, path, payload, headers):
        self.calls.append((dest, path, payload, dict(headers)))
        return self.replies.pop(0)

    def make(self, sid, mode="doublethink", source="real", check=ALLOW):
        self.store.create({"session_id": sid, "mode": mode, "source": source, "memo": "m", "canary": "c",
                           "confirmed_secrets": [], "approved_public_terms": []})
        return Pipeline(self.led, self.store, self.transport, lambda p, s, k: check, 8702)

    def test_ids_issued_and_continue(self):
        pipe = self.make("s_tav000001")
        self.replies = [tavily_reply(3), tavily_reply(2, start=3, credits=1)]
        r1 = tavily.search(pipe, "s_tav000001", "planner", "need_a", "q one", "general", api_key="tvly-K")
        r2 = tavily.search(pipe, "s_tav000001", "planner", "need_a", "q two", "news", api_key="tvly-K")
        self.assertEqual(r1["result_ids"], ["r_01", "r_02", "r_03"])
        self.assertEqual(r2["result_ids"], ["r_04", "r_05"])
        s = self.store.get("s_tav000001")
        self.assertEqual(s["result_ids"]["r_04"], "https://ex3.example.com/a")
        self.assertEqual(s["queries_sent"], ["q one", "q two"])
        self.assertEqual(s["call_count"], 2)
        self.assertEqual(s["credits_used"], 2)
        self.assertEqual(len(s["urls_returned"]), 5)
        self.assertIn("Content 4", s["public_text_received"])
        self.assertEqual(self.store.state("s_tav000001").docs["r_02"]["title"], "Title 1")

    def test_response_shape_planner(self):
        pipe = self.make("s_tav000002")
        self.replies = [tavily_reply(2)]
        r = tavily.search(pipe, "s_tav000002", "planner", "n", "q", "general", api_key="tvly-K")
        self.assertEqual(set(r), {"status", "rule", "ledger_seq", "result_ids", "credits_used", "ledger"})
        self.assertEqual((r["status"], r["rule"], r["ledger_seq"], r["credits_used"]), ("sent", None, 1, 1))
        self.assertEqual([row["row_type"] for row in r["ledger"]], ["attempt", "result"])
        text = json.dumps(r)
        for leak in ("tavily-internal", "example.com", "Title", "Content", "req-xyz"):
            self.assertNotIn(leak, text)

    def test_tavily_ids_never_passed_on(self):
        pipe = self.make("s_tav000003", mode="single_agent", source="fake")
        self.replies = [tavily_reply(2)]
        r = tavily.search(pipe, "s_tav000003", "baseline", "n", "q", "general", api_key=None)
        self.assertNotIn("tavily-internal", json.dumps(r))
        self.assertNotIn("tavily-internal", json.dumps(self.store.get("s_tav000003")))
        self.assertEqual(r["results"][0], {"result_id": "r_01", "title": "Title 0",
                                           "url": "https://ex0.example.com/a", "content": "Content 0"})

    def test_real_destination_and_auth(self):
        pipe = self.make("s_tav000004")
        self.replies = [tavily_reply(1)]
        tavily.search(pipe, "s_tav000004", "planner", "n", "q", "general", api_key="tvly-K")
        dest, path, payload, headers = self.calls[0]
        self.assertEqual((dest, path), ("api.tavily.com", "/search"))
        self.assertEqual(headers, {"Authorization": "Bearer tvly-K"})
        self.assertEqual(payload, canonical_json(tavily.search_body("q", "general")))

    def test_real_without_key_refused_before_ledger(self):
        pipe = self.make("s_tav000009")
        with self.assertRaises(tavily.TavilyError):
            tavily.search(pipe, "s_tav000009", "planner", "n", "q", "general", api_key=None)
        self.assertEqual(self.led.rows("s_tav000009"), [])

    def test_fake_destination_no_auth_no_credits(self):
        pipe = self.make("s_tav000005", mode="compromised", source="fake")
        self.replies = [tavily_reply(1, credits=1)]
        r = tavily.search(pipe, "s_tav000005", "baseline", "n", "q", "general", api_key="tvly-K")
        dest, path, payload, headers = self.calls[0]
        self.assertEqual(dest, "127.0.0.1:8702")
        self.assertNotIn("Authorization", headers)
        self.assertEqual(r["credits_used"], 0)
        self.assertIsNone(r["ledger"][1]["credits_used"])
        self.assertEqual(self.store.get("s_tav000005")["credits_used"], 0)

    def test_blocked(self):
        pipe = self.make("s_tav000006", check={"decision": "block", "rule": "canary", "detail": "canary seen"})
        r = tavily.search(pipe, "s_tav000006", "planner", "n", "q", "general", api_key="tvly-K")
        self.assertEqual(r, {"status": "blocked", "rule": "canary", "detail": "canary seen", "ledger_seq": 1,
                             "result_ids": [], "credits_used": 0, "ledger": r["ledger"]})
        self.assertEqual(self.calls, [])
        s = self.store.get("s_tav000006")
        self.assertEqual((s["queries_sent"], s["call_count"]), ([], 0))

    def test_http_error(self):
        pipe = self.make("s_tav000007")
        self.replies = [(401, b'{"detail":{"error":"Unauthorized"}}')]
        r = tavily.search(pipe, "s_tav000007", "planner", "n", "q", "general", api_key="tvly-K")
        self.assertEqual((r["status"], r["result_ids"], r["credits_used"]), ("error", [], 0))
        self.assertEqual(r["ledger"][1]["http_status"], 401)
        self.assertEqual(self.store.get("s_tav000007")["call_count"], 1)

    def test_id_overflow(self):
        pipe = self.make("s_tav000008")
        self.store.state("s_tav000008").next_result_n = 99
        self.replies = [tavily_reply(2)]
        r = tavily.search(pipe, "s_tav000008", "planner", "n", "q", "general", api_key="tvly-K")
        self.assertEqual(r["result_ids"], ["r_99"])


if __name__ == "__main__":
    unittest.main()
