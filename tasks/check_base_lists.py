#!/usr/bin/env python3
"""Check every task's must-pass list (tests/base_tests.json.gz): empty, placeholder (`<suite>`), counts off, volatile names.
Usage: python3 check_base_lists.py [dataset_dir]  (prints one line per finding; exits 1 if a task outside KNOWN_WITHOUT_LIST has one)
Rebuild a list in the task image: grade an empty patch at least three times and keep the tests that always pass."""

import gzip
import json
import re
import sys
from pathlib import Path

VOLATILE = (
    ("temporary path", re.compile(r"/tmp/[^\s/]*\d{3,}")),
    ("process id", re.compile(r"\bpid[=: ]\d+", re.IGNORECASE)),
)
# A Go value printed as `(type)(0xaddress)`, as in testify's `(func()_int)(0x5fc7e0)`; fixed hex test values (go's
# `TestFillBytes/0xffffffff`, symfony's URL data sets) are not addresses.
ADDRESS = re.compile(r"\)\(0x[0-9a-fA-F]{6,}\)")
# Tasks whose must-pass list is still empty or a placeholder; reported, but they do not fail the check.
KNOWN_WITHOUT_LIST = frozenset({"datafusion", "dmd", "jest", "oxc", "phpspreadsheet", "rails", "sunpy"})


def check_task(task: Path) -> tuple[list[str], list[str]]:
    """`(findings, notes)` for one task directory."""
    tests = task / "tests"
    with gzip.open(tests / "base_tests.json.gz", "rt") as stream:
        lists = json.load(stream)
    bundle = json.loads((tests / "swesweep_eval.json").read_text())
    passing, ignored = lists.get("passing", []), lists.get("ignored", [])
    findings, notes = [], []
    if not passing:
        findings.append("no passing tests: the regression gate checks nothing")
    if any("<suite>" in name for name in passing + ignored):
        findings.append("placeholder <suite> entry: the suite produced no per-test results")
    if bundle.get("n_base_passing") != len(passing):
        findings.append(f"n_base_passing {bundle.get('n_base_passing')} != {len(passing)} listed")
    if bundle.get("n_base_test_ignore") != len(ignored):
        findings.append(f"n_base_test_ignore {bundle.get('n_base_test_ignore')} != {len(ignored)} listed")
    if not isinstance(lists.get("environment_failed", []), list):
        findings.append(f"environment_failed should be a list of tests, got {lists['environment_failed']!r:.40}")
    runs = lists.get("environment_runs")
    if passing and not (isinstance(runs, list) and runs and all(isinstance(r, str) and r for r in runs)):
        findings.append(f"environment_runs should list the runs the list was recorded from, got {runs!r:.60}")
    for label, pattern in VOLATILE:
        hits = [name for name in passing if pattern.search(name)]
        if hits:
            findings.append(f"{len(hits)} name(s) with a {label}, e.g. {hits[0][:100]}")
    addressed = [name for name in passing if ADDRESS.search(name)]
    if addressed:
        notes.append(f"{len(addressed)} name(s) with a memory address (it changes whenever the code size changes)")
    return findings, notes


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent
    tasks = sorted(p for p in root.iterdir() if (p / "tests" / "base_tests.json.gz").is_file())
    failing = known = 0
    for task in tasks:
        findings, notes = check_task(task)
        is_known = task.name.split("__", 1)[-1] in KNOWN_WITHOUT_LIST
        failing += bool(findings) and not is_known
        known += bool(findings) and is_known
        for line in findings:
            print(f"{task.name}: {'known: ' if is_known else ''}{line}")
        for line in notes:
            print(f"{task.name}: note: {line}")
    print(f"{len(tasks)} tasks, {failing} with findings ({known} known tasks without a list)")
    return 1 if failing else 0


if __name__ == "__main__":
    sys.exit(main())
