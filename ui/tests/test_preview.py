"""ui/preview.py serves only /ui/ and /shared/ on loopback, and refuses every other path."""
import http.client
import threading
import unittest

from ui import preview


class PreviewServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = preview.make_server(port=0)   # ephemeral port for tests
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def request(self, path, method="GET"):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            conn.putrequest(method, path, skip_accept_encoding=True)   # raw path, no client-side normalising
            conn.endheaders()
            resp = conn.getresponse()
            resp.read()
            return resp
        finally:
            conn.close()

    def test_binds_loopback_only(self):
        self.assertEqual(self.server.server_address[0], "127.0.0.1")
        self.assertEqual(preview.HOST, "127.0.0.1")
        self.assertEqual(preview.PORT, 8703)

    def test_serves_the_page(self):
        resp = self.request("/ui/index.html")
        self.assertEqual(resp.status, 200)
        self.assertEqual(resp.getheader("Cache-Control"), "no-store")
        self.assertEqual(resp.getheader("X-Content-Type-Options"), "nosniff")

    def test_serves_shared_fixtures(self):
        self.assertEqual(self.request("/shared/fixtures/demo_events.jsonl").status, 200)

    def test_head_allowed(self):
        self.assertEqual(self.request("/ui/app.js", method="HEAD").status, 200)

    def test_root_redirects_to_page(self):
        resp = self.request("/")
        self.assertEqual(resp.status, 302)
        self.assertEqual(resp.getheader("Location"), "/ui/index.html")

    def test_refuses_other_folders(self):
        for path in ("/gate/server.py", "/notes/SPEC.md", "/CLAUDE.md", "/app/run.py", "/ledger/doublethink.db"):
            with self.subTest(path=path):
                self.assertEqual(self.request(path).status, 404)

    def test_refuses_traversal(self):
        for path in ("/ui/../gate/server.py", "/ui/%2e%2e/gate/server.py", "/ui/..%2fgate/server.py",
                     "/shared/../CLAUDE.md", "/ui//index.html", "/ui/./index.html", "/ui/%5c..%5cCLAUDE.md",
                     "/ui/index.html%00"):
            with self.subTest(path=path):
                self.assertEqual(self.request(path).status, 404)

    def test_refuses_dotfiles(self):
        for path in ("/.env", "/.git/config", "/shared/.env", "/ui/.hidden"):
            with self.subTest(path=path):
                self.assertEqual(self.request(path).status, 404)

    def test_refuses_directory_listing(self):
        for path in ("/ui/", "/shared/", "/shared/fixtures/"):
            with self.subTest(path=path):
                self.assertEqual(self.request(path).status, 403)

    def test_refuses_writes(self):
        self.assertEqual(self.request("/ui/index.html", method="POST").status, 501)

    def test_python_files_in_ui_are_not_served(self):
        # The server's own source and tests are not part of the page.
        for path in ("/ui/preview.py", "/ui/tests/test_preview.py", "/ui/__init__.py"):
            with self.subTest(path=path):
                self.assertEqual(self.request(path).status, 404)


class AuditHookTest(unittest.TestCase):
    def test_hook_refuses_non_loopback(self):
        with self.assertRaises(preview.NetworkRefused):
            preview._audit("socket.connect", (None, ("93.184.216.34", 443)))
        with self.assertRaises(preview.NetworkRefused):
            preview._audit("socket.getaddrinfo", ("example.com", 443))

    def test_hook_allows_loopback(self):
        preview._audit("socket.connect", (None, ("127.0.0.1", 8703)))
        preview._audit("socket.getaddrinfo", ("127.0.0.1", 8703))


if __name__ == "__main__":
    unittest.main()
