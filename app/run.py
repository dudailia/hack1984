"""Doublethink app server: the page, the live event stream and the control API (shared/FORMATS.md §10, §11).

    python3 -m app.run [--no-children] [--port N]

Starts the Gate (python3 -m gate.server) and the local Tavily stand-in (python3 -m fake_tavily.server) as child
processes, waits for their health checks, then serves on 127.0.0.1:APP_PORT (default 8700) and prints the UI URL
with this launch's token. Ctrl-C stops everything. Standard library only. Binds 127.0.0.1 only; talks to the
Gate over loopback; never reads API keys (ports come from baseline.config, which refuses key names).

Routes (§11). The token is required on /api/* and /events, as ?token= or the X-DT-Token header:
- GET /ui/..., /shared/fixtures/..., /shared/results/...   static, read only, no path traversal
- GET /events                                              SSE; replays the current run; honours Last-Event-ID
- POST /api/run {mode, source, plant_careless, question}   -> {session_id}
- POST /api/verify {session_id}                            Gate bundle -> bundles/<id>.json -> proof/verify.py
- POST /api/tamper {session_id, seq}                       one byte changed in a COPY, then verified
- POST /api/inject {text}, POST /api/inject/reset          "Try to break it": plant text on the stand-in's
                                                           poisoned page (fake_tavily.inject); refused (409)
                                                           while a run is active; text 1 to 2,000 characters
- GET /api/bundle?session_id=                              bundle download
Verify, tamper and bundle answer 404 for a session this app did not run or that has not finished (no run_done).

The run loop is app.loop.start_run (Aayush), imported lazily; while it does not exist, app._loop_stub replays
shared/fixtures/demo_events.jsonl instead (marked STUB LOOP at startup).
"""
import argparse
import atexit
import hmac
import http.client
import importlib
import importlib.util
import json
import mimetypes
import os
import re
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlsplit

from app.events import PING, EventHub, frame
from baseline import config
from fake_tavily import inject as fake_inject

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOOPBACK = "127.0.0.1"
MODES = ("single_agent", "compromised", "two_minds", "doublethink")
FAKE_ONLY = ("single_agent", "compromised", "two_minds")  # §1: these require source fake
SESSION_RE = re.compile(r"^s_[a-z0-9]{1,32}$")
STATIC = {"/ui/": ("ui",), "/shared/fixtures/": ("shared", "fixtures"), "/shared/results/": ("shared", "results")}
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
         ".css": "text/css; charset=utf-8", ".json": "application/json", ".jsonl": "application/x-ndjson",
         ".md": "text/plain; charset=utf-8", ".txt": "text/plain; charset=utf-8", ".svg": "image/svg+xml",
         ".png": "image/png", ".ico": "image/x-icon", ".woff2": "font/woff2"}
PROOF_KEYS = ("bundle_head", "tampered", "tampered_seq", "valid", "broken_at_seq", "rows_checked", "reason",
              "signer_key_sha256")
MAX_BODY = 64 * 1024
MAX_QUESTION = 500
MAX_INJECT = 2000
_LOOKUP = object()


def _default_question():
    with open(os.path.join(REPO, "shared", "fixtures", "halyard_session.json"), encoding="utf-8") as f:
        return json.load(f)["question"]


class ApiError(Exception):
    def __init__(self, status, code, detail):
        super().__init__(detail)
        self.status, self.code, self.detail = status, code, detail


# ---------------------------------------------------------------- lazy lookups (other owners' modules)

def load_start_run():
    """(start_run, is_stub): app.loop.start_run (Aayush) if it exists, else the replay stub."""
    if importlib.util.find_spec("app.loop") is not None:
        return importlib.import_module("app.loop").start_run, False
    from app import _loop_stub
    return _loop_stub.start_run, True


def load_tamper_helper():
    """proof.tamper.tamper_and_verify (Anant) if it exists, else None (then the built-in byte flip is used)."""
    try:
        if importlib.util.find_spec("proof.tamper") is None:
            return None
        return getattr(importlib.import_module("proof.tamper"), "tamper_and_verify", None)
    except ImportError:
        return None


def load_guard():
    """shared.guard.install_loopback_guard if it exists, else None."""
    try:
        if importlib.util.find_spec("shared.guard") is None:
            return None
        return getattr(importlib.import_module("shared.guard"), "install_loopback_guard", None)
    except ImportError:
        return None


# ---------------------------------------------------------------- loopback helpers

def http_status(port, path, timeout=2):
    conn = http.client.HTTPConnection(LOOPBACK, port, timeout=timeout)
    try:
        conn.request("GET", path)
        resp = conn.getresponse()
        resp.read()
        return resp.status
    finally:
        conn.close()


def _write_atomic(path, data):
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".tmp-")
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


def flip_row_byte(data, seq):
    """Copy of bundle bytes with ONE byte changed in row `seq`: the first hex char of its commitment (attempt)
    or response_commitment (result), else of its hash. Raises KeyError if there is no such row."""
    bundle = json.loads(data)
    rows = [r for r in bundle.get("rows", []) if isinstance(r, dict) and r.get("seq") == seq]
    if not rows:
        raise KeyError(seq)
    row = rows[0]
    for key in ("commitment", "response_commitment", "hash"):
        value = row.get(key)
        if isinstance(value, str) and value:
            needle = ('"%s":"%s' % (key, value)).encode("utf-8")
            if data.count(needle) == 1:
                i = data.index(needle) + len(key) + 4
                new = b"1" if data[i:i + 1] == b"0" else b"0"
                return data[:i] + new + data[i + 1:]
    raise KeyError(seq)


# ---------------------------------------------------------------- the app

class App:
    def __init__(self, root=REPO, gate_port=None, token=None, bundles_dir=None, verify_cmd=None, start_run=None,
                 tamper_helper=_LOOKUP, ping_interval=15.0, hub=None, inject_state_path=None):
        self.root = os.path.realpath(root)
        self.gate_port = gate_port if gate_port is not None else config.gate_port()
        self.token = token or secrets.token_urlsafe(32)
        self.bundles_dir = bundles_dir or os.path.join(self.root, "bundles")
        self.verify_cmd = verify_cmd
        self.start_run = start_run
        self.tamper_helper = tamper_helper
        self.ping_interval = ping_interval
        self.hub = hub or EventHub()
        # None = fake_tavily.inject's default (FAKE_TAVILY_STATE or fake_tavily/state/planted.txt), the file the
        # stand-in started by the launcher reads on every request.
        self.inject_state_path = inject_state_path
        self._run_lock = threading.Lock()  # serialises /api/run with /api/inject*
        self._last_sid = None              # the session /api/run last started, until the hub sees its run_done

    def ui_url(self, port):
        return "http://%s:%d/ui/index.html?token=%s" % (LOOPBACK, port, self.token)

    def token_ok(self, given):
        return isinstance(given, str) and bool(given) and hmac.compare_digest(given.encode(), self.token.encode())

    # ---- static
    def static_path(self, raw_path):
        """Absolute file path for a static URL path, or None. Every decoded segment must be a plain name, and the
        resolved file (symlinks followed) must stay inside its folder."""
        for prefix, parts in STATIC.items():
            if raw_path.startswith(prefix):
                break
        else:
            return None
        names = []
        for seg in raw_path[len(prefix):].split("/"):
            try:
                name = unquote(seg, errors="strict") if "%" in seg else seg
            except UnicodeDecodeError:
                return None
            if name in ("", ".", "..") or any(c in name for c in "/\\\x00") or ":" in name:
                return None
            names.append(name)
        base = os.path.realpath(os.path.join(self.root, *parts))
        full = os.path.realpath(os.path.join(base, *names))
        if not full.startswith(base + os.sep) or not os.path.isfile(full):
            return None
        return full

    # ---- /api/run
    def api_run(self, body):
        _only_keys(body, {"mode", "source", "plant_careless", "question"})
        mode, source = body.get("mode"), body.get("source")
        careless = body.get("plant_careless", False)
        question = body.get("question", None)
        if mode not in MODES:
            raise ApiError(400, "bad_mode", "mode must be one of %s" % ", ".join(MODES))
        if source not in ("real", "fake"):
            raise ApiError(400, "bad_source", "source must be real or fake")
        if mode in FAKE_ONLY and source != "fake":
            raise ApiError(400, "source_not_allowed", "mode %s runs only on source fake" % mode)
        if not isinstance(careless, bool):
            raise ApiError(400, "bad_request", "plant_careless must be true or false")
        if question is None:
            question = _default_question()
        if not isinstance(question, str) or not question.strip() or len(question) > MAX_QUESTION:
            raise ApiError(400, "bad_request", "question must be 1 to %d characters" % MAX_QUESTION)
        start_run = self.start_run or load_start_run()[0]
        with self._run_lock:
            try:
                sid = start_run(mode, source, careless, question, self.hub.emit)
            except ValueError as e:
                if "already active" in str(e).lower():
                    raise ApiError(409, "run_in_progress", str(e))
                raise ApiError(400, "bad_request", str(e))
            if not isinstance(sid, str) or not SESSION_RE.match(sid):
                raise ApiError(500, "bad_session_id", "the run loop returned an invalid session id")
            self._last_sid = sid
        return {"session_id": sid}

    # ---- "Try to break it": the planted text on the stand-in's poisoned page
    def run_active(self):
        """True while a run has started and not reached run_done (app.loop always emits run_done)."""
        last = self._last_sid
        return self.hub.running() is not None or (last is not None and not self.hub.finished(last))

    def _refuse_if_running(self):
        if self.run_active():
            raise ApiError(409, "run_in_progress", "wait for the current run to finish")

    def api_inject(self, body):
        _only_keys(body, {"text"})
        text = body.get("text")
        if not isinstance(text, str) or not text or len(text) > MAX_INJECT or "\x00" in text:
            raise ApiError(400, "bad_request", "text must be 1 to %d characters" % MAX_INJECT)
        with self._run_lock:
            self._refuse_if_running()
            fake_inject.set_planted(text, self.inject_state_path)
        return {"status": "ok", "chars": len(text)}

    def api_inject_reset(self, body):
        if body is not None:
            _only_keys(body, set())
        with self._run_lock:
            self._refuse_if_running()
            fake_inject.reset(self.inject_state_path)
        return {"status": "ok"}

    # ---- sessions and bundles
    def finished_session(self, sid):
        if not isinstance(sid, str) or not SESSION_RE.match(sid) or not self.hub.finished(sid):
            raise ApiError(404, "unknown_session", "no finished run with this session id")
        return sid

    def bundle_path(self, sid):
        return os.path.join(self.bundles_dir, sid + ".json")

    def fetch_bundle(self, sid):
        """GET the bundle from the Gate and save it as bundles/<sid>.json; return the bytes."""
        conn = http.client.HTTPConnection(LOOPBACK, self.gate_port, timeout=30)
        try:
            conn.request("GET", "/v1/bundle?session_id=" + sid)
            resp = conn.getresponse()
            data = resp.read()
        except OSError as e:
            raise ApiError(502, "gate_bundle_unavailable", "Gate unreachable: %s" % e.__class__.__name__)
        finally:
            conn.close()
        if resp.status != 200:
            raise ApiError(502, "gate_bundle_unavailable", "Gate answered HTTP %d" % resp.status)
        try:
            bundle = json.loads(data)
        except ValueError:
            raise ApiError(502, "gate_bundle_unavailable", "Gate bundle is not JSON")
        if not isinstance(bundle, dict) or bundle.get("session_id") != sid:
            raise ApiError(502, "gate_bundle_unavailable", "Gate bundle is for another session")
        os.makedirs(self.bundles_dir, exist_ok=True)
        _write_atomic(self.bundle_path(sid), data)
        return data

    def saved_bundle(self, sid):
        """The saved original if present, else fetched. Never rewrites an existing original."""
        path = self.bundle_path(sid)
        if os.path.isfile(path):
            with open(path, "rb") as f:
                return f.read()
        return self.fetch_bundle(sid)

    def _verify_cmd(self):
        if self.verify_cmd:
            return list(self.verify_cmd)
        script = os.path.join(self.root, "proof", "verify.py")
        if not os.path.isfile(script):
            raise ApiError(503, "proof_unavailable", "proof/verify.py is not present")
        return [sys.executable, script]

    def run_verifier(self, path):
        """Run the verifier on `path`; return its parsed --json result. valid only if exit 0 and valid is true."""
        cmd = self._verify_cmd() + [path, "--json"]
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=30, cwd=self.root)
        except (OSError, subprocess.SubprocessError) as e:
            raise ApiError(502, "verifier_error", "verifier did not run: %s" % e.__class__.__name__)
        try:
            out = json.loads(r.stdout.decode("utf-8").strip().splitlines()[-1])
        except (ValueError, IndexError, UnicodeDecodeError):
            out = None
        if not isinstance(out, dict) or "valid" not in out:
            raise ApiError(502, "verifier_error", "verifier output is not the --json result")
        out["valid"] = out.get("valid") is True and r.returncode == 0
        return out

    def _proof_data(self, result, bundle, tampered, seq):
        data = {k: result.get(k) for k in PROOF_KEYS}
        if data["bundle_head"] is None:
            data["bundle_head"] = bundle.get("head")
        data["tampered"], data["tampered_seq"] = tampered, seq
        return data

    def api_verify(self, body):
        _only_keys(body, {"session_id"})
        sid = self.finished_session(body.get("session_id"))
        self._verify_cmd()  # 503 before fetching if there is no verifier
        data = self.fetch_bundle(sid)
        result = self.run_verifier(self.bundle_path(sid))
        proof = self._proof_data(result, json.loads(data), False, None)
        self.hub.emit("proof_result", sid, proof)
        return proof

    def api_tamper(self, body):
        _only_keys(body, {"session_id", "seq"})
        sid = self.finished_session(body.get("session_id"))
        seq = body.get("seq")
        if type(seq) is not int or seq < 1:
            raise ApiError(400, "bad_request", "seq must be a positive integer")
        helper = load_tamper_helper() if self.tamper_helper is _LOOKUP else self.tamper_helper
        if helper is None:
            self._verify_cmd()
        original = self.saved_bundle(sid)
        bundle = json.loads(original)
        if not any(isinstance(r, dict) and r.get("seq") == seq for r in bundle.get("rows", [])):
            raise ApiError(404, "unknown_seq", "no row %d in this bundle" % seq)
        copy_path = os.path.join(self.bundles_dir, "%s.tampered-%d.json" % (sid, seq))
        _write_atomic(copy_path, original)  # the original file is never opened for writing
        if helper is not None:
            try:
                result = helper(copy_path, seq)
            except Exception as e:  # noqa: BLE001  (another owner's code; report, never crash the server)
                raise ApiError(502, "verifier_error", "tamper helper failed: %s" % e.__class__.__name__)
            if not isinstance(result, dict):
                raise ApiError(502, "verifier_error", "tamper helper returned no result")
        else:
            _write_atomic(copy_path, flip_row_byte(original, seq))
            result = self.run_verifier(copy_path)
        if result.get("valid") is not False:
            raise ApiError(502, "verifier_error", "a tampered copy must not verify")
        proof = self._proof_data(result, bundle, True, seq)
        self.hub.emit("proof_result", sid, proof)
        return proof

    def api_bundle(self, sid):
        sid = self.finished_session(sid)
        return sid, self.saved_bundle(sid)


def _only_keys(body, allowed):
    if not isinstance(body, dict):
        raise ApiError(400, "bad_json", "body must be a JSON object")
    extra = set(body) - allowed
    if extra:
        raise ApiError(400, "bad_request", "unknown keys: %s" % ", ".join(sorted(extra)))


# ---------------------------------------------------------------- HTTP

def _handler(app):
    class Handler(BaseHTTPRequestHandler):
        server_version = "doublethink-app/1"
        sys_version = ""

        def log_message(self, fmt, *args):
            pass  # request lines carry the token in the query; never log them

        def _send(self, status, data, ctype="application/json", extra=None, head=False):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            if not head:
                self.wfile.write(data)

        def _json(self, status, obj):
            self._send(status, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

        def _error(self, status, code, detail):
            self._json(status, {"status": "error", "error": code, "detail": detail})

        def _authorized(self, query):
            given = self.headers.get("X-DT-Token")
            if given is None:
                given = (query.get("token") or [None])[0]
            if app.token_ok(given):
                return True
            self._error(401, "unauthorized", "token required")
            return False

        def _body(self):
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                raise ApiError(400, "bad_json", "bad Content-Length")
            if n > MAX_BODY:
                raise ApiError(413, "too_large", "body too large")
            try:
                return json.loads(self.rfile.read(n) or b"null")
            except (ValueError, UnicodeDecodeError):
                raise ApiError(400, "bad_json", "body is not JSON")

        def _static(self, path, head):
            full = app.static_path(path)
            if full is None:
                return self._error(404, "not_found", "no such file")
            with open(full, "rb") as f:
                data = f.read()
            ext = os.path.splitext(full)[1].lower()
            ctype = TYPES.get(ext) or mimetypes.guess_type(full)[0] or "application/octet-stream"
            self._send(200, data, ctype, head=head)

        def do_HEAD(self):
            u = urlsplit(self.path)
            if any(u.path.startswith(p) for p in STATIC):
                return self._static(u.path, head=True)
            self._error(404, "not_found", "no such route")

        def do_GET(self):
            u = urlsplit(self.path)
            query = parse_qs(u.query)
            if any(u.path.startswith(p) for p in STATIC):
                return self._static(u.path, head=False)
            if u.path == "/events":
                if self._authorized(query):
                    self._events()
                return
            if u.path == "/api/bundle":
                if not self._authorized(query):
                    return
                try:
                    sid, data = app.api_bundle((query.get("session_id") or [None])[0])
                except ApiError as e:
                    return self._error(e.status, e.code, e.detail)
                return self._send(200, data, "application/json",
                                  {"Content-Disposition": 'attachment; filename="%s.json"' % sid})
            self._error(404, "not_found", "no such route")

        def do_POST(self):
            u = urlsplit(self.path)
            routes = {"/api/run": app.api_run, "/api/verify": app.api_verify, "/api/tamper": app.api_tamper,
                      "/api/inject": app.api_inject, "/api/inject/reset": app.api_inject_reset}
            route = routes.get(u.path)
            if route is None:
                status = 405 if any(u.path.startswith(p) for p in STATIC) else 404
                return self._error(status, "not_found", "no such route")
            if not self._authorized(parse_qs(u.query)):
                return
            try:
                self._json(200, route(self._body()))
            except ApiError as e:
                self._error(e.status, e.code, e.detail)

        def _events(self):
            last = self.headers.get("Last-Event-ID")
            last = int(last) if last and last.strip().isdigit() else None
            sub = app.hub.subscribe(last)
            try:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Accel-Buffering", "no")
                self.end_headers()
                for env in sub.backlog:
                    self.wfile.write(frame(env))
                self.wfile.flush()
                while True:
                    try:
                        env = sub.queue.get(timeout=app.ping_interval)
                    except Exception:  # queue.Empty: idle
                        self.wfile.write(PING)
                        self.wfile.flush()
                        continue
                    if env is None:
                        return
                    self.wfile.write(frame(env))
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                return
            finally:
                app.hub.unsubscribe(sub)

    return Handler


class AppServer(ThreadingHTTPServer):
    daemon_threads = True


def make_server(app, port=None, host=LOOPBACK):
    if host != LOOPBACK:
        raise ValueError("the app binds %s only" % LOOPBACK)
    if port is None:
        port = int(config.env_value("APP_PORT", "8700"))
    return AppServer((LOOPBACK, port), _handler(app))


# ---------------------------------------------------------------- launcher

def default_children(gate_port, fake_port):
    return [("gate", [sys.executable, "-m", "gate.server"], gate_port, "/v1/health"),
            ("fake_tavily", [sys.executable, "-m", "fake_tavily.server"], fake_port, "/health")]


class Children:
    """Child processes started together, each waited on until its health URL answers 200."""

    def __init__(self, specs, cwd=REPO):
        self.specs, self.cwd, self.procs = specs, cwd, []

    def start(self, timeout=15.0):
        try:
            for name, argv, _port, _path in self.specs:
                # children log to stderr so stdout carries only the UI URL
                self.procs.append((name, subprocess.Popen(argv, cwd=self.cwd, stdout=sys.stderr)))
            deadline = time.monotonic() + timeout
            for (name, proc), (_n, _a, port, path) in zip(self.procs, self.specs):
                while True:
                    if proc.poll() is not None:
                        raise RuntimeError("%s exited with code %s" % (name, proc.returncode))
                    try:
                        if http_status(port, path, timeout=1) == 200:
                            break
                    except OSError:
                        pass
                    if time.monotonic() > deadline:
                        raise RuntimeError("%s not healthy on 127.0.0.1:%d%s" % (name, port, path))
                    time.sleep(0.1)
        except BaseException:
            self.stop()
            raise

    def stop(self):
        for _name, proc in self.procs:
            if proc.poll() is None:
                proc.terminate()
        for _name, proc in self.procs:
            try:
                proc.wait(5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(5)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python3 -m app.run", description="Doublethink app server (loopback)")
    ap.add_argument("--port", type=int, default=None, help="default: APP_PORT from env/.env, else 8700")
    ap.add_argument("--no-children", action="store_true", help="do not start the Gate and fake Tavily")
    args = ap.parse_args(argv)
    port = args.port if args.port is not None else int(config.env_value("APP_PORT", "8700"))
    gate_port = config.gate_port()
    fake_port = int(config.env_value("FAKE_TAVILY_PORT", "8702"))

    kids = Children([] if args.no_children else default_children(gate_port, fake_port))
    atexit.register(kids.stop)
    try:
        kids.start()
    except RuntimeError as e:
        print("app: %s" % e, file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130

    guard = load_guard()
    if guard is not None:
        guard()
    else:
        # TODO(guard): shared.guard.install_loopback_guard() (invariant 1) once it lands in shared/. Note that
        # /api/verify starts proof/verify.py as a subprocess, so the guard must allow that.
        print("app: shared.guard not found; loopback guard NOT installed (TODO)", file=sys.stderr)

    start_run, is_stub = load_start_run()
    app = App(gate_port=gate_port, start_run=start_run)
    srv = make_server(app, port)
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    if is_stub:
        print("app: STUB LOOP (app/loop.py not found): runs replay shared/fixtures/demo_events.jsonl", file=sys.stderr)
    print(app.ui_url(srv.server_address[1]), flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        app.hub.close()
        srv.server_close()
        kids.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
