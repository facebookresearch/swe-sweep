from __future__ import annotations

from fractions import Fraction

from swesweep import cli
from swesweep.scoring import format_report, score_paths
from test_scoring import write_trial


def make_trials(tmp_path):
    for name, task, reward, resolved in (
        ("alpha-1", "synthetic-alpha", 1.0, 10),
        ("alpha-2", "synthetic-alpha", 0.0, 0),
        ("beta-1", "synthetic-beta", 1.0, 10),
    ):
        write_trial(tmp_path, name, task,
                    {"n_subtasks": 10, "n_resolved": resolved, "visible_ok": 1, "reward": reward})


def test_report_average_weights_each_graded_trial_once(tmp_path):
    make_trials(tmp_path)
    report = score_paths([tmp_path])
    # The benchmark weights tasks by bug count after averaging their attempts;
    # the descriptive trial mean weights the three attempts equally.
    assert report["summary"]["score"] == float(Fraction(3, 4))
    text = format_report(report, per_task=False, as_json=False)
    line = text.splitlines()[-1]
    assert line.endswith(f"{float(Fraction(2, 3)):.4f}")
    assert "mean trial reward (graded trials)" in line


def test_info_mean_retains_the_existing_failed_grader_exclusion(tmp_path, capsys):
    make_trials(tmp_path)
    write_trial(tmp_path, "failed", "synthetic-gamma",
                {"n_subtasks": 90, "n_resolved": 0, "visible_ok": 0,
                 "reward": 0.0, "grader_failed": 1})
    assert cli.main(["info", str(tmp_path), "--per-task"]) == 0
    text = capsys.readouterr().out
    assert "1 evaluation failure(s) excluded" in text
    assert "mean trial reward (graded trials): 0.6667" in text
    assert "75.00%" in text  # The benchmark score keeps its existing definition.


def test_report_with_no_graded_trials_retains_zero_default(tmp_path):
    write_trial(tmp_path, "failed", "synthetic-gamma",
                {"n_subtasks": 90, "n_resolved": 0, "visible_ok": 0,
                 "reward": 0.0, "grader_failed": 1})
    text = format_report(score_paths([tmp_path]), per_task=False, as_json=False)
    assert "mean trial reward (graded trials): 0.0000" in text
