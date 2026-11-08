"""The one send path (shared/FORMATS.md §1, §6, §7). The order never changes:

1. serialize the body canonically, once;
2. Gate rules;
3. checks.run_all on the exact bytes (always, even if a Gate rule fired; if it raises: gate.check_error);
4. decide;
5. write the attempt row (if this fails, nothing is sent);
6. send those exact bytes, only if allowed;
7. write the result row.
"""
import copy

from gate.canonical import canonical_json

TAVILY = "api.tavily.com"
ANTHROPIC = "api.anthropic.com"

R_HOST = "gate.host_not_allowed"
R_FAKE = "gate.fake_not_allowed"
R_ANTHROPIC = "gate.anthropic_not_reader"
R_UNKNOWN_ID = "gate.unknown_result_id"
R_CHECK_ERROR = "gate.check_error"
R_PATH = "gate.path_not_allowed"
PRE_RULES = {R_UNKNOWN_ID}

ANTHROPIC_VERSION = "2023-06-01"
# Exact POST destinations: host -> path for each kind. Anything else is gate.path_not_allowed.
KIND_PATH = {"search": "/search", "extract": "/extract", "reader": "/v1/messages"}
TAVILY_PATHS = {"/search", "/extract"}
ANTHROPIC_PATHS = {"/v1/messages"}

GATE_DETAIL = {
    R_PATH: "path is not allowed for this destination and kind",
    R_HOST: "destination is not on the allowlist for this session and kind",
    R_FAKE: "the local Tavily stand-in is not allowed in a real session",
    R_ANTHROPIC: "api.anthropic.com is for reader jobs only",
    R_UNKNOWN_ID: "result id was not issued in this session",
    R_CHECK_ERROR: "the checks failed to run; blocked (fail closed)",
}


def _valid_check_result(r):
    if not isinstance(r, dict) or r.get("decision") not in ("allow", "block"):
        return False
    if r.get("rule") is not None and not isinstance(r.get("rule"), str):
        return False
    if r.get("detail") is not None and not isinstance(r.get("detail"), str):
        return False
    if r["decision"] == "block" and not r.get("rule"):
        return False
    return True


class GateConfigError(Exception):
    """A required key is missing from .env. Raised before any ledger row; nothing is sent."""


class Pipeline:
    def __init__(self, ledger, sessions, transport, run_all, fake_port, keys=None):
        self.ledger = ledger
        self.sessions = sessions
        self.transport = transport
        self.run_all = run_all
        self.fake = f"127.0.0.1:{int(fake_port)}"
        self._keys = dict(keys or {})  # {"tavily": ..., "anthropic": ...} from .env; never logged

    def __repr__(self):
        return "Pipeline()"

    def _headers(self, destination):
        """Only the Gate builds outbound headers, from its own .env keys. Callers never supply any."""
        if destination == TAVILY:
            key = self._keys.get("tavily")
            if not key:
                raise GateConfigError("TAVILY_API_KEY is not set")
            return {"Authorization": f"Bearer {key}"}
        if destination == ANTHROPIC:
            key = self._keys.get("anthropic")
            if not key:
                raise GateConfigError("ANTHROPIC_API_KEY is not set")
            return {"x-api-key": key, "anthropic-version": ANTHROPIC_VERSION}
        return {}

    def path_rule(self, kind, destination, path):
        allowed = ANTHROPIC_PATHS if destination == ANTHROPIC else TAVILY_PATHS
        if path not in allowed or KIND_PATH.get(kind) != path:
            return R_PATH
        return None

    def gate_rule(self, session, kind, destination, path):
        rule = self._host_rule(session, kind, destination)
        return rule or self.path_rule(kind, destination, path)

    def _host_rule(self, session, kind, destination):
        if destination not in (TAVILY, ANTHROPIC, self.fake):
            return R_HOST
        if destination == self.fake and session["source"] != "fake":
            return R_FAKE
        if destination == ANTHROPIC and kind != "reader":
            return R_ANTHROPIC
        if kind == "reader" and destination != ANTHROPIC:
            return R_HOST
        if destination == TAVILY and session["source"] != "real":
            return R_HOST  # invariant 7: fake-only modes never reach the real Tavily
        return None

    def send(self, session_id, component, kind, destination, path, body_obj, pre_rule=None, credits_fn=None):
        session = self.sessions.get(session_id)
        enforce = self.sessions.enforce(session_id)

        # 1. one canonical serialization; these exact bytes are checked, committed and sent
        payload = canonical_json(body_obj)

        # 2. Gate rules (host first, then exact path)
        if pre_rule is not None and pre_rule not in PRE_RULES:
            raise ValueError("unknown pre_rule")
        g_rule = self.gate_rule(session, kind, destination, path) or pre_rule
        headers = {}
        if not g_rule:
            headers = self._headers(destination)  # missing key: GateConfigError, before any row

        # 3. checks, always
        try:
            check = self.run_all(payload.decode("utf-8"), copy.deepcopy(session), kind)
            check_ok = _valid_check_result(check)
        except BaseException:  # incl. SystemExit: fail closed, and still write the attempt row
            check, check_ok = None, False

        # 4. decide
        if g_rule:
            decision, rule, detail = "blocked", g_rule, GATE_DETAIL[g_rule]
        elif not check_ok:
            decision, rule, detail = "blocked", R_CHECK_ERROR, GATE_DETAIL[R_CHECK_ERROR]
        elif check["decision"] == "block":
            rule, detail = check["rule"], check.get("detail")
            decision = "blocked" if (enforce or kind == "reader") else "allowed"
        else:
            decision, rule, detail = "allowed", None, None

        # 5. attempt row before any send; an exception here means nothing is sent
        attempt = self.ledger.append_attempt(session_id, component, kind, destination, payload, decision, rule)
        out = {"status": "blocked", "rule": rule, "detail": detail, "ledger_seq": attempt["seq"],
               "rows": [attempt], "http_status": None, "response": None, "transport_error": None}
        if decision != "allowed":
            return out

        # 6. send exactly the committed bytes
        http_status, response, transport_error = None, b"", None
        try:
            http_status, response = self.transport(destination, path, payload, headers or {})
        except Exception as e:
            # the exception TYPE only (e.g. SSLCertVerificationError, TimeoutError): its message can carry hosts,
            # paths or worse, and it is never ledgered
            http_status, response, transport_error = None, b"", type(e).__name__
        ok = http_status is not None and 200 <= http_status < 300

        credits = None
        if ok and credits_fn is not None:
            try:
                credits = credits_fn(http_status, response)
            except Exception:
                credits = None
            if not isinstance(credits, int) or isinstance(credits, bool):
                credits = None

        # 7. result row
        result = self.ledger.append_result(session_id, attempt["seq"], "sent" if ok else "error",
                                           http_status, credits, response)
        out.update(status="sent" if ok else "error", rows=[attempt, result], http_status=http_status,
                   response=response if ok else None, transport_error=transport_error)
        return out
