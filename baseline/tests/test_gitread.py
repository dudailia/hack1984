"""gitread: refs and objects read from .git directly, checked against git itself on throwaway repos.

The tests run git (they are not guarded); the module under test never does.
"""
import os
import shutil
import subprocess
import tempfile
import unittest

from baseline import gitread

GIT = shutil.which("git")
ENV = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.com", GIT_COMMITTER_NAME="t",
           GIT_COMMITTER_EMAIL="t@example.com", GIT_CONFIG_NOSYSTEM="1", HOME="/nonexistent")


def git(cwd, *args):
    r = subprocess.run([GIT, "-c", "init.defaultBranch=main", "-c", "gc.auto=0", *args], cwd=cwd, env=ENV,
                       capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise AssertionError("git %s: %s" % (" ".join(args), r.stderr))
    return r.stdout.strip()


def write(root, rel, text):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


BIG = "".join("def check_%d(payload):\n    return payload.count(%r)\n\n" % (i, "x" * (i % 7)) for i in range(300))


@unittest.skipUnless(GIT, "git not installed")
class GitReadTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.repo = os.path.join(self.tmp, "repo")
        os.makedirs(self.repo)
        git(self.repo, "init", "-q")
        write(self.repo, "checks/__init__.py", "")
        write(self.repo, "checks/rules.py", BIG)
        write(self.repo, "checks/tests/test_rules.py", "# test\n")
        write(self.repo, "README.md", "readme\n")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "one")
        git(self.repo, "tag", "-a", "checks-frozen", "-m", "frozen")
        self.frozen_commit = git(self.repo, "rev-parse", "checks-frozen^{commit}")
        for i in range(3):  # later commits: similar blobs, so gc writes deltas
            write(self.repo, "checks/rules.py", BIG + "# rev %d\n" % i)
            git(self.repo, "commit", "-q", "-am", "rev %d" % i)
        git(self.repo, "checkout", "-q", "checks-frozen", "--", "checks")
        git(self.repo, "commit", "-q", "-am", "back to frozen checks")
        write(self.repo, "notes.txt", "after\n")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "after")

    def assert_matches_git(self, path=None):
        r = gitread.Repo(path or self.repo)
        self.assertEqual(r.read_ref("HEAD"), git(path or self.repo, "rev-parse", "HEAD"))
        self.assertEqual(gitread.short_head(path or self.repo), git(path or self.repo, "rev-parse", "HEAD")[:7])
        self.assertEqual(r.read_ref("refs/tags/checks-frozen"), git(self.repo, "rev-parse", "refs/tags/checks-frozen"))
        self.assertEqual(r.peel_to_commit(r.read_ref("refs/tags/checks-frozen")), self.frozen_commit)
        self.assertTrue(gitread.tag_exists(path or self.repo, "checks-frozen"))
        self.assertFalse(gitread.tag_exists(path or self.repo, "no-such-tag"))
        for line in git(self.repo, "rev-list", "--objects", "--all").splitlines():
            sha = line.split()[0]
            kind, body = r.read_object(sha)
            self.assertEqual(kind, git(self.repo, "cat-file", "-t", sha))
            self.assertEqual(len(body), int(git(self.repo, "cat-file", "-s", sha)))

    def test_loose_objects_and_loose_refs(self):
        self.assertTrue(os.path.isfile(os.path.join(self.repo, ".git", "refs", "tags", "checks-frozen")))
        self.assert_matches_git()

    def test_packed_objects_with_deltas_and_packed_refs(self):
        git(self.repo, "gc", "-q", "--aggressive", "--prune=now")
        git(self.repo, "pack-refs", "--all")
        self.assertFalse(os.path.exists(os.path.join(self.repo, ".git", "refs", "tags", "checks-frozen")))
        self.assertTrue(os.listdir(os.path.join(self.repo, ".git", "objects", "pack")))
        verify = git(self.repo, "verify-pack", "-v",
                     *[os.path.join(self.repo, ".git", "objects", "pack", n)
                       for n in os.listdir(os.path.join(self.repo, ".git", "objects", "pack")) if n.endswith(".idx")])
        self.assertIn("chain length", verify, "the pack must contain deltas for this test to mean anything")
        self.assert_matches_git()

    def test_detached_head(self):
        git(self.repo, "checkout", "-q", "--detach", "HEAD~1")
        self.assert_matches_git()

    def test_worktree(self):
        wt = os.path.join(self.tmp, "wt")
        git(self.repo, "worktree", "add", "-q", "--detach", wt, "HEAD~2")
        git(self.repo, "pack-refs", "--all")
        self.assertTrue(os.path.isfile(os.path.join(wt, ".git")))
        self.assert_matches_git(wt)

    def test_checks_match_frozen(self):
        self.assertIs(gitread.matches_tag(self.repo, "checks-frozen", "checks", exclude=("tests",)), True)
        write(self.repo, "checks/tests/test_rules.py", "# changed test only\n")
        self.assertIs(gitread.matches_tag(self.repo, "checks-frozen", "checks", exclude=("tests",)), True)
        os.makedirs(os.path.join(self.repo, "checks", "__pycache__"))
        write(self.repo, "checks/__pycache__/rules.cpython-313.pyc", "x")
        self.assertIs(gitread.matches_tag(self.repo, "checks-frozen", "checks", exclude=("tests",)), True)
        git(self.repo, "gc", "-q", "--prune=now")
        self.assertIs(gitread.matches_tag(self.repo, "checks-frozen", "checks", exclude=("tests",)), True)

    def test_changed_added_or_removed_check_file_does_not_match(self):
        rules = os.path.join(self.repo, "checks", "rules.py")
        write(self.repo, "checks/rules.py", BIG + "# edited\n")
        self.assertIs(gitread.matches_tag(self.repo, "checks-frozen", "checks", exclude=("tests",)), False)
        write(self.repo, "checks/rules.py", BIG)
        write(self.repo, "checks/extra.py", "x = 1\n")  # untracked code is importable code
        self.assertIs(gitread.matches_tag(self.repo, "checks-frozen", "checks", exclude=("tests",)), False)
        os.remove(os.path.join(self.repo, "checks", "extra.py"))
        os.remove(rules)
        self.assertIs(gitread.matches_tag(self.repo, "checks-frozen", "checks", exclude=("tests",)), False)

    def test_missing_tag_or_repo_is_unknown(self):
        self.assertIsNone(gitread.matches_tag(self.repo, "nope", "checks"))
        self.assertIsNone(gitread.matches_tag(self.tmp, "checks-frozen", "checks"))
        self.assertIsNone(gitread.short_head(self.tmp))
        self.assertFalse(gitread.tag_exists(self.tmp, "checks-frozen"))

    def test_corrupt_object_is_an_error_not_a_match(self):
        sha = git(self.repo, "rev-parse", "HEAD:README.md")
        path = os.path.join(self.repo, ".git", "objects", sha[:2], sha[2:])
        os.chmod(path, 0o644)
        import zlib
        with open(path, "wb") as f:
            f.write(zlib.compress(b"blob 5\0fake\n"))
        with self.assertRaises(gitread.GitError):
            gitread.Repo(self.repo).read_object(sha)

    def test_ref_names_are_not_paths(self):
        r = gitread.Repo(self.repo)
        for bad in ("../HEAD", "refs/tags/../../config", "/etc/passwd", "refs/tags/a\0b", ""):
            with self.assertRaises(gitread.GitError):
                r.read_ref(bad)

    def test_this_repo(self):
        repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.assertEqual(gitread.short_head(repo), git(repo, "rev-parse", "HEAD")[:7])
        has_tag = subprocess.run([GIT, "-C", repo, "rev-parse", "-q", "--verify", "refs/tags/checks-frozen"],
                                 capture_output=True).returncode == 0
        self.assertEqual(gitread.tag_exists(repo, "checks-frozen"), has_tag)


if __name__ == "__main__":
    unittest.main()
