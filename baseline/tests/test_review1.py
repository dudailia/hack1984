"""Review 1 (notes/REVIEW_1.md): findings in baseline/. Tests named after a finding failed on the
code before the review; tests ending in _ok or _still_ok pin legitimate input that must stay accepted."""
import os
import subprocess
import sys
import textwrap
import unittest

from baseline import config, ollama

REPO = config.REPO

# Runs main() in a child process (audit hooks cannot be removed) with run() replaced by a probe that tries
# non-loopback DNS and connect, a loopback connect, and a subprocess. 192.0.2.1 is TEST-NET-1 (never routed).
PROBE = textwrap.dedent("""
    import socket, subprocess, sys

    def probe(*a, **kw):
        out = []
        try:
            socket.getaddrinfo("api.tavily.com", 443)
            out.append("dns:open")
        except PermissionError:
            out.append("dns:blocked")
        except OSError:
            out.append("dns:open")
        s = socket.socket()
        s.settimeout(0.2)
        try:
            s.connect(("192.0.2.1", 9))
            out.append("connect:open")
        except PermissionError:
            out.append("connect:blocked")
        except OSError:
            out.append("connect:open")
        finally:
            s.close()
        srv = socket.socket()
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        c = socket.socket()
        try:
            c.connect(srv.getsockname())
            out.append("loopback:open")
        except PermissionError:
            out.append("loopback:blocked")
        finally:
            c.close()
            srv.close()
        try:
            subprocess.run(["true"])
            out.append("subprocess:open")
        except PermissionError:
            out.append("subprocess:blocked")
        sys.stderr.write("PROBE " + " ".join(out) + "\\n")
        return %s
""")


def run_child(code):
    p = subprocess.run([sys.executable, "-c", code], cwd=REPO, capture_output=True, text=True, timeout=30,
                       env=dict(os.environ, PYTHONPATH=REPO))
    for line in p.stderr.splitlines():
        if line.startswith("PROBE "):
            return line.split()[1:]
    raise AssertionError("probe did not run: %s" % p.stderr[-2000:])


class R1LoopbackGuard(unittest.TestCase):
    """R1-10: baseline.agent.main runs with no loopback-only audit hook (invariant 1)."""

    def test_agent_main_installs_the_guard(self):
        code = PROBE % '{"steps": []}' + textwrap.dedent("""
            import baseline.agent as a
            a.load_demo_spec = lambda: {}
            a.run = probe
            a.main(["--mode", "single_agent"])
        """)
        self.assertEqual(run_child(code), ["dns:blocked", "connect:blocked", "loopback:open", "subprocess:blocked"])


class R1OllamaCloud(unittest.TestCase):
    """R1-09: an Ollama cloud model name sends the memo to ollama.com, outside the Gate (invariants 1 and 5)."""

    CLOUD = ("gpt-oss:120b-cloud", "qwen3-coder:480b-cloud", "deepseek-v3.1:671b-cloud", "kimi-k2:1t-cloud",
             "glm-4.6:cloud", "GPT-OSS:120B-CLOUD", " gpt-oss:20b-cloud ")

    def test_config_refuses_cloud_models(self):
        for name in self.CLOUD:
            with self.assertRaises(ValueError, msg=name):
                config.ollama_model(env={"OLLAMA_MODEL": name}, env_file=os.devnull)

    def test_client_refuses_cloud_models(self):
        for name in self.CLOUD:
            with self.assertRaises(ValueError, msg=name):
                ollama.OllamaClient(11434, name)

    def test_client_refuses_registry_paths(self):
        for name in ("registry.example.com/x/qwen3:8b", "hf.co/someone/model"):
            with self.assertRaises(ValueError, msg=name):
                ollama.OllamaClient(11434, name)

    def test_local_models_ok(self):
        for name in ("qwen3:8b", "qwen3:4b", "llama3.1:8b"):
            self.assertEqual(config.ollama_model(env={"OLLAMA_MODEL": name}, env_file=os.devnull), name)
            ollama.OllamaClient(11434, name)


if __name__ == "__main__":
    unittest.main()
