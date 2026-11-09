from __future__ import annotations

import json
from pathlib import Path

import pytest

from swesweep.scoring import score_paths


def write_trial(root: Path, trial: str, task: str, reward: dict[str, float]) -> None:
    trial_dir = root / trial
    verifier = trial_dir / "verifier"
    verifier.mkdir(parents=True)
    (trial_dir / "config.json").write_text(json.dumps({"task": {"path": f"/tasks/{task}"}}))
    (verifier / "reward.json").write_text(json.dumps(reward))


def test_infrastructure_failure_without_trial_fields_is_reported(tmp_path: Path):
    root = tmp_path / "jobs"
    write_trial(root, "crash-1", "swe-sweep__crash", {"reward": 0.0, "grader_failed": 1.0})

    report = score_paths([root])

    assert report["summary"]["evaluation_failures"] == ["swe-sweep__crash"]
    assert report["summary"]["graded_tasks"] == 0
    assert report["summary"]["graded_bugs"] == 0
    assert report["summary"]["score"] == 0.0
    assert report["tasks"] == []


def test_boolean_infrastructure_failure_is_reported(tmp_path: Path):
    root = tmp_path / "jobs"
    write_trial(root, "crash-1", "swe-sweep__crash", {"reward": 0.0, "grader_failed": True})

    report = score_paths([root])

    assert report["summary"]["evaluation_failures"] == ["swe-sweep__crash"]
    assert report["tasks"] == []


def test_incomplete_failure_keeps_a_graded_sibling(tmp_path: Path):
    root = tmp_path / "jobs"
    write_trial(
        root,
        "ok-1",
        "swe-sweep__ok",
        {"n_subtasks": 4, "n_resolved": 2, "visible_ok": 1, "reward": 0.5},
    )
    write_trial(root, "crash-1", "swe-sweep__crash", {"reward": 0.0, "grader_failed": 1})

    report = score_paths([root])

    assert report["summary"]["graded_tasks"] == 1
    assert report["summary"]["graded_bugs"] == 4
    assert report["summary"]["resolved_bugs"] == 2
    assert report["summary"]["evaluation_failures"] == ["swe-sweep__crash"]


def test_reward_missing_the_failure_marker_is_still_ignored(tmp_path: Path):
    root = tmp_path / "jobs"
    write_trial(root, "partial-1", "swe-sweep__partial", {"reward": 0.0})

    with pytest.raises(ValueError, match="no SWE-sweep reward.json"):
        score_paths([root])
