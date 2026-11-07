"""The baseline's only way to open a connection: JSON POST to 127.0.0.1.

http.client is used instead of urllib so that no proxy setting (HTTP_PROXY and friends) can route a request
off the machine. Any host other than 127.0.0.1 is refused before a socket is created (invariant 1).
"""
import http.client
import json

LOOPBACK = "127.0.0.1"


def encode(obj):
    """Canonical JSON (FORMATS §0)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def check_port(port):
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("port must be an int 1-65535, got %r" % (port,))
    return port


def post_json(port, path, obj, host=LOOPBACK, timeout=30):
    """POST obj as canonical JSON; return (http_status, parsed JSON body or None)."""
    if host != LOOPBACK:
        raise ValueError("baseline connects to %s only, not %r" % (LOOPBACK, host))
    check_port(port)
    if not path.startswith("/"):
        raise ValueError("path must start with /")
    body = encode(obj)
    conn = http.client.HTTPConnection(LOOPBACK, port, timeout=timeout)
    try:
        conn.request("POST", path, body=body, headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        raw = resp.read()
    finally:
        conn.close()
    try:
        parsed = json.loads(raw) if raw else None
    except (ValueError, UnicodeDecodeError):
        parsed = None
    return resp.status, parsed
