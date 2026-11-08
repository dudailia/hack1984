"""No code path in app/, baseline/, fake_tavily/ or reader/ starts a program, except the launcher.

Static check over the source (tests excluded): any call that can start a program (subprocess.*, os.system, os.popen,
os.exec*, os.spawn*, os.posix_spawn*, os.fork*, os.startfile, pty.*) or any import of multiprocessing is a failure,
with one allowed site: app/run.py Children.start, which starts the Gate and the Tavily stand-in before
main() installs the guard. Verification runs in process (proof.verify.verify_bytes) and the red team reads .git
directly (baseline.gitread), so neither needs a program. The run-time side (a guarded process cannot start one) is
tested in child processes: baseline/tests/test_review1.py, fake_tavily/tests/test_review1.py,
app/tests/test_launcher.py.
"""
import ast
import os
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FOLDERS = ("app", "baseline", "fake_tavily", "reader")
SUBPROCESS_STARTS = {"run", "Popen", "call", "check_call", "check_output", "getoutput", "getstatusoutput"}
OS_STARTS = ("system", "popen", "exec", "spawn", "posix_spawn", "fork", "startfile")
ALLOWED = {("app/run.py", "Children.start", "subprocess.Popen")}


def sources():
    for folder in FOLDERS:
        for dirpath, dirnames, filenames in os.walk(os.path.join(REPO, folder)):
            dirnames[:] = [d for d in dirnames if d not in ("tests", "__pycache__")]
            for name in sorted(filenames):
                if name.endswith(".py"):
                    path = os.path.join(dirpath, name)
                    yield os.path.relpath(path, REPO).replace(os.sep, "/"), path


def program_starts(rel, path):
    """[(file, enclosing function, what)] for every place in one file that could start a program."""
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read(), rel)
    found, scope = [], []

    def visit(node):
        named = isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        if named:
            scope.append(node.name)
        where = ".".join(scope) or "<module>"
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[0] in ("multiprocessing", "pty"):
                    found.append((rel, where, "import " + a.name))
        elif isinstance(node, ast.ImportFrom):
            mod = (node.module or "").split(".")[0]
            for a in node.names:
                if mod in ("multiprocessing", "pty") or (mod == "subprocess" and a.name in SUBPROCESS_STARTS) \
                        or (mod == "os" and a.name.startswith(OS_STARTS)):
                    found.append((rel, where, "from %s import %s" % (node.module, a.name)))
        elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            mod, attr = node.value.id, node.attr
            if (mod == "subprocess" and attr in SUBPROCESS_STARTS) or (mod == "os" and attr.startswith(OS_STARTS)) \
                    or mod == "pty":
                found.append((rel, where, "%s.%s" % (mod, attr)))
        for child in ast.iter_child_nodes(node):
            visit(child)
        if named:
            scope.pop()

    visit(tree)
    return found


class NoProgramsTest(unittest.TestCase):
    def test_only_the_launcher_starts_programs(self):
        found = [hit for rel, path in sources() for hit in program_starts(rel, path)]
        self.assertEqual(set(found), ALLOWED, "only Children.start (before the guard) may start a program")
        self.assertEqual(len(found), 1)

    def test_the_scan_sees_what_it_should(self):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
            f.write("import os, subprocess\nfrom os import execv\nimport multiprocessing\n"
                    "def f():\n    subprocess.run(['git'])\n    os.system('x')\n    os.posix_spawn('/bin/x', [], {})\n")
        self.addCleanup(os.remove, f.name)
        what = sorted(h[2] for h in program_starts("x.py", f.name))
        self.assertEqual(what, ["from os import execv", "import multiprocessing", "os.posix_spawn", "os.system",
                                "subprocess.run"])

    def test_no_git_or_verifier_program_in_these_folders(self):
        for rel, path in sources():
            with open(path, encoding="utf-8") as f:
                text = f.read()
            self.assertNotIn('"git"', text, rel)
            self.assertNotIn("verify.py\", ", text, rel)


if __name__ == "__main__":
    unittest.main()
