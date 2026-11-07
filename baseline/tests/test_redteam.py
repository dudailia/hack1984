"""redteam: skeleton only. It parses its arguments and never opens the attack file before checks-frozen."""
import builtins
import unittest
from unittest import mock

from baseline import redteam


class RedteamSkeletonTest(unittest.TestCase):
    def test_args(self):
        a = redteam.parse_args(["--attacks", "ATTACKS.md", "--modes", "all", "--out", "out.json"])
        self.assertEqual(a.attacks, "ATTACKS.md")
        self.assertEqual(a.modes, ["single_agent", "compromised", "two_minds", "doublethink"])
        self.assertEqual(a.out, "out.json")
        a = redteam.parse_args(["--attacks", "x", "--modes", "compromised,doublethink", "--out", "o"])
        self.assertEqual(a.modes, ["compromised", "doublethink"])

    def test_bad_mode_rejected(self):
        with self.assertRaises(SystemExit), mock.patch("sys.stderr"):
            redteam.parse_args(["--attacks", "x", "--modes", "everything", "--out", "o"])

    def test_required(self):
        with self.assertRaises(SystemExit), mock.patch("sys.stderr"):
            redteam.parse_args(["--modes", "all", "--out", "o"])

    def test_main_not_implemented_and_never_opens_attack_file(self):
        real_open = builtins.open
        opened = []

        def spy(file, *a, **kw):
            opened.append(str(file))
            return real_open(file, *a, **kw)

        with mock.patch("builtins.open", spy), mock.patch("io.open", spy):
            with self.assertRaises(NotImplementedError):
                redteam.main(["--attacks", "/nonexistent/ATTACKS.md", "--modes", "all", "--out", "/nonexistent/o"])
        self.assertEqual(opened, [])


if __name__ == "__main__":
    unittest.main()
