from __future__ import annotations

import gzip
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

from swesweep.scoring import score_paths
from test_scoring import write_trial

ROOT = Path(__file__).resolve().parents[1]
GRADER = ROOT / "tasks/swe-sweep__click/tests/shared/swesweep_grade.py"
AGENT_PATCH = (
    "diff --git a/notes.txt b/notes.txt\nnew file mode 100644\n--- /dev/null\n+++ b/notes.txt\n@@ -0,0 +1 @@\n+agent\n"
)


def load_grader() -> ModuleType:
    module = ModuleType("synthetic_grader_build_failure")
    module.__file__ = str(GRADER)
    exec(compile(GRADER.read_bytes(), str(GRADER), "exec"), module.__dict__)
    return module


def git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args], check=True, capture_output=True
    )


def make_task(root: Path, build_cmd: str) -> Path:
    """A one-file repository with a build step and two subtasks whose hidden tests fail."""
    repo = root / "repo"
    (repo / "tests").mkdir(parents=True)
    (repo / "pytest.ini").write_text("[pytest]\n")
    (repo / "tests" / "test_base.py").write_text("def test_base():\n    pass\n")
    git(repo, "init", "-q")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "base")
    git(repo, "tag", "baseline")
    tests = root / "tests"
    subtasks = []
    for sid in ("s1", "s2"):
        patch = tests / "subtasks" / sid / "test.patch"
        patch.parent.mkdir(parents=True)
        patch.write_text(
            f"diff --git a/tests/test_{sid}.py b/tests/test_{sid}.py\nnew file mode 100644\n"
            f"--- /dev/null\n+++ b/tests/test_{sid}.py\n@@ -0,0 +1,2 @@\n+def test_{sid}():\n+    assert False\n"
        )
        subtasks.append({"id": sid, "f2p": [f"tests.test_{sid}::test_{sid}"], "target_files": ["src.py"]})
    bundle = {
        "task": "beta",
        "version": "1",
        "container_repo": str(repo),
        "reproduction": {"suite": "pytest", "needs_build": True, "build_cmd": build_cmd},
        "evaluation": {"paths": "tests"},
        "subtasks": subtasks,
    }
    (tests / "swesweep_eval.json").write_text(json.dumps(bundle))
    with gzip.open(tests / "base_tests.json.gz", "wt") as f:
        json.dump({"passing": ["tests.test_base::test_base"], "ignored": []}, f)
    (tests / "shared").symlink_to(GRADER.parent, target_is_directory=True)
    return tests


@pytest.mark.parametrize("build_cmd,build_ok", [("exit 1", 0.0), ("true", 1.0)])
def test_agent_build_failure_keeps_the_task_bugs_in_the_score(tmp_path, monkeypatch, build_cmd, build_ok):
    # The grader imports its evaluator from the task's `shared/` dir and runs `python -m pytest`.
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.setenv("PATH", str(Path(sys.executable).parent) + os.pathsep + os.environ.get("PATH", ""))
    tests = make_task(tmp_path / "task", build_cmd)
    patch = tmp_path / "model.patch"
    patch.write_text(AGENT_PATCH)
    jobs = tmp_path / "jobs"
    (jobs / "beta-1").mkdir(parents=True)
    (jobs / "beta-1" / "config.json").write_text(json.dumps({"task": {"path": "/tasks/swe-sweep__beta"}}))

    load_grader().grade(tests, patch, jobs / "beta-1" / "verifier")

    reward = json.loads((jobs / "beta-1" / "verifier" / "reward.json").read_text())
    assert reward["agent_build_ok"] == build_ok
    assert reward["grader_failed"] == 0.0
    # A patch that does not build scores 0 on every bug of the task, like one that builds
    # and resolves nothing; its bugs are not dropped from the task.
    assert (reward["reward"], reward["n_resolved"], reward["n_subtasks"]) == (0.0, 0.0, 2.0)

    write_trial(jobs, "alpha-1", "swe-sweep__alpha", {"n_subtasks": 2, "n_resolved": 2, "visible_ok": 1, "reward": 1.0})
    summary = score_paths([jobs])["summary"]
    # 2 resolved bugs over the 4 accepted bugs of both tasks.
    assert (summary["resolved_bugs"], summary["graded_bugs"], summary["score"]) == (2, 4, 0.5)
