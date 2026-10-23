"""Tasks whose hidden tests are compiled rebuild the tree after applying them."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tasks" / "swe-sweep__goawk" / "tests" / "shared"))

from swesweep_eval.eval.runner_config import EvalRunnerConfig  # noqa: E402


def test_rebuild_after_hidden_tests_is_opt_in():
    assert EvalRunnerConfig(repo="/repo").rebuild_hidden_tests is False
    assert EvalRunnerConfig(repo="/repo", rebuild_hidden_tests=True).rebuild_hidden_tests is True
    bundle = json.loads((ROOT / "tasks" / "swe-sweep__tarantool" / "tests" / "swesweep_eval.json").read_text())
    assert bundle["evaluation"]["rebuild_hidden_tests"] is True
