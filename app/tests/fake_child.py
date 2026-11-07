"""Stand-in child process for the launcher test: serves GET <health path> on 127.0.0.1:<port>.

    python3 fake_child.py PORT HEALTH_PATH [--never-healthy]
"""
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer


def main(argv):
    port, health, never = int(argv[0]), argv[1], "--never-healthy" in argv

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            ok = self.path == health and not never
            self.send_response(200 if ok else 503)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"ok" if ok else b"no")

    HTTPServer(("127.0.0.1", port), H).serve_forever()


if __name__ == "__main__":
    main(sys.argv[1:])
