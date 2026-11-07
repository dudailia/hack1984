import json
import os
import tempfile
import unittest

from gate import tavily
from gate.canonical import canonical_json
from gate.errors import ApiError
from gate.ledger import Ledger
from gate.pipeline import Pipeline
from gate.session import SessionStore
from gate.tests.test_tavily import tavily_reply

ALLOW = {"decision": "allow", "rule": None, "detail": None}
Q1, Q2 = "payments processing growth 2025", "listed payments ev revenue"


def extract_reply(urls_texts, failed=(), credits=1):
    body = {"results": [{"url": u, "raw_content": t, "images": []} for u, t in urls_texts],
            "failed_results": [{"url": u, "error": "timeout"} for u in failed], "response_time": 0.5}
    if credits is not None:
        body["usage"] = {"credits": credits}
    return 200, json.dumps(body).encode()


def url(i):
    return f"https://ex{i}.example.com/a"


class Base(unittest.TestCase):
    mode, source = "doublethink", "real"

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.led = Ledger(os.path.join(self.dir.name, "t.db"))
        self.store = SessionStore(self.led, lambda m, t: [])
        self.sid = "s_ext000001"
        self.store.create({"session_id": self.sid, "mode": self.mode, "source": self.source, "memo": "m",
                           "canary": "c", "confirmed_secrets": [], "approved_public_terms": []})
        self.calls, self.replies, self.check = [], [], ALLOW
        self.pipe = Pipeline(self.led, self.store, self.transport, lambda p, s, k: self.check, 8702,
                             keys={"tavily": "tvly-K"})
        comp = "planner" if self.mode in ("doublethink", "two_minds") else "baseline"
        self.comp = comp
        # two searches: r_01..r_03 from Q1, r_04..r_05 from Q2
        self.replies = [tavily_reply(3), tavily_reply(2, start=3)]
        tavily.search(self.pipe, self.sid, comp, "n", Q1, "general")
        tavily.search(self.pipe, self.sid, comp, "n", Q2, "general")
        self.calls.clear()

    def tearDown(self):
        self.led.close()
        self.dir.cleanup()

    def transport(self, dest, path, payload, headers):
        self.calls.append((dest, path, payload, dict(headers)))
        return self.replies.pop(0)

    def extract(self, ids, preset="text"):
        return tavily.extract(self.pipe, self.sid, self.comp, "n", ids, preset)


class TestExtractBody(unittest.TestCase):
    def test_presets(self):
        t = tavily.extract_body([url(0)], "q", "text")
        self.assertEqual(t, {"urls": [url(0)], "query": "q", "extract_depth": "basic", "format": "text",
                             "chunks_per_source": 3, "include_usage": True})
        self.assertEqual(tavily.extract_body([url(0)], "q", "tables")["extract_depth"], "advanced")
        with self.assertRaises(ValueError):
            tavily.extract_body([url(0)], "q", "advanced")

    def test_parse_extract(self):
        texts, failed, credits = tavily.parse_extract(extract_reply([(url(0), "T0")], failed=[url(1)])[1])
        self.assertEqual((texts, failed, credits), ({url(0): "T0"}, [url(1)], 1))

    def test_parse_extract_tolerates_junk(self):
        body = json.dumps({"results": [{"url": 1}, "x", {"url": url(0), "raw_content": None}],
                           "failed_results": "nope"}).encode()
        self.assertEqual(tavily.parse_extract(body), ({}, [], None))


class TestExtract(Base):
    def test_sent_body_and_query_from_search(self):
        self.replies = [extract_reply([(url(3), "Extracted three"), (url(4), "Extracted four")])]
        r = self.extract(["r_04", "r_05"], "tables")
        self.assertEqual(r["status"], "sent")
        dest, path, payload, headers = self.calls[0]
        self.assertEqual((dest, path), ("api.tavily.com", "/extract"))
        self.assertEqual(headers, {"Authorization": "Bearer tvly-K"})
        self.assertEqual(payload, canonical_json(tavily.extract_body([url(3), url(4)], Q2, "tables")))
        self.assertEqual(r["result_ids"], ["r_04", "r_05"])
        self.assertEqual(r["credits_used"], 1)
        self.assertEqual(set(r), {"status", "rule", "ledger_seq", "result_ids", "credits_used", "ledger"})

    def test_failed_results_read(self):
        self.replies = [extract_reply([(url(0), "Zero text")], failed=[url(1)])]
        r = self.extract(["r_01", "r_02"])
        self.assertEqual(r["result_ids"], ["r_01"])
        st = self.store.state(self.sid)
        self.assertEqual(st.extracted, {"r_01": "Zero text"})

    def test_text_capped(self):
        self.replies = [extract_reply([(url(0), "x" * 40000)])]
        self.extract(["r_01"])
        self.assertEqual(len(self.store.state(self.sid).extracted["r_01"]), tavily.MAX_DOC_CHARS)
        self.assertEqual(tavily.MAX_DOC_CHARS, 30000)

    def test_session_updates(self):
        s = self.store.get(self.sid)
        before = (s["call_count"], s["credits_used"], list(s["queries_sent"]), len(s["urls_returned"]))
        self.replies = [extract_reply([(url(0), "Zero extracted")])]
        self.extract(["r_01"])
        self.assertEqual(s["call_count"], before[0] + 1)
        self.assertEqual(s["credits_used"], before[1] + 1)
        self.assertEqual(s["queries_sent"], before[2], "extract query is not a new query")
        self.assertEqual(len(s["urls_returned"]), before[3], "no duplicate urls")
        self.assertIn("Zero extracted", s["public_text_received"])

    def test_unknown_id_blocked_and_ledgered(self):
        r = self.extract(["r_01", "r_77"])
        self.assertEqual((r["status"], r["rule"]), ("blocked", "gate.unknown_result_id"))
        self.assertEqual(self.calls, [])
        self.assertEqual(r["ledger"][0]["decision"], "blocked")
        self.assertEqual(self.store.get(self.sid)["call_count"], 2)

    def test_mixed_searches_refused_before_ledger(self):
        n = len(self.led.rows(self.sid))
        with self.assertRaises(ApiError) as cm:
            self.extract(["r_01", "r_04"])
        self.assertEqual((cm.exception.http, cm.exception.code), (400, "mixed_searches"))
        self.assertEqual(len(self.led.rows(self.sid)), n)
        self.assertEqual(self.calls, [])

    def test_bad_ids_refused_before_ledger(self):
        n = len(self.led.rows(self.sid))
        for ids in ([], ["r_1"], ["x"], ["r_01", "r_01"], [f"r_{i:02d}" for i in range(1, 22)], "r_01", [1]):
            with self.assertRaises(ApiError, msg=repr(ids)):
                self.extract(ids)
        with self.assertRaises(ApiError):
            self.extract(["r_01"], preset="advanced")
        self.assertEqual(len(self.led.rows(self.sid)), n)

    def test_check_block(self):
        self.check = {"decision": "block", "rule": "provenance", "detail": "d"}
        r = self.extract(["r_01"])
        self.assertEqual((r["status"], r["rule"], r["detail"], r["result_ids"]), ("blocked", "provenance", "d", []))
        self.assertEqual(self.calls, [])

    def test_http_error(self):
        self.replies = [(432, b'{"detail":"limit"}')]
        r = self.extract(["r_01"])
        self.assertEqual((r["status"], r["result_ids"]), ("error", []))
        self.assertEqual(self.store.state(self.sid).extracted, {})

    def test_planner_gets_ids_only(self):
        self.replies = [extract_reply([(url(0), "Zero secret-free text")])]
        r = self.extract(["r_01"])
        self.assertNotIn("Zero", json.dumps(r))
        self.assertNotIn("example.com", json.dumps(r))


class TestExtractFake(Base):
    mode, source = "compromised", "fake"

    def test_fake_destination_and_baseline_results(self):
        self.replies = [extract_reply([(url(0), "Fake text")], credits=None)]
        r = self.extract(["r_01"])
        dest, path, payload, headers = self.calls[0]
        self.assertEqual((dest, path, headers), ("127.0.0.1:8702", "/extract", {}))
        self.assertEqual(r["credits_used"], 0)
        self.assertIsNone(r["ledger"][1]["credits_used"])
        self.assertEqual(r["results"], [{"result_id": "r_01", "title": "Title 0", "url": url(0),
                                         "content": "Fake text"}])


if __name__ == "__main__":
    unittest.main()
