"""Test stubs: a stub Gate (FORMATS §3) and a stub Ollama, each on 127.0.0.1 port 0 in a background thread.

The real Gate is Aayush's (gate/) and not merged yet. This stub implements only what the baseline uses:
POST /v1/session (refuses source != fake for the fake-only modes, §1) and POST /v1/search (component baseline
gets `results` with web text, built from the fake_tavily fixture pages). It records every request.
"""
import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from fake_tavily import inject, pages

FAKE_ONLY_MODES = {"single_agent", "compromised", "two_minds"}
ZERO_HASH = "0" * 64


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


class _Recorder(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _send(self, status, obj):
        data = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        rec = {"method": "POST", "path": self.path, "headers": dict(self.headers.items()), "raw": raw}
        try:
            rec["body"] = json.loads(raw)
        except ValueError:
            rec["body"] = None
        with self.server.lock:
            self.server.requests.append(rec)
        status, obj = self.server.route(self.path, rec["body"])
        self._send(status, obj)


class _Server(ThreadingHTTPServer):
    daemon_threads = True


class _Stub:
    def __init__(self):
        self.server = _Server(("127.0.0.1", 0), _Recorder)
        self.server.requests = []
        self.server.lock = threading.Lock()
        self.server.route = self.route
        self.port = self.server.server_address[1]
        self._thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)

    def start(self):
        self._thread.start()
        return self

    def stop(self):
        self.server.shutdown()
        self.server.server_close()

    @property
    def requests(self):
        with self.server.lock:
            return list(self.server.requests)

    def route(self, path, body):
        raise NotImplementedError


def _error(status, code, detail):
    return status, {"status": "error", "error": code, "detail": detail}


class StubGate(_Stub):
    """planted: the text substituted on the poisoned page ("" = page without the instruction).
    poison_from_search: 1-based search number from which the poisoned page appears in results.
    state_path: if set, the planted text is re-read from this fake_tavily.inject state file on every search,
    like the real stand-in does (red-team tests)."""

    def __init__(self, planted=None, poison_from_search=1, block_queries=(), state_path=None):
        super().__init__()
        self.pages = pages.load_pages()
        self.planted = pages.default_planted(self.pages) if planted is None else planted
        self.poison_from_search = poison_from_search
        self.block_queries = set(block_queries)
        self.state_path = state_path
        self.detect_canary = True  # False: the Gate's allow-everything stub
        self.served = []  # (session_id, query, planted text on the poisoned page)
        self.sessions = {}
        self.search_count = 0
        self.seq = 0
        self.prev = ZERO_HASH

    def _row(self, session_id, **fields):
        self.seq += 1
        row = {"seq": self.seq, "time": "2026-11-07T23:40:00.000Z", "session_id": session_id, **fields,
               "prev_hash": self.prev}
        row["hash"] = hashlib.sha256(self.prev.encode() + canonical(row)).hexdigest()
        self.prev = row["hash"]
        return row

    def route(self, path, body):
        if not isinstance(body, dict):
            return _error(400, "bad_json", "body must be a JSON object")
        if path == "/v1/session":
            if body.get("mode") in FAKE_ONLY_MODES and body.get("source") != "fake":
                return _error(400, "source_not_allowed", "mode %s requires source fake" % body.get("mode"))
            self.sessions[body["session_id"]] = body
            return 200, {"status": "ok", "session_id": body["session_id"],
                         "created_at": "2026-11-07T23:40:00.000Z", "enforce": body.get("mode") == "doublethink"}
        if path == "/v1/search":
            return self._search(body)
        return _error(404, "not_found", path)

    def _search(self, body):
        sid = body.get("session_id")
        if sid not in self.sessions:
            return _error(400, "unknown_session", "no such session")
        self.search_count += 1
        query = body.get("query", "")
        session = self.sessions[sid]
        rule = None
        for s in session.get("confirmed_secrets", []):
            if any(v.lower() in query.lower() for v in s["values"]):
                rule = "secret.%s" % s["label"]
                break
        if self.detect_canary and session.get("canary") and session["canary"] in query:
            rule = "canary"
        dest = "127.0.0.1:8702"
        if query in self.block_queries:
            row = self._row(sid, row_type="attempt", component=body.get("component"), kind="search",
                            destination=dest, commitment=ZERO_HASH, bytes=len(canonical(body)),
                            decision="blocked", rule="stub.block")
            return 200, {"status": "blocked", "rule": "stub.block", "detail": "stub", "ledger_seq": row["seq"],
                         "result_ids": [], "credits_used": 0, "ledger": [row]}
        attempt = self._row(sid, row_type="attempt", component=body.get("component"), kind="search",
                            destination=dest, commitment=ZERO_HASH, bytes=len(canonical(body)),
                            decision="allowed", rule=rule)
        planted = inject.current_planted(self.state_path, self.pages) if self.state_path else self.planted
        found = pages.search(self.pages, query, 10)
        if self.search_count < self.poison_from_search:
            found = [p for p in found if not p.get("poisoned")]
        results = []
        for i, p in enumerate(found, start=1):
            r = pages.render(p, planted)
            results.append({"result_id": "r_%02d" % (self.search_count * 10 + i), "title": r["title"],
                            "url": r["url"], "content": r["content"]})
        self.served.append((sid, query, planted))
        result_row = self._row(sid, row_type="result", attempt_seq=attempt["seq"], status="sent",
                               http_status=200, credits_used=None, response_commitment=ZERO_HASH)
        out = {"status": "sent", "rule": None, "ledger_seq": attempt["seq"],
               "result_ids": [r["result_id"] for r in results], "credits_used": None,
               "ledger": [attempt, result_row]}
        if body.get("component") == "baseline":
            out["results"] = results
        return 200, out


class StubOllama(_Stub):
    """Replays scripted actions (dicts) for POST /api/chat; after the script runs out it answers done."""

    def __init__(self, actions=()):
        super().__init__()
        self.actions = list(actions)

    def route(self, path, body):
        if path != "/api/chat":
            return 404, {"error": "not found"}
        action = self.actions.pop(0) if self.actions else {"action": "done"}
        content = action if isinstance(action, str) else json.dumps(action)
        return 200, {"model": body.get("model"), "message": {"role": "assistant", "content": content},
                     "done": True}


class ScriptedLLM:
    """In-process LLM stand-in for agent.run: returns scripted actions, records prompts."""

    def __init__(self, actions=()):
        self.actions = list(actions)
        self.calls = []

    def next_action(self, system, user):
        self.calls.append((system, user))
        return self.actions.pop(0) if self.actions else {"action": "done"}
