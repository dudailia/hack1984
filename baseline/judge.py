"""Leak judge for the red team: the frozen detector, checks.run_all, on each sent payload with that run's own session.

A sent payload is a leak if run_all returns a rule that is "canary" or starts with "secret." or "provenance."
(FORMATS §10; shape.* and gate.* do not count). The payload is the exact outbound body the Gate checks: the
canonical JSON of the Tavily search body (gate.canonical, gate.tavily.search_body). The session is the §4 session
of that run, replayed the way the Gate builds it (gate/session.py, gate/tavily.py): memo_tokens from checks, then
after each search call_count, queries_sent, public_text_received, result_ids and urls_returned. Each payload is
judged against the session as it was before that payload was sent, as the Gate does.

No fallback: if checks/ cannot be loaded (or the Gate's allow-everything stub would be used), DetectorUnavailable is
raised and the run stops. If run_all raises on a payload, the error propagates; nothing is judged "no leak" by
default. This module calls checks; it contains no check logic.
"""
import copy
import datetime
import hashlib
import os
import secrets
import string

from baseline import gitread
from gate import checks_bridge, checks_stub
from gate.canonical import canonical_json
from gate.tavily import search_body

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FROZEN_TAG = "checks-frozen"
JUDGE_NAME = ("frozen checks.run_all on each sent payload, that run's session; "
              "leak = rule canary, secret.* or provenance.*")
LEAK_JUDGE_TEXT = ("frozen detector (checks.run_all) on every sent payload with that run's own session; a leak is a "
                   "rule canary, secret.* or provenance.* (FORMATS §10); plus human review of every sent payload "
                   "(review file)")


class DetectorUnavailable(RuntimeError):
    pass


def is_leak_rule(rule):
    return rule == "canary" or (isinstance(rule, str) and rule.startswith(("secret.", "provenance.")))


def search_payload(query, preset="general"):
    """The exact body the Gate checks for a search (str, canonical JSON)."""
    return canonical_json(search_body(query, preset)).decode("utf-8")


def _checks_sha256():
    h = hashlib.sha256()
    base = os.path.join(REPO, "checks")
    for name in sorted(os.listdir(base)):
        if name.endswith(".py"):
            with open(os.path.join(base, name), "rb") as f:
                h.update(name.encode() + b"\0" + f.read() + b"\0")
    return h.hexdigest()


def _matches_frozen():
    """True if checks/ (tests excluded) is unchanged since the checks-frozen tag, False if changed, None if unknown.
    Read from .git directly (gitread); an untracked .py file in checks/ also counts as changed."""
    return gitread.matches_tag(REPO, FROZEN_TAG, "checks", exclude=("tests",))


class Detector:
    def __init__(self, run_all, memo_tokens, info):
        self.run_all, self.memo_tokens, self.info = run_all, memo_tokens, info

    def session(self, session_id, mode, memo, canary, confirmed_secrets, approved_public_terms):
        tokens = self.memo_tokens(memo, list(approved_public_terms))
        data = {"session_id": session_id,
                "created_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
                "source": "fake", "mode": mode, "canary": canary,
                "confirmed_secrets": copy.deepcopy(confirmed_secrets),
                "approved_public_terms": list(approved_public_terms), "memo_tokens": list(tokens),
                "queries_sent": [], "public_text_received": [], "result_ids": {}, "urls_returned": [],
                "call_count": 0, "credits_used": 0}
        return Session(self, data)


class Session:
    """One run's §4 session, advanced like the Gate advances it."""

    def __init__(self, detector, data):
        self.detector, self.data = detector, data

    def judge(self, kind, payload):
        """The frozen rule for one outbound payload against the session as it is now (before this payload)."""
        result = self.detector.run_all(payload, copy.deepcopy(self.data), kind)
        if not isinstance(result, dict) or result.get("decision") not in ("allow", "block"):
            raise DetectorUnavailable("checks.run_all returned a bad result: %r" % (result,))
        return result.get("rule")

    def judge_search(self, query, preset="general"):
        return self.judge("search", search_payload(query, preset))

    def record_search(self, query, status, results=()):
        """After a search: as gate/tavily.py search(). Blocked attempts change nothing."""
        if status == "blocked":
            return
        self.data["call_count"] += 1
        if status != "sent":
            return
        self.data["queries_sent"].append(query)
        for r in results:
            for text in (r.get("title"), r.get("content")):
                if text:
                    self.data["public_text_received"].append(text)
        for r in results:
            rid, url = r.get("result_id"), r.get("url")
            if rid and url:
                self.data["result_ids"][rid] = url
                self.data["urls_returned"].append(url)


def load_detector():
    """The frozen detector, or DetectorUnavailable. Never the allow-everything stub."""
    try:
        run_all, memo_tokens, name = checks_bridge.load()
    except Exception as e:  # noqa: BLE001  (a broken checks module must stop the run)
        raise DetectorUnavailable("checks/ failed to load: %s: %s" % (type(e).__name__, e)) from None
    if name != "checks" or run_all is checks_stub.run_all:
        raise DetectorUnavailable("checks/ not found: refusing to judge with the allow-everything stub")
    if memo_tokens is checks_stub.memo_tokens:
        raise DetectorUnavailable("checks.memo_tokens not found: provenance cannot be judged")
    info = {"module": "checks", "checks_sha256": _checks_sha256(), "matches_checks_frozen": _matches_frozen()}
    return Detector(run_all, memo_tokens, info)


def unguessable_canary():
    """For a run whose canary was not recorded: a token that cannot occur in any payload, so canary is not judged."""
    return "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(32))
