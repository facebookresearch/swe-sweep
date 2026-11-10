"""A real pytest INTERNALERROR must not pass the pristine visible gate."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

# Keep interpreter caches out of the vendored-source synchronization check.
sys.dont_write_bytecode = True

SHARED = Path(__file__).resolve().parents[1] / "tasks/swe-sweep__gson/tests/shared"
sys.path.insert(0, str(SHARED))
from swesweep_eval.eval.suites.utils.evaluation import OutputCapture, passed_set, run_pytest  # noqa: E402

spec = importlib.util.spec_from_file_location("grader_pytest_status_test", SHARED / "swesweep_grade.py")
grader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(grader)


class LocalPytest:
    def __init__(self, root):
        self.report = root / "report.xml"

    def exists(self, _path):
        return self.report.exists()

    def remove(self, _path):
        self.report.unlink(missing_ok=True)

    def read_text(self, _path):
        return self.report.read_text()

    def execute(self, command, *, cwd, timeout, merge_stderr):
        # Isolate the helper's fixed /tmp/report.xml and use this test's interpreter.
        command = [sys.executable, *command[1:]]
        command = [f"--junitxml={self.report}" if arg.startswith("--junitxml=") else arg for arg in command]
        return subprocess.run(
            command,
            cwd=cwd,
            timeout=timeout,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT if merge_stderr else subprocess.PIPE,
            check=False,
        )


class PytestRunnerStatusTest(unittest.TestCase):
    def run_fixture(self, root):
        return run_pytest(LocalPytest(root), str(root), ["test_synthetic.py"], [], 10, OutputCapture(2000, 20000))

    def test_internal_error_with_passing_partial_xml_is_unmeasurable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "test_synthetic.py").write_text("def test_pass():\n    assert True\n")
            (root / "conftest.py").write_text(
                "def pytest_runtest_logfinish(nodeid, location):\n"
                '    raise RuntimeError("synthetic reporting failure")\n'
            )
            outcomes, timed_out, captured = self.run_fixture(root)
            self.assertEqual(captured["returncode"], 3)
            self.assertFalse(timed_out)
            verdict = {"detail": {}}
            error = grader._compare_visible(
                outcomes, timed_out, frozenset({"test_synthetic::test_pass"}), True, verdict, passed_set
            )
            self.assertTrue(error, "pytest exited3 but pristine visible gate accepted the partial report")
            self.assertIsNone(outcomes)
            self.assertIn("INTERNALERROR", captured["text"])

    def test_normal_pass_and_test_failure_still_return_measured_outcomes(self):
        for assertion, expected_code, expected_outcome in (("True", 0, "passed"), ("False", 1, "failed")):
            with self.subTest(assertion=assertion), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "test_synthetic.py").write_text(f"def test_pass():\n    assert {assertion}\n")
                outcomes, timed_out, captured = self.run_fixture(root)
                self.assertEqual(captured["returncode"], expected_code)
                self.assertEqual(outcomes, {"test_synthetic::test_pass": expected_outcome})
                self.assertFalse(timed_out)


if __name__ == "__main__":
    unittest.main()
