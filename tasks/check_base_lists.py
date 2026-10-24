#!/usr/bin/env python3
"""Check every task's must-pass list (tests/base_tests.json.gz): empty, placeholder (`<suite>`), counts off, volatile names.
Usage: python3 check_base_lists.py [dataset_dir]  (prints one line per finding, exits 1 if any; stdlib only)
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
ADDRESS = re.compile(r"0x[0-9a-fA-F]{6,}")


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
    failing = 0
    for task in tasks:
        findings, notes = check_task(task)
        failing += bool(findings)
        for line in findings:
            print(f"{task.name}: {line}")
        for line in notes:
            print(f"{task.name}: note: {line}")
    print(f"{len(tasks)} tasks, {failing} with findings")
    return 1 if failing else 0


if __name__ == "__main__":
    sys.exit(main())
