"""Every task's stored must-pass list (tests/base_tests.json.gz) is checked by tasks/check_base_lists.py."""

from __future__ import annotations

import gzip
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_must_pass_lists_have_no_new_defects():
    checker = _load(ROOT / "tasks" / "check_base_lists.py", "check_base_lists_under_test")
    known = checker.KNOWN_WITHOUT_LIST  # a task must leave this set when its list is rebuilt, and no task may join it
    bad = set()
    for task in sorted((ROOT / "tasks").glob("swe-sweep__*")):
        findings, _ = checker.check_task(task)
        if findings:
            bad.add(task.name.split("__", 1)[1])
    assert bad == known, {"new": bad - known, "fixed": known - bad}


def test_the_check_passes_with_only_the_known_tasks_and_fails_on_a_new_one(tmp_path, capsys):
    checker = _load(ROOT / "tasks" / "check_base_lists.py", "check_base_lists_exit")

    def task(name, passing):
        tests = tmp_path / f"swe-sweep__{name}" / "tests"
        tests.mkdir(parents=True)
        with gzip.open(tests / "base_tests.json.gz", "wt") as f:
            json.dump({"passing": passing, "ignored": [], "environment_runs": ["run-1"]}, f)
        (tests / "swesweep_eval.json").write_text(json.dumps({"n_base_passing": len(passing), "n_base_test_ignore": 0}))

    task("rails", [])
    task("good", ["pkg::TestA"])
    sys.argv = ["check_base_lists.py", str(tmp_path)]
    assert checker.main() == 0
    task("newbad", [])
    assert checker.main() == 1


def test_only_go_value_addresses_are_noted():
    checker = _load(ROOT / "tasks" / "check_base_lists.py", "check_base_lists_address")
    assert checker.ADDRESS.search("assert::TestNotEqual/NotEqual((func()_int)(0x5fc7e0),_(func()_int)(0x5fc800))")
    assert not checker.ADDRESS.search("math/big::TestFillBytes/0xffffffff")
    assert not checker.ADDRESS.search('UrlSanitizerTest.testParse with data set "http://0xfffffff"')
