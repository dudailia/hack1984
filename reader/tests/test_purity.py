"""reader/ is pure: no network modules, no subprocess, no file reads at call time."""
import ast
import unittest
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]
FORBIDDEN_MODULES = {"socket", "ssl", "http", "urllib", "urllib3", "requests", "httpx", "asyncio", "subprocess",
                     "ftplib", "smtplib", "telnetlib", "xmlrpc", "multiprocessing", "os", "pathlib", "io", "shutil"}
FORBIDDEN_CALLS = {"open", "exec", "eval", "__import__", "compile"}


class ReaderIsPure(unittest.TestCase):
    def test_no_network_or_file_access(self):
        files = sorted(PKG.glob("*.py"))
        self.assertTrue(files)
        for path in files:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertNotIn(alias.name.split(".")[0], FORBIDDEN_MODULES, path.name)
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    self.assertNotIn((node.module or "").split(".")[0], FORBIDDEN_MODULES, path.name)
                elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    self.assertNotIn(node.func.id, FORBIDDEN_CALLS, path.name)


if __name__ == "__main__":
    unittest.main()
