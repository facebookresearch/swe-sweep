"""GoogleTest's disabled and failed-then-skipped XML must not count as passes."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
SHARED = ROOT / 'tasks/swe-sweep__opencv/tests/shared'
sys.path.insert(0, str(SHARED))
from swesweep_eval.eval.suites.concrete.gtest import GTestSuite  # noqa: E402
from swesweep_eval.eval.suites.utils.compiled import _parse_junit as compiled_junit  # noqa: E402
from swesweep_eval.eval.suites.utils.evaluation import parse_junit, OutputCapture  # noqa: E402
from swesweep_eval.eval.suites.utils.pytest import run_pytest  # noqa: E402

spec = importlib.util.spec_from_file_location('grader_junit_status_test', SHARED / 'swesweep_grade.py')
grader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(grader)
path = ROOT / 'tasks/swe-sweep__three-js/tests/shared/swesweep_eval/eval/suites/utils/javascript.py'
spec = importlib.util.spec_from_file_location('javascript_junit_status_test', path)
javascript = importlib.util.module_from_spec(spec)
spec.loader.exec_module(javascript)


def environment(report):
    return SimpleNamespace(exists=lambda path: True, read_text=lambda path: report,
                           remove=lambda path: None,
                           execute=lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout='synthetic report'))


def report(cases):
    return '<testsuites><testsuite name="Synthetic">' + cases + '</testsuite></testsuites>'


class JunitStatusTest(unittest.TestCase):
    def suite(self):
        return GTestSuite(build_dir='/synthetic/build', bin_dir='/synthetic/bin',
                          binary_re=r'^test.cpp$', binary_fmt='synthetic_test')

    def grade(self, xml):
        result = grader._new_subtask_result()
        grader._run_targets(environment(xml), self.suite(),
                            SimpleNamespace(test_timeout=1, repo='/synthetic'),
                            ['test.cpp'], [], OutputCapture(1000, 10000), '1', result)
        return result

    def test_disabled_google_test_is_not_a_successful_executed_case(self):
        xml = report('<testcase classname="Synthetic" name="DISABLED_case" '
                     'status="notrun" result="suppressed"/>')
        outcomes, count, error, timed_out = self.suite().run_tests(
            environment(xml), '/synthetic', ['test.cpp'], [], 1, '1')
        self.assertEqual(outcomes, {'Synthetic.DISABLED_case': 'skipped'})
        self.assertEqual(count, 0)
        self.assertFalse(error)
        self.assertFalse(timed_out)
        self.assertFalse(self.grade(xml)['resolved'])

    def test_failed_then_skipped_google_test_is_still_a_failure(self):
        for markers in ('<failure/><skipped/>', '<skipped/><failure/>'):
            with self.subTest(markers=markers):
                xml = report('<testcase classname="Synthetic" name="passed"/>'
                             '<testcase classname="Synthetic" name="failed" status="run" result="completed">'
                             + markers + '</testcase>')
                result = self.grade(xml)
                self.assertFalse(result['resolved'])
                self.assertEqual(result['failed'], ['Synthetic.failed'])

    def test_shared_readers_agree_and_plain_cases_are_unchanged(self):
        readers = [lambda env: parse_junit(env, '/report'),
                   lambda env: compiled_junit(env, '/report', qualified=True)[0],
                   lambda env: javascript._parse_junit(env, '/report')[0],
                   lambda env: run_pytest(env, '/synthetic', [], [], 1)[0]]
        cases = [('<testcase name="case"/>', 'passed'),
                 ('<testcase name="case"><skipped/></testcase>', 'skipped'),
                 ('<testcase name="case" status="notrun" result="suppressed"/>', 'skipped'),
                 ('<testcase name="case"><failure/><skipped/></testcase>', 'failed'),
                 ('<testcase name="case"><error/><skipped/></testcase>', 'error')]
        for case, expected in cases:
            for reader in readers:
                with self.subTest(case=case, reader=reader):
                    self.assertEqual(list(reader(environment(report(case))).values()), [expected])


if __name__ == '__main__':
    unittest.main()
