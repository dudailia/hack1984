"""Review 1 (notes/REVIEW_1.md): findings in fake_tavily/. Tests named after a finding failed on the
code before the review; tests ending in _ok or _still_ok pin legitimate input that must stay accepted."""
import textwrap
import unittest

from baseline.tests.test_review1 import PROBE, run_child


class R1LoopbackGuard(unittest.TestCase):
    """R1-10: fake_tavily.server.main runs with no loopback-only audit hook (invariant 1)."""

    def test_server_main_installs_the_guard(self):
        code = PROBE % "None" + textwrap.dedent("""
            import fake_tavily.server as s

            class Srv:
                server_address = ("127.0.0.1", 0)
                def serve_forever(self):
                    probe()
                def server_close(self):
                    pass

            s.make_server = lambda **kw: Srv()
            s.main([])
        """)
        self.assertEqual(run_child(code), ["dns:blocked", "connect:blocked", "loopback:open", "subprocess:blocked"])

    def test_server_cannot_bind_beyond_loopback_once_guarded(self):
        code = textwrap.dedent("""
            import socket, sys
            from baseline import netguard
            netguard.install()
            s = socket.socket()
            try:
                s.bind(("0.0.0.0", 0))
                sys.stderr.write("PROBE bind:open\\n")
            except PermissionError:
                sys.stderr.write("PROBE bind:blocked\\n")
        """)
        self.assertEqual(run_child(code), ["bind:blocked"])


if __name__ == "__main__":
    unittest.main()
