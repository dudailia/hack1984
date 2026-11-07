import contextlib
import io
import sys
import types
import unittest
from unittest import mock

from gate import checks_bridge, checks_stub


class TestStub(unittest.TestCase):
    def test_allows_and_warns_every_call(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            r1 = checks_stub.run_all("{}", {}, "search")
            r2 = checks_stub.run_all("{}", {}, "search")
        self.assertEqual(r1, {"decision": "allow", "rule": None, "detail": None})
        self.assertEqual(r1, r2)
        self.assertEqual(err.getvalue().count("CHECKS STUB"), 2)

    def test_memo_tokens_stub(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(checks_stub.memo_tokens("anything", ["payments"]), [])


class TestBridge(unittest.TestCase):
    def test_stub_when_checks_absent(self):
        with mock.patch("importlib.util.find_spec", return_value=None), \
                contextlib.redirect_stderr(io.StringIO()) as err:
            run_all, memo_tokens, name = checks_bridge.load()
        self.assertIs(run_all, checks_stub.run_all)
        self.assertEqual(name, "stub")
        self.assertIn("CHECKS STUB", err.getvalue())

    def test_real_checks_used(self):
        fake = types.ModuleType("checks")
        fake.run_all = lambda p, s, k: {"decision": "block", "rule": "x", "detail": None}
        fake.memo_tokens = lambda m, t: ["t"]
        with mock.patch("importlib.util.find_spec", return_value=object()), \
                mock.patch.dict(sys.modules, {"checks": fake}):
            run_all, memo_tokens, name = checks_bridge.load()
        self.assertIs(run_all, fake.run_all)
        self.assertIs(memo_tokens, fake.memo_tokens)
        self.assertEqual(name, "checks")

    def test_real_checks_without_memo_tokens_warns(self):
        fake = types.ModuleType("checks")
        fake.run_all = lambda p, s, k: None
        with mock.patch("importlib.util.find_spec", return_value=object()), \
                mock.patch.dict(sys.modules, {"checks": fake}), \
                contextlib.redirect_stderr(io.StringIO()) as err:
            run_all, memo_tokens, name = checks_bridge.load()
        self.assertIs(memo_tokens, checks_stub.memo_tokens)
        self.assertIn("memo_tokens", err.getvalue())

    def test_broken_checks_raises(self):
        def boom(name):
            raise SyntaxError("broken checks")

        with mock.patch("importlib.util.find_spec", return_value=object()), \
                mock.patch("importlib.import_module", side_effect=boom), \
                mock.patch.dict(sys.modules):
            sys.modules.pop("checks", None)
            with self.assertRaises(SyntaxError):
                checks_bridge.load()

    def test_checks_without_run_all_raises(self):
        fake = types.ModuleType("checks")
        with mock.patch("importlib.util.find_spec", return_value=object()), \
                mock.patch.dict(sys.modules, {"checks": fake}):
            with self.assertRaises(RuntimeError):
                checks_bridge.load()


if __name__ == "__main__":
    unittest.main()
