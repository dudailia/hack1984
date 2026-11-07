"""STUB of app/run.py's control API (FORMATS §11) for testing eval/ before app/run.py is merged.

Not the real app. It runs nothing: each POST /api/run picks the next template run from
shared/fixtures/demo_events.jsonl, gives it a fresh session id, puts the posted question into run_started
(the behaviour eval needs from the real app), and GET /events replays that run as SSE frames.

    python3 -m eval.stub_app            # port 0 = any free port; prints the URL to pass as --app-url
"""
import argparse
import copy
import itertools
import json
import os
import secrets
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs

from eval.loopback import REPO

FIXTURE = os.path.join(REPO, "shared", "fixtures", "demo_events.jsonl")
ANSWERED = "s_dtreal1"   # doublethink, real, answered with cited numbers
BLOCKED = "s_careless1"  # doublethink, real, planted careless query blocked, no answer


def load_runs(path=FIXTURE):
    runs = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                e = json.loads(line)
                if e.get("session_id"):
                    runs.setdefault(e["session_id"], []).append(e)
    return runs


class StubApp:
    """scenarios: template session ids, cycled per run. Special values: 'ignore_question' (answered run that keeps the
    fixture question), 'no_run_done' (stream closes before run_done), 'error' (POST /api/run returns 409)."""

    def __init__(self, scenarios=(ANSWERED,), fixture=FIXTURE, token=None, port=0, speed=0.0):
        self.runs = load_runs(fixture)
        self.scenarios = itertools.cycle(scenarios)
        self.token = token or secrets.token_hex(8)
        self.speed = speed
        self.posts = []
        self.current = None  # (session_id, events, truncate)
        self.lock = threading.Lock()
        self._n = 0
        self.server = ThreadingHTTPServer(("127.0.0.1", port), self._handler())
        self.port = self.server.server_address[1]
        self.thread = None

    @property
    def url(self):
        return "http://127.0.0.1:%d/ui/index.html?token=%s" % (self.port, self.token)

    def start(self):
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self

    def stop(self):
        self.server.shutdown()
        self.server.server_close()

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()

    def new_run(self, body):
        with self.lock:
            scenario = next(self.scenarios)
            if scenario == "error":
                return None
            self._n += 1
            sid = "s_stub%02d" % self._n
            template = ANSWERED if scenario in ("ignore_question", "no_run_done") else scenario
            events = copy.deepcopy(self.runs[template])
            base = events[0]["t_ms"]
            for i, e in enumerate(events, 1):
                e["session_id"], e["seq"], e["t_ms"] = sid, i, e["t_ms"] - base
                if e["type"] == "run_started":
                    e["data"]["mode"] = body.get("mode")
                    e["data"]["source"] = body.get("source")
                    if scenario != "ignore_question":
                        e["data"]["question"] = body.get("question")
            events = [e for e in events if e["type"] != "proof_result"]
            if scenario == "no_run_done":
                events = [e for e in events if e["type"] != "run_done"]
            self.current = (sid, events)
            return sid

    def _handler(self):
        app = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _authed(self):
                q = parse_qs(urlsplit(self.path).query)
                return self.headers.get("X-DT-Token") == app.token or (q.get("token") or [None])[0] == app.token

            def _json(self, status, obj):
                data = json.dumps(obj).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self):
                if urlsplit(self.path).path != "/api/run":
                    return self._json(404, {"status": "error", "error": "not_found", "detail": self.path})
                if not self._authed():
                    return self._json(403, {"status": "error", "error": "bad_token", "detail": "token required"})
                n = int(self.headers.get("Content-Length") or 0)
                try:
                    body = json.loads(self.rfile.read(n) or b"{}")
                except ValueError:
                    return self._json(400, {"status": "error", "error": "bad_json", "detail": ""})
                app.posts.append(body)
                sid = app.new_run(body)
                if sid is None:
                    return self._json(409, {"status": "error", "error": "run_in_progress", "detail": "stub"})
                self._json(200, {"session_id": sid})

            def do_GET(self):
                if urlsplit(self.path).path != "/events":
                    return self._json(404, {"status": "error", "error": "not_found", "detail": self.path})
                if not self._authed():
                    return self._json(403, {"status": "error", "error": "bad_token", "detail": "token required"})
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                cur = app.current
                if not cur:
                    return
                _, events = cur
                last = 0
                try:
                    self.wfile.write(b": ping\n\n")
                    for e in events:
                        if app.speed:
                            time.sleep(max(0, e["t_ms"] - last) / 1000.0 * app.speed)
                            last = e["t_ms"]
                        frame = "id: %d\ndata: %s\n\n" % (e["seq"], json.dumps(e, ensure_ascii=False))
                        self.wfile.write(frame.encode("utf-8"))
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    pass

        return H


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python3 -m eval.stub_app", description="STUB app/run.py for eval/ tests")
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--speed", type=float, default=0.0, help="replay timing factor (0 = instant, 1 = recorded)")
    ap.add_argument("--scenarios", default=ANSWERED, help="comma-separated template session ids, cycled")
    args = ap.parse_args(argv)
    app = StubApp(scenarios=args.scenarios.split(","), port=args.port, speed=args.speed).start()
    print("STUB app (not app/run.py): %s" % app.url, flush=True)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        app.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
