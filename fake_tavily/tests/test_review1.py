"""Review 1 (notes/REVIEW_1.md): findings in fake_tavily/. Tests named after a finding failed on the
code before the review; tests ending in _ok or _still_ok pin legitimate input that must stay accepted."""
import unittest

from baseline.tests.test_review1 import assert_guarded, probe_code, run_child


class R1LoopbackGuard(unittest.TestCase):
    """R1-10: fake_tavily.server.main runs with no loopback-only audit hook (invariant 1). Now shared.guard,
    "fake_tavily", installed after the server socket is bound (so --port 0 works)."""

    def test_server_main_installs_the_guard_after_binding(self):
        code = probe_code("None", """
            import fake_tavily.server as s
            real_make_server = s.make_server

            class Srv:
                def __init__(self, **kw):
                    self.real = real_make_server(**kw)  # binds before the guard
                    self.server_address = self.real.server_address
                def serve_forever(self):
                    probe()
                def server_close(self):
                    self.real.server_close()

            s.make_server = lambda **kw: Srv(**kw)
            s.main(["--port", "0"])
        """)
        # the stand-in connects to nothing, not even the Gate's port
        assert_guarded(self, run_child(code), "fake_tavily", "blocked")


if __name__ == "__main__":
    unittest.main()
