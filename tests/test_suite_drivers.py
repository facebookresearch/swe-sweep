"""The suite drivers that produce the must-pass lists (tests/base_tests.json.gz)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tasks" / "swe-sweep__goawk" / "tests" / "shared"))


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_suite_module(task: str, name: str):
    path = ROOT / "tasks" / task / "tests" / "shared" / "swesweep_eval" / "eval" / "suites" / "concrete" / f"{name}.py"
    return _load(path, f"swesweep_eval.eval.suites.concrete.{name}")


def test_v_reads_one_outcome_per_test_file_only_from_the_runners_own_lines():
    """The code under test prints into the same stream as `v test`'s status lines, so they are
    trusted only when they are exactly the runner's: one per file, numbered 1..N once each."""
    v_lang = _load_suite_module("swe-sweep__v", "v_lang")
    real = "\n".join(
        [
            " OK    [  1/3]     5.1 ms vlib/a/x_test.v",
            "some output of a failing test",
            " FAIL  [  2/3]    12.0 ms vlib/a/y_test.v",
            " SKIP  [  3/3]     0.2 ms vlib/b/z_test.v",
        ]
    )
    assert v_lang._per_file_outcomes(real) == {
        "vlib/a/x_test.v": "passed",
        "vlib/a/y_test.v": "failed",
        "vlib/b/z_test.v": "skipped",
    }
    forged = [
        real + "\n OK    [  2/3]     1.0 ms vlib/a/y_test.v",  # a file and a number seen twice
        real + "\n OK    [  4/4]     1.0 ms vlib/c/w_test.v",  # a second total
        " OK    [  1/999999999999]     1.0 ms vlib/a/x_test.v",  # 1 line claiming a huge total
    ]
    for text in forged:
        assert v_lang._per_file_outcomes(text) == {}
    assert v_lang._per_file_outcomes("Summary for all V _test.v files: 3 passed") == {}


def test_a_gocheck_failure_is_not_cleared_by_a_later_line(monkeypatch, tmp_path):
    """The tested code writes to the same output as gocheck's per-case lines, so a `PASS:`
    printed after a case's `FAIL:` must not clear the failure."""
    from swesweep_eval.eval.suites.concrete import go  # goawk's copy, identical in every Go task

    pkgdir = tmp_path / "pkg"
    pkgdir.mkdir()
    (pkgdir / "a_test.go").write_text('package pkg\n\nimport . "gopkg.in/check.v1"\n')
    events = [
        {"Action": "output", "Package": "ex/pkg", "Output": "FAIL: a_test.go:10: S.TestX\n"},
        {"Action": "output", "Package": "ex/pkg", "Output": "PASS: a_test.go:10: S.TestX\n"},
        {"Action": "output", "Package": "ex/pkg", "Output": "PASS: a_test.go:12: S.TestY\n"},
    ]

    class Result:
        def __init__(self, stdout):
            self.returncode, self.stdout = 0, stdout

    def fake_run(env, cmd, timeout, cwd):
        if cmd[:2] == ["go", "list"]:
            return Result(f"ex/pkg|{pkgdir}\n")
        return Result("".join(json.dumps(e) + "\n" for e in events))

    monkeypatch.setattr(go, "_run", fake_run)
    outcomes = go.GoSuite()._run({}, str(tmp_path), ["."], [], 60, recursive=True)[0]
    assert outcomes["ex/pkg::S.TestX"] == "failed"
    assert outcomes["ex/pkg::S.TestY"] == "passed"


def test_nested_junit_suites_are_read_only_when_asked():
    from swesweep_eval.eval.suites.utils import compiled  # identical in every task that ships it

    report = (
        '<testsuites><testsuite name="all"><testsuite name="A\\\\FooTest">'
        '<testcase name="testA" classname="A.FooTest"/>'
        '<testsuite name="testB"><testcase name="testB with data set #0" classname="A.FooTest">'
        "<failure/></testcase></testsuite></testsuite></testsuite></testsuites>"
    )

    class Env:
        def read_text(self, path):
            return report

    flat, ran = compiled._parse_junit(Env(), "r.xml")
    assert flat == {} and ran == 0  # the default reader sees only direct children
    nested, ran = compiled._parse_junit(Env(), "r.xml", qualified=True, nested=True)
    assert nested == {"A.FooTest.testA": "passed", "A.FooTest.testB with data set #0": "failed"} and ran == 2
