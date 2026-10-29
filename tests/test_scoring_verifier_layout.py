from __future__ import annotations

import json
from pathlib import Path

import pytest
from harbor.models.trial.paths import TrialPaths

from swesweep import cli
from swesweep.scoring import score_paths


ZERO = {"n_subtasks": 10, "n_resolved": 0, "visible_ok": 1, "reward": 0.0}
FULL = {"n_subtasks": 10, "n_resolved": 10, "visible_ok": 1, "reward": 1.0}


def trial_paths(root):
    paths = TrialPaths(root / "synthetic-trial")
    paths.mkdir()
    paths.config_path.write_text(json.dumps({"task": {"path": "/synthetic/alpha"}}))
    paths.reward_json_path.write_text(json.dumps(ZERO))
    assert paths.reward_json_path.relative_to(paths.trial_dir) == Path("verifier/reward.json")
    return paths


@pytest.mark.parametrize("directory", ["agent_dir", "user_agent_dir", "artifacts_dir"])
def test_nonverifier_logs_cannot_add_an_extra_scored_attempt(tmp_path, directory):
    paths = trial_paths(tmp_path)
    logs = getattr(paths, directory)
    logs.mkdir(exist_ok=True)
    (logs / "reward.json").write_text(json.dumps(FULL))
    report = score_paths([tmp_path])
    # The genuine verifier solved zero bugs. Another log's 10/10 must not turn
    # that result into a two-attempt mean of 5/10.
    assert report["summary"]["score"] == 0.0
    assert report["summary"]["resolved_bugs"] == 0.0
    assert report["tasks"][0]["trials"] == 1


@pytest.mark.parametrize("root_kind", ["job", "trial", "verifier"])
def test_supported_roots_find_the_genuine_verifier_result(tmp_path, root_kind):
    paths = trial_paths(tmp_path)
    root = {"job": tmp_path, "trial": paths.trial_dir, "verifier": paths.verifier_dir}[root_kind]
    report = score_paths([root])
    assert report["summary"]["graded_tasks"] == 1
    assert report["summary"]["score"] == 0.0
    assert report["tasks"][0]["trials"] == 1


def test_info_json_ignores_a_reward_shaped_agent_log(tmp_path, capsys):
    paths = trial_paths(tmp_path)
    (paths.agent_dir / "reward.json").write_text(json.dumps(FULL))
    assert cli.main(["info", str(tmp_path), "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["summary"]["score"] == 0.0
    assert report["tasks"][0]["trials"] == 1


def test_agent_log_alone_is_not_a_graded_verifier_result(tmp_path):
    paths = trial_paths(tmp_path)
    paths.reward_json_path.unlink()
    (paths.agent_dir / "reward.json").write_text(json.dumps(FULL))
    with pytest.raises(ValueError, match="no SWE-sweep reward.json"):
        score_paths([tmp_path])


def test_directory_case_alias_preserves_native_filesystem_identity(tmp_path):
    paths = trial_paths(tmp_path)
    alias = paths.trial_dir / "VERIFIER"
    if alias.exists():
        # On a case-insensitive filesystem this names the real verifier folder.
        assert score_paths([alias]) == score_paths([paths.verifier_dir])
    else:
        # On a case-sensitive filesystem it is a distinct, nonverifier folder.
        alias.mkdir()
        (alias / "reward.json").write_text(json.dumps(FULL))
        assert score_paths([tmp_path])["summary"]["score"] == 0.0


@pytest.mark.parametrize("directory", ["agent_dir", "user_agent_dir", "artifacts_dir"])
@pytest.mark.parametrize("query_nested_root", [False, True])
def test_nested_verifier_logs_below_a_known_trial_are_not_attempts(
    tmp_path, directory, query_nested_root
):
    paths = trial_paths(tmp_path)
    nested = getattr(paths, directory) / "nested" / "verifier"
    nested.mkdir(parents=True)
    (nested / "reward.json").write_text(json.dumps(FULL))
    if query_nested_root:
        with pytest.raises(ValueError, match="no SWE-sweep reward.json"):
            score_paths([nested])
    else:
        report = score_paths([tmp_path])
        assert report["summary"]["score"] == 0.0
        assert report["tasks"][0]["trials"] == 1


def test_config_free_trial_still_uses_directory_name(tmp_path):
    paths = trial_paths(tmp_path)
    paths.config_path.unlink()
    report = score_paths([tmp_path])
    assert report["tasks"][0]["task"] == paths.trial_dir.name
    assert report["tasks"][0]["trials"] == 1
