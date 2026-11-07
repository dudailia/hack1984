import http.server
import io
import json
import os
import tempfile
import threading
import unittest
import urllib.error
from unittest import mock

from planner import ollama, schema

MSGS = [{"role": "system", "content": "Today is 2026-11-07."}, {"role": "user", "content": "hi"}]
ENV = {"OLLAMA_MODEL": "qwen3:4b", "OLLAMA_PORT": 11434}


class FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


class Capture:
    def __init__(self, reply=None, raw=None, exc=None):
        self.reqs = []
        self.raw = raw if raw is not None else json.dumps(
            {"message": {"role": "assistant", "content": reply or '{"action":"done"}'}}).encode()
        self.exc = exc

    def __call__(self, req, timeout=None):
        self.reqs.append((req, timeout))
        if self.exc:
            raise self.exc
        return FakeResp(self.raw)


class TestBody(unittest.TestCase):
    def test_exact_shape(self):
        b = ollama.build_body("qwen3:8b", MSGS)
        self.assertEqual(b, {"model": "qwen3:8b", "think": False, "stream": False,
                             "format": schema.ACTION_JSON_SCHEMA, "options": {"temperature": 0},
                             "messages": MSGS})
        self.assertIs(b["think"], False)
        self.assertIs(b["stream"], False)

    def test_sent_bytes(self):
        cap = Capture()
        out = ollama.chat(MSGS, env=ENV, urlopen=cap)
        self.assertEqual(out, '{"action":"done"}')
        req, timeout = cap.reqs[0]
        self.assertEqual(req.full_url, "http://127.0.0.1:11434/api/chat")
        self.assertEqual(req.get_method(), "POST")
        self.assertEqual(req.get_header("Content-type"), "application/json")
        self.assertEqual(json.loads(req.data), ollama.build_body("qwen3:4b", MSGS))
        self.assertTrue(timeout and timeout > 0)
        # No auth header, ever.
        self.assertEqual({k.lower() for k, _ in req.header_items()}, {"content-type"})

    def test_custom_port(self):
        cap = Capture()
        ollama.chat(MSGS, env={"OLLAMA_MODEL": "m", "OLLAMA_PORT": 9999}, urlopen=cap)
        self.assertEqual(cap.reqs[0][0].full_url, "http://127.0.0.1:9999/api/chat")

    def test_errors(self):
        for cap in (Capture(raw=b"not json"), Capture(raw=b'{"message":{}}'), Capture(raw=b"[]"),
                    Capture(raw=b'{"message":{"content":5}}'),
                    Capture(exc=urllib.error.URLError("refused")), Capture(exc=OSError("x")),
                    Capture(exc=TimeoutError())):
            with self.assertRaises(ollama.OllamaError):
                ollama.chat(MSGS, env=ENV, urlopen=cap)


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        self.server.hits.append(self.path)
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if self.server.redirect_to:
            self.send_response(302)
            self.send_header("Location", self.server.redirect_to)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        body = json.dumps({"message": {"role": "assistant", "content": '{"action":"done"}'}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


class TestDefaultOpener(unittest.TestCase):
    """The real opener (not a mock): ignores proxy variables, refuses redirects. Loopback servers only."""

    def server(self, redirect_to=None):
        srv = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
        srv.hits, srv.redirect_to = [], redirect_to
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        return srv

    def env_for(self, srv):
        return {"OLLAMA_MODEL": "m", "OLLAMA_PORT": srv.server_address[1]}

    def test_ignores_proxy_variables(self):
        trap = self.server()
        target = self.server()
        proxy = "http://127.0.0.1:%d" % trap.server_address[1]
        with mock.patch.dict(os.environ, {"http_proxy": proxy, "HTTP_PROXY": proxy, "all_proxy": proxy,
                                          "no_proxy": "", "NO_PROXY": ""}):
            self.assertEqual(ollama.chat(MSGS, env=self.env_for(target)), '{"action":"done"}')
        self.assertEqual(target.hits, ["/api/chat"])
        self.assertEqual(trap.hits, [])

    def test_refuses_redirect(self):
        elsewhere = self.server()
        redirector = self.server(redirect_to="http://127.0.0.1:%d/api/chat" % elsewhere.server_address[1])
        with self.assertRaises(ollama.OllamaError):
            ollama.chat(MSGS, env=self.env_for(redirector))
        self.assertEqual(redirector.hits, ["/api/chat"])
        self.assertEqual(elsewhere.hits, [])


class TestEnv(unittest.TestCase):
    def write(self, text):
        fd, path = tempfile.mkstemp(suffix=".env")
        with os.fdopen(fd, "w") as f:
            f.write(text)
        self.addCleanup(os.remove, path)
        return path

    def test_only_two_keys(self):
        p = self.write("TAVILY_API_KEY=tvly-SECRETKEY\nANTHROPIC_API_KEY=sk-ant-SECRET\n"
                       "# comment\nOLLAMA_MODEL=qwen3:8b\nexport OLLAMA_PORT=\"11500\"\nGATE_PORT=8701\n")
        env = ollama.load_env(p)
        self.assertEqual(env, {"OLLAMA_MODEL": "qwen3:8b", "OLLAMA_PORT": 11500})
        self.assertNotIn("SECRET", repr(env))

    def test_default_port(self):
        self.assertEqual(ollama.load_env(self.write("OLLAMA_MODEL=qwen3:4b\n"))["OLLAMA_PORT"], 11434)

    def test_inline_comment(self):
        env = ollama.load_env(self.write("OLLAMA_MODEL=qwen3:4b  # dev\n"))
        self.assertEqual(env["OLLAMA_MODEL"], "qwen3:4b")

    def test_missing_model(self):
        with self.assertRaises(ValueError):
            ollama.load_env(self.write("OLLAMA_PORT=11434\n"))

    def test_refuses_cloud_models(self):
        for name in ("gpt-oss:120b-cloud", "qwen3-coder:480b-cloud", "deepseek:cloud", "model-CLOUD",
                     "x:Cloud", "kimi-k2:1t-cloud ", '"glm-4.6:cloud"'):
            with self.assertRaises(ValueError, msg=name):
                ollama.load_env(self.write("OLLAMA_MODEL=%s\n" % name))

    def test_local_models_allowed(self):
        for name in ("qwen3:8b", "qwen3:4b", "llama3.1:8b", "cloudy-llama:7b"):
            self.assertEqual(ollama.load_env(self.write("OLLAMA_MODEL=%s\n" % name))["OLLAMA_MODEL"], name)

    def test_chat_refuses_cloud_without_calling(self):
        cap = Capture()
        for name in ("gpt-oss:120b-cloud", "m:CLOUD"):
            with self.assertRaises(ollama.OllamaError):
                ollama.chat(MSGS, env={"OLLAMA_MODEL": name, "OLLAMA_PORT": 11434}, urlopen=cap)
        self.assertEqual(cap.reqs, [])

    def test_bad_port(self):
        for v in ("abc", "0", "70000", "-1"):
            with self.assertRaises(ValueError):
                ollama.load_env(self.write("OLLAMA_MODEL=m\nOLLAMA_PORT=%s\n" % v))

    def test_ignores_os_environ(self):
        p = self.write("OLLAMA_MODEL=from_file\n")
        with mock.patch.dict(os.environ, {"OLLAMA_MODEL": "from_environ", "OLLAMA_PORT": "1"}):
            self.assertEqual(ollama.load_env(p), {"OLLAMA_MODEL": "from_file", "OLLAMA_PORT": 11434})

    def test_source_never_reads_environ(self):
        with open(ollama.__file__, encoding="utf-8") as f:
            src = f.read()
        self.assertNotIn("environ", src)
        self.assertNotIn("getenv", src)
        self.assertNotIn("API_KEY", src)

    def test_host_is_loopback_constant(self):
        self.assertEqual(ollama.OLLAMA_HOST, "127.0.0.1")


if __name__ == "__main__":
    unittest.main()
