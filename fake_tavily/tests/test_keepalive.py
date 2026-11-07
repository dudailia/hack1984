"""Several requests on one connection: each is answered, logged with its own path, and routed to its own handler.

Background: a report that the stand-in logged the Gate's second /search as a different path. The Gate opens one
connection per request and is unaffected, but a keep-alive client (two /search on one connection) had its second
request silently dropped, and the log line is the request line read from the socket. These tests pin:
- two /search on one connection: two answers, two log lines saying /search, do_search called twice;
- an error path that does not read the body closes the connection, so body bytes are never parsed as a request.
"""
import io
import json
import re
import socket
import struct
import threading
import time
import unittest
from unittest import mock

from fake_tavily import server as fake_server

LOG = re.compile(r'"(GET|POST) (\S+) HTTP/1\.[01]" (\d{3})')


def http_request(path, body, extra_headers=""):
    data = json.dumps(body).encode() if not isinstance(body, bytes) else body
    return (b"POST %s HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Type: application/json\r\n%sContent-Length: %d\r\n\r\n"
            % (path.encode(), extra_headers.encode(), len(data))) + data


def read_responses(sock, n, timeout=3):
    """Read up to n HTTP responses from one socket. Returns [(status, headers, body_json)]; stops on close."""
    sock.settimeout(timeout)
    f = sock.makefile("rb")
    out = []
    try:
        for _ in range(n):
            status_line = f.readline()
            if not status_line:
                break
            status = int(status_line.split()[1])
            headers = {}
            while True:
                line = f.readline().decode("latin-1").rstrip("\r\n")
                if not line:
                    break
                k, v = line.split(":", 1)
                headers[k.strip().lower()] = v.strip()
            body = f.read(int(headers.get("content-length", "0")))
            out.append((status, headers, json.loads(body) if body else None))
    except (socket.timeout, ConnectionError):
        pass
    return out


def closed_by_server(sock, timeout=3):
    sock.settimeout(timeout)
    try:
        return sock.recv(1) == b""
    except (socket.timeout, ConnectionError):
        return False


class KeepAliveTest(unittest.TestCase):
    def setUp(self):
        self.srv = fake_server.make_server(port=0, verbose=True)
        threading.Thread(target=self.srv.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)
        self.port = self.srv.server_address[1]
        self.err = io.StringIO()
        p = mock.patch("sys.stderr", self.err)
        p.start()
        self.addCleanup(p.stop)
        self.calls = []
        real_search, real_extract = fake_server.do_search, fake_server.do_extract

        def spy(name, fn):
            def wrapped(srv, body):
                self.calls.append((name, body.get("query") or body.get("urls")))
                return fn(srv, body)
            return wrapped

        p2 = mock.patch.dict(fake_server.ROUTES, {"/search": spy("search", real_search),
                                                   "/extract": spy("extract", real_extract)})
        p2.start()
        self.addCleanup(p2.stop)

    def logged(self):
        return [LOG.search(line).groups() for line in self.err.getvalue().splitlines() if LOG.search(line)]

    def connect(self):
        s = socket.create_connection(("127.0.0.1", self.port), timeout=5)
        self.addCleanup(s.close)
        return s

    def test_two_searches_on_one_connection(self):
        s = self.connect()
        s.sendall(http_request("/search", {"query": "payments sector growth 2025"}))
        first = read_responses(s, 1)
        s.sendall(http_request("/search", {"query": "listed payments EV/revenue"}))
        second = read_responses(s, 1)
        self.assertEqual([r[0] for r in first + second], [200, 200])
        self.assertEqual([r[2]["query"] for r in first + second],
                         ["payments sector growth 2025", "listed payments EV/revenue"])
        self.assertTrue(all("results" in r[2] for r in first + second), "both answered by the search handler")
        self.assertEqual(self.logged(), [("POST", "/search", "200"), ("POST", "/search", "200")])
        self.assertEqual(self.calls, [("search", "payments sector growth 2025"),
                                      ("search", "listed payments EV/revenue")])

    def test_two_pipelined_searches(self):
        s = self.connect()
        s.sendall(http_request("/search", {"query": "a growth"}) + http_request("/search", {"query": "b growth"}))
        resp = read_responses(s, 2)
        self.assertEqual([(r[0], r[2]["query"]) for r in resp], [(200, "a growth"), (200, "b growth")])
        self.assertEqual(self.logged(), [("POST", "/search", "200"), ("POST", "/search", "200")])
        self.assertEqual([c[0] for c in self.calls], ["search", "search"])

    def test_search_then_extract_on_one_connection_route_separately(self):
        s = self.connect()
        s.sendall(http_request("/search", {"query": "payments growth"})
                  + http_request("/extract", {"urls": ["https://research.example.com/payments-outlook-2030"]}))
        resp = read_responses(s, 2)
        self.assertEqual([r[0] for r in resp], [200, 200])
        self.assertIn("results", resp[1][2])
        self.assertIn("failed_results", resp[1][2])
        self.assertEqual(self.logged(), [("POST", "/search", "200"), ("POST", "/extract", "200")])
        self.assertEqual([c[0] for c in self.calls], ["search", "extract"])

    def test_unread_body_is_never_parsed_as_a_request(self):
        # An unknown route returns before reading the body. The body here is itself an HTTP request; it must not
        # be answered, routed or logged as one.
        smuggled = http_request("/deep-research", {"query": "x"})
        s = self.connect()
        s.sendall(http_request("/nope", smuggled))
        resp = read_responses(s, 2)
        self.assertEqual([r[0] for r in resp], [404])
        self.assertEqual(resp[0][1].get("connection"), "close")
        self.assertTrue(closed_by_server(s))
        self.assertEqual(self.logged(), [("POST", "/nope", "404")])
        self.assertEqual(self.calls, [])

    def test_oversized_body_closes(self):
        s = self.connect()
        head = (b"POST /search HTTP/1.1\r\nHost: x\r\nContent-Length: %d\r\n\r\n" % (fake_server.MAX_BODY + 1))
        s.sendall(head + http_request("/search", {"query": "smuggled"}))
        resp = read_responses(s, 2)
        self.assertEqual([r[0] for r in resp], [413])
        self.assertTrue(closed_by_server(s))
        self.assertEqual(self.calls, [])

    def test_bad_content_length_closes(self):
        s = self.connect()
        s.sendall(b"POST /search HTTP/1.1\r\nHost: x\r\nContent-Length: abc\r\n\r\n"
                  + http_request("/search", {"query": "smuggled"}))
        resp = read_responses(s, 2)
        self.assertEqual([r[0] for r in resp], [400])
        self.assertTrue(closed_by_server(s))
        self.assertEqual(self.calls, [])

    def test_connection_close_is_honoured(self):
        s = self.connect()
        s.sendall(http_request("/search", {"query": "payments growth"}, "Connection: close\r\n"))
        self.assertEqual([r[0] for r in read_responses(s, 1)], [200])
        self.assertTrue(closed_by_server(s))

    def test_one_connection_per_request_like_the_gate(self):
        for q in ("payments growth", "payments peers EV/revenue"):
            s = socket.create_connection(("127.0.0.1", self.port), timeout=5)
            s.sendall(http_request("/search", {"query": q}, "Connection: close\r\n"))
            self.assertEqual(read_responses(s, 1)[0][2]["query"], q)
            s.close()
        self.assertEqual(self.logged(), [("POST", "/search", "200"), ("POST", "/search", "200")])
        self.assertEqual([c[0] for c in self.calls], ["search", "search"])


class ClientResetTest(unittest.TestCase):
    """A client that resets a kept-alive connection (common after reading one response) is not an error: no
    traceback on stderr, and the server keeps serving."""

    def test_reset_after_a_response_is_quiet(self):
        srv = fake_server.make_server(port=0)
        threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        err = io.StringIO()
        with mock.patch("sys.stderr", err):
            for _ in range(3):
                s = socket.create_connection(("127.0.0.1", srv.server_address[1]), timeout=5)
                s.sendall(http_request("/search", {"query": "payments growth"}))
                s.recv(64)  # part of the response only
                s.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))  # close with RST
                s.close()
            s = socket.create_connection(("127.0.0.1", srv.server_address[1]), timeout=5)
            s.sendall(http_request("/search", {"query": "payments growth"}, "Connection: close\r\n"))
            self.assertEqual(read_responses(s, 1)[0][0], 200)
            s.close()
            time.sleep(0.2)
        self.assertNotIn("Traceback", err.getvalue())
        self.assertNotIn("ConnectionResetError", err.getvalue())


if __name__ == "__main__":
    unittest.main()
