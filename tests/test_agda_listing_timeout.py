"""A timeout while listing Agda's corpus is a timed-out run, not a grader crash."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]


def _suite():
    shared = str(ROOT / "tasks" / "swe-sweep__agda" / "tests" / "shared")
    for key in list(sys.modules):
        if key == "swesweep_eval" or key.startswith("swesweep_eval."):
            del sys.modules[key]
    sys.path.insert(0, shared)
    try:
        from swesweep_eval.eval.suites.concrete.agda_tasty import AgdaTastySuite
    finally:
        sys.path.remove(shared)
    return AgdaTastySuite()


def test_listing_timeout_is_reported():
    class Env:
        def execute(self, cmd, timeout=None, **_kwargs):
            raise subprocess.TimeoutExpired(cmd, timeout or 0)

    outcomes, count, error, timed_out = _suite().run_tests(Env(), "/repo", None, [], 30, "1")

    assert outcomes == {}
    assert count == 0
    assert error is False
    assert timed_out is True


def test_listing_still_names_cases():
    class Env:
        def execute(self, _cmd, **_kwargs):
            return SimpleNamespace(returncode=0, stdout="all.Fail.Issue1234\n")

    assert _suite()._population(Env(), "/repo", 5) == {"Fail": ["all/Fail/Issue1234"]}
