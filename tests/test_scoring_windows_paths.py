from __future__ import annotations

import json
from fractions import Fraction
from pathlib import PureWindowsPath

import pytest
from harbor.models.trial.config import TaskConfig

from swesweep import cli
from swesweep.scoring import score_paths
from test_scoring import write_trial


def windows_trial(root, name, source_path, solved):
    task = PureWindowsPath(source_path).name
    write_trial(root, name, task,
                {"n_subtasks": 10, "n_resolved": solved, "visible_ok": 1, "reward": solved / 10})
    # Use the pinned producer schema for the actual serialized task configuration.
    task_config = TaskConfig(path=source_path).model_dump(mode="json")
    (root / name / "config.json").write_text(json.dumps({"task": task_config}))


@pytest.mark.parametrize("first,second", [
    (r"C:\checkout\tasks", r"D:\worker\tasks"),
    (r"\\host-one\share\tasks", r"\\host-two\share\tasks"),
])
def test_windows_reports_group_one_task_across_checkout_roots(tmp_path, first, second):
    windows_trial(tmp_path, "alpha-1", first + r"\synthetic-alpha", 0)
    windows_trial(tmp_path, "alpha-2", second + r"\synthetic-alpha", 10)
    windows_trial(tmp_path, "beta-1", first + r"\synthetic-beta", 10)
    report = score_paths([tmp_path])
    # Alpha averages 0 and 10 resolved; beta resolves 10. Each has 10 bugs:
    # the independent expected benchmark fraction is (5 + 10) / (10 + 10).
    assert report["summary"]["score"] == float(Fraction(3, 4))
    assert report["summary"]["graded_tasks"] == 2
    assert [(task["task"], task["trials"]) for task in report["tasks"]] == [
        ("synthetic-alpha", 2), ("synthetic-beta", 1)]


def test_info_json_uses_portable_names_for_serialized_windows_paths(tmp_path, capsys):
    windows_trial(tmp_path, "alpha-1", r"C:\tasks\synthetic-alpha", 0)
    windows_trial(tmp_path, "alpha-2", r"D:\tasks\synthetic-alpha", 10)
    windows_trial(tmp_path, "beta-1", r"C:\tasks\synthetic-beta", 10)
    assert cli.main(["info", str(tmp_path), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["summary"]["score"] == float(Fraction(3, 4))


def test_posix_basename_with_literal_backslash_is_not_reinterpreted(tmp_path):
    write_trial(tmp_path, "one", r"synthetic\alpha",
                {"n_subtasks": 10, "n_resolved": 5, "visible_ok": 1, "reward": 0.5})
    report = score_paths([tmp_path])
    assert report["tasks"][0]["task"] == r"synthetic\alpha"
