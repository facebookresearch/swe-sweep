# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from swesweep import cli
from swesweep.patch_agent import PatchAgent


def test_release_contains_100_harbor_tasks():
    tasks = cli.task_directories()
    assert len(tasks) == 100
    for task in tasks:
        assert (task / "environment" / "Dockerfile").is_file()
        assert (task / "tests" / "Dockerfile").is_file()
        assert (task / "tests" / "swesweep_eval.json").is_file()


def test_eval_wraps_harbor_with_reference_arguments(tmp_path, monkeypatch):
    patch = tmp_path / "submission.diff"
    patch.write_text("diff --git a/a b/a\n")
    calls = []

    def fake_run(command, check=False):
        calls.append((command, check))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    output = tmp_path / "results"
    assert cli.main(["eval", "dateutil", str(patch), "-o", str(output), "--dry-run"]) == 0

    command, check = calls[0]
    assert check is False
    assert command[:4] == [cli.sys.executable, "-m", "harbor.cli.main", "run"]
    assert command[command.index("--path") + 1].endswith("tasks/swe-sweep__dateutil")
    assert command[command.index("--agent") + 1] == "swesweep.patch_agent:PatchAgent"
    assert command[command.index("--agent-kwarg") + 1] == f"patch_path={patch.resolve()}"
    assert command[command.index("--jobs-dir") + 1] == str(output.resolve())
    assert "--dry-run" in command


def test_eval_subset_uses_temporary_harbor_task(tmp_path, monkeypatch):
    source = cli.resolve_task("dateutil")
    bundle = json.loads((source / "tests" / "swesweep_eval.json").read_text())
    selected = bundle["subtasks"][0]["id"]
    patch = tmp_path / "submission.diff"
    patch.write_text("diff --git a/a b/a\n")

    def fake_run(command, check=False):
        task_dir = Path(command[command.index("--path") + 1])
        configured = json.loads((task_dir / "tests" / "swesweep_eval.json").read_text())
        assert [bug["id"] for bug in configured["subtasks"]] == [selected]
        assert configured["build_jobs"] == 7
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    assert cli.main(["eval", "dateutil", str(patch), "--bugs", selected, "--build-jobs", "7"]) == 0


def test_patch_agent_uploads_and_applies_patch(tmp_path):
    patch = tmp_path / "submission.diff"
    patch.write_text("diff --git a/a b/a\n")

    class Environment:
        task_env_config = SimpleNamespace(workdir="/workspace")

        def __init__(self):
            self.upload = None
            self.command = None

        async def upload_file(self, source_path, target_path):
            self.upload = (source_path, target_path)

        async def exec(self, command, cwd=None):
            self.command = (command, cwd)
            return SimpleNamespace(return_code=0, stdout="", stderr="")

    environment = Environment()
    agent = PatchAgent(logs_dir=tmp_path, patch_path=str(patch))
    context = SimpleNamespace(metadata=None)
    asyncio.run(agent.run("", environment, context))

    assert environment.upload == (patch.resolve(), "/tmp/swe-sweep-submission.patch")
    assert environment.command == (
        "git apply --binary --whitespace=nowarn /tmp/swe-sweep-submission.patch",
        "/workspace",
    )
    assert context.metadata == {"submission_patch": "submission.diff"}


def test_dockerhub_pull_placeholder(capsys):
    assert cli.main(["infra", "dockerhub", "pull", "--all", "--dry-run"]) == 1
    assert "No prebuilt task images are configured yet" in capsys.readouterr().err


def test_unknown_task_is_rejected(tmp_path):
    patch = tmp_path / "submission.diff"
    patch.write_text("")
    with pytest.raises(SystemExit, match="2"):
        cli.main(["eval", "not-a-task", str(patch)])
