from __future__ import annotations

from fractions import Fraction

import pytest

from swesweep import cli
from swesweep.scoring import score_paths
from test_scoring import write_trial


def reward(total, resolved, *, failed=False):
    return {
        "n_subtasks": total,
        "n_resolved": resolved,
        "visible_ok": 1,
        "reward": 0.0 if failed else resolved / total,
        "grader_failed": int(failed),
    }


def test_different_task_denominators_are_not_pooled_in_either_order(tmp_path):
    write_trial(tmp_path, "full", "synthetic-alpha", reward(20, 20))
    write_trial(tmp_path, "subset", "synthetic-alpha", reward(10, 10))
    # Each input is a perfect run, but neither 150% nor 75% is a valid result of
    # combining two different task definitions as repeated attempts.
    for roots in ([tmp_path / "subset", tmp_path / "full"], [tmp_path / "full", tmp_path / "subset"]):
        with pytest.raises(ValueError, match=r"synthetic-alpha.*n_subtasks"):
            score_paths(roots)


@pytest.mark.parametrize(
    "field,value", [("n_subtasks", 10.5), ("n_subtasks", -1), ("n_resolved", 2.5), ("n_resolved", 11)]
)
def test_bug_counts_are_whole_and_bounded(tmp_path, field, value):
    data = reward(10, 2)
    data[field] = value
    write_trial(tmp_path, "one", "synthetic-alpha", data)
    with pytest.raises(ValueError, match=field):
        score_paths([tmp_path])


def test_integral_numeric_counts_and_failed_trial_policy_are_preserved(tmp_path):
    write_trial(tmp_path, "first", "synthetic-alpha", reward(10, 8))
    write_trial(tmp_path, "second", "synthetic-alpha", reward(10.0, 10.0))
    write_trial(tmp_path, "failed", "synthetic-alpha", reward(90, 0, failed=True))
    report = score_paths([tmp_path])
    assert report["summary"]["score"] == float(Fraction(9, 10))
    assert report["tasks"][0]["trials"] == 2
    assert report["summary"]["evaluation_failures"] == ["synthetic-alpha"]


def test_info_reports_incompatible_task_definitions_as_a_usage_error(tmp_path, capsys):
    write_trial(tmp_path, "full", "synthetic-alpha", reward(20, 20))
    write_trial(tmp_path, "subset", "synthetic-alpha", reward(10, 10))
    with pytest.raises(SystemExit) as caught:
        cli.main(["info", str(tmp_path), "--json"])
    assert caught.value.code == 2
    assert "synthetic-alpha" in capsys.readouterr().err
