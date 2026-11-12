"""pytest ``-k`` names have to stay identifiers."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]


def _modules():
    shared = ROOT / "tasks" / "swe-sweep__agda" / "tests" / "shared"
    sys.path.insert(0, str(shared))
    try:
        from swesweep_eval.eval.suites.utils import evaluation
        from swesweep_eval.eval.suites.utils import pytest as pytest_utils
    finally:
        sys.path.remove(str(shared))
    return evaluation, pytest_utils


class _Env:
    def __init__(self) -> None:
        self.cmd = None

    def exists(self, _path):
        return False

    def remove(self, _path):
        return None

    def execute(self, cmd, **_kwargs):
        self.cmd = list(cmd)
        return SimpleNamespace(returncode=0, stdout="")


class _Cap:
    def clip(self, text):
        return text or "", False


def test_hyphenated_case_name_is_not_subtraction():
    _evaluation, pytest_utils = _modules()
    expression = pytest_utils.keyword_expression(["test_added", "testMatchAsPatternIntersection-skip"])
    assert expression == "test_added or (testMatchAsPatternIntersection and skip)"


def test_reproduction_runner_uses_the_expression():
    _evaluation, pytest_utils = _modules()
    env = _Env()
    pytest_utils.run_pytest(env, "/repo", ["tests/test_driver.py"], ["testFoo-skip"], 5)
    assert env.cmd[env.cmd.index("-k") + 1] == "(testFoo and skip)"


def test_evaluation_runner_uses_the_expression():
    evaluation, _pytest_utils = _modules()
    env = _Env()
    evaluation.run_pytest(env, "/repo", ["tests/test_driver.py"], ["testFoo-skip"], 5, _Cap())
    assert env.cmd[env.cmd.index("-k") + 1] == "(testFoo and skip)"
