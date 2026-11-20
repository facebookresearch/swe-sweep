from __future__ import annotations

import tomllib
from types import MethodType, SimpleNamespace

import pytest
from harbor.models.task.config import VerifierConfig
from harbor.trial.trial import Trial

from swesweep import cli


@pytest.mark.parametrize("verifier", ["", "[verifier]\n", "[verifier]\ntimeout_sec=120\n"])
def test_requested_seconds_are_effective_with_explicit_or_default_harbor_timeout(tmp_path, verifier):
    task = tmp_path / "synthetic-task"
    task.mkdir()
    (task / "task.toml").write_text(verifier)
    command = cli.harbor_eval_command(task, tmp_path / "submission.diff", tmp_path / "jobs", timeout=30, dry_run=True)
    multiplier = float(command[command.index("--verifier-timeout-multiplier") + 1])
    # Use the actual pinned Harbor schema and consumer, without starting a trial.
    config = VerifierConfig.model_validate(tomllib.loads(verifier).get("verifier", {}))
    trial = SimpleNamespace(
        config=SimpleNamespace(
            timeout_multiplier=1.0,
            verifier_timeout_multiplier=multiplier,
            verifier=SimpleNamespace(override_timeout_sec=None, max_timeout_sec=None),
        ),
        task=SimpleNamespace(config=SimpleNamespace(verifier=config)),
    )
    trial._resolve_timeout_sec = MethodType(Trial._resolve_timeout_sec, trial)
    assert Trial._compute_verifier_timeout_sec(trial) == pytest.approx(30)


@pytest.mark.parametrize("value", ["nan", "inf", "-inf"])
def test_nonfinite_requested_timeout_is_rejected_before_evaluation(value, monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(cli, "resolve_task", lambda name: calls.append(name))
    with pytest.raises(SystemExit, match="2"):
        cli.main(["eval", "synthetic-task", "unused.diff", f"--timeout={value}"])
    assert calls == []
    assert "--timeout" in capsys.readouterr().err


@pytest.mark.parametrize("value", ["nan", "inf", "-inf"])
def test_nonfinite_task_timeout_cannot_generate_a_nonfinite_multiplier(tmp_path, value):
    (tmp_path / "task.toml").write_text(f"[verifier]\ntimeout_sec={value}\n")
    with pytest.raises(ValueError, match="invalid verifier timeout"):
        cli.harbor_eval_command(tmp_path, tmp_path / "submission.diff", tmp_path / "jobs", timeout=30, dry_run=True)


@pytest.mark.parametrize("requested,configured", [(1e308, 1e-308), (1e-308, 1e308)])
def test_unrepresentable_timeout_multiplier_is_rejected(tmp_path, requested, configured):
    (tmp_path / "task.toml").write_text(f"[verifier]\ntimeout_sec={configured}\n")
    with pytest.raises(ValueError, match="invalid verifier timeout multiplier"):
        cli.harbor_eval_command(
            tmp_path, tmp_path / "submission.diff", tmp_path / "jobs", timeout=requested, dry_run=True
        )
