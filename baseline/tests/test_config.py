"""config: only the named key is read from .env; ports are validated."""
import os
import tempfile
import unittest

from baseline import config


class ConfigTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env_file = os.path.join(self.tmp.name, ".env")
        with open(self.env_file, "w", encoding="utf-8") as f:
            f.write("TAVILY_API_KEY=tvly-secret\n# comment\nexport GATE_PORT=9123  # gate\n"
                    "OLLAMA_MODEL='qwen3:8b'\nOLLAMA_PORT=bad\n")

    def test_env_wins_over_file(self):
        self.assertEqual(config.env_value("GATE_PORT", "1", env={"GATE_PORT": "9999"}, env_file=self.env_file),
                         "9999")

    def test_file_value_parsed(self):
        self.assertEqual(config.env_value("GATE_PORT", None, env={}, env_file=self.env_file), "9123")
        self.assertEqual(config.env_value("OLLAMA_MODEL", None, env={}, env_file=self.env_file), "qwen3:8b")

    def test_default_when_missing(self):
        self.assertEqual(config.env_value("APP_PORT", "8700", env={}, env_file=self.env_file), "8700")
        self.assertEqual(config.env_value("APP_PORT", "8700", env={}, env_file=os.path.join(self.tmp.name, "no")),
                         "8700")

    def test_api_keys_never_readable(self):
        for key in ("TAVILY_API_KEY", "ANTHROPIC_API_KEY"):
            with self.assertRaises(ValueError):
                config.env_value(key, None, env={}, env_file=self.env_file)

    def test_ports(self):
        self.assertEqual(config.gate_port(env={}, env_file=self.env_file), 9123)
        self.assertEqual(config.gate_port(env={}, env_file=os.path.join(self.tmp.name, "no")), 8701)
        with self.assertRaises(ValueError):
            config.ollama_port(env={}, env_file=self.env_file)
        self.assertEqual(config.ollama_model(env={}, env_file=self.env_file), "qwen3:8b")
        self.assertEqual(config.ollama_model(env={}, env_file=os.path.join(self.tmp.name, "no")), "qwen3:4b")


if __name__ == "__main__":
    unittest.main()
