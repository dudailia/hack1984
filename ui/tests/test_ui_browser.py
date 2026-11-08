"""Browser tests for the page: the Outbound panel and the four fixes on main, in headless Edge or Chrome.

ui/tests/ui.test.html loads ui/outbound.js and the real page (ui/index.html) in an iframe at many replay times, runs
the checks in the browser and writes PASS / FAIL lines into #result. This test serves it with ui/preview.py on an
ephemeral loopback port, dumps the DOM with the browser in headless mode, and asserts there is no FAIL.

Every non-loopback host is mapped to NOTFOUND for the browser, so the test itself cannot reach the network.
Skipped, with a reason, when no Edge or Chrome is installed (set DT_BROWSER to a browser executable to override).
"""
import glob
import os
import re
import shutil
import subprocess
import tempfile
import threading
import unittest

from ui import preview

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Every replay file in shared/fixtures/ (demo_events.jsonl and any other scenario's *events*.jsonl).
EVENT_FILES = sorted(os.path.basename(p) for p in glob.glob(os.path.join(ROOT, "shared", "fixtures", "*events*.jsonl"))
                     if re.fullmatch(r"[a-z0-9_-]+\.jsonl", os.path.basename(p)))

CANDIDATES = (
    os.environ.get("DT_BROWSER", ""),
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    shutil.which("google-chrome") or "",
    shutil.which("chromium") or "",
    shutil.which("msedge") or "",
)
BROWSER = next((p for p in CANDIDATES if p and os.path.isfile(p)), None)

# Flags shared with ui/check_network.py: no background traffic, and only loopback resolves.
QUIET_FLAGS = [
    "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
    "--disable-background-networking", "--disable-component-update", "--disable-sync",
    "--disable-domain-reliability", "--disable-client-side-phishing-detection", "--no-pings",
    "--metrics-recording-only", "--disable-quic",
    "--disable-features=OptimizationHints,MediaRouter,Translate,AutofillServerCommunication",
    "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1",
]


def dump_dom(url, budget_ms, timeout_s=300):
    profile = tempfile.mkdtemp(prefix="dt-ui-test-")
    try:
        cmd = [BROWSER, *QUIET_FLAGS, f"--user-data-dir={profile}", "--window-size=1320,900",
               f"--virtual-time-budget={budget_ms}", "--dump-dom", url]
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout_s)
        return res.stdout
    finally:
        shutil.rmtree(profile, ignore_errors=True)


@unittest.skipUnless(BROWSER, "no Edge or Chrome found; set DT_BROWSER to run the browser tests")
class BrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = preview.make_server(port=0)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_page_in_browser(self):
        self.assertIn("demo_events.jsonl", EVENT_FILES)
        for name in EVENT_FILES:
            with self.subTest(events=name):
                query = "" if name == "demo_events.jsonl" else f"?events={name}"
                html = dump_dom(f"http://127.0.0.1:{self.port}/ui/tests/ui.test.html{query}", budget_ms=600000)
                m = re.search(r'<pre id="result">(.*?)</pre>', html, re.S)
                self.assertIsNotNone(m, "no #result in the dumped DOM")
                lines = [ln for ln in m.group(1).splitlines() if ln.strip()]
                fails = [ln for ln in lines if ln.startswith("FAIL")]
                done = [ln for ln in lines if ln.startswith("DONE")]
                self.assertTrue(done, "harness did not finish:\n" + "\n".join(lines[-15:]))
                self.assertEqual(fails, [], "\n".join(fails))
                passes = [ln for ln in lines if ln.startswith("PASS")]
                self.assertGreaterEqual(len(passes), 30, "too few checks ran:\n" + "\n".join(lines))

if __name__ == "__main__":
    unittest.main()
