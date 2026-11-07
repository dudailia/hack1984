"""GateClient: requests match FORMATS §3 exactly; the session is refused unless source = fake."""
import json
import unittest

from baseline import gate_client
from baseline.agent import load_demo_spec
from baseline.tests.stubs import StubGate, canonical


class GateClientTest(unittest.TestCase):
    def setUp(self):
        self.gate = StubGate().start()
        self.addCleanup(self.gate.stop)
        self.client = gate_client.GateClient(self.gate.port)
        self.spec = load_demo_spec()

    def _session(self, **over):
        kw = dict(session_id=self.spec["session_id"], mode="single_agent", memo=self.spec["memo"],
                  canary=self.spec["canary"], confirmed_secrets=self.spec["confirmed_secrets"],
                  approved_public_terms=self.spec["approved_public_terms"])
        kw.update(over)
        return self.client.create_session(**kw)

    def test_session_request_matches_spec(self):
        resp = self._session(mode="compromised")
        self.assertEqual(resp["status"], "ok")
        [req] = self.gate.requests
        self.assertEqual(req["method"], "POST")
        self.assertEqual(req["path"], "/v1/session")
        self.assertEqual(req["headers"].get("Content-Type"), "application/json")
        expected = {"session_id": self.spec["session_id"], "mode": "compromised", "source": "fake",
                    "memo": self.spec["memo"], "canary": self.spec["canary"],
                    "confirmed_secrets": self.spec["confirmed_secrets"],
                    "approved_public_terms": self.spec["approved_public_terms"]}
        self.assertEqual(req["body"], expected)
        self.assertEqual(req["raw"], canonical(expected))

    def test_search_request_matches_spec(self):
        self._session()
        resp = self.client.search(self.spec["session_id"], "sector_growth", "payments sector growth 2025", "general")
        self.assertEqual(resp["status"], "sent")
        self.assertTrue(resp["results"])
        req = self.gate.requests[-1]
        self.assertEqual(req["path"], "/v1/search")
        self.assertEqual(req["headers"].get("Content-Type"), "application/json")
        expected = {"session_id": self.spec["session_id"], "component": "baseline", "need": "sector_growth",
                    "query": "payments sector growth 2025", "options": {"preset": "general"}}
        self.assertEqual(req["body"], expected)
        self.assertEqual(req["raw"], canonical(expected))

    def test_session_refused_unless_source_fake(self):
        for source in ("real", "", None, "FAKE"):
            with self.subTest(source=source):
                with self.assertRaises(ValueError):
                    self._session(source=source)
        self.assertEqual(self.gate.requests, [], "a refused session must not reach the Gate")

    def test_session_refused_for_non_baseline_modes(self):
        for mode in ("doublethink", "two_minds", "anything"):
            with self.subTest(mode=mode):
                with self.assertRaises(ValueError):
                    self._session(mode=mode)
        self.assertEqual(self.gate.requests, [])

    def test_gate_refusal_raises_gate_error(self):
        # Bypass the client-side guard to prove a Gate-side refusal also stops the run.
        status, body = gate_client.loopback.post_json(
            self.gate.port, "/v1/session",
            {"session_id": "s_x1234567", "mode": "single_agent", "source": "real", "memo": "m", "canary": "c",
             "confirmed_secrets": [], "approved_public_terms": []})
        self.assertEqual(status, 400)
        with self.assertRaises(gate_client.GateError) as cm:
            gate_client.check_response(status, body)
        self.assertEqual(cm.exception.code, "source_not_allowed")

    def test_search_on_unknown_session_raises(self):
        with self.assertRaises(gate_client.GateError):
            self.client.search("s_nosuchsess", "sector_growth", "payments", "general")

    def test_bad_search_args_refused_locally(self):
        self._session()
        n = len(self.gate.requests)
        for need, query, preset in (("Bad Need", "q", "general"), ("ok", "", "general"),
                                    ("ok", "q", "advanced"), ("ok", "x" * 401, "general")):
            with self.subTest(need=need, preset=preset):
                with self.assertRaises(ValueError):
                    self.client.search(self.spec["session_id"], need, query, preset)
        self.assertEqual(len(self.gate.requests), n)

    def test_blocked_is_returned_not_raised(self):
        self.gate.block_queries.add("blocked query")
        self._session()
        resp = self.client.search(self.spec["session_id"], "sector_growth", "blocked query", "general")
        self.assertEqual(resp["status"], "blocked")


class LoopbackTest(unittest.TestCase):
    def test_non_loopback_host_refused(self):
        for host in ("api.tavily.com", "localhost", "0.0.0.0", "10.0.0.1", "127.0.0.2"):
            with self.subTest(host=host):
                with self.assertRaises(ValueError):
                    gate_client.loopback.post_json(8701, "/v1/health", {}, host=host)

    def test_bad_port_refused(self):
        for port in (0, -1, 70000, "8701", None):
            with self.subTest(port=port):
                with self.assertRaises(ValueError):
                    gate_client.GateClient(port)

    def test_body_is_canonical_json(self):
        obj = {"b": 1, "a": "é"}
        self.assertEqual(gate_client.loopback.encode(obj), b'{"a":"\xc3\xa9","b":1}')
        self.assertEqual(json.loads(gate_client.loopback.encode(obj)), obj)


if __name__ == "__main__":
    unittest.main()
