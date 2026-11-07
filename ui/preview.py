"""Static preview server for the UI (owner: Sheara). Standard library only.

    python ui/preview.py        ->  http://127.0.0.1:8703/ui/index.html

Serves only /ui/ and /shared/ from the repo, on 127.0.0.1:8703, and refuses every other path: no other folder, no
traversal, no dotfiles, no directory listings, no Python sources, GET and HEAD only. It replaces
`python -m http.server` from the repo root, which exposed every file in the repo (Ilia's request).

Invariant 1: this process may reach loopback only. A loopback-only audit hook is installed before the socket opens.
"""
import http.server
import os
import posixpath
import sys
import urllib.parse

HOST = "127.0.0.1"
PORT = 8703
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALLOWED_PREFIXES = ("/ui/", "/shared/")
ALLOWED_ROOTS = tuple(os.path.realpath(os.path.join(REPO, p.strip("/"))) for p in ALLOWED_PREFIXES)
# Only what the page needs. No .py, no .md, no databases, no keys.
ALLOWED_SUFFIXES = (".html", ".css", ".js", ".json", ".jsonl", ".svg", ".png", ".woff2")
LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


class NetworkRefused(RuntimeError):
    pass


def _audit(event, args):
    if event == "socket.connect":
        addr = args[1] if len(args) > 1 else None
        if isinstance(addr, tuple) and addr and addr[0] not in LOOPBACK_HOSTS:
            raise NetworkRefused("ui/preview.py may connect to loopback only, not %r" % (addr[0],))
    elif event == "socket.getaddrinfo":
        host = args[0] if args else None
        if isinstance(host, bytes):
            host = host.decode("ascii", "replace")
        if host is not None and host not in LOOPBACK_HOSTS:
            raise NetworkRefused("ui/preview.py may resolve loopback only, not %r" % (host,))


_hook_installed = False


def install_audit_hook():
    """Idempotent: an audit hook cannot be removed, so install it once per process."""
    global _hook_installed
    if not _hook_installed:
        sys.addaudithook(_audit)
        _hook_installed = True


def allowed_path(raw_path):
    """Return the normalised URL path if it may be served, else None."""
    path = urllib.parse.urlsplit(raw_path).path
    decoded = urllib.parse.unquote(path)
    if "\\" in decoded or "\x00" in decoded or "%" in decoded:
        return None
    normal = posixpath.normpath(decoded) + ("/" if decoded.endswith("/") else "")
    if normal != decoded:                               # "..", "//", "/./" and similar tricks
        return None
    if not decoded.startswith(ALLOWED_PREFIXES):
        return None
    if any(seg.startswith(".") for seg in decoded.split("/") if seg):
        return None
    return decoded


class Handler(http.server.SimpleHTTPRequestHandler):
    server_version = "doublethink-preview"
    sys_version = ""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=REPO, **kwargs)

    def _route(self):
        """Return the allowed path, or None after sending the refusal."""
        if urllib.parse.urlsplit(self.path).path == "/":
            self.send_response(302)
            self.send_header("Location", "/ui/index.html")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return None
        path = allowed_path(self.path)
        if path is None:
            self.send_error(404)
            return None
        if path.endswith("/"):
            self.send_error(403, "Directory listing refused")
            return None
        if not path.lower().endswith(ALLOWED_SUFFIXES):
            self.send_error(404)
            return None
        real = os.path.realpath(os.path.join(REPO, path.lstrip("/")))
        if not any(real == root or real.startswith(root + os.sep) for root in ALLOWED_ROOTS):
            self.send_error(404)   # a symlink must not lead out of ui/ or shared/
            return None
        return path

    def do_GET(self):
        if self._route() is not None:
            super().do_GET()

    def do_HEAD(self):
        if self._route() is not None:
            super().do_HEAD()

    def list_directory(self, path):
        self.send_error(403, "Directory listing refused")
        return None

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()


def make_server(port=PORT):
    install_audit_hook()
    return http.server.ThreadingHTTPServer((HOST, port), Handler)


def main():
    server = make_server()
    print("Doublethink UI preview: http://%s:%d/ui/index.html (serves /ui/ and /shared/ only; Ctrl+C stops)"
          % (HOST, server.server_address[1]), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
