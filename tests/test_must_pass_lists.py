"""Every task's stored must-pass list (tests/base_tests.json.gz) is checked by tasks/check_base_lists.py."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Tasks whose stored must-pass list is still empty or a placeholder. A task must leave this set
# when its list is rebuilt, and no task may join it.
KNOWN_BAD_BASE_LISTS = {"datafusion", "dmd", "jest", "oxc", "phpspreadsheet", "rails", "sunpy"}


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_must_pass_lists_have_no_new_defects():
    checker = _load(ROOT / "tasks" / "check_base_lists.py", "check_base_lists_under_test")
    bad = set()
    for task in sorted((ROOT / "tasks").glob("swe-sweep__*")):
        findings, _ = checker.check_task(task)
        if findings:
            bad.add(task.name.split("__", 1)[1])
    assert bad == KNOWN_BAD_BASE_LISTS, {"new": bad - KNOWN_BAD_BASE_LISTS, "fixed": KNOWN_BAD_BASE_LISTS - bad}
