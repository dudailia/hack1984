"""Client for the app control API (FORMATS §11) and its event stream (§10). Loopback only.

http.client is used instead of urllib so no proxy variable can route a request off the machine.
"""
import http.client
import json
import socket
import time
from urllib.parse import quote, urlsplit, parse_qs

LOOPBACK = "127.0.0.1"


class AppError(RuntimeError):
    """The app answered with an error, closed the stream early, or did not finish in time."""


def parse_app_url(url):
    """'http://127.0.0.1:8700/ui/index.html?token=abc' (as printed by app/run.py) -> (port, token)."""
    parts = urlsplit(url)
    if parts.scheme != "http" or parts.hostname not in (LOOPBACK, "localhost"):
        raise ValueError("app URL must be http://127.0.0.1:<port>/...")
    if parts.port is None:
        raise ValueError("app URL must include the port")
    token = (parse_qs(parts.query).get("token") or [None])[0]
    return parts.port, token


class AppClient:
    def __init__(self, port, token, timeout=30.0):
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError("port must be an int 1-65535, got %r" % (port,))
        if not token:
            raise ValueError("a token is required (FORMATS §11)")
        self.port = port
        self.token = token
        self.timeout = timeout

    def _headers(self):
        return {"X-DT-Token": self.token}

    def start_run(self, body):
        """POST /api/run; returns the session_id."""
        data = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        conn = http.client.HTTPConnection(LOOPBACK, self.port, timeout=self.timeout)
        try:
            headers = dict(self._headers(), **{"Content-Type": "application/json"})
            conn.request("POST", "/api/run", body=data, headers=headers)
            resp = conn.getresponse()
            raw = resp.read()
        finally:
            conn.close()
        try:
            parsed = json.loads(raw) if raw else None
        except (ValueError, UnicodeDecodeError):
            parsed = None
        if resp.status != 200 or not isinstance(parsed, dict) or not isinstance(parsed.get("session_id"), str):
            err = parsed.get("error") if isinstance(parsed, dict) else None
            raise AppError("POST /api/run failed: HTTP %d %s" % (resp.status, err or ""))
        return parsed["session_id"]

    def collect_run(self, session_id, deadline_s, idle_s=30.0):
        """Read /events until run_done for session_id. Returns that session's envelopes in order.

        On connect the app replays the current run (§10), so connecting after POST /api/run loses nothing.
        Envelopes for other sessions (an earlier run being replayed) are skipped.
        """
        end = time.monotonic() + deadline_s
        conn = http.client.HTTPConnection(LOOPBACK, self.port, timeout=min(idle_s, deadline_s))
        events = []
        try:
            conn.request("GET", "/events?token=" + quote(self.token, safe=""),
                         headers=dict(self._headers(), Accept="text/event-stream"))
            resp = conn.getresponse()
            if resp.status != 200:
                raise AppError("GET /events failed: HTTP %d" % resp.status)
            for env in iter_sse(resp, end):
                if env.get("session_id") != session_id:
                    continue
                events.append(env)
                if env.get("type") == "run_done":
                    return events
        except socket.timeout:
            raise AppError("no event for %.0f s while waiting for run_done" % idle_s)
        finally:
            conn.close()
        if time.monotonic() >= end:
            raise AppError("timed out after %.0f s waiting for run_done" % deadline_s)
        raise AppError("event stream closed before run_done")


def iter_sse(resp, end=None):
    """Yield parsed envelopes from an SSE response: 'id:' and 'data:' lines, blank line ends a frame,
    ':' lines are comments (pings). Stops when the stream closes or the monotonic deadline passes."""
    data_lines = []
    while end is None or time.monotonic() < end:
        line = resp.fp.readline()
        if not line:
            return
        line = line.decode("utf-8").rstrip("\r\n")
        if line == "":
            if data_lines:
                try:
                    env = json.loads("\n".join(data_lines))
                except ValueError:
                    env = None
                data_lines = []
                if isinstance(env, dict):
                    yield env
            continue
        if line.startswith(":"):
            continue
        field, _, value = line.partition(":")
        if value.startswith(" "):
            value = value[1:]
        if field == "data":
            data_lines.append(value)
