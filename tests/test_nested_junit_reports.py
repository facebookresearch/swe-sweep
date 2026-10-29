"""The shared JUnit readers support nested suites emitted by PHPUnit."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
SHARED = ROOT / 'tasks/swe-sweep__symfony/tests/shared'
sys.path.insert(0, str(SHARED))
from swesweep_eval.eval.suites.concrete.phpunit import PhpUnitSuite  # noqa: E402
from swesweep_eval.eval.suites.utils.evaluation import parse_junit  # noqa: E402
from swesweep_eval.eval.suites.utils.compiled import _parse_junit as compiled_junit  # noqa: E402
from swesweep_eval.eval.suites.utils.pytest import run_pytest  # noqa: E402

path = ROOT / 'tasks/swe-sweep__three-js/tests/shared/swesweep_eval/eval/suites/utils/javascript.py'
spec = importlib.util.spec_from_file_location('javascript_nested_test', path)
javascript = importlib.util.module_from_spec(spec)
spec.loader.exec_module(javascript)

CASES = ('<testcase classname="Synthetic" name="first"/>',
         '<testcase classname="Synthetic" name="second"><failure/></testcase>',
         '<testcase classname="Synthetic" name="third"><skipped/></testcase>')


def environment(text):
    return SimpleNamespace(exists=lambda path: True, read_text=lambda path: text,
                           remove=lambda path: None,
                           execute=lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout='synthetic report'))


class NestedJunitTest(unittest.TestCase):
    def test_phpunit_adapter_reads_producer_shaped_nested_report(self):
        # PHPUnit's startTestSuite/endTest callbacks nest configuration/class suites.
        report = '<testsuites><testsuite name="configuration"><testsuite name="class">' \
                 + CASES[0] + '</testsuite></testsuite></testsuites>'
        outcomes, count, error, timed_out = PhpUnitSuite().run_tests(
            environment(report), '/synthetic', ['SyntheticTest.php'], [], 1, '1')
        self.assertEqual(outcomes, {'first': 'passed'})
        self.assertEqual(count, 1)
        self.assertFalse(error)
        self.assertFalse(timed_out)

    def test_nested_and_flat_reports_have_identical_cases_in_all_readers(self):
        readers = [lambda env: parse_junit(env, '/report'),
                   lambda env: compiled_junit(env, '/report', qualified=True)[0],
                   lambda env: javascript._parse_junit(env, '/report')[0],
                   lambda env: run_pytest(env, '/synthetic', [], [], 1)[0]]
        flat = '<testsuite>' + ''.join(CASES) + '</testsuite>'
        nested = '<testsuite>' + CASES[0] + '<testsuite>' + CASES[1] \
                 + '<testsuite>' + CASES[2] + '</testsuite></testsuite></testsuite>'
        for reader in readers:
            expected = reader(environment(flat))
            for report in (nested, '<testsuites>' + nested + '</testsuites>'):
                with self.subTest(reader=reader, report=report):
                    actual = reader(environment(report))
                    self.assertEqual(actual, expected)
                    self.assertEqual(len(actual), 3)  # no duplicate parent traversal
                    self.assertEqual(list(actual.values()), ['passed', 'failed', 'skipped'])


if __name__ == '__main__':
    unittest.main()
