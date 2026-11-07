"""Regression tests for the invariant-auditor findings on the first Gate build."""
import json
import os
import sqlite3
import tempfile
import unittest
from unittest import mock

from gate import checks_bridge, transport
from gate.ledger import Ledger
from gate.pipeline import Pipeline
from gate.session import SessionStore, SessionError
from gate import server


def sbody(sid):
    return {"session_id": sid, "mode": "doublethink", "source": "real", "memo": "m", "canary": "c",
            "confirmed_secrets": [], "approved_public_terms": []}


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, "t.db")
        self.led = Ledger(self.path)

    def tearDown(self):
        self.led.close()
        self.dir.cleanup()


class TestIdTrailingNewline(Base):
    def test_session_id_newline_refused(self):
        store = SessionStore(self.led, lambda m: [])
        with self.assertRaises(SessionError):
            store.create(sbody("s_abcdefgh\n"))

    def test_need_newline_refused(self):
        self.assertIsNone(server.NEED_RE.fullmatch("need\n"))
        self.assertIsNone(server.NEED_RE.fullmatch("bad-need"))


class TestInsertTriggers(Base):
    def test_insert_or_replace_refused(self):
        self.led.append_attempt("s_hard00001", "planner", "search", "api.tavily.com", b"{}", "allowed", None)
        con = sqlite3.connect(self.path)
        with self.assertRaises(sqlite3.DatabaseError):
            con.execute("INSERT OR REPLACE INTO ledger VALUES ('s_hard00001',1,'attempt',x'00','h',x'00',x'00')")
        con.close()
        self.assertTrue(self.led.verify_chain("s_hard00001"))

    def test_seq_gap_refused(self):
        con = sqlite3.connect(self.path)
        with self.assertRaises(sqlite3.DatabaseError):
            con.execute("INSERT INTO ledger VALUES ('s_hard00002',2,'attempt',x'00','h',x'00',x'00')")
        con.close()


class TestCheckSystemExit(Base):
    def test_system_exit_in_checks_is_check_error_with_row(self):
        store = SessionStore(self.led, lambda m: [])
        store.create(sbody("s_hard00003"))

        def exits(p, s, k):
            raise SystemExit(1)
        sent = []
        pipe = Pipeline(self.led, store, lambda *a: sent.append(a) or (200, b"{}"), exits, 8702)
        out = pipe.send("s_hard00003", "planner", "search", "api.tavily.com", "/search", {"q": 1})
        self.assertEqual((out["status"], out["rule"]), ("blocked", "gate.check_error"))
        self.assertEqual(len(self.led.rows("s_hard00003")), 1)
        self.assertEqual(sent, [])


class TestTransport(unittest.TestCase):
    def test_refuses_non_allowlisted_host(self):
        for dest in ("evil.example.com", "api.tavily.com.evil.com", "10.0.0.1:80", "localhost:8702"):
            with self.assertRaises(ValueError):
                transport.https_post(dest, "/search", b"{}", {})

    def test_oversize_response_truncated_not_raised(self):
        class Resp:
            status = 200

            def read(self, n):
                return b"x" * n

        class Conn:
            def __init__(self, *a, **k):
                pass

            def request(self, *a, **k):
                pass

            def getresponse(self):
                return Resp()

            def close(self):
                pass

        with mock.patch("http.client.HTTPSConnection", Conn):
            status, body = transport.https_post("api.tavily.com", "/search", b"{}", {})
        self.assertEqual(status, 200)
        self.assertEqual(len(body), transport.MAX_RESPONSE)


class TestBridgeOrigin(unittest.TestCase):
    def test_checks_outside_repo_refused(self):
        spec = mock.Mock(origin="/usr/lib/python3/site-packages/checks/__init__.py")
        with mock.patch("importlib.util.find_spec", return_value=spec):
            with self.assertRaises(RuntimeError):
                checks_bridge.load()


class TestNegativeContentLength(Base):
    def test_negative_content_length_400(self):
        import http.client
        import threading
        srv = server.make_server(self.led, lambda *a: (200, b"{}"), lambda p, s, k: None, lambda m: [], 8702, None,
                                 port=0)
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        try:
            conn = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=5)
            conn.putrequest("POST", "/v1/session")
            conn.putheader("Content-Type", "application/json")
            conn.putheader("Content-Length", "-1")
            conn.endheaders()
            r = conn.getresponse()
            self.assertEqual(r.status, 400)
            self.assertEqual(json.loads(r.read())["status"], "error")
            conn.close()
        finally:
            srv.shutdown()
            srv.server_close()


if __name__ == "__main__":
    unittest.main()
