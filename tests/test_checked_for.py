"""A bug's own targeted run checks the ignored tests its hidden patch rewrites; every other run still ignores them."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tasks" / "swe-sweep__duckdb" / "tests" / "shared"))

import swesweep_grade  # noqa: E402


class Suite:
    def run_selected(self, env, repo, files, names, timeout, capture, jobs):
        return {"t::own_fix": "passed", "t::stale_copy": "failed"}, False, ""


def _run(checked):
    swesweep_grade._IGNORED_TESTS.clear()
    swesweep_grade._IGNORED_TESTS.add("t::stale_copy")
    result = {"detail": {}}
    swesweep_grade._run_targets(
        None,
        Suite(),
        SimpleNamespace(test_timeout=60, repo="/r"),
        [],
        [],
        None,
        "1",
        result,
        f2p=frozenset({"t::own_fix"}),
        checked=frozenset(checked),
    )
    return result


def test_an_ignored_test_counts_only_in_the_run_of_the_bug_whose_hidden_patch_rewrites_it():
    assert _run([])["resolved"] is True  # any other bug: the stale copy is ignored
    own = _run(["t::stale_copy"])  # the bug that rewrites it: its updated copy must pass
    assert own["resolved"] is False and own["failed"] == ["t::stale_copy"]
