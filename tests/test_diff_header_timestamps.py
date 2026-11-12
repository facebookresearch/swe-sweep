"""A git timestamp after the path is not part of the path."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEADER = "+++ b/tests/pkg/path with spaces/Main.lean\t2020-01-01 00:00:00.000000000 +0000\n"


def _load(task: str, module: str, name: str):
    shared = str(ROOT / "tasks" / task / "tests" / "shared")
    for key in list(sys.modules):
        if key == "swesweep_eval" or key.startswith("swesweep_eval."):
            del sys.modules[key]
    sys.path.insert(0, shared)
    try:
        imported = __import__(module, fromlist=[name])
    finally:
        sys.path.remove(shared)
    return getattr(imported, name)


def test_pytest_targets_drop_the_timestamp():
    target_tests = _load("swe-sweep__agda", "swesweep_eval.eval.suites.utils.pytest", "target_tests")
    files, _names = target_tests(
        "diff --git a/tests/test_a.py b/tests/test_a.py\n" + HEADER.replace("Main.lean", "test_a.py")
    )
    assert files == ["tests/pkg/path with spaces/test_a.py"]


def test_hunk_splitter_drops_the_timestamp():
    per_file = _load("swe-sweep__agda", "swesweep_eval.eval.suites.utils.compiled", "_per_file_hunks")
    hunks = per_file(
        "diff --git a/file.py b/file.py\n" + HEADER.replace("Main.lean", "file.py") + "@@ -0,0 +1 @@\n+x\n"
    )
    assert [hunk.path for hunk in hunks] == ["tests/pkg/path with spaces/file.py"]


def test_inline_case_reads_the_timestamp_free_path(tmp_path: Path):
    suite_cls = _load(
        "swe-sweep__mypy",
        "swesweep_eval.eval.suites.concrete.pytest_inline_case",
        "PytestInlineCaseSuite",
    )
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    case_file = corpus / "a.txt"
    case_file.write_text("[case Hidden]\nbody\n")
    seen = {}

    class Env:
        def read_text(self, path):
            seen["path"] = path
            return Path(path).read_text()

    suite = suite_cls(corpus_re=r"corpus/a\.txt", drivers=["tests/test_driver.py"], repo=str(tmp_path))
    diff = "+++ b/corpus/a.txt\t2020-01-01 00:00:00\n@@ -1 +1 @@\n+changed\n"
    _files, names = suite.targets(diff, env=Env())
    assert seen["path"] == str(tmp_path / "corpus" / "a.txt")
    assert "Hidden" in names
