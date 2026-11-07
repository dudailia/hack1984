"""Launcher: starts children, waits for health, stops them on exit; a child that never gets healthy is an error."""
import socket
import sys
import time
import unittest

from app import run
from app.tests.helpers import FAKE_CHILD


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def alive(proc):
    return proc.poll() is None


class LauncherTest(unittest.TestCase):
    def test_start_wait_stop(self):
        p1, p2 = free_port(), free_port()
        kids = run.Children([("gate", [sys.executable, FAKE_CHILD, str(p1), "/v1/health"], p1, "/v1/health"),
                             ("fake_tavily", [sys.executable, FAKE_CHILD, str(p2), "/health"], p2, "/health")])
        self.addCleanup(kids.stop)
        kids.start(timeout=10)
        procs = [p for _n, p in kids.procs]
        self.assertTrue(all(alive(p) for p in procs))
        self.assertEqual(run.http_status(p1, "/v1/health"), 200)
        kids.stop()
        self.assertFalse(any(alive(p) for p in procs))
        kids.stop()  # idempotent

    def test_unhealthy_child_fails_and_stops_others(self):
        p1, p2 = free_port(), free_port()
        kids = run.Children([("gate", [sys.executable, FAKE_CHILD, str(p1), "/v1/health"], p1, "/v1/health"),
                             ("fake_tavily", [sys.executable, FAKE_CHILD, str(p2), "/health", "--never-healthy"], p2,
                              "/health")])
        self.addCleanup(kids.stop)
        t0 = time.monotonic()
        with self.assertRaises(RuntimeError) as cm:
            kids.start(timeout=1.5)
        self.assertIn("fake_tavily", str(cm.exception))
        self.assertLess(time.monotonic() - t0, 8)
        self.assertFalse(any(alive(p) for _n, p in kids.procs))

    def test_default_children(self):
        specs = run.default_children(8701, 8702)
        self.assertEqual([s[0] for s in specs], ["gate", "fake_tavily"])
        self.assertEqual(specs[0][1][1:], ["-m", "gate.server"])
        self.assertEqual(specs[1][1][1:], ["-m", "fake_tavily.server"])
        self.assertEqual((specs[0][2], specs[0][3]), (8701, "/v1/health"))
        self.assertEqual((specs[1][2], specs[1][3]), (8702, "/health"))

    def test_guard_lookup(self):
        fn = run.load_guard()
        self.assertTrue(fn is None or callable(fn))


if __name__ == "__main__":
    unittest.main()
