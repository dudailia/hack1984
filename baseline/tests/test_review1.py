"""Review 1 (notes/REVIEW_1.md): findings in baseline/. Tests named after a finding failed on the
code before the review; tests ending in _ok or _still_ok pin legitimate input that must stay accepted."""
import os
import subprocess
import sys
import textwrap
import unittest

from baseline import config, ollama

REPO = config.REPO

# Runs an entry point's main() in a child process (audit hooks cannot be removed) with its work replaced by a probe.
# shared.guard.install_loopback_guard is wrapped to record the role and to read a temp .env whose GATE_PORT is a
# loopback listener opened before the guard; another listener is a loopback port no role may reach. The probe tries
# non-loopback DNS and connect (192.0.2.1 is TEST-NET-1, never routed), GATE_PORT, the other loopback port, a
# bind on 0.0.0.0 and a subprocess.
PROBE = textwrap.dedent("""
    import os, socket, subprocess, sys, tempfile
    import shared.guard as _guard

    _allowed, _other = socket.socket(), socket.socket()
    for _s in (_allowed, _other):
        _s.bind(("127.0.0.1", 0))
        _s.listen(4)
    _env = os.path.join(tempfile.mkdtemp(), ".env")
    with open(_env, "w") as _f:
        _f.write("GATE_PORT=%d\\nOLLAMA_PORT=1\\nAPP_PORT=2\\nFAKE_TAVILY_PORT=3\\n" % _allowed.getsockname()[1])
    ROLES = []
    _install = _guard.install_loopback_guard

    def _recording_install(role, env_path=None):
        ROLES.append(role)
        return _install(role, env_path=_env)

    _guard.install_loopback_guard = _recording_install

    def _try(out, name, fn):
        try:
            fn()
            out.append(name + ":open")
        except PermissionError:
            out.append(name + ":blocked")
        except OSError:
            out.append(name + ":open")

    def _connect(host, port):
        c = socket.socket()
        c.settimeout(0.2)
        try:
            c.connect((host, port))
        finally:
            c.close()

    def _bind_any():
        b = socket.socket()
        try:
            b.bind(("0.0.0.0", 0))
        finally:
            b.close()

    def probe(*a, **kw):
        out = ["role:" + ",".join(ROLES)]
        _try(out, "dns", lambda: socket.getaddrinfo("api.tavily.com", 443))
        _try(out, "connect", lambda: _connect("192.0.2.1", 9))
        _try(out, "gate_port", lambda: _connect("127.0.0.1", _allowed.getsockname()[1]))
        _try(out, "other_port", lambda: _connect("127.0.0.1", _other.getsockname()[1]))
        _try(out, "bind_any", _bind_any)
        _try(out, "subprocess", lambda: subprocess.run(["true"]))
        out.extend(EXTRA_PROBES())
        sys.stderr.write("PROBE " + " ".join(out) + "\\n")
        return RETURN_VALUE

    def EXTRA_PROBES():
        return []
""")
BLOCKED = ["dns:blocked", "connect:blocked", "other_port:blocked", "bind_any:blocked", "subprocess:blocked"]


def probe_code(return_value, body):
    return PROBE.replace("RETURN_VALUE", return_value) + textwrap.dedent(body)


def run_child(code):
    p = subprocess.run([sys.executable, "-c", code], cwd=REPO, capture_output=True, text=True, timeout=60,
                       env=dict(os.environ, PYTHONPATH=REPO))
    for line in p.stderr.splitlines():
        if line.startswith("PROBE "):
            return line.split()[1:]
    raise AssertionError("probe did not run: %s" % p.stderr[-2000:])


def assert_guarded(test, result, role, gate_port):
    """The role was installed once, everything in BLOCKED is blocked, and GATE_PORT is open or blocked as given."""
    test.assertEqual(result[0], "role:" + role)
    for item in BLOCKED:
        test.assertIn(item, result)
    test.assertIn("gate_port:" + gate_port, result)


class R1LoopbackGuard(unittest.TestCase):
    """R1-10: baseline.agent.main runs with no loopback-only audit hook (invariant 1). Now shared.guard, "baseline"."""

    def test_agent_main_installs_the_guard(self):
        code = probe_code('{"steps": []}', """
            import baseline.agent as a
            a.load_demo_spec = lambda: {}
            a.run = probe
            a.main(["--mode", "single_agent"])
        """)
        assert_guarded(self, run_child(code), "baseline", "open")

    def test_redteam_main_installs_the_guard_before_anything_else(self):
        code = probe_code('{"modes": {}, "judge": "probe", "attacks": []}', """
            import baseline.redteam as r
            r.run_redteam = probe
            r.main(["--attacks", "x.md", "--modes", "compromised", "--out", "/nonexistent/x.json"])
        """)
        assert_guarded(self, run_child(code), "baseline", "open")

    def test_redteam_reads_git_facts_under_the_guard(self):
        code = probe_code("None", """
            import baseline.redteam as r, baseline.judge as j

            def EXTRA_PROBES():
                return ["commit:%s" % (r._commit() != "unknown"), "frozen:%s" % r.checks_frozen(),
                        "matches:%s" % (j._matches_frozen() is not None)]

            r.run_redteam = lambda *a, **kw: (probe(), {"modes": {}, "judge": "probe", "attacks": []})[1]
            r.main(["--attacks", "x.md", "--modes", "compromised", "--out", "/nonexistent/x.json"])
        """)
        out = run_child(code)
        assert_guarded(self, out, "baseline", "open")
        has_tag = subprocess.run(["git", "-C", REPO, "rev-parse", "-q", "--verify", "refs/tags/checks-frozen"],
                                 capture_output=True).returncode == 0
        self.assertIn("commit:True", out)
        self.assertIn("frozen:%s" % has_tag, out)
        self.assertIn("matches:%s" % has_tag, out)


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
