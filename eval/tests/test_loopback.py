import os
import subprocess
import sys
import tempfile
import unittest

from eval import loopback
from eval.app_client import AppClient, AppError, parse_app_url
from eval.stub_app import StubApp

REPO = loopback.REPO


class AuditHook(unittest.TestCase):
    """The hook is permanent per process, so it is tested in a child interpreter."""

    def child(self, code):
        prog = "from eval.loopback import install_audit_hook; install_audit_hook()\n" + code
        return subprocess.run([sys.executable, "-c", prog], cwd=REPO, capture_output=True, text=True, timeout=30)

    def test_non_loopback_connect_refused(self):
        r = self.child("import socket\ns = socket.socket()\ntry:\n    s.connect(('93.184.216.34', 443))\n"
                       "except Exception as e:\n    print(type(e).__name__)\n")
        self.assertIn("NetworkRefused", r.stdout)

    def test_dns_lookup_of_real_host_refused(self):
        r = self.child("import socket\ntry:\n    socket.getaddrinfo('api.tavily.com', 443)\n"
                       "except Exception as e:\n    print(type(e).__name__)\n")
        self.assertIn("NetworkRefused", r.stdout)

    def test_loopback_allowed(self):
        r = self.child("import socket\nsrv = socket.socket(); srv.bind(('127.0.0.1', 0)); srv.listen(1)\n"
                       "c = socket.socket(); c.connect(srv.getsockname()); print('ok')\n")
        self.assertEqual(r.stdout.strip(), "ok", r.stderr)


class EnvKeys(unittest.TestCase):
    def test_only_port_and_model_readable(self):
        with self.assertRaises(ValueError):
            loopback.env_value("TAVILY_API_KEY", None)
        with self.assertRaises(ValueError):
            loopback.env_value("ANTHROPIC_API_KEY", None)

    def test_reads_values_from_env_file_without_keeping_others(self):
        with tempfile.NamedTemporaryFile("w", suffix=".env", delete=False) as f:
            f.write("TAVILY_API_KEY=nope\nexport APP_PORT=8799 # c\nOLLAMA_MODEL='qwen3:8b'\n")
        try:
            self.assertEqual(loopback.app_port(env={}, env_file=f.name), 8799)
            self.assertEqual(loopback.planner_model(env={}, env_file=f.name), "qwen3:8b")
        finally:
            os.unlink(f.name)


class Client(unittest.TestCase):
    def test_parse_app_url(self):
        self.assertEqual(parse_app_url("http://127.0.0.1:8700/ui/index.html?token=ab%2Bc"), (8700, "ab+c"))
        for bad in ("https://127.0.0.1:8700/?token=x", "http://example.com:8700/?token=x", "http://127.0.0.1/?token=x"):
            with self.assertRaises(ValueError):
                parse_app_url(bad)

    def test_wrong_token_is_an_app_error(self):
        with StubApp() as app:
            with self.assertRaises(AppError):
                AppClient(app.port, "wrong").start_run({"mode": "doublethink"})

    def test_collect_skips_other_sessions_and_stops_at_run_done(self):
        with StubApp() as app:
            c = AppClient(app.port, app.token)
            sid = c.start_run({"mode": "doublethink", "source": "real", "question": "q"})
            events = c.collect_run(sid, 10)
            self.assertEqual(events[0]["type"], "run_started")
            self.assertEqual(events[-1]["type"], "run_done")
            self.assertTrue(all(e["session_id"] == sid for e in events))
            with self.assertRaises(AppError):
                c.collect_run("s_other", 10)

    def test_replay_with_recorded_timing_respects_deadline(self):
        with StubApp(speed=1.0) as app:  # the fixture run lasts ~14 s at speed 1
            c = AppClient(app.port, app.token)
            sid = c.start_run({"mode": "doublethink", "source": "real", "question": "q"})
            with self.assertRaises(AppError):
                c.collect_run(sid, deadline_s=0.5, idle_s=0.5)


if __name__ == "__main__":
    unittest.main()
