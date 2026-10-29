from __future__ import annotations

import sys
from pathlib import Path

import pytest

SHARED = Path(__file__).resolve().parents[1] / "tasks/swe-sweep__gson/tests/shared"
sys.path.insert(0, str(SHARED))
from swesweep_eval.eval.suites.utils.evaluation import OutputCapture


@pytest.mark.parametrize("limit,text_length", [(1, 5000), (100, 101), (100, 5000), (2000, 5000)])
def test_budget_exhaustion_keeps_tail_inside_positive_invocation_limit(limit, text_length):
    capture = OutputCapture(limit=limit, budget=limit)
    assert capture.clip("x" * limit) == ("x" * limit, False)
    text = "".join(chr(65 + index % 26) for index in range(text_length))
    output, truncated = capture.clip(text)
    marker, separator, retained = output.partition("\n")
    expected_length = min(limit, 2000)
    assert separator
    assert marker == f"[... output budget for this eval is spent; last {expected_length} chars ...]"
    assert retained == text[-expected_length:]
    assert len(retained) <= limit
    assert truncated
    # The total budget remains soft: fallback diagnostics do not change accounting.
    assert capture.spent == limit


def test_default_limit_retains_existing_short_tail_policy():
    capture = OutputCapture(limit=200000, budget=1)
    assert capture.clip("x") == ("x", False)
    assert capture.clip("short diagnostic") == ("short diagnostic", False)
    text = "x" * 4999 + "Z"
    output, truncated = capture.clip(text)
    assert output.endswith("x" * 1999 + "Z")
    assert output.split("\n", 1)[0].endswith("last 2000 chars ...]")
    assert truncated
    assert capture.spent == 1
