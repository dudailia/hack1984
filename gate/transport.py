"""The only module in gate/ that opens network connections. Called only by gate/pipeline.py (wired in server.py).

HTTPS for public hosts, plain HTTP only to the loopback Tavily stand-in. http.client never follows redirects.
Headers are passed through and never logged or stored.
"""
import http.client
import re
import ssl

TIMEOUT_S = 30
MAX_RESPONSE = 20 * 1024 * 1024
_CTX = ssl.create_default_context()


PUBLIC_HOSTS = {"api.tavily.com", "api.anthropic.com"}
LOOPBACK_RE = re.compile(r"127\.0\.0\.1:[0-9]{1,5}")


def https_post(destination, path, payload, headers):
    """Defence in depth: the pipeline already enforces the exact per-session allowlist."""
    if destination not in PUBLIC_HOSTS and not LOOPBACK_RE.fullmatch(destination):
        raise ValueError("destination not allowed")
    if not path.startswith("/"):
        raise ValueError("path must start with /")
    if destination.startswith("127.0.0.1:"):
        host, port = destination.split(":")
        conn = http.client.HTTPConnection(host, int(port), timeout=TIMEOUT_S)
    else:
        conn = http.client.HTTPSConnection(destination, 443, timeout=TIMEOUT_S, context=_CTX)
    h = {"Content-Type": "application/json", "Accept": "application/json", "User-Agent": "doublethink-gate/0.1"}
    h.update(headers)
    try:
        conn.request("POST", path, body=payload, headers=h)
        resp = conn.getresponse()
        # truncate instead of raising: the request was sent, so the status (and credits) must still be ledgered
        return resp.status, resp.read(MAX_RESPONSE)
    finally:
        conn.close()
