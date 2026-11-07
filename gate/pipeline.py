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
PRE_RULES = {R_UNKNOWN_ID}

GATE_DETAIL = {
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


class Pipeline:
    def __init__(self, ledger, sessions, transport, run_all, fake_port):
        self.ledger = ledger
        self.sessions = sessions
        self.transport = transport
        self.run_all = run_all
        self.fake = f"127.0.0.1:{int(fake_port)}"

    def gate_rule(self, session, kind, destination):
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

    def send(self, session_id, component, kind, destination, path, body_obj, headers=None, pre_rule=None,
             credits_fn=None):
        session = self.sessions.get(session_id)
        enforce = self.sessions.enforce(session_id)

        # 1. one canonical serialization; these exact bytes are checked, committed and sent
        payload = canonical_json(body_obj)

        # 2. Gate rules
        if pre_rule is not None and pre_rule not in PRE_RULES:
            raise ValueError("unknown pre_rule")
        g_rule = pre_rule or self.gate_rule(session, kind, destination)

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
               "rows": [attempt], "http_status": None, "response": None}
        if decision != "allowed":
            return out

        # 6. send exactly the committed bytes
        http_status, response = None, b""
        try:
            http_status, response = self.transport(destination, path, payload, headers or {})
        except Exception:
            http_status, response = None, b""
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
                   response=response if ok else None)
        return out
