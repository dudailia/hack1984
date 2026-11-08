"""Test helpers for app/: a temp repo root, a stub Gate serving bundles, test bundles, an SSE reader and a base
TestCase that runs app.run on 127.0.0.1 port 0. No gate/, proof/ or checks/ code is imported."""
import hashlib
import http.client
import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from app import _loop_stub, events, run
from app.tests import fake_verify

HERE = os.path.dirname(os.path.abspath(__file__))
FAKE_CHILD = os.path.join(HERE, "fake_child.py")
SECRET = "TAVILY_API_KEY=tvly-must-never-be-served"


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def make_bundle(session_id, n_rows=4):
    """A small bundle whose row hashes the fake verifier checks (sha256 of the row without `hash`)."""
    rows, prev = [], "0" * 64
    for seq in range(1, n_rows + 1):
        if seq % 2:
            row = {"seq": seq, "session_id": session_id, "row_type": "attempt",
                   "commitment": hashlib.sha256(b"c%d" % seq).hexdigest(), "decision": "allowed", "prev_hash": prev}
        else:
            row = {"seq": seq, "session_id": session_id, "row_type": "result", "attempt_seq": seq - 1,
                   "response_commitment": hashlib.sha256(b"r%d" % seq).hexdigest(), "prev_hash": prev}
        row["hash"] = hashlib.sha256(canonical(row)).hexdigest()
        prev = row["hash"]
        rows.append(row)
    return canonical({"v": 1, "format": "doublethink-bundle", "session_id": session_id,
                      "exported": "2026-11-07T23:41:44.000Z", "rows": rows, "head": prev})


def make_root(tmp):
    """A repo-like root with static files, a secret file outside the static folders, and a symlink out."""
    os.makedirs(os.path.join(tmp, "ui", "css"))
    os.makedirs(os.path.join(tmp, "shared", "fixtures"))
    os.makedirs(os.path.join(tmp, "shared", "results"))
    files = {"ui/index.html": "<!doctype html><title>Doublethink</title>", "ui/css/app.css": "body{}",
             "shared/fixtures/demo.json": '{"demo":true}', "shared/results/results.json": '{"v":1}',
             ".env": SECRET, "shared/FORMATS.md": "# formats"}
    for rel, text in files.items():
        with open(os.path.join(tmp, rel), "w", encoding="utf-8") as f:
            f.write(text)
    os.symlink(os.path.join(tmp, ".env"), os.path.join(tmp, "ui", "link.txt"))
    return tmp


class StubGate:
    """GET /v1/health and GET /v1/bundle?session_id= on 127.0.0.1:0. Records bundle requests."""

    def __init__(self):
        self.bundles = {}
        self.requests = []
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                u = urlsplit(self.path)
                outer.requests.append(self.path)
                if u.path == "/v1/health":
                    return self._send(200, b'{"status":"ok"}')
                sid = parse_qs(u.query).get("session_id", [None])[0]
                if u.path == "/v1/bundle" and sid in outer.bundles:
                    return self._send(200, outer.bundles[sid])
                self._send(404, b'{"status":"error","error":"unknown_session","detail":"no bundle"}')

            def _send(self, status, data):
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.server.daemon_threads = True
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()

    def stop(self):
        self.server.shutdown()
        self.server.server_close()


class FakeLoop:
    """Records calls; behaves like start_run with the given return value or exception."""

    def __init__(self, result="s_fakeloop01", exc=None):
        self.result, self.exc, self.calls = result, exc, []

    def __call__(self, mode, source, plant_careless, question, emit):
        self.calls.append((mode, source, plant_careless, question))
        if self.exc:
            raise self.exc
        return self.result


class AppCase(unittest.TestCase):
    start_run = None  # default: a FakeLoop
    signer = True

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = make_root(self._tmp.name)
        self.bundles_dir = os.path.join(self.root, "bundles")
        self.gate = StubGate()
        self.addCleanup(self.gate.stop)
        self.loop = self.start_run or FakeLoop()
        self.app = run.App(root=self.root, gate_port=self.gate.port, token="tok-123", bundles_dir=self.bundles_dir,
                           verifier=fake_verify.verifier(self.signer), start_run=self.loop, ping_interval=0.2,
                           tamper_helper=None)
        self.srv = run.make_server(self.app, port=0)
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()
        self.addCleanup(self._stop)

    def _stop(self):
        self.app.hub.close()
        self.srv.shutdown()
        self.srv.server_close()

    # ---- HTTP
    def request(self, method, path, body=None, headers=None, token=True):
        if token is True:
            sep = "&" if "?" in path else "?"
            path = path + sep + "token=tok-123"
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        data = None
        if body is not None:
            data = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
        try:
            conn.request(method, path, body=data, headers=dict(headers or {}))
            resp = conn.getresponse()
            if (resp.getheader("Content-Type") or "").startswith("text/event-stream"):
                return resp.status, dict(resp.getheaders()), b""  # a stream never ends; do not read it
            return resp.status, dict(resp.getheaders()), resp.read()
        finally:
            conn.close()

    def api(self, path, body, token=True):
        status, _h, raw = self.request("POST", path, body, {"Content-Type": "application/json"}, token=token)
        try:
            return status, json.loads(raw)
        except ValueError:
            return status, raw

    # ---- SSE
    def sse(self, until=lambda frames: False, last_event_id=None, timeout=10, path="/events?token=tok-123",
            keep_pings=False):
        """Read SSE frames until `until(frames)` is true. Returns a list of ("event", envelope) or ("ping", None)."""
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=timeout)
        headers = {} if last_event_id is None else {"Last-Event-ID": str(last_event_id)}
        conn.request("GET", path, headers=headers)
        resp = conn.getresponse()
        self.assertEqual(resp.status, 200)
        self.assertTrue(resp.getheader("Content-Type").startswith("text/event-stream"))
        frames, block = [], []
        try:
            while not until(frames):
                line = resp.fp.readline()
                if not line:
                    break
                line = line.decode("utf-8").rstrip("\n")
                if line:
                    block.append(line)
                    continue
                if block == [": ping"]:
                    if keep_pings:
                        frames.append(("ping", None))
                else:
                    self.assertEqual(len(block), 2, block)
                    self.assertTrue(block[0].startswith("id: "), block)
                    self.assertTrue(block[1].startswith("data: "), block)
                    env = json.loads(block[1][len("data: "):])
                    self.assertEqual(block[0], "id: %d" % env["seq"])
                    frames.append(("event", env))
                block = []
        finally:
            conn.close()
        return frames

    @staticmethod
    def types(frames):
        return [env["type"] for kind, env in frames if kind == "event"]

    def finished_session(self, sid, bundle=True):
        """A session the hub has seen through run_done, with its bundle on the stub Gate."""
        self.app.hub.emit("run_started", sid, {"mode": "doublethink", "source": "fake", "plant_careless": False,
                                              "question": "q"})
        self.app.hub.emit("run_done", sid, {"outcome": "answered", "source": "fake", "credits_total": 0,
                                           "seconds": 1.0, "leaks": 0, "blocked": 0, "head": "0" * 64})
        if bundle:
            self.gate.bundles[sid] = make_bundle(sid)
        return sid


__all__ = ["AppCase", "FakeLoop", "StubGate", "make_bundle", "make_root", "canonical", "SECRET",
           "FAKE_CHILD", "events", "_loop_stub", "shutil"]
