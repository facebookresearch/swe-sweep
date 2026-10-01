from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from swesweep import cli
from swesweep.scoring import score_paths

ROOT = Path(__file__).resolve().parents[1]


def write_trial(root: Path, trial: str, task: str, reward: dict[str, float]) -> None:
    trial_dir = root / trial
    verifier = trial_dir / "verifier"
    verifier.mkdir(parents=True)
    (trial_dir / "config.json").write_text(json.dumps({"task": {"path": f"/tasks/{task}"}}))
    (verifier / "reward.json").write_text(json.dumps(reward))


def graded_roots(tmp_path: Path) -> tuple[Path, Path]:
    first = tmp_path / "first"
    second = tmp_path / "second"
    write_trial(
        first,
        "alpha-1",
        "swe-sweep__alpha",
        {"n_subtasks": 10, "n_resolved": 8, "visible_ok": 1, "reward": 0.8},
    )
    write_trial(
        first,
        "alpha-2",
        "swe-sweep__alpha",
        {"n_subtasks": 10, "n_resolved": 10, "visible_ok": 0, "reward": 0.0},
    )
    write_trial(
        second,
        "beta-1",
        "swe-sweep__beta",
        {"n_subtasks": 5, "n_resolved": 2, "visible_ok": 1, "reward": 0.4},
    )
    write_trial(
        second,
        "failed-1",
        "swe-sweep__failed",
        {
            "n_subtasks": 7,
            "n_resolved": 0,
            "visible_ok": 0,
            "reward": 0.0,
            "grader_failed": 1,
        },
    )
    return first, second


def test_score_summary_uses_public_fields(tmp_path):
    roots = graded_roots(tmp_path)

    report = score_paths(roots)

    assert report["summary"] == {
        "graded_tasks": 2,
        "graded_bugs": 15,
        "resolved_bugs": 6,
        "score": 0.4,
        "score_ignoring_regressions": 11 / 15,
        "evaluation_failures": ["swe-sweep__failed"],
    }


def test_info_command_emits_json_and_per_task_output(tmp_path, capsys):
    roots = graded_roots(tmp_path)

    assert cli.main(["info", *(str(root) for root in roots), "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["summary"]["resolved_bugs"] == 6

    assert cli.main(["info", *(str(root) for root in roots), "--per-task"]) == 0
    output = capsys.readouterr().out
    assert "swe-sweep__alpha" in output
    assert "swe-sweep__beta" in output
    assert "swe-sweep__failed" in output


def test_tasks_score_script_uses_the_same_aggregator(tmp_path):
    roots = graded_roots(tmp_path)

    result = subprocess.run(
        [sys.executable, str(ROOT / "tasks" / "score.py"), *(str(root) for root in roots), "--json"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(result.stdout)["summary"]["score"] == 0.4
