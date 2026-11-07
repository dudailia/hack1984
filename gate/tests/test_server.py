import contextlib
import http.client
import io
import json
import os
import tempfile
import threading
import unittest

from gate import server
from gate.ledger import Ledger
from gate.tests.test_tavily import tavily_reply

ALLOW = {"decision": "allow", "rule": None, "detail": None}


def session(sid, mode="doublethink", source="real"):
    return {"session_id": sid, "mode": mode, "source": source, "memo": "PROJECT X memo", "canary": "c4n4ry",
            "confirmed_secrets": [{"label": "buyer", "values": ["Ossory"]}], "approved_public_terms": ["payments"]}


class TestServer(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.led = Ledger(os.path.join(self.dir.name, "t.db"))
        self.check = ALLOW
        self.calls = []
        self.srv = server.make_server(self.led, self.transport, lambda p, s, k: self.check, lambda m, t: [],
                                      fake_port=8702, tavily_key="tvly-K", port=0)
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
        self.assertEqual(self.req("POST", "/v1/extract", {})[0], 404)
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
