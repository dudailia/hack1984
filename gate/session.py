"""Sessions (shared/FORMATS.md §1 and §4), created by POST /v1/session and held by the Gate.

The memo is used once to compute memo_tokens and is not kept. Gate internals (result text, id counter) live in
GateState, outside the §4 session dict that checks.run_all receives.
"""
import copy
import re
import threading

from gate import canonical as c

SESSION_ID_RE = re.compile(r"^s_[a-z0-9]{8,16}$")
MODES = {"single_agent", "compromised", "two_minds", "doublethink"}
SOURCES = {"real", "fake"}
FAKE_ONLY_MODES = {"single_agent", "compromised", "two_minds"}


class SessionError(Exception):
    def __init__(self, code, detail, http=400):
        super().__init__(detail)
        self.code, self.detail, self.http = code, detail, http


class GateState:
    """Per-session Gate internals. Never passed to checks or to the Planner."""

    def __init__(self):
        self.next_result_n = 1
        self.docs = {}  # result_id -> {"url", "title", "content"}
        self.lock = threading.Lock()


def _str_list(v):
    return isinstance(v, list) and all(isinstance(x, str) for x in v)


def _validate(b):
    if not isinstance(b, dict):
        raise SessionError("bad_request", "body must be a JSON object")
    sid = b.get("session_id")
    if not isinstance(sid, str) or not SESSION_ID_RE.fullmatch(sid):
        raise SessionError("bad_session_id", "session_id must match s_[a-z0-9]{8,16}")
    if b.get("mode") not in MODES:
        raise SessionError("bad_mode", "unknown mode")
    if b.get("source") not in SOURCES:
        raise SessionError("bad_source", "unknown source")
    if b["mode"] in FAKE_ONLY_MODES and b["source"] != "fake":
        raise SessionError("mode_source_mismatch", f"mode {b['mode']} requires source fake")
    if not isinstance(b.get("memo"), str) or not b["memo"]:
        raise SessionError("bad_memo", "memo must be a non-empty string")
    if not isinstance(b.get("canary"), str) or not b["canary"]:
        raise SessionError("bad_canary", "canary must be a non-empty string")
    secrets = b.get("confirmed_secrets")
    if not isinstance(secrets, list) or not all(
            isinstance(s, dict) and set(s) == {"label", "values"} and isinstance(s["label"], str)
            and _str_list(s["values"]) for s in secrets):
        raise SessionError("bad_confirmed_secrets", "confirmed_secrets must be [{label, values[]}]")
    if not _str_list(b.get("approved_public_terms")):
        raise SessionError("bad_approved_public_terms", "approved_public_terms must be a list of strings")


class SessionStore:
    def __init__(self, ledger, memo_tokens_fn):
        self._ledger = ledger
        self._memo_tokens_fn = memo_tokens_fn
        self._sessions = {}
        self._state = {}
        self._enforce = {}
        self._lock = threading.Lock()

    def create(self, body):
        _validate(body)
        sid = body["session_id"]
        # Anant's interface: memo_tokens(memo, approved_public_terms) -> [str], called once per session
        tokens = self._memo_tokens_fn(body["memo"], list(body["approved_public_terms"]))
        if not _str_list(tokens):
            raise SessionError("memo_tokens_error", "memo_tokens function returned a bad value", http=500)
        session = {
            "session_id": sid,
            "created_at": c.utc_now(),
            "source": body["source"],
            "mode": body["mode"],
            "canary": body["canary"],
            "confirmed_secrets": copy.deepcopy(body["confirmed_secrets"]),
            "approved_public_terms": list(body["approved_public_terms"]),
            "memo_tokens": list(tokens),
            "queries_sent": [],
            "public_text_received": [],
            "result_ids": {},
            "urls_returned": [],
            "call_count": 0,
            "credits_used": 0,
        }
        with self._lock:
            if sid in self._sessions or self._ledger.has_session(sid):
                raise SessionError("session_exists", "session id already used", http=409)
            self._sessions[sid] = session
            self._state[sid] = GateState()
            self._enforce[sid] = body["mode"] == "doublethink"
        return session

    def get(self, sid):
        with self._lock:
            if sid not in self._sessions:
                raise SessionError("unknown_session", "no such session", http=404)
            return self._sessions[sid]

    def state(self, sid) -> GateState:
        self.get(sid)
        return self._state[sid]

    def enforce(self, sid) -> bool:
        self.get(sid)
        return self._enforce[sid]
