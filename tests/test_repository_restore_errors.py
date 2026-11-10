"""Repository restoration failures must abort grading before dirty tests run."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest

# Keep interpreter caches out of the vendored-source synchronization check.
sys.dont_write_bytecode = True

SHARED = Path(__file__).resolve().parents[1] / "tasks/swe-sweep__gson/tests/shared"
sys.path.insert(0, str(SHARED))
from swesweep_eval.eval.repository import ContainerRepository  # noqa: E402
from swesweep_eval.infra.container_session import ContainerSession  # noqa: E402


class RepositoryRestoreTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.env = ContainerSession(environment={"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"})
        self.env.start()
        self.addCleanup(self.env.cleanup)
        self.repo = ContainerRepository(self.env, str(self.root))
        self.git("init", "-q")
        self.git("config", "user.name", "Synthetic Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        (self.root / "test_case.py").write_text("baseline\n")
        self.git("add", "test_case.py")
        self.git("commit", "-qm", "synthetic baseline")
        self.git("tag", "baseline")

    def git(self, *args):
        result = self.repo.git(*args)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def test_failed_reset_aborts_before_clean(self):
        self.git("tag", "-d", "baseline")
        (self.root / "test_case.py").write_text("dirty\n")
        marker = self.root / "untracked.txt"
        marker.write_text("preserve after failed reset\n")
        with self.assertRaisesRegex(RuntimeError, "git reset"):
            self.repo.reset()
        self.assertTrue(marker.exists(), "failed reset must not continue to git clean")

    def test_failed_test_file_checkout_is_not_silently_accepted(self):
        path = self.root / "test_case.py"
        path.write_text("dirty test content\n")
        (self.root / ".git" / "index.lock").write_text("synthetic lock contention\n")
        with self.assertRaisesRegex(RuntimeError, "git checkout"):
            self.repo.restore_files(["test_case.py"])
        self.assertEqual(path.read_text(), "dirty test content\n")

    def test_successful_reset_and_restore_keep_the_existing_contract(self):
        path = self.root / "test_case.py"
        path.write_text("dirty\n")
        (self.root / "untracked.txt").write_text("temporary\n")
        self.repo.reset()
        self.assertEqual(path.read_text(), "baseline\n")
        self.assertFalse((self.root / "untracked.txt").exists())
        path.write_text("dirty again\n")
        (self.root / "added_test.py").write_text("new\n")
        self.repo.restore_files(["test_case.py", "added_test.py"])
        self.assertEqual(path.read_text(), "baseline\n")
        self.assertFalse((self.root / "added_test.py").exists())


if __name__ == "__main__":
    unittest.main()
