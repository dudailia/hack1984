"""The page and workspace.html contact only 127.0.0.1 (full replay in both views and themes): runs ui/check_network.py into a temp file."""
import contextlib
import io
import os
import tempfile
import unittest

from ui import check_network
from ui.tests.test_ui_browser import BROWSER


@unittest.skipUnless(BROWSER, "no Edge or Chrome found; set DT_BROWSER to run the network check")
class NetworkCheck(unittest.TestCase):
    def test_full_replay_is_loopback_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "network-replay.md")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = check_network.main(out=out)
            with open(out, encoding="utf-8") as f:
                report = f.read()
        self.assertEqual(code, 0, buf.getvalue() + "\n" + report)
        self.assertIn("Verdict: PASS", report)
        self.assertIn("Replay reached the end: yes", report)
        self.assertNotIn("Replay reached the end: no", report)


if __name__ == "__main__":
    unittest.main()
