"""Tasks whose hidden tests are compiled rebuild the tree after applying them."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tasks" / "swe-sweep__goawk" / "tests" / "shared"))

from swesweep_eval.eval.runner_config import EvalRunnerConfig  # noqa: E402


def test_rebuild_after_hidden_tests_is_opt_in():
    assert EvalRunnerConfig(repo="/repo").rebuild_hidden_tests is False
    assert EvalRunnerConfig(repo="/repo", rebuild_hidden_tests=True).rebuild_hidden_tests is True
    bundle = json.loads((ROOT / "tasks" / "swe-sweep__tarantool" / "tests" / "swesweep_eval.json").read_text())
    assert bundle["evaluation"]["rebuild_hidden_tests"] is True


def _grade_one_subtask(tmp_path, monkeypatch, rebuild, build_ok=True):
    """Drive the grader's per-subtask step with stand-ins and return (result, the order of apply/build/run)."""
    from types import SimpleNamespace

    import swesweep_grade as grade

    events = []
    patch = tmp_path / grade.SUBTASKS_DIRNAME / "bug-1" / "test.patch"
    patch.parent.mkdir(parents=True)
    patch.write_text("diff --git a/test/t.c b/test/t.c\n--- a/test/t.c\n+++ b/test/t.c\n@@ -1 +1 @@\n-a\n+b\n")

    class Repo:
        def apply_patch(self, path):
            events.append("apply")
            return True, ""

        def restore_files(self, paths):
            events.append("restore")

    suite = SimpleNamespace(targets=lambda diff, env=None: (["t"], ["n"]), no_targets="none")
    config = SimpleNamespace(needs_build=True, rebuild_hidden_tests=rebuild, repo="/repo")
    for name in ("drop_bytecode_caches", "prepare_incremental_build", "refresh_build_graph"):
        monkeypatch.setattr(grade, name, lambda *a, **k: None)
    monkeypatch.setattr(
        grade, "_build", lambda *a: events.append("build") or (build_ok, "" if build_ok else "cc: error", "")
    )
    monkeypatch.setattr(grade, "_run_targets", lambda *a, **k: events.append("run"))
    result, _ = grade._run_hidden_tests(None, Repo(), suite, config, tmp_path, "bug-1", None, "1")
    return result, events


def test_compiled_hidden_tests_are_rebuilt_after_the_hidden_patch(tmp_path, monkeypatch):
    result, events = _grade_one_subtask(tmp_path, monkeypatch, rebuild=True)
    assert events == ["apply", "build", "run", "restore"]
    assert "error" not in result["detail"]


def test_a_failed_rebuild_is_reported_and_its_tests_are_not_run(tmp_path, monkeypatch):
    result, events = _grade_one_subtask(tmp_path, monkeypatch, rebuild=True, build_ok=False)
    assert events == ["apply", "build", "restore"]
    assert result["detail"]["error"].startswith("build failed after hidden test patch: ")


def test_without_the_option_there_is_no_rebuild(tmp_path, monkeypatch):
    _, events = _grade_one_subtask(tmp_path, monkeypatch, rebuild=False)
    assert events == ["apply", "run", "restore"]
