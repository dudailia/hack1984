"""Gate HTTP server on 127.0.0.1:GATE_PORT (shared/FORMATS.md §3). Standard library only.

Endpoints for now: GET /v1/health, POST /v1/session, POST /v1/search. Extract and read come later.
Run: python3 -m gate.server [--db PATH]
"""
import argparse
import json
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from gate import checks_bridge, env, tavily
from gate.ledger import DEFAULT_DB, Ledger
from gate.pipeline import Pipeline
from gate.session import SessionError, SessionStore

MAX_BODY = 1024 * 1024
MAX_QUERY = 400
NEED_RE = re.compile(r"^[a-z0-9_]{1,32}$")
SEARCH_KEYS = {"session_id", "component", "need", "query", "options"}
COMPONENT_MODES = {"planner": {"two_minds", "doublethink"}, "baseline": {"single_agent", "compromised"}}


class ApiError(Exception):
    def __init__(self, http, code, detail):
        super().__init__(detail)
        self.http, self.code, self.detail = http, code, detail


class Gate:
    def __init__(self, ledger, transport, run_all, memo_tokens_fn, fake_port, tavily_key):
        self.ledger = ledger
        self.sessions = SessionStore(ledger, memo_tokens_fn)
        self.pipeline = Pipeline(ledger, self.sessions, transport, run_all, fake_port)
        self._tavily_key = tavily_key

    def __repr__(self):
        return "Gate()"

    def create_session(self, body):
        s = self.sessions.create(body)
        return {"status": "ok", "session_id": s["session_id"], "created_at": s["created_at"],
                "enforce": self.sessions.enforce(s["session_id"])}

    def search(self, body):
        if set(body) != SEARCH_KEYS:
            raise ApiError(400, "bad_request", "search body must have exactly " + ", ".join(sorted(SEARCH_KEYS)))
        sid = body["session_id"]
        if not isinstance(sid, str):
            raise ApiError(400, "bad_session_id", "session_id must be a string")
        session = self.sessions.get(sid)
        component = body["component"]
        if component not in COMPONENT_MODES:
            raise ApiError(400, "bad_component", "component must be planner or baseline")
        if session["mode"] not in COMPONENT_MODES[component]:
            raise ApiError(400, "component_mode_mismatch", f"component {component} not allowed in this mode")
        if not isinstance(body["need"], str) or not NEED_RE.fullmatch(body["need"]):
            raise ApiError(400, "bad_need", "need must match [a-z0-9_]{1,32}")
        q = body["query"]
        if not isinstance(q, str) or not q.strip() or len(q) > MAX_QUERY:
            raise ApiError(400, "bad_query", f"query must be a non-empty string of at most {MAX_QUERY} chars")
        opts = body["options"]
        if not isinstance(opts, dict) or set(opts) != {"preset"} or opts["preset"] not in tavily.SEARCH_PRESETS:
            raise ApiError(400, "bad_options", "options must be {preset: general|finance|news}")
        try:
            return tavily.search(self.pipeline, sid, component, body["need"], q, opts["preset"],
                                 api_key=self._tavily_key)
        except tavily.TavilyError as e:
            raise ApiError(500, "gate_config", str(e)) from None


def _handler(gate):
    class Handler(BaseHTTPRequestHandler):
        server_version = "doublethink-gate"
        sys_version = ""

        def log_message(self, fmt, *args):  # method, path and status only; never bodies or headers
            pass

        def log_request(self, code="-", size="-"):
            sys.stderr.write(f"gate {self.command} {self.path.split('?')[0]} {code}\n")

        def _send(self, status, obj):
            data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _error(self, status, code, detail):
            self._send(status, {"status": "error", "error": code, "detail": detail})

        def do_GET(self):
            if self.path == "/v1/health":
                return self._send(200, {"status": "ok"})
            self._error(404, "not_found", "no such endpoint")

        def _body(self):
            if not (self.headers.get("Content-Type") or "").startswith("application/json"):
                raise ApiError(415, "bad_content_type", "Content-Type must be application/json")
            try:
                n = int(self.headers.get("Content-Length") or "0")
            except ValueError:
                raise ApiError(400, "bad_request", "bad Content-Length") from None
            if n < 0:
                self.close_connection = True
                raise ApiError(400, "bad_request", "bad Content-Length")
            if n > MAX_BODY:
                self.close_connection = True
                raise ApiError(413, "too_large", "body too large")
            try:
                body = json.loads(self.rfile.read(n))
            except ValueError:
                raise ApiError(400, "bad_json", "body is not valid JSON") from None
            if not isinstance(body, dict):
                raise ApiError(400, "bad_request", "body must be a JSON object")
            return body

        def do_POST(self):
            routes = {"/v1/session": gate.create_session, "/v1/search": gate.search}
            fn = routes.get(self.path)
            if fn is None:
                return self._error(404, "not_found", "no such endpoint")
            try:
                self._send(200, fn(self._body()))
            except ApiError as e:
                self._error(e.http, e.code, e.detail)
            except SessionError as e:
                self._error(e.http, e.code, e.detail)
            except Exception as e:  # never echo internals that might carry payloads
                sys.stderr.write(f"gate internal error: {type(e).__name__}\n")
                self._error(500, "internal", type(e).__name__)

    return Handler


def make_server(ledger, transport, run_all, memo_tokens_fn, fake_port, tavily_key, port, host="127.0.0.1"):
    if host != "127.0.0.1":
        raise ValueError("the Gate binds 127.0.0.1 only")
    gate = Gate(ledger, transport, run_all, memo_tokens_fn, fake_port, tavily_key)
    srv = ThreadingHTTPServer((host, port), _handler(gate))
    srv.daemon_threads = True
    srv.gate = gate
    return srv


def main(argv=None):
    from gate.transport import https_post

    ap = argparse.ArgumentParser(description="Doublethink Gate")
    ap.add_argument("--db", default=DEFAULT_DB)
    args = ap.parse_args(argv)
    e = env.load()
    run_all, memo_tokens, checks_name = checks_bridge.load()
    srv = make_server(Ledger(args.db), https_post, run_all, memo_tokens, fake_port=e.port("FAKE_TAVILY_PORT"),
                      tavily_key=e.get("TAVILY_API_KEY"), port=e.port("GATE_PORT"))
    sys.stderr.write(f"gate listening on 127.0.0.1:{srv.server_address[1]} checks={checks_name} db={args.db}\n")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
