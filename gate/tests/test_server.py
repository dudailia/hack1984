import contextlib
import copy
import http.client
import io
import json
import os
import tempfile
import threading
import unittest
from unittest import mock

from gate import bundle, server
from gate.ledger import Ledger
from gate.tests.test_tavily import tavily_reply

ALLOW = {"decision": "allow", "rule": None, "detail": None}


def session(sid, mode="doublethink", source="real"):
    return {"session_id": sid, "mode": mode, "source": source, "memo": "PROJECT X memo", "canary": "c4n4ry",
            "confirmed_secrets": [{"label": "buyer", "values": ["Ossory"]}], "approved_public_terms": ["payments"]}


class TestRunAllSeesSessionUpdates(unittest.TestCase):
    """End to end through the HTTP server: the session run_all receives on the 2nd search reflects the 1st."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.led = Ledger(os.path.join(self.dir.name, "t.db"))
        self.seen = []
        self.replies = [tavily_reply(3, start=0, credits=1), tavily_reply(2, start=3, credits=1)]

        def run_all(payload, session, kind):
            self.seen.append(copy.deepcopy(session))  # snapshot exactly what the checks were given
            return ALLOW

        def transport(dest, path, payload, headers):
            return self.replies.pop(0)

        self.srv = server.make_server(self.led, transport, run_all, lambda m, t: [], fake_port=8702,
                                      keys={"tavily": "tvly-K"}, port=0)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.led.close()
        self.dir.cleanup()

    def post(self, path, body):
        conn = http.client.HTTPConnection("127.0.0.1", self.srv.server_address[1], timeout=5)
        conn.request("POST", path, body=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
        r = conn.getresponse()
        out = (r.status, json.loads(r.read()))
        conn.close()
        return out

    def test_second_run_all_sees_first_search(self):
        self.assertEqual(self.post("/v1/session", session("s_e2e000001"))[0], 200)
        q1, q2 = "payments processing growth 2025", "listed payments companies ev revenue"
        for q in (q1, q2):
            st, b = self.post("/v1/search", {"session_id": "s_e2e000001", "component": "planner", "need": "n",
                                             "query": q, "options": {"preset": "general"}})
            self.assertEqual((st, b["status"]), (200, "sent"))
        self.assertEqual(len(self.seen), 2)

        first, second = self.seen
        self.assertEqual((first["queries_sent"], first["call_count"], first["credits_used"]), ([], 0, 0))
        self.assertEqual(first["public_text_received"], [])

        urls = [f"https://ex{i}.example.com/a" for i in range(3)]
        self.assertEqual(second["queries_sent"], [q1])
        for i in range(3):
            self.assertIn(f"Title {i}", second["public_text_received"])
            self.assertIn(f"Content {i}", second["public_text_received"])
        self.assertEqual(second["urls_returned"], urls)
        self.assertEqual(second["result_ids"], {"r_01": urls[0], "r_02": urls[1], "r_03": urls[2]})
        self.assertEqual(second["call_count"], 1)
        self.assertEqual(second["credits_used"], 1)
        # nothing from the second search leaked backwards into what the second call saw
        self.assertNotIn("Content 3", second["public_text_received"])


class TestServer(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.led = Ledger(os.path.join(self.dir.name, "t.db"))
        self.check = ALLOW
        self.calls = []
        self.srv = server.make_server(self.led, self.transport, lambda p, s, k: self.check, lambda m, t: [],
                                      fake_port=8702, keys={"tavily": "tvly-K"}, port=0)
        self.port = self.srv.server_address[1]
        self.t = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.t.start()

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.led.close()
        self.dir.cleanup()

    def transport(self, dest, path, payload, headers):
        self.calls.append((dest, path, payload))
        return tavily_reply(2)

    def req(self, method, path, body=None, raw=None, ctype="application/json"):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        headers = {"Content-Type": ctype} if data is not None else {}
        conn.request(method, path, body=data, headers=headers)
        r = conn.getresponse()
        out = (r.status, json.loads(r.read() or b"null"))
        conn.close()
        return out

    def test_binds_loopback(self):
        self.assertEqual(self.srv.server_address[0], "127.0.0.1")
        with self.assertRaises(ValueError):
            server.make_server(self.led, self.transport, None, None, 8702, None, port=0, host="0.0.0.0")

    def test_health(self):
        self.assertEqual(self.req("GET", "/v1/health"), (200, {"status": "ok"}))

    def test_session_create(self):
        st, b = self.req("POST", "/v1/session", session("s_srv000001"))
        self.assertEqual(st, 200)
        self.assertEqual(set(b), {"status", "session_id", "created_at", "enforce"})
        self.assertEqual((b["status"], b["session_id"], b["enforce"]), ("ok", "s_srv000001", True))

    def test_session_mismatch_and_duplicate(self):
        st, b = self.req("POST", "/v1/session", session("s_srv000002", mode="compromised", source="real"))
        self.assertEqual((st, b["status"], b["error"]), (400, "error", "mode_source_mismatch"))
        self.req("POST", "/v1/session", session("s_srv000003"))
        st, b = self.req("POST", "/v1/session", session("s_srv000003"))
        self.assertEqual((st, b["error"]), (409, "session_exists"))

    def test_search_sent(self):
        self.req("POST", "/v1/session", session("s_srv000004"))
        st, b = self.req("POST", "/v1/search", {"session_id": "s_srv000004", "component": "planner",
                                                "need": "sector_growth", "query": "payments growth 2025",
                                                "options": {"preset": "general"}})
        self.assertEqual(st, 200)
        self.assertEqual((b["status"], b["rule"], b["ledger_seq"], b["result_ids"], b["credits_used"]),
                         ("sent", None, 1, ["r_01", "r_02"], 1))
        self.assertEqual([r["row_type"] for r in b["ledger"]], ["attempt", "result"])
        text = json.dumps(b)
        for leak in ("url", "title", "content", "example.com"):
            self.assertNotIn(leak, text)
        self.assertEqual(self.calls[0][0], "api.tavily.com")

    def test_search_blocked_is_200(self):
        self.check = {"decision": "block", "rule": "secret.buyer", "detail": "matches a confirmed secret (buyer)"}
        self.req("POST", "/v1/session", session("s_srv000005"))
        st, b = self.req("POST", "/v1/search", {"session_id": "s_srv000005", "component": "planner", "need": "n",
                                                "query": "Ossory offer", "options": {"preset": "general"}})
        self.assertEqual(st, 200)
        self.assertEqual((b["status"], b["rule"], b["detail"], b["result_ids"], b["credits_used"]),
                         ("blocked", "secret.buyer", "matches a confirmed secret (buyer)", [], 0))
        self.assertEqual(len(b["ledger"]), 1)
        self.assertEqual(self.calls, [])

    def test_baseline_gets_results_on_fake(self):
        self.req("POST", "/v1/session", session("s_srv000006", mode="single_agent", source="fake"))
        st, b = self.req("POST", "/v1/search", {"session_id": "s_srv000006", "component": "baseline", "need": "n",
                                                "query": "q", "options": {"preset": "general"}})
        self.assertEqual(st, 200)
        self.assertEqual(b["results"][0]["result_id"], "r_01")
        self.assertEqual(self.calls[0][0], "127.0.0.1:8702")

    def test_component_must_match_mode(self):
        self.req("POST", "/v1/session", session("s_srv000007"))
        st, b = self.req("POST", "/v1/search", {"session_id": "s_srv000007", "component": "baseline", "need": "n",
                                                "query": "q", "options": {"preset": "general"}})
        self.assertEqual((st, b["error"]), (400, "component_mode_mismatch"))
        self.req("POST", "/v1/session", session("s_srv000008", mode="compromised", source="fake"))
        st, b = self.req("POST", "/v1/search", {"session_id": "s_srv000008", "component": "planner", "need": "n",
                                                "query": "q", "options": {"preset": "general"}})
        self.assertEqual((st, b["error"]), (400, "component_mode_mismatch"))

    def test_search_validation(self):
        self.req("POST", "/v1/session", session("s_srv000009"))
        good = {"session_id": "s_srv000009", "component": "planner", "need": "n", "query": "q",
                "options": {"preset": "general"}}
        bad = [dict(good, session_id="s_nosuch001"), dict(good, component="reader"), dict(good, need="Bad-Need"),
               dict(good, query=""), dict(good, query="x" * 401), dict(good, query=5),
               dict(good, options={"preset": "advanced"}), dict(good, options={}),
               dict(good, options={"preset": "general", "auto_parameters": True}), dict(good, extra=1)]
        for body in bad:
            st, b = self.req("POST", "/v1/search", body)
            self.assertIn(st, (400, 404), msg=str(body)[:100])
            self.assertEqual(b["status"], "error")
        self.assertEqual(self.calls, [])
        self.assertEqual(self.led.rows("s_srv000009"), [])

    def test_bad_requests(self):
        self.assertEqual(self.req("GET", "/nope")[0], 404)
        self.assertEqual(self.req("POST", "/v1/crawl", {})[0], 404)
        self.assertEqual(self.req("POST", "/v1/extract", {})[0], 400)
        self.assertEqual(self.req("GET", "/v1/bundle/x")[0], 404)
        self.assertEqual(self.req("POST", "/v1/session", raw=b"{not json")[0], 400)
        self.assertEqual(self.req("POST", "/v1/session", raw=b"[]")[0], 400)
        self.assertEqual(self.req("POST", "/v1/session", session("s_srv000010"), ctype="text/plain")[0], 415)

    def test_body_too_large(self):
        # Declare a length over the cap but send a tiny body: the server rejects on the header alone, so the
        # client never races a closed socket (the old 1 MB send hit BrokenPipeError about 1 run in 6).
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.putrequest("POST", "/v1/session")
        conn.putheader("Content-Type", "application/json")
        conn.putheader("Content-Length", str(server.MAX_BODY + 1))
        conn.endheaders(b"{}")
        r = conn.getresponse()
        st, b = r.status, json.loads(r.read())
        conn.close()
        self.assertEqual(st, 413)
        self.assertEqual(b, {"status": "error", "error": "too_large", "detail": "body too large"})
        self.assertEqual(self.led.rows("s_srv000001"), [])

    def test_log_has_no_bodies(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.req("POST", "/v1/session", session("s_srv000011"))
        self.assertNotIn("PROJECT X", err.getvalue())
        self.assertNotIn("Ossory", err.getvalue())


if __name__ == "__main__":
    unittest.main()


class TestPartTwoEndpoints(unittest.TestCase):
    """/v1/extract, /v1/read and /v1/bundle through the real server, mock transport."""

    def setUp(self):
        from gate.tests import test_read as tr
        from gate.tests import test_extract as te
        self.tr, self.te = tr, te
        self.dir = tempfile.TemporaryDirectory()
        self.led = Ledger(os.path.join(self.dir.name, "t.db"))
        self.calls = []
        self.keys = {"tavily": "tvly-K", "anthropic": "sk-ant-K"}
        self.start()

    def start(self):
        self.srv = server.make_server(self.led, self.transport, lambda p, s, k: ALLOW, lambda m, t: [],
                                      fake_port=8702, keys=self.keys, port=0)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def stop(self):
        self.srv.shutdown()
        self.srv.server_close()

    def tearDown(self):
        self.stop()
        self.led.close()
        self.dir.cleanup()

    def transport(self, dest, path, payload, headers):
        self.calls.append((dest, path, payload, dict(headers)))
        if path == "/search":
            return self.tr.search_reply()
        if path == "/extract":
            return self.te.extract_reply([(self.tr.PAGES[0][0], "Extracted page text.")])
        return self.tr.anthropic_reply([self.tr.claim()])

    def req(self, method, path, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.srv.server_address[1], timeout=5)
        data = json.dumps(body).encode() if body is not None else None
        conn.request(method, path, body=data, headers={"Content-Type": "application/json"} if data else {})
        r = conn.getresponse()
        raw = r.read()
        out = (r.status, r.getheader("Content-Type"), raw)
        conn.close()
        return out

    def jreq(self, method, path, body=None):
        st, _, raw = self.req(method, path, body)
        return st, json.loads(raw)

    def setup_session(self, sid="s_two000001", mode="doublethink", source="real"):
        self.assertEqual(self.jreq("POST", "/v1/session", session(sid, mode, source))[0], 200)
        comp = "planner" if mode in ("doublethink", "two_minds") else "baseline"
        st, b = self.jreq("POST", "/v1/search", {"session_id": sid, "component": comp, "need": "sector_growth",
                                                 "query": self.tr.QUERY, "options": {"preset": "general"}})
        self.assertEqual(b["status"], "sent")
        return sid

    def read_body(self, sid, **kw):
        b = {"session_id": sid, "need": "sector_growth", "result_ids": ["r_01", "r_02"],
             "claim_types": ["revenue_growth"]}
        b.update(kw)
        return b

    def test_extract_then_read(self):
        sid = self.setup_session()
        st, b = self.jreq("POST", "/v1/extract", {"session_id": sid, "component": "planner", "need": "sector_growth",
                                                  "result_ids": ["r_01"], "options": {"preset": "text"}})
        self.assertEqual((st, b["status"], b["result_ids"]), (200, "sent", ["r_01"]))
        self.assertNotIn("Extracted page text", json.dumps(b))
        st, b = self.jreq("POST", "/v1/read", self.read_body(sid))
        self.assertEqual((st, b["status"], b["job"]), (200, "sent", "j_01"))
        self.assertEqual(b["typed"]["found"], False, "quote no longer in r_01 text once extracted")
        self.assertEqual(self.calls[-1][:2], ("api.anthropic.com", "/v1/messages"))

    def test_read_typed(self):
        sid = self.setup_session()
        st, b = self.jreq("POST", "/v1/read", self.read_body(sid))
        self.assertEqual(st, 200)
        self.assertEqual(b["typed"]["values"][0]["value"], 7.4)
        self.assertEqual([r["row_type"] for r in b["ledger"]], ["attempt", "result"])

    def test_caller_cannot_supply_path_header_or_key(self):
        sid = self.setup_session()
        n = len(self.calls)
        for extra in ({"path": "/v1/files"}, {"headers": {"x-api-key": "evil"}}, {"api_key": "evil"},
                      {"destination": "evil.example.com"}):
            st, b = self.jreq("POST", "/v1/read", self.read_body(sid, **extra))
            self.assertEqual((st, b["status"], b["error"]), (400, "error", "bad_request"), extra)
            st, b = self.jreq("POST", "/v1/extract", dict({"session_id": sid, "component": "planner", "need": "n",
                                                           "result_ids": ["r_01"], "options": {"preset": "text"}},
                                                          **extra))
            self.assertEqual((st, b["error"]), (400, "bad_request"), extra)
            st, b = self.jreq("POST", "/v1/search", {"session_id": sid, "component": "planner", "need": "n",
                                                     "query": "q", "options": {"preset": "general"}, **extra})
            self.assertEqual((st, b["error"]), (400, "bad_request"), extra)
        self.assertEqual(len(self.calls), n)

    def test_extract_options_cannot_carry_extras(self):
        sid = self.setup_session()
        st, b = self.jreq("POST", "/v1/extract", {"session_id": sid, "component": "planner", "need": "n",
                                                  "result_ids": ["r_01"],
                                                  "options": {"preset": "text", "extract_depth": "advanced"}})
        self.assertEqual((st, b["error"]), (400, "bad_options"))

    def test_mixed_searches_400(self):
        sid = self.setup_session()
        self.jreq("POST", "/v1/search", {"session_id": sid, "component": "planner", "need": "n", "query": "other q",
                                         "options": {"preset": "general"}})
        n = len(self.led.rows(sid))
        st, b = self.jreq("POST", "/v1/read", self.read_body(sid, result_ids=["r_01", "r_03"]))
        self.assertEqual((st, b["error"]), (400, "mixed_searches"))
        self.assertEqual(len(self.led.rows(sid)), n)

    def test_read_missing_anthropic_key(self):
        self.stop()
        self.keys = {"tavily": "tvly-K"}
        self.start()
        sid = self.setup_session()
        n = len(self.led.rows(sid))
        st, b = self.jreq("POST", "/v1/read", self.read_body(sid))
        self.assertEqual((st, b["status"], b["error"]), (500, "error", "gate_config"))
        self.assertIn("ANTHROPIC_API_KEY", b["detail"])
        self.assertEqual(len(self.led.rows(sid)), n)
        st, b = self.jreq("GET", "/v1/health")
        self.assertEqual(st, 200, "server still up")

    def test_read_refused_in_single_agent(self):
        sid = self.setup_session("s_two000002", mode="single_agent", source="fake")
        st, b = self.jreq("POST", "/v1/read", self.read_body(sid))
        self.assertEqual((st, b["error"]), (400, "component_mode_mismatch"))

    def test_bundle_not_available(self):
        sid = self.setup_session()
        with mock.patch("gate.bundle._load", side_effect=bundle.NotAvailable("proof/ is not present")):
            st, b = self.jreq("GET", f"/v1/bundle?session_id={sid}")
        self.assertEqual((st, b["status"], b["error"]), (501, "error", "not_available"))

    def test_bundle_bytes_served_exactly(self):
        sid = self.setup_session()
        payload = b'{"format":"doublethink-bundle","v":1}'
        with mock.patch("gate.bundle._load", return_value=lambda *a, **k: payload):
            st, ctype, raw = self.req("GET", f"/v1/bundle?session_id={sid}")
        self.assertEqual((st, raw), (200, payload))
        self.assertTrue(ctype.startswith("application/json"))

    def test_bundle_errors(self):
        self.assertEqual(self.jreq("GET", "/v1/bundle?session_id=s_nosuch0001")[0], 404)
        self.assertEqual(self.jreq("GET", "/v1/bundle?session_id=../etc")[0], 400)
        self.assertEqual(self.jreq("GET", "/v1/bundle")[0], 400)
        sid = self.setup_session()
        with mock.patch("gate.bundle._load", return_value=mock.Mock(side_effect=RuntimeError("x"))):
            st, b = self.jreq("GET", f"/v1/bundle?session_id={sid}")
        self.assertEqual((st, b["error"]), (500, "internal"))
