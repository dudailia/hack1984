"""Fake Tavily: a loopback-only stand-in for Tavily POST /search and POST /extract.

Standard library only. Binds 127.0.0.1 and nothing else. Serves the fictional Halyard fixture pages, one of
them poisoned (notes/DEMO.md). The baseline, compromised and two_minds modes and every red-team run use it
(invariant 7). It never reads API keys and ignores the Authorization header.

    python3 -m fake_tavily.server [--port N]
"""
import argparse
import json
import math
import os
import sys
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from fake_tavily import inject, pages

LOOPBACK = "127.0.0.1"
DEFAULT_PORT = 8702
PORT_KEY = "FAKE_TAVILY_PORT"
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAX_BODY = 1 << 20
MAX_RESULTS_LIMIT = 20
MAX_EXTRACT_URLS = 20


def resolve_port(env=None, env_file=None):
    """FAKE_TAVILY_PORT from the environment, else from .env, else 8702.

    In .env only the FAKE_TAVILY_PORT line is looked at; every other line (API keys included) is skipped
    unparsed and not kept.
    """
    env = os.environ if env is None else env
    raw = env.get(PORT_KEY)
    if raw is None:
        raw = _port_from_env_file(env_file or os.path.join(REPO, ".env"))
    if raw is None:
        return DEFAULT_PORT
    raw = raw.strip()
    if not raw.isdigit() or not 1 <= int(raw) <= 65535:
        raise ValueError("%s must be a port number 1-65535" % PORT_KEY)
    return int(raw)


def _port_from_env_file(path):
    try:
        f = open(path, encoding="utf-8")
    except FileNotFoundError:
        return None
    with f:
        for line in f:
            s = line.strip()
            if s.startswith("export "):
                s = s[len("export "):].lstrip()
            if s.startswith(PORT_KEY + "="):
                return s.split("=", 1)[1].split("#", 1)[0].strip().strip("'\"")
    return None


class TavilyError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


def _flag(body, key):
    return body.get(key) not in (None, False, "", 0)


def do_search(srv, body):
    query = body.get("query")
    if not isinstance(query, str) or not query.strip():
        raise TavilyError(400, "query is required")
    max_results = body.get("max_results", 5)
    if type(max_results) is not int or not 0 <= max_results <= MAX_RESULTS_LIMIT:
        raise TavilyError(400, "max_results must be an integer between 0 and %d" % MAX_RESULTS_LIMIT)
    planted = inject.current_planted(srv.state_path, srv.pages)
    want_raw = _flag(body, "include_raw_content")
    results = []
    for rank, page in enumerate(pages.search(srv.pages, query, max_results)):
        r = pages.render(page, planted)
        results.append({
            "title": r["title"],
            "url": r["url"],
            "content": r["content"],
            "score": pages.score(rank),
            "raw_content": r["raw_content"] if want_raw else None,
        })
    out = {
        "query": query,
        "follow_up_questions": None,
        "answer": None,
        "images": [],
        "results": results,
    }
    credits = 2 if body.get("search_depth") == "advanced" else 1
    return out, credits


def do_extract(srv, body):
    urls = body.get("urls")
    if isinstance(urls, str):
        urls = [urls]
    if (not isinstance(urls, list) or not urls or len(urls) > MAX_EXTRACT_URLS
            or not all(isinstance(u, str) and u.strip() for u in urls)):
        raise TavilyError(400, "urls must be a non-empty string or list of up to %d strings" % MAX_EXTRACT_URLS)
    planted = inject.current_planted(srv.state_path, srv.pages)
    results, failed = [], []
    for url in urls:
        page = pages.lookup(srv.pages, url)
        if page is None:
            failed.append({"url": url, "error": "Failed to fetch url"})
        else:
            results.append({"url": url, "raw_content": pages.render(page, planted)["raw_content"], "images": []})
    rate = 2 if body.get("extract_depth") == "advanced" else 1
    return {"results": results, "failed_results": failed}, rate * math.ceil(len(results) / 5)


ROUTES = {"/search": do_search, "/extract": do_extract}


class Handler(BaseHTTPRequestHandler):
    server_version = "fake-tavily/1"
    sys_version = ""

    def log_message(self, fmt, *args):
        # The request line holds method and path only; headers (Authorization included) are never logged.
        if self.server.verbose:
            sys.stderr.write("fake_tavily %s\n" % (fmt % args))

    def _send(self, status, obj):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _error(self, status, message):
        self._send(status, {"detail": {"error": message}})

    def do_GET(self):
        if urlsplit(self.path).path == "/health":
            self._send(200, {"status": "ok"})
        else:
            self._error(404, "Not found")

    def do_POST(self):
        t0 = time.perf_counter()
        route = ROUTES.get(urlsplit(self.path).path)
        if route is None:
            return self._error(404, "Not found")
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self._error(400, "Invalid Content-Length")
        if length > MAX_BODY:
            return self._error(413, "Request body too large")
        try:
            body = json.loads(self.rfile.read(length) or b"null")
        except (ValueError, UnicodeDecodeError):
            return self._error(400, "Invalid JSON body")
        if not isinstance(body, dict):
            return self._error(400, "Request body must be a JSON object")
        try:
            out, credits = route(self.server, body)
        except TavilyError as e:
            return self._error(e.status, e.message)
        out["response_time"] = round(time.perf_counter() - t0, 2)
        if _flag(body, "include_usage"):
            out["usage"] = {"credits": credits}
        out["request_id"] = str(uuid.uuid4())
        self._send(200, out)


class FakeTavilyServer(ThreadingHTTPServer):
    daemon_threads = True


def make_server(port=None, host=LOOPBACK, fixtures_dir=pages.DEFAULT_FIXTURES, state_path=None, verbose=False):
    if host != LOOPBACK:
        raise ValueError("fake_tavily binds %s only, not %r" % (LOOPBACK, host))
    srv = FakeTavilyServer((LOOPBACK, resolve_port() if port is None else port), Handler)
    srv.pages = pages.load_pages(fixtures_dir)
    srv.state_path = state_path  # None means inject.default_state_path() at request time
    srv.verbose = verbose
    return srv


def main(argv=None):
    # TODO(guard): install shared.guard (loopback-only audit hook, invariant 1) once it lands in shared/.
    ap = argparse.ArgumentParser(prog="python3 -m fake_tavily.server", description="Loopback Tavily stand-in")
    ap.add_argument("--port", type=int, default=None, help="default: FAKE_TAVILY_PORT from env/.env, else 8702")
    args = ap.parse_args(argv)
    srv = make_server(port=args.port, verbose=True)
    print("fake tavily on http://%s:%d" % srv.server_address[:2], flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
