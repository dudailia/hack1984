"""app/run.py: token, static files without traversal, §11 routes, verify/tamper/bundle, end to end with the stub."""
import hashlib
import json
import os
import sys
import time
import unittest
from unittest import mock

from app import _loop_stub, run
from app.tests.helpers import SECRET, AppCase, FakeLoop, make_bundle

SID = "s_finished1"


class TokenTest(AppCase):
    def test_api_and_events_need_token(self):
        for method, path in (("POST", "/api/run"), ("POST", "/api/verify"), ("POST", "/api/tamper"),
                             ("GET", "/api/bundle?session_id=" + SID), ("GET", "/events")):
            for token_kw, headers in ((False, {}), ("bad", {}), (False, {"X-DT-Token": "tok-12"}),
                                      (False, {"X-DT-Token": ""})):
                p = path if token_kw is False else path + ("&" if "?" in path else "?") + "token=bad"
                with self.subTest(path=path, token=token_kw, headers=headers):
                    status, _h, raw = self.request(method, p, b"{}" if method == "POST" else None, headers,
                                                   token=False)
                    self.assertEqual(status, 401)
                    self.assertEqual(json.loads(raw)["error"], "unauthorized")
        self.assertEqual(self.loop.calls, [])

    def test_header_and_query_token_accepted(self):
        status, _h, _r = self.request("GET", "/api/bundle?session_id=s_unknown01", headers={"X-DT-Token": "tok-123"},
                                      token=False)
        self.assertEqual(status, 404)
        status, _h, _r = self.request("GET", "/api/bundle?session_id=s_unknown01")
        self.assertEqual(status, 404)

    def test_launch_url(self):
        self.assertEqual(self.app.ui_url(8700), "http://127.0.0.1:8700/ui/index.html?token=tok-123")

    def test_default_token_random(self):
        a, b = run.App(root=self.root), run.App(root=self.root)
        self.assertGreaterEqual(len(a.token), 32)
        self.assertNotEqual(a.token, b.token)


class StaticTest(AppCase):
    def test_serves_static_without_token(self):
        for path, ctype, body in (("/ui/index.html", "text/html", b"<!doctype html><title>Doublethink</title>"),
                                  ("/ui/css/app.css", "text/css", b"body{}"),
                                  ("/shared/fixtures/demo.json", "application/json", b'{"demo":true}'),
                                  ("/shared/results/results.json", "application/json", b'{"v":1}')):
            with self.subTest(path=path):
                status, headers, raw = self.request("GET", path, token=False)
                self.assertEqual(status, 200)
                self.assertTrue(headers["Content-Type"].startswith(ctype))
                self.assertEqual(raw, body)

    def test_traversal_refused(self):
        for path in ("/ui/../.env", "/ui/%2e%2e/.env", "/ui/..%2f.env", "/ui/%2E%2E%2F.env",
                     "/shared/fixtures/../../.env", "/shared/fixtures/..%2F..%2F.env",
                     "/shared/results/%2e%2e/FORMATS.md",
                     "/ui/..\\.env", "/ui/%5c..%5c.env", "/ui//etc/passwd", "/ui/%2Fetc%2Fpasswd", "/ui/./index.html",
                     "/ui/link.txt", "/ui/", "/ui", "/ui/css", "/ui/index.html%00.txt", "/shared/FORMATS.md",
                     "/.env", "/shared/fixtures", "/ui/nope.html"):
            with self.subTest(path=path):
                status, _h, raw = self.request("GET", path, token=False)
                self.assertEqual(status, 404)
                self.assertNotIn(b"tvly", raw)

    def test_read_only(self):
        status, _h, _r = self.request("POST", "/ui/index.html", b"x", token=False)
        self.assertIn(status, (404, 405))
        with open(os.path.join(self.root, "ui", "index.html"), encoding="utf-8") as f:
            self.assertEqual(f.read(), "<!doctype html><title>Doublethink</title>")

    def test_head(self):
        status, headers, raw = self.request("HEAD", "/ui/index.html", token=False)
        self.assertEqual(status, 200)
        self.assertEqual(raw, b"")
        self.assertEqual(headers["Content-Length"], "41")

    def test_unknown_route(self):
        self.assertEqual(self.request("GET", "/nope", token=False)[0], 404)
        self.assertEqual(self.request("GET", "/api/nope")[0], 404)


class RunApiTest(AppCase):
    def test_starts_run_and_returns_session(self):
        status, body = self.api("/api/run", {"mode": "doublethink", "source": "real", "plant_careless": True,
                                             "question": "How fast?"})
        self.assertEqual((status, body), (200, {"session_id": "s_fakeloop01"}))
        self.assertEqual(self.loop.calls, [("doublethink", "real", True, "How fast?")])

    def test_defaults(self):
        status, _ = self.api("/api/run", {"mode": "compromised", "source": "fake"})
        self.assertEqual(status, 200)
        mode, source, careless, question = self.loop.calls[0]
        self.assertEqual((mode, source, careless), ("compromised", "fake", False))
        self.assertIn("EV/revenue", question)

    def test_fake_only_modes_refuse_real(self):
        for mode in ("single_agent", "compromised", "two_minds"):
            with self.subTest(mode=mode):
                status, body = self.api("/api/run", {"mode": mode, "source": "real", "plant_careless": False})
                self.assertEqual(status, 400)
                self.assertEqual(body["error"], "source_not_allowed")
        self.assertEqual(self.loop.calls, [])

    def test_bad_bodies(self):
        for body in ({"mode": "nope", "source": "fake"}, {"mode": "doublethink", "source": "cloud"},
                     {"source": "fake"}, {"mode": "doublethink"},
                     {"mode": "doublethink", "source": "fake", "plant_careless": "yes"},
                     {"mode": "doublethink", "source": "fake", "question": ""},
                     {"mode": "doublethink", "source": "fake", "question": "x" * 501},
                     {"mode": "doublethink", "source": "fake", "extra": 1}, [], b"not json"):
            with self.subTest(body=body):
                status, resp = self.api("/api/run", body)
                self.assertEqual(status, 400)
                self.assertEqual(resp["status"], "error")
        self.assertEqual(self.loop.calls, [])


class RunApiLoopErrorsTest(AppCase):
    def test_already_active_is_409(self):
        self.app.start_run = FakeLoop(exc=ValueError("a run is already active"))
        status, body = self.api("/api/run", {"mode": "doublethink", "source": "fake"})
        self.assertEqual((status, body["error"]), (409, "run_in_progress"))

    def test_other_value_error_is_400(self):
        self.app.start_run = FakeLoop(exc=ValueError("question too long for the planner"))
        status, body = self.api("/api/run", {"mode": "doublethink", "source": "fake"})
        self.assertEqual((status, body["error"]), (400, "bad_request"))
        self.assertIn("question too long", body["detail"])

    def test_bad_session_id_from_loop_is_500(self):
        self.app.start_run = FakeLoop(result="../../etc")
        status, body = self.api("/api/run", {"mode": "doublethink", "source": "fake"})
        self.assertEqual(status, 500)


class SessionGuardTest(AppCase):
    def test_unknown_or_unfinished_session_404(self):
        self.app.hub.emit("run_started", "s_running01", {})
        self.gate.bundles["s_running01"] = make_bundle("s_running01")
        self.gate.bundles["s_neverseen"] = make_bundle("s_neverseen")
        for sid in ("s_unknown01", "s_running01", "s_neverseen", "../etc", "", None, 5):
            with self.subTest(sid=sid):
                self.assertEqual(self.api("/api/verify", {"session_id": sid})[0], 404)
                self.assertEqual(self.api("/api/tamper", {"session_id": sid, "seq": 1})[0], 404)
                q = "" if sid is None else str(sid)
                self.assertEqual(self.request("GET", "/api/bundle?session_id=" + q)[0], 404)
        self.assertEqual([e for e in self.app.hub.events("s_running01") if e["type"] == "proof_result"], [])
        self.assertFalse(os.path.exists(self.bundles_dir))


class VerifyTest(AppCase):
    def test_verify_valid_emits_proof_result(self):
        self.finished_session(SID)
        status, body = self.api("/api/verify", {"session_id": SID})
        self.assertEqual(status, 200)
        pr = self.app.hub.events(SID)[-1]
        self.assertEqual(pr["type"], "proof_result")
        bundle = json.loads(self.gate.bundles[SID])
        self.assertEqual(pr["data"], {"bundle_head": bundle["head"], "tampered": False, "tampered_seq": None,
                                      "valid": True, "broken_at_seq": None, "rows_checked": 4, "reason": None,
                                      "signer_key_sha256": "ab" * 32})
        self.assertEqual(body, pr["data"])
        with open(os.path.join(self.bundles_dir, SID + ".json"), "rb") as f:
            self.assertEqual(f.read(), self.gate.bundles[SID])
        self.assertEqual(self.gate.requests[-1], "/v1/bundle?session_id=" + SID)

    def test_gate_without_bundle_is_502_and_never_valid(self):
        self.finished_session(SID, bundle=False)
        status, body = self.api("/api/verify", {"session_id": SID})
        self.assertEqual((status, body["error"]), (502, "gate_bundle_unavailable"))
        self.assertNotIn("proof_result", [e["type"] for e in self.app.hub.events(SID)])

    def test_invalid_bundle_reported_invalid(self):
        self.finished_session(SID)
        b = json.loads(self.gate.bundles[SID])
        b["rows"][1]["response_commitment"] = "0" * 64
        self.gate.bundles[SID] = json.dumps(b).encode()
        status, body = self.api("/api/verify", {"session_id": SID})
        self.assertEqual(status, 200)
        self.assertEqual((body["valid"], body["broken_at_seq"], body["reason"]), (False, 2, "hash_mismatch"))

    def test_verifier_missing_is_503(self):
        self.finished_session(SID)
        self.app.verify_cmd = None  # default: <root>/proof/verify.py, which does not exist in the temp root
        status, body = self.api("/api/verify", {"session_id": SID})
        self.assertEqual((status, body["error"]), (503, "proof_unavailable"))
        self.assertNotIn("proof_result", [e["type"] for e in self.app.hub.events(SID)])

    def test_verifier_garbage_is_502(self):
        self.finished_session(SID)
        self.app.verify_cmd = [sys.executable, "-c", "print('VALID')"]
        status, body = self.api("/api/verify", {"session_id": SID})
        self.assertEqual((status, body["error"]), (502, "verifier_error"))
        self.assertNotIn("proof_result", [e["type"] for e in self.app.hub.events(SID)])

    def test_valid_json_but_nonzero_exit_is_not_valid(self):
        self.finished_session(SID)
        out = json.dumps({"valid": True, "rows_checked": 4, "broken_at_seq": None, "reason": None})
        self.app.verify_cmd = [sys.executable, "-c", "import sys; print(%r); sys.exit(1)" % out]
        status, body = self.api("/api/verify", {"session_id": SID})
        self.assertEqual(status, 200)
        self.assertIs(body["valid"], False)


class VerifyNoSignerTest(AppCase):
    signer = False

    def test_signer_null_when_absent(self):
        self.finished_session(SID)
        status, body = self.api("/api/verify", {"session_id": SID})
        self.assertEqual(status, 200)
        self.assertIsNone(body["signer_key_sha256"])


class TamperTest(AppCase):
    def setUp(self):
        super().setUp()
        self.finished_session(SID)
        self.assertEqual(self.api("/api/verify", {"session_id": SID})[0], 200)
        self.original = os.path.join(self.bundles_dir, SID + ".json")
        with open(self.original, "rb") as f:
            self.orig_bytes = f.read()
        self.orig_mtime = os.stat(self.original).st_mtime_ns

    def assert_original_untouched(self):
        with open(self.original, "rb") as f:
            self.assertEqual(f.read(), self.orig_bytes)
        self.assertEqual(os.stat(self.original).st_mtime_ns, self.orig_mtime)

    def test_fallback_flips_one_byte_in_copy(self):
        for seq in (1, 2, 3, 4):
            with self.subTest(seq=seq):
                status, body = self.api("/api/tamper", {"session_id": SID, "seq": seq})
                self.assertEqual(status, 200)
                self.assertEqual((body["tampered"], body["tampered_seq"], body["valid"]), (True, seq, False))
                self.assertEqual((body["broken_at_seq"], body["reason"]), (seq, "hash_mismatch"))
                self.assertEqual(self.app.hub.events(SID)[-1]["data"], body)
                copy = os.path.join(self.bundles_dir, "%s.tampered-%d.json" % (SID, seq))
                with open(copy, "rb") as f:
                    tampered = f.read()
                self.assertEqual(len(tampered), len(self.orig_bytes))
                self.assertEqual(sum(a != b for a, b in zip(tampered, self.orig_bytes)), 1)
                self.assert_original_untouched()
        # the original still verifies
        status, body = self.api("/api/verify", {"session_id": SID})
        self.assertIs(body["valid"], True)

    def test_uses_proof_helper_on_a_copy(self):
        seen = []

        def helper(path, seq):
            seen.append(path)
            with open(path, "rb") as f:
                self.assertEqual(f.read(), self.orig_bytes)
            with open(path, "wb") as f:  # even a helper that writes its input cannot reach the original
                f.write(b"garbage")
            return {"bundle_head": "h", "tampered": True, "tampered_seq": seq, "valid": False, "broken_at_seq": seq,
                    "rows_checked": seq, "reason": "hash_mismatch", "extra_key": "dropped"}

        self.app.tamper_helper = helper
        status, body = self.api("/api/tamper", {"session_id": SID, "seq": 3})
        self.assertEqual(status, 200)
        self.assertEqual(len(seen), 1)
        self.assertNotEqual(os.path.realpath(seen[0]), os.path.realpath(self.original))
        self.assertEqual(body, {"bundle_head": "h", "tampered": True, "tampered_seq": 3, "valid": False,
                                "broken_at_seq": 3, "rows_checked": 3, "reason": "hash_mismatch",
                                "signer_key_sha256": None})
        self.assert_original_untouched()

    def test_helper_cannot_claim_valid_for_a_tamper(self):
        self.app.tamper_helper = lambda path, seq: {"valid": True, "tampered": True, "tampered_seq": seq}
        status, body = self.api("/api/tamper", {"session_id": SID, "seq": 1})
        self.assertEqual(status, 502)
        self.assert_original_untouched()

    def test_bad_seq(self):
        for seq in (0, 5, -1, "1", True, None, 1.0):
            with self.subTest(seq=seq):
                status, _ = self.api("/api/tamper", {"session_id": SID, "seq": seq})
                self.assertIn(status, (400, 404))
        self.assert_original_untouched()

    def test_tamper_fetches_original_if_not_saved(self):
        sid = self.finished_session("s_finished2")
        status, body = self.api("/api/tamper", {"session_id": sid, "seq": 2})
        self.assertEqual(status, 200)
        with open(os.path.join(self.bundles_dir, sid + ".json"), "rb") as f:
            self.assertEqual(f.read(), self.gate.bundles[sid])


class BundleDownloadTest(AppCase):
    def test_download(self):
        self.finished_session(SID)
        status, headers, raw = self.request("GET", "/api/bundle?session_id=" + SID)
        self.assertEqual(status, 200)
        self.assertEqual(raw, self.gate.bundles[SID])
        self.assertIn('attachment; filename="%s.json"' % SID, headers["Content-Disposition"])
        self.assertTrue(headers["Content-Type"].startswith("application/json"))


class EndToEndStubTest(AppCase):
    """POST /api/run with the stub loop, then read /events to run_done."""

    start_run = staticmethod(_loop_stub.start_run)

    def setUp(self):
        p = mock.patch.object(_loop_stub, "TIME_SCALE", 0.0)
        p.start()
        self.addCleanup(p.stop)
        super().setUp()
        self.addCleanup(_loop_stub.wait_idle, 5)

    def run_and_read(self, body):
        status, resp = self.api("/api/run", body)
        self.assertEqual(status, 200, resp)
        sid = resp["session_id"]
        frames = self.sse(until=lambda fr: any(env["type"] == "run_done" and env["session_id"] == sid
                                               for _k, env in fr))
        envs = [env for _k, env in frames if env["session_id"] == sid]
        return sid, envs

    def test_compromised_run_streams_to_run_done(self):
        sid, envs = self.run_and_read({"mode": "compromised", "source": "fake", "plant_careless": False})
        self.assertRegex(sid, r"^s_[a-z0-9]{8,16}$")
        types = [e["type"] for e in envs]
        self.assertEqual(types[:3], ["run_started", "memo_loaded", "parties_confirmed"])
        self.assertEqual(types[-1], "run_done")
        self.assertIn("ledger_row", types)
        self.assertNotIn("beat", types)
        seqs = [e["seq"] for e in envs]
        self.assertEqual(seqs, list(range(seqs[0], seqs[0] + len(seqs))))
        self.assertEqual(envs[0]["data"]["mode"], "compromised")
        leaks = [e for e in envs if e["type"] == "ledger_row" and e["data"]["row"]["session_id"] != sid]
        self.assertEqual(leaks, [], "fixture session ids are rewritten to the new session id")
        self.assertTrue(self.app.hub.finished(sid))

    def test_last_event_id_resume_over_http(self):
        sid, envs = self.run_and_read({"mode": "doublethink", "source": "fake"})
        cut = envs[4]["seq"]
        frames = self.sse(until=lambda fr: any(env["type"] == "run_done" for _k, env in fr), last_event_id=cut)
        self.assertEqual([env["seq"] for _k, env in frames], [e["seq"] for e in envs if e["seq"] > cut])

    def test_second_run_while_active_is_409(self):
        with mock.patch.object(_loop_stub, "TIME_SCALE", 1.0):
            status, resp = self.api("/api/run", {"mode": "doublethink", "source": "fake"})
            self.assertEqual(status, 200)
            status, body = self.api("/api/run", {"mode": "doublethink", "source": "fake"})
            self.assertEqual((status, body["error"]), (409, "run_in_progress"))
            _loop_stub.cancel()

    def test_ping_when_idle(self):
        t0 = time.monotonic()
        frames = self.sse(until=lambda fr: ("ping", None) in fr, keep_pings=True, timeout=5)
        self.assertIn(("ping", None), frames)
        self.assertLess(time.monotonic() - t0, 3)


class StubLoopContractTest(unittest.TestCase):
    def setUp(self):
        p = mock.patch.object(_loop_stub, "TIME_SCALE", 0.0)
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(_loop_stub.wait_idle, 5)

    def test_returns_immediately_and_emits_positional(self):
        calls = []
        sid = _loop_stub.start_run("doublethink", "real", False, "q?", lambda t, s, d: calls.append((t, s, d)))
        self.assertRegex(sid, r"^s_[a-z0-9]{8,16}$")
        self.assertTrue(_loop_stub.wait_idle(5))
        self.assertEqual(calls[0][0], "run_started")
        self.assertEqual(calls[-1][0], "run_done")
        self.assertEqual({s for _t, s, _d in calls}, {sid})
        self.assertEqual(calls[0][2]["question"], "q?")
        self.assertIn("answer", [t for t, _s, _d in calls])

    def test_validation(self):
        for args in (("single_agent", "real"), ("two_minds", "real"), ("nope", "fake"), ("doublethink", "x")):
            with self.subTest(args=args), self.assertRaises(ValueError):
                _loop_stub.start_run(args[0], args[1], False, "q", lambda *a: None)

    def test_already_active(self):
        with mock.patch.object(_loop_stub, "TIME_SCALE", 1.0):
            _loop_stub.start_run("doublethink", "fake", False, "q", lambda *a: None)
            with self.assertRaises(ValueError) as cm:
                _loop_stub.start_run("doublethink", "fake", False, "q", lambda *a: None)
            self.assertIn("already active", str(cm.exception))
            _loop_stub.cancel()

    def test_fixture_choice(self):
        for args, want in ((("compromised", "fake", False), "compromised"), (("single_agent", "fake", False),
                                                                              "single_agent"),
                           (("doublethink", "fake", True), "doublethink"), (("doublethink", "real", False),
                                                                           "doublethink")):
            calls = []
            _loop_stub.start_run(*args, "q", lambda t, s, d: calls.append((t, d)))
            _loop_stub.wait_idle(5)
            self.assertEqual(calls[0][1]["mode"], want)
            self.assertEqual(calls[0][1]["plant_careless"], args[2])
            if args[2]:
                self.assertIn("blocked", [t for t, _d in calls])


class LoaderTest(unittest.TestCase):
    def test_falls_back_to_stub_when_loop_missing(self):
        real = run.importlib.util.find_spec
        with mock.patch.object(run.importlib.util, "find_spec",
                               side_effect=lambda name, *a: None if name == "app.loop" else real(name, *a)):
            fn, is_stub = run.load_start_run()
        self.assertIs(fn, _loop_stub.start_run)
        self.assertTrue(is_stub)

    def test_uses_app_loop_when_present(self):
        if not os.path.exists(os.path.join(run.REPO, "app", "loop.py")):
            self.skipTest("app/loop.py not merged")
        from app import loop
        fn, is_stub = run.load_start_run()
        self.assertIs(fn, loop.start_run)
        self.assertFalse(is_stub)

    def test_tamper_helper_absent_is_none(self):
        if os.path.exists(os.path.join(run.REPO, "proof", "tamper.py")):
            self.skipTest("proof/tamper.py exists")
        self.assertIsNone(run.load_tamper_helper())


class FlipTest(unittest.TestCase):
    def test_flip_targets_row_commitment(self):
        data = make_bundle("s_flip0000")
        b = json.loads(data)
        for row in b["rows"]:
            out = run.flip_row_byte(data, row["seq"])
            diff = [i for i, (x, y) in enumerate(zip(data, out)) if x != y]
            self.assertEqual(len(diff), 1)
            value = row.get("commitment") or row.get("response_commitment")
            self.assertEqual(diff[0], data.index(value.encode()))
            self.assertIn(chr(out[diff[0]]), "0123456789abcdef")
        with self.assertRaises(KeyError):
            run.flip_row_byte(data, 99)
        self.assertEqual(hashlib.sha256(data).hexdigest(), hashlib.sha256(make_bundle("s_flip0000")).hexdigest())


if __name__ == "__main__":
    unittest.main()
