"""Client for the Gate API (FORMATS §3) as component "baseline", on source=fake sessions only (invariant 7).

The baseline never calls Tavily or fake_tavily itself: every search is a request to the Gate on loopback.
"""
import re

from baseline import loopback

BASELINE_MODES = ("single_agent", "compromised")
PRESETS = ("general", "finance", "news")
MAX_QUERY = 400
_NEED = re.compile(r"[a-z0-9_]{1,32}")


class GateError(Exception):
    def __init__(self, code, detail, http_status=None):
        super().__init__("%s: %s" % (code, detail))
        self.code = code
        self.detail = detail
        self.http_status = http_status


def check_response(status, body):
    """Raise GateError for an error reply; return the body otherwise. `blocked` is a normal reply."""
    if not isinstance(body, dict):
        raise GateError("bad_response", "Gate reply is not a JSON object", status)
    if status >= 400 or body.get("status") == "error":
        raise GateError(body.get("error") or "http_%d" % status, body.get("detail"), status)
    return body


class GateClient:
    def __init__(self, port, timeout=60):
        self.port = loopback.check_port(port)
        self.timeout = timeout

    def _post(self, path, obj):
        return check_response(*loopback.post_json(self.port, path, obj, timeout=self.timeout))

    def create_session(self, session_id, mode, memo, canary, confirmed_secrets, approved_public_terms,
                       source="fake"):
        if source != "fake":
            raise ValueError("the baseline runs only on source=fake (invariant 7), got %r" % (source,))
        if mode not in BASELINE_MODES:
            raise ValueError("baseline mode must be one of %s, got %r" % (BASELINE_MODES, mode))
        body = {"session_id": session_id, "mode": mode, "source": "fake", "memo": memo, "canary": canary,
                "confirmed_secrets": confirmed_secrets, "approved_public_terms": approved_public_terms}
        resp = self._post("/v1/session", body)
        if resp.get("status") != "ok" or resp.get("session_id") != session_id:
            raise GateError("bad_response", "session not created")
        return resp

    def search(self, session_id, need, query, preset):
        if not isinstance(need, str) or not _NEED.fullmatch(need):
            raise ValueError("need must match [a-z0-9_]{1,32}")
        if not isinstance(query, str) or not query.strip() or len(query) > MAX_QUERY:
            raise ValueError("query must be a non-empty string of at most %d chars" % MAX_QUERY)
        if preset not in PRESETS:
            raise ValueError("preset must be one of %s" % (PRESETS,))
        body = {"session_id": session_id, "component": "baseline", "need": need, "query": query,
                "options": {"preset": preset}}
        return self._post("/v1/search", body)
