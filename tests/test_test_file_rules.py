"""Which files the grader reverts as tests (tasks/*/tests/shared/, identical in every task)."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tasks" / "swe-sweep__goawk" / "tests" / "shared"))

from swesweep_eval.eval.suites.utils.evaluation import is_test_file  # noqa: E402

_PATCH_FILE_RE = re.compile(r"^(?:\+\+\+ b/|--- a/)(.+)$", re.MULTILINE)

# Known, reviewed exceptions to the scan below.
# Official fixes that also edit a real test file next to their source change (the revert of
# the test part is correct): dart-sdk object_test.cc (+ object.cc), datafusion tests/arithmetic.rs
# (+ binary.rs).
OFFICIAL_FIX_TEST_FILES = {
    ("dart-sdk", "runtime/vm/object_test.cc"),
    ("datafusion", "datafusion/expr-common/src/type_coercion/binary/tests/arithmetic.rs"),
}
# Hidden-test files no path rule can tell from source: ruff's inline `mod tests` in mod.rs,
# v's test-runner list.
HIDDEN_FILES_NOT_TESTS = {"ruff": "/mod.rs", "v": "cmd/tools/vtest-self.v"}


def _patch_files(path: Path) -> set[str]:
    text = path.read_text(errors="ignore")
    return {name for name in _PATCH_FILE_RE.findall(text) if name != "/dev/null"}


def test_official_fixes_are_never_reverted_and_hidden_tests_always_are():
    """Every file an official fix edits must survive the revert step, and every file a hidden
    test patch edits must be reverted, under each task's own test_dirs / source_files."""
    wrong_fix, wrong_test = [], []
    for task in sorted((ROOT / "tasks").glob("swe-sweep__*")):
        name = task.name.split("__", 1)[1]
        evaluation = json.loads((task / "tests" / "swesweep_eval.json").read_text())["evaluation"]
        test_dirs = evaluation.get("test_dirs", ()) if isinstance(evaluation, dict) else ()
        source_files = evaluation.get("source_files", ()) if isinstance(evaluation, dict) else ()
        for patch in (task / "tests" / "oracle").glob("*.patch"):
            for path in _patch_files(patch):
                if is_test_file(path, test_dirs, source_files) and (name, path) not in OFFICIAL_FIX_TEST_FILES:
                    wrong_fix.append(f"{name}: {path}")
        for patch in (task / "tests" / "subtasks").glob("*/test.patch"):
            for path in _patch_files(patch):
                if (
                    not is_test_file(path, test_dirs, source_files)
                    and HIDDEN_FILES_NOT_TESTS.get(name, "\0") not in path
                ):
                    wrong_test.append(f"{name}: {path}")
    assert not wrong_fix, "official-fix files treated as tests:\n" + "\n".join(sorted(set(wrong_fix)))
    assert not wrong_test, "hidden-test files not treated as tests:\n" + "\n".join(sorted(set(wrong_test)))


def test_source_files_are_never_test_files():
    assert is_test_file("actionpack/lib/action_controller/test_case.rb")
    assert not is_test_file(
        "actionpack/lib/action_controller/test_case.rb", (), ("actionpack/lib/action_controller/test_case.rb",)
    )


def _load_shared_module(task: str, relpath: str):
    """Load one shared module by path (tasks ship different subsets of the shared tree)."""
    import importlib.util

    path = ROOT / "tasks" / task / "tests" / "shared" / relpath
    spec = importlib.util.spec_from_file_location(path.stem + "_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_jest_name_patterns_can_be_anchored():
    javascript = _load_shared_module("swe-sweep__babel", "swesweep_eval/eval/suites/utils/javascript.py")
    loose = re.compile(javascript._pattern(["duplicate proto"]))
    exact = re.compile(javascript._pattern(["duplicate proto"], anchored=True))
    title = "es2015/destructuring/duplicate proto 4"
    assert loose.search(title)  # the default narrows, it does not select exactly
    assert not exact.search(title)
    assert exact.search("es2015/destructuring/duplicate proto")


def test_babel_selects_fixture_tests_exactly():
    bundle = json.loads((ROOT / "tasks" / "swe-sweep__babel" / "tests" / "swesweep_eval.json").read_text())
    assert bundle["reproduction"]["suite"]["anchor_names"] is True
