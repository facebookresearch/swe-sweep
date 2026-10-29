from __future__ import annotations

import json
from fractions import Fraction

import pytest

from swesweep import cli
from swesweep.scoring import score_paths
from test_scoring import graded_roots


def test_overlapping_roots_count_each_trial_file_once(tmp_path):
    first, second = graded_roots(tmp_path)
    expected = score_paths([first, second])
    # Alpha's two attempts count 4 resolved after its regression gate, plus
    # beta's 2: the independent expected benchmark fraction is 6 / 15.
    assert expected["summary"]["score"] == float(Fraction(6, 15))
    for roots in ([first, second, first / "alpha-1"], [first, second, first]):
        assert score_paths(roots) == expected


def test_symlinked_root_is_the_same_set_of_trial_files(tmp_path):
    first, second = graded_roots(tmp_path)
    alias = tmp_path / "alias"
    try:
        alias.symlink_to(first, target_is_directory=True)
    except (OSError, NotImplementedError) as error:
        pytest.skip(f"directory symlinks unavailable: {error}")
    assert score_paths([first, second, alias]) == score_paths([first, second])


def test_info_json_is_unchanged_when_a_trial_root_is_repeated(tmp_path, capsys):
    first, second = graded_roots(tmp_path)
    assert cli.main(["info", str(first), str(second), str(first / "alpha-1"), "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["summary"]["score"] == float(Fraction(6, 15))
    assert [task["trials"] for task in report["tasks"]] == [2, 1]


def test_unreadable_symlink_loop_does_not_hide_other_valid_trials(tmp_path):
    first, second = graded_roots(tmp_path)
    broken = tmp_path / "broken" / "verifier"
    broken.mkdir(parents=True)
    try:
        (broken / "reward.json").symlink_to("reward.json")
    except (OSError, NotImplementedError) as error:
        pytest.skip(f"symlinks unavailable: {error}")
    assert score_paths([tmp_path]) == score_paths([first, second])
