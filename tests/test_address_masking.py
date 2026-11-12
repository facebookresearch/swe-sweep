"""Must-pass names that embed a memory address are matched with the address masked."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tasks" / "swe-sweep__testify" / "tests" / "shared"))

import swesweep_grade  # noqa: E402


def test_memory_addresses_in_test_names_are_masked():
    stored = "pkg::TestNotEqual/NotEqual((func()_int)(0x5fc7e0),(func()_int)(0x5fc800))"
    observed = "pkg::TestNotEqual/NotEqual((func()_int)(0x60a1c0),(func()_int)(0x60a1e0))"
    assert swesweep_grade.stable_test_id(stored) == swesweep_grade.stable_test_id(observed)
    assert swesweep_grade.stable_test_id("pkg::TestFoo/0x1f") == "pkg::TestFoo/0x1f"  # short hex is data


def _regressions(base: set[str], post: dict[str, str]) -> list[str]:
    out = {"detail": {}}
    error = swesweep_grade._compare_visible(
        post, False, frozenset(base), False, out, lambda d: {k for k, v in d.items() if v == "passed"}
    )
    assert not error
    return out["regressions"]


def test_an_address_rename_is_not_a_regression():
    base = {"pkg::TestNotEqual/NotEqual((func()_int)(0x5fc7e0))", "pkg::TestOther"}
    post = {"pkg::TestNotEqual/NotEqual((func()_int)(0x60a1c0))": "passed", "pkg::TestOther": "passed"}
    assert _regressions(base, post) == []
    post["pkg::TestOther"] = "failed"
    assert _regressions(base, post) == ["pkg::TestOther"]


def test_a_masked_sibling_does_not_hide_a_real_failure():
    base = {"math/big::TestFillBytes/0xffffffff", "math/big::TestFillBytes/0xffffffffffffffff"}
    post = {"math/big::TestFillBytes/0xffffffff": "failed", "math/big::TestFillBytes/0xffffffffffffffff": "passed"}
    assert _regressions(base, post) == ["math/big::TestFillBytes/0xffffffff"]
