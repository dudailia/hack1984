"""Gate HTTP server on 127.0.0.1:GATE_PORT (shared/FORMATS.md §3). Standard library only.

Endpoints: GET /v1/health, POST /v1/session, POST /v1/search, POST /v1/extract, POST /v1/read,
GET /v1/bundle?session_id=. Request bodies must have exactly the §3 keys: a caller can never supply a path,
header, key or destination (the Gate builds all of those itself).
Run: python3 -m gate.server [--db PATH]
"""
import argparse
import json
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from gate import bundle, checks_bridge, env, read, tavily
from gate.errors import ApiError
from gate.ledger import DEFAULT_DB, Ledger
from gate.pipeline import GateConfigError, Pipeline
from gate.session import SESSION_ID_RE, SessionError, SessionStore

MAX_BODY = 1024 * 1024
MAX_QUERY = 400
NEED_RE = re.compile(r"^[a-z0-9_]{1,32}$")
SEARCH_KEYS = {"session_id", "component", "need", "query", "options"}
EXTRACT_KEYS = {"session_id", "component", "need", "result_ids", "options"}
READ_KEYS = {"session_id", "need", "result_ids", "claim_types"}
COMPONENT_MODES = {"planner": {"two_minds", "doublethink"}, "baseline": {"single_agent", "compromised"}}


def _exact_keys(body, keys, what):
    if set(body) != keys:
        raise ApiError(400, "bad_request", f"{what} body must have exactly " + ", ".join(sorted(keys)))
    if not isinstance(body["session_id"], str):
        raise ApiError(400, "bad_session_id", "session_id must be a string")


class Gate:
    def __init__(self, ledger, transport, run_all, memo_tokens_fn, fake_port, keys):
        self.ledger = ledger
        self.sessions = SessionStore(ledger, memo_tokens_fn)
        # keys come from .env only (main); callers can never supply a key, header or path
        self.pipeline = Pipeline(ledger, self.sessions, transport, run_all, fake_port, keys=keys)

    def __repr__(self):
        return "Gate()"

    def create_session(self, body):
        s = self.sessions.create(body)
        return {"status": "ok", "session_id": s["session_id"], "created_at": s["created_at"],
                "enforce": self.sessions.enforce(s["session_id"])}

    def _component_need_preset(self, body, presets):
        session = self.sessions.get(body["session_id"])
        component = body["component"]
        if component not in COMPONENT_MODES:
            raise ApiError(400, "bad_component", "component must be planner or baseline")
        if session["mode"] not in COMPONENT_MODES[component]:
            raise ApiError(400, "component_mode_mismatch", f"component {component} not allowed in this mode")
        if not isinstance(body["need"], str) or not NEED_RE.fullmatch(body["need"]):
            raise ApiError(400, "bad_need", "need must match [a-z0-9_]{1,32}")
        opts = body["options"]
        if not isinstance(opts, dict) or set(opts) != {"preset"} or opts["preset"] not in presets:
            raise ApiError(400, "bad_options", "options must be {preset: " + "|".join(sorted(presets)) + "}")
        return component, opts["preset"]

    def search(self, body):
        _exact_keys(body, SEARCH_KEYS, "search")
        component, preset = self._component_need_preset(body, tavily.SEARCH_PRESETS)
        q = body["query"]
        if not isinstance(q, str) or not q.strip() or len(q) > MAX_QUERY:
            raise ApiError(400, "bad_query", f"query must be a non-empty string of at most {MAX_QUERY} chars")
        return tavily.search(self.pipeline, body["session_id"], component, body["need"], q, preset)

    def extract(self, body):
        _exact_keys(body, EXTRACT_KEYS, "extract")
        component, preset = self._component_need_preset(body, tavily.EXTRACT_PRESETS)
        return tavily.extract(self.pipeline, body["session_id"], component, body["need"], body["result_ids"], preset)

    def read(self, body):
        _exact_keys(body, READ_KEYS, "read")
        self.sessions.get(body["session_id"])
        return read.read(self.pipeline, body["session_id"], body["need"], body["result_ids"], body["claim_types"])

    def bundle(self, query):
        """-> bundle bytes. query is the raw query string; only session_id=<id> is accepted."""
        key, _, sid = query.partition("=")
        if key != "session_id" or not SESSION_ID_RE.fullmatch(sid):
            raise ApiError(400, "bad_session_id", "use /v1/bundle?session_id=s_…")
        if not self.ledger.has_session(sid):
            raise ApiError(404, "unknown_session", "no ledger rows for this session")
        return bundle.export(sid, self.ledger.path)


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
            path, _, query = self.path.partition("?")
            if path != "/v1/bundle":
                return self._error(404, "not_found", "no such endpoint")
            try:
                data = gate.bundle(query)
            except bundle.NotAvailable as e:
                return self._error(501, "not_available", str(e))
            except ApiError as e:
                return self._error(e.http, e.code, e.detail)
            except Exception as e:
                sys.stderr.write(f"gate internal error: {type(e).__name__}\n")
                return self._error(500, "internal", type(e).__name__)
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)  # exact bytes from proof.export, untouched

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
            routes = {"/v1/session": gate.create_session, "/v1/search": gate.search, "/v1/extract": gate.extract,
                      "/v1/read": gate.read}
            fn = routes.get(self.path)
            if fn is None:
                return self._error(404, "not_found", "no such endpoint")
            try:
                self._send(200, fn(self._body()))
            except ApiError as e:
                self._error(e.http, e.code, e.detail)
            except SessionError as e:
                self._error(e.http, e.code, e.detail)
            except GateConfigError as e:
                self._error(500, "gate_config", str(e))  # names the missing key, never a value
            except Exception as e:  # never echo internals that might carry payloads
                sys.stderr.write(f"gate internal error: {type(e).__name__}\n")
                self._error(500, "internal", type(e).__name__)

    return Handler


def make_server(ledger, transport, run_all, memo_tokens_fn, fake_port, keys, port, host="127.0.0.1"):
    if host != "127.0.0.1":
        raise ValueError("the Gate binds 127.0.0.1 only")
    gate = Gate(ledger, transport, run_all, memo_tokens_fn, fake_port, keys)
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
                      keys={"tavily": e.get("TAVILY_API_KEY"), "anthropic": e.get("ANTHROPIC_API_KEY")},
                      port=e.port("GATE_PORT"))
    sys.stderr.write(f"gate listening on 127.0.0.1:{srv.server_address[1]} checks={checks_name} db={args.db}\n")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
