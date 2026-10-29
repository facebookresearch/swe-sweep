"""Synthetic targeted outcomes must cover the declared fail-to-pass tests."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

SHARED = Path(__file__).resolve().parents[1] / 'tasks/swe-sweep__gson/tests/shared'
sys.path.insert(0, str(SHARED))
spec = importlib.util.spec_from_file_location('grader_f2p_test', SHARED / 'swesweep_grade.py')
grader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(grader)


class TargetCoverageTest(unittest.TestCase):
    def result(self, outcomes, expected):
        suite = SimpleNamespace(run_selected=lambda *args: (outcomes, False, {}))
        config = SimpleNamespace(test_timeout=1, repo='/synthetic')
        result = grader._new_subtask_result()
        grader._run_targets(None, suite, config, [], [], None, '1', result,
                            f2p=frozenset(expected))
        return result

    def test_missing_or_skipped_f2p_cannot_be_replaced_by_unrelated_pass(self):
        for status in (None, 'skipped'):
            with self.subTest(status=status):
                outcomes = {'synthetic::unrelated': 'passed'}
                if status:
                    outcomes['synthetic::regression'] = status
                result = self.result(outcomes, {'synthetic::regression'})
                self.assertFalse(result['resolved'])
                self.assertEqual(result['detail']['f2p_not_passed'], ['synthetic::regression'])
                self.assertEqual(result['n_failed'], 0)  # no fabricated failure outcome

    def test_every_explicit_f2p_must_pass(self):
        expected = {'synthetic::first', 'synthetic::second'}
        result = self.result({'synthetic::first': 'passed'}, expected)
        self.assertFalse(result['resolved'])
        self.assertEqual(result['detail']['f2p_not_passed'], ['synthetic::second'])
        complete = self.result({test: 'passed' for test in expected}, expected)
        self.assertTrue(complete['resolved'])

    def test_failure_and_legacy_scope_controls(self):
        self.assertFalse(self.result({'synthetic::regression': 'failed'},
                                     {'synthetic::regression'})['resolved'])
        self.assertTrue(self.result({'synthetic::one': 'passed'}, set())['resolved'])
        self.assertTrue(self.result({'synthetic::one': 'passed'},
                                    {grader.PROCESS_LEVEL_FAILURE_NODE})['resolved'])

    def test_go_scope_and_unicode_normalization_match_existing_ids(self):
        with mock.patch.object(grader, '_GO_MODULE_ROOT', 'example.test/project'):
            result = self.result({'.::TestRegression': 'passed'},
                                 {'example.test/project::TestRegression'})
            self.assertTrue(result['resolved'])
        expected = 'synthetic::title-\ud83d'
        result = self.result({grader.normalize_test_id(expected): 'passed'}, {expected})
        self.assertTrue(result['resolved'])


if __name__ == '__main__':
    unittest.main()
