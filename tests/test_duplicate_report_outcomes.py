"""Ordinary duplicate report identities cannot hide a failing observation."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

# Keep interpreter caches out of the vendored-source synchronization check.
sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[1]
SHARED = ROOT / "tasks/swe-sweep__gson/tests/shared"
sys.path.insert(0, str(SHARED))
from swesweep_eval.eval.suites.utils.evaluation import parse_junit, record_outcome  # noqa: E402
from swesweep_eval.eval.suites.utils.compiled import _parse_junit as compiled_junit  # noqa: E402
from swesweep_eval.eval.suites.utils.pytest import run_pytest  # noqa: E402

path = ROOT / "tasks/swe-sweep__three-js/tests/shared/swesweep_eval/eval/suites/utils/javascript.py"
spec = importlib.util.spec_from_file_location("javascript_duplicate_test", path)
javascript = importlib.util.module_from_spec(spec)
spec.loader.exec_module(javascript)


def environment(text):
    return SimpleNamespace(
        exists=lambda path: True,
        read_text=lambda path: text,
        remove=lambda path: None,
        execute=lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout="fixture"),
    )


class DuplicateOutcomeTest(unittest.TestCase):
    def test_jest_duplicate_titles_are_independent_of_file_order(self):
        for statuses in (("failed", "passed"), ("passed", "failed")):
            with self.subTest(statuses=statuses):
                report = {
                    "testResults": [
                        {
                            "name": f"/synthetic/spec{number}.js",
                            "assertionResults": [
                                {"ancestorTitles": ["Synthetic suite"], "title": "same title", "status": status}
                            ],
                        }
                        for number, status in enumerate(statuses)
                    ]
                }
                outcomes, count, error = javascript._parse_jest_json(environment(json.dumps(report)), "/report")
                self.assertEqual(outcomes, {"Synthetic suite same title": "failed"})
                self.assertEqual(count, 1)  # existing logical identities remain stable
                self.assertFalse(error)

    def test_junit_readers_preserve_nonpassing_duplicates_in_either_order(self):
        readers = [
            lambda env: parse_junit(env, "/report"),
            lambda env: compiled_junit(env, "/report", qualified=True)[0],
            lambda env: javascript._parse_junit(env, "/report")[0],
            lambda env: run_pytest(env, "/synthetic", [], [], 1)[0],
        ]
        for status in ("failed", "error", "skipped"):
            for statuses in ((status, "passed"), ("passed", status)):
                tag = {"failed": "failure", "error": "error", "skipped": "skipped"}[status]
                cases = "".join(
                    '<testcase classname="Synthetic" name="same">'
                    + (f"<{tag}/>" if current != "passed" else "")
                    + "</testcase>"
                    for current in statuses
                )
                report = "<testsuites><testsuite>" + cases + "</testsuite></testsuites>"
                for reader in readers:
                    with self.subTest(statuses=statuses, reader=reader):
                        outcomes = reader(environment(report))
                        self.assertEqual(list(outcomes.values()), [status])

    def test_error_and_failure_are_not_downgraded_to_skip(self):
        for statuses, expected in ((("error", "failed"), "error"), (("failed", "skipped"), "failed")):
            for order in (statuses, tuple(reversed(statuses))):
                with self.subTest(order=order):
                    outcomes = {}
                    for status in order:
                        record_outcome(outcomes, "synthetic", status)
                    self.assertEqual(outcomes, {"synthetic": expected})

    def test_distinct_ids_and_duplicate_passes_preserve_existing_results(self):
        report = (
            '<testsuite><testcase classname="Synthetic" name="first"/>'
            '<testcase classname="Synthetic" name="second"><failure/></testcase></testsuite>'
        )
        self.assertEqual(
            parse_junit(environment(report), "/report"), {"Synthetic::first": "passed", "Synthetic::second": "failed"}
        )
        duplicate = '<testsuite><testcase name="same"/><testcase name="same"/></testsuite>'
        self.assertEqual(parse_junit(environment(duplicate), "/report"), {"same": "passed"})


if __name__ == "__main__":
    unittest.main()
