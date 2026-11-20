"""Whole-suite errors are not successful partial evaluation reports."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
import unittest

# Keep interpreter caches out of the vendored-source synchronization check.
sys.dont_write_bytecode = True

SHARED = Path(__file__).resolve().parents[1] / "tasks/swe-sweep__gson/tests/shared"
sys.path.insert(0, str(SHARED))
from swesweep_eval.eval.suites.concrete.reproduction_evaluation import ReproductionEvaluationSuite  # noqa: E402
from swesweep_eval.eval.suites.utils.evaluation import OutputCapture, passed_set  # noqa: E402

spec = importlib.util.spec_from_file_location("grader_suite_error_test", SHARED / "swesweep_grade.py")
grader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(grader)


class ReproductionErrorTest(unittest.TestCase):
    def adapter(self, outcomes, error, timed_out=False):
        suite = SimpleNamespace(
            no_targets="fixture", run_tests=lambda *args: (outcomes, len(outcomes), error, timed_out)
        )
        return ReproductionEvaluationSuite(suite)

    def test_partial_passing_outcomes_do_not_hide_whole_suite_error(self):
        suite = self.adapter({"synthetic::first": "passed"}, True)
        post, timed_out, captured = suite.run_all(None, "/synthetic", 1, OutputCapture(1000, 10000), "1")
        self.assertIsNone(post)
        self.assertFalse(timed_out)
        self.assertIn("suite reported an error", captured["text"])
        result = {"detail": {}}
        error = grader._compare_visible(post, timed_out, frozenset({"synthetic::first"}), True, result, passed_set)
        self.assertIn("pristine visible suite", error)

    def test_targeted_run_with_partial_report_and_error_cannot_resolve(self):
        suite = self.adapter({"synthetic::first": "passed"}, True)
        result = grader._new_subtask_result()
        grader._run_targets(
            None,
            suite,
            SimpleNamespace(test_timeout=1, repo="/synthetic"),
            [],
            [],
            OutputCapture(1000, 10000),
            "1",
            result,
        )
        self.assertFalse(result["resolved"])
        self.assertIn("produced no report", result["detail"]["error"])

    def test_normal_outcomes_and_timeout_contract_are_preserved(self):
        for outcomes in ({"synthetic::first": "passed"}, {"synthetic::first": "failed"}):
            suite = self.adapter(outcomes, False)
            actual, timed_out, _captured = suite.run_selected(
                None, "/synthetic", [], [], 1, OutputCapture(1000, 10000), "1"
            )
            self.assertEqual(actual, outcomes)
            self.assertFalse(timed_out)
        suite = self.adapter({"synthetic::first": "passed"}, False, True)
        actual, timed_out, _captured = suite.run_selected(
            None, "/synthetic", [], [], 1, OutputCapture(1000, 10000), "1"
        )
        self.assertIsNone(actual)
        self.assertTrue(timed_out)


if __name__ == "__main__":
    unittest.main()
