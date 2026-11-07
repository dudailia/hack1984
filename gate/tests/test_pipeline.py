import glob
import os
import re
import tempfile
import unittest

from gate import canonical as c
from gate.ledger import Ledger
from gate.pipeline import Pipeline
from gate.session import SessionStore

FAKE_PORT = 8702
FAKE = f"127.0.0.1:{FAKE_PORT}"
GATE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ALLOW = {"decision": "allow", "rule": None, "detail": None}
BLOCK = {"decision": "block", "rule": "secret.buyer", "detail": "matches a confirmed secret (buyer)"}


def session_body(sid, mode="doublethink", source="real"):
    return {"session_id": sid, "mode": mode, "source": source, "memo": "m", "canary": "kq7m2xw9tpa4hd3n",
            "confirmed_secrets": [], "approved_public_terms": []}


class RecordingTransport:
    """Asserts at call time that an attempt row for exactly these bytes is already in the ledger."""

    def __init__(self, test, ledger, sid, reply=(200, b'{"ok":true}'), exc=None):
        self.test, self.ledger, self.sid, self.reply, self.exc = test, ledger, sid, reply, exc
        self.calls = []

    def __call__(self, destination, path, payload, headers):
        rows = self.ledger.rows(self.sid)
        self.test.assertTrue(rows, "transport called with no ledger row")
        last = rows[-1]
        self.test.assertEqual(last["row_type"], "attempt")
        self.test.assertEqual(last["decision"], "allowed")
        nonce, stored = self.ledger.private(self.sid, last["seq"])
        self.test.assertEqual(stored, payload)
        self.test.assertEqual(c.commitment(nonce, payload), last["commitment"])
        self.test.assertEqual(last["bytes"], len(payload))
        self.test.assertEqual(last["destination"], destination)
        self.calls.append((destination, path, payload, headers))
        if self.exc:
            raise self.exc
        return self.reply


class Base(unittest.TestCase):
    sid = "s_pipe00001"
    mode, source = "doublethink", "real"
    check = ALLOW

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.led = Ledger(os.path.join(self.dir.name, "t.db"))
        self.store = SessionStore(self.led, memo_tokens_fn=lambda m, t: [])
        self.store.create(session_body(self.sid, self.mode, self.source))
        self.check_calls = []
        self.tr = RecordingTransport(self, self.led, self.sid)

    def tearDown(self):
        self.led.close()
        self.dir.cleanup()

    def run_all(self, payload, session, kind):
        self.check_calls.append((payload, kind))
        if isinstance(self.check, Exception):
            raise self.check
        return self.check

    def pipe(self):
        return Pipeline(self.led, self.store, self.tr, self.run_all, FAKE_PORT)

    def send(self, kind="search", dest="api.tavily.com", body=None, **kw):
        body = body if body is not None else {"query": "payments processing growth", "topic": "general"}
        return self.pipe().send(self.sid, "planner", kind, dest, "/search", body,
                                headers={"Authorization": "Bearer tvly-NEVERSTORE"}, **kw)


class TestAllowed(Base):
    def test_sent_rows_and_exact_bytes(self):
        body = {"query": "café growth", "max_results": 10}
        out = self.send(body=body, credits_fn=lambda status, resp: 1)
        self.assertEqual(out["status"], "sent")
        self.assertEqual(len(self.tr.calls), 1)
        sent = self.tr.calls[0][2]
        self.assertEqual(sent, c.canonical_json(body))
        self.assertEqual(self.check_calls[0][0], sent.decode("utf-8"))
        rows = self.led.rows(self.sid)
        self.assertEqual([r["row_type"] for r in rows], ["attempt", "result"])
        self.assertEqual(rows[1]["attempt_seq"], 1)
        self.assertEqual(rows[1]["http_status"], 200)
        self.assertEqual(rows[1]["credits_used"], 1)
        self.assertEqual(out["rows"], rows)
        self.assertEqual(out["ledger_seq"], 1)
        self.assertEqual(out["response"], b'{"ok":true}')
        self.assertTrue(self.led.verify_chain(self.sid))

    def test_headers_never_stored(self):
        self.send()
        with open(os.path.join(self.dir.name, "t.db"), "rb") as f:
            con_bytes = f.read()
        self.assertNotIn(b"NEVERSTORE", con_bytes)
        self.assertNotIn(b"Authorization", con_bytes)

    def test_check_gets_a_copy_of_session(self):
        def mutating(payload, session, kind):
            session["call_count"] = 999
            return ALLOW
        Pipeline(self.led, self.store, self.tr, mutating, FAKE_PORT).send(
            self.sid, "planner", "search", "api.tavily.com", "/search", {"q": 1})
        self.assertEqual(self.store.get(self.sid)["call_count"], 0)

    def test_http_error_gives_error_result(self):
        for status in (401, 500):
            self.tr.reply = (status, b'{"detail":"no"}')
            out = self.send()
            self.assertEqual(out["status"], "error")
            self.assertEqual(out["rows"][-1]["status"], "error")
            self.assertEqual(out["rows"][-1]["http_status"], status)

    def test_transport_exception_gives_error_result(self):
        self.tr.exc = OSError("connection refused")
        out = self.send()
        self.assertEqual(out["status"], "error")
        r = out["rows"][-1]
        self.assertEqual((r["row_type"], r["status"], r["http_status"], r["credits_used"]),
                         ("result", "error", None, None))

    def test_credits_fn_failure_is_null(self):
        def bad(status, resp):
            raise ValueError("bad json")
        out = self.send(credits_fn=bad)
        self.assertIsNone(out["rows"][-1]["credits_used"])


class TestBlocked(Base):
    check = BLOCK

    def test_check_block_enforced(self):
        out = self.send()
        self.assertEqual(out["status"], "blocked")
        self.assertEqual(out["rule"], "secret.buyer")
        self.assertEqual(out["detail"], "matches a confirmed secret (buyer)")
        self.assertEqual(self.tr.calls, [])
        rows = self.led.rows(self.sid)
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["decision"], rows[0]["rule"]), ("blocked", "secret.buyer"))

    def test_check_raises_fails_closed(self):
        self.check = RuntimeError("boom")
        out = self.send()
        self.assertEqual((out["status"], out["rule"]), ("blocked", "gate.check_error"))
        self.assertEqual(self.tr.calls, [])

    def test_malformed_check_result_fails_closed(self):
        for bad in (None, "allow", {"decision": "ok"}, {"decision": "block", "rule": None, "detail": None},
                    {"decision": "allow", "rule": 5, "detail": None}):
            self.check = bad
            out = self.send()
            self.assertEqual(out["rule"], "gate.check_error", msg=repr(bad))
        self.assertEqual(self.tr.calls, [])

    def test_ledger_failure_means_no_send(self):
        self.check = ALLOW

        def broken(*a, **k):
            raise RuntimeError("disk full")
        self.led.append_attempt = broken
        with self.assertRaises(RuntimeError):
            self.send()
        self.assertEqual(self.tr.calls, [])


class TestGateRules(Base):
    def assert_gate_block(self, rule, **kw):
        n = len(self.check_calls)
        out = self.send(**kw)
        self.assertEqual((out["status"], out["rule"]), ("blocked", rule))
        self.assertEqual(self.tr.calls, [])
        self.assertEqual(len(self.check_calls), n + 1, "run_all must run even when a gate rule fires")
        self.assertEqual(out["rows"][-1]["decision"], "blocked")
        self.assertEqual(out["rows"][-1]["rule"], rule)

    def test_host_not_allowed(self):
        self.assert_gate_block("gate.host_not_allowed", dest="evil.example.com")
        self.assert_gate_block("gate.host_not_allowed", dest="api.tavily.com.evil.com")
        self.assert_gate_block("gate.host_not_allowed", dest="API.TAVILY.COM")
        self.assert_gate_block("gate.host_not_allowed", dest="127.0.0.1:9999")

    def test_fake_not_allowed_on_real(self):
        self.assert_gate_block("gate.fake_not_allowed", dest=FAKE)

    def test_anthropic_not_reader(self):
        self.assert_gate_block("gate.anthropic_not_reader", dest="api.anthropic.com", kind="search")

    def test_reader_only_to_anthropic(self):
        self.assert_gate_block("gate.host_not_allowed", dest="api.tavily.com", kind="reader")

    def test_unknown_result_id_pre_rule(self):
        self.assert_gate_block("gate.unknown_result_id", kind="extract", pre_rule="gate.unknown_result_id")

    def test_gate_rule_beats_check_rule(self):
        self.check = BLOCK
        self.assert_gate_block("gate.host_not_allowed", dest="evil.example.com")

    def test_reader_to_anthropic_allowed(self):
        out = self.send(dest="api.anthropic.com", kind="reader")
        self.assertEqual(out["status"], "sent")


class TestFakeOnlyMode(Base):
    sid = "s_base00001"
    mode, source = "compromised", "fake"
    check = BLOCK

    def test_check_block_recorded_but_allowed(self):
        out = self.send(dest=FAKE)
        self.assertEqual(out["status"], "sent")
        self.assertEqual(out["rule"], "secret.buyer")
        a = out["rows"][0]
        self.assertEqual((a["decision"], a["rule"], a["destination"]), ("allowed", "secret.buyer", FAKE))
        self.assertEqual(len(self.tr.calls), 1)

    def test_real_tavily_refused_on_fake(self):
        out = self.send(dest="api.tavily.com")
        self.assertEqual((out["status"], out["rule"]), ("blocked", "gate.host_not_allowed"))
        self.assertEqual(self.tr.calls, [])

    def test_reader_check_block_enforced_in_every_mode(self):
        out = self.send(dest="api.anthropic.com", kind="reader")
        self.assertEqual((out["status"], out["rule"]), ("blocked", "secret.buyer"))
        self.assertEqual(self.tr.calls, [])

    def test_check_error_enforced_in_fake_mode(self):
        self.check = RuntimeError("boom")
        out = self.send(dest=FAKE)
        self.assertEqual((out["status"], out["rule"]), ("blocked", "gate.check_error"))
        self.assertEqual(self.tr.calls, [])


class TestDoublethinkOnFake(Base):
    sid = "s_dtfake001"
    mode, source = "doublethink", "fake"
    check = BLOCK

    def test_enforced_on_fake(self):
        out = self.send(dest=FAKE)
        self.assertEqual(out["status"], "blocked")
        self.assertEqual(self.tr.calls, [])


class TestSourceLevel(unittest.TestCase):
    """Network access is confined to gate/transport.py."""

    def gate_sources(self):
        out = {}
        for p in glob.glob(os.path.join(GATE_DIR, "*.py")):
            with open(p, encoding="utf-8") as f:
                out[os.path.basename(p)] = f.read()
        return out

    def test_network_imports_only_in_transport(self):
        pat = re.compile(r"^\s*(import|from)\s+(urllib|http\.client|socket|ssl|requests|httpx)\b", re.M)
        offenders = [name for name, src in self.gate_sources().items() if pat.search(src)]
        self.assertEqual(offenders, ["transport.py"])

    def test_https_post_only_wired_in_server(self):
        users = sorted(n for n, s in self.gate_sources().items() if "https_post" in s)
        self.assertTrue(set(users) <= {"transport.py", "server.py"}, users)


if __name__ == "__main__":
    unittest.main()
