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


def test_a_whole_workspace_cargo_run_keys_each_case_by_its_test_binary():
    """Bare case names collide across test binaries; the workspace run keys them as a targeted run does."""
    cargo = _load_suite_module("swe-sweep__syn", "cargo")
    out = "\n".join(
        [
            "     Running unittests src/lib.rs (target/debug/deps/syn-af9baf24406c65cd)",
            "test parse::tests::x ... ok",
            "     Running tests/test_lit.rs (target/debug/deps/test_lit-b311748c7abcbc34)",
            "test floats ... ok",
            "test bytes ... FAILED",
            "     Running tests/test_expr.rs (target/debug/deps/test_expr-47007c69f622b102)",
            "test floats ... FAILED",
            "     Running tests/all/main.rs (target/debug/deps/all-0011aabb22cc33dd)",
            "test traps::backtrace ... ignored",
        ]
    )
    assert cargo.CargoSuite().workspace_outcomes(out)["floats"] == "failed"  # unqualified: the last binary read wins
    assert cargo.CargoSuite(qualified=True).workspace_outcomes(out) == {
        "syn::parse::tests::x": "passed",
        "test_lit::floats": "passed",
        "test_lit::bytes": "failed",
        "test_expr::floats": "failed",
        "all::traps::backtrace": "skipped",
    }


def test_testament_reads_the_per_category_results_files_not_the_shared_stdout():
    """`testament all`'s children interleave on one stdout; each writes its own results file, read line by line."""
    testament = _load_suite_module("swe-sweep__nim", "testament")
    files = {
        "/nim/testresults/stdlib.json": "[\n"
        + '{"name": "tests/stdlib/tmarshal.nim c --mm:orc", "result": "reSuccess"},\n'
        + '{"name": "tests/stdlib/tmarshal.nim c --mm:refc", "result": "reOutputsDiffer"},\n'
        + '{"name": "tests/stdlib/tos.nim c (allowed to fail) ", "result": "reDisabled"}]\n',  # testament's close
        "/nim/testresults/gc.json": '[\n{"name": "tests/gc/tgc.nim c", "result": "reSuccess"},\n',  # a crashed child: unclosed
    }

    class Env:
        def find_files(self, root):
            return [p for p in files if p.startswith(root + "/")]

        def read_text(self, path):
            return files[path]

    assert testament.TestamentSuite._json_outcomes(Env(), "/nim/testresults") == {
        "tests/stdlib/tmarshal.nim c --mm:orc": "passed",
        "tests/stdlib/tmarshal.nim c --mm:refc": "failed",
        "tests/stdlib/tos.nim c": "skipped",
        "tests/gc/tgc.nim c": "passed",
    }


def test_minitest_per_test_reads_verbose_lines_only_when_they_add_up_to_the_summary():
    """The tested code prints into the same stream as `bin/test -v`'s result lines, so a gem's lines count only
    when there are as many as its summary's runs; a gem that leaves no report is skipped, not fatal."""
    path = (
        ROOT
        / "tasks"
        / "swe-sweep__rails"
        / "tests"
        / "shared"
        / "swesweep_eval"
        / "eval"
        / "suites"
        / "utils"
        / "minitest.py"
    )
    minitest = _load(path, "swesweep_eval.eval.suites.utils.minitest")
    real = "\n".join(
        [
            "FooTest#test_a = 0.00 s = .",
            "exists#test_0001_makes sql = 0.01 s = .",
            "exists#test_0001_makes sql = 0.00 s = F",  # spec-style names repeat across files
            "BarTest#test_b = 0.12 s = S",
            "",
            "4 runs, 7 assertions, 1 failures, 0 errors, 1 skips",
        ]
    )
    assert minitest.verbose_outcomes(real) == {
        "FooTest#test_a": "passed",
        "exists#test_0001_makes sql": "failed",
        "BarTest#test_b": "skipped",
    }
    assert minitest.verbose_outcomes(real.replace("4 runs", "3 runs")) is None  # a forged extra line
    assert minitest.verbose_outcomes("FooTest#test_a = 0.00 s = .") is None  # no summary: the run died

    class Result:
        def __init__(self, stdout, returncode=0):
            self.stdout, self.returncode = stdout, returncode

    class Env:
        def execute(self, argv, cwd=None, timeout=None, merge_stderr=False):
            if argv[0] == "find":
                return Result("/rails/activemodel/bin/test\n/rails/railties/bin/test\n")
            assert argv == ["bundle", "exec", "bin/test", "-v"]
            return Result(real) if cwd == "/rails/activemodel" else Result("LoadError: yarn", 1)

    outcomes, n, error, timed_out = minitest.run_minitest_per_test(Env(), "/rails", 600)
    assert (n, error, timed_out) == (3, False, False)
    assert outcomes["activemodel::FooTest#test_a"] == "passed"
    assert not any(k.startswith("railties::") for k in outcomes)
