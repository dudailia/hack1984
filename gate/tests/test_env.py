import os
import tempfile
import unittest

from gate import env


class TestEnv(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, ".env")
        with open(self.path, "w") as f:
            f.write("# comment\n\nTAVILY_API_KEY=tvly-SECRETVALUE\nGATE_PORT=8701\n"
                    "export FAKE_TAVILY_PORT = \"8702\"\nQUOTED='a b'\nTRAIL=x # note\n")

    def tearDown(self):
        self.dir.cleanup()

    def test_parse(self):
        e = env.load(self.path)
        self.assertEqual(e.get("GATE_PORT"), "8701")
        self.assertEqual(e.get("FAKE_TAVILY_PORT"), "8702")
        self.assertEqual(e.get("QUOTED"), "a b")
        self.assertEqual(e.get("TRAIL"), "x")
        self.assertEqual(e.port("GATE_PORT"), 8701)

    def test_missing_key_names_key_not_values(self):
        e = env.load(self.path)
        with self.assertRaises(KeyError) as cm:
            e.require("ANTHROPIC_API_KEY")
        self.assertIn("ANTHROPIC_API_KEY", str(cm.exception))
        self.assertNotIn("SECRETVALUE", str(cm.exception))

    def test_repr_hides_values(self):
        e = env.load(self.path)
        self.assertNotIn("SECRETVALUE", repr(e))
        self.assertNotIn("SECRETVALUE", str(e))

    def test_bad_port(self):
        with open(self.path, "a") as f:
            f.write("BAD_PORT=abc\n")
        with self.assertRaises(ValueError):
            env.load(self.path).port("BAD_PORT")

    def test_does_not_use_os_environ(self):
        os.environ["ONLY_IN_ENVIRON"] = "1"
        try:
            self.assertIsNone(env.load(self.path).get("ONLY_IN_ENVIRON"))
        finally:
            del os.environ["ONLY_IN_ENVIRON"]


if __name__ == "__main__":
    unittest.main()
