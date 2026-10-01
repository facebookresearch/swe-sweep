# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""Explicit operations on the repository inside an evaluation container."""

from __future__ import annotations

import subprocess
from pathlib import PurePosixPath

from swesweep_eval.infra.container_session import ContainerSession


def _build_argv(build_cmd: str | None, build_jobs_flag: str | None, jobs: str) -> list[str]:
    if build_cmd:
        return ["sh", "-c", build_cmd]
    command = ["python", "setup.py", "build_ext", "--inplace"]
    if build_jobs_flag:
        command += [build_jobs_flag, jobs]
    return command


class ContainerRepository:
    """A checked-out task repository accessed through one container session."""

    def __init__(self, env: ContainerSession, path: str):
        self.env = env
        self.path = path

    def git(self, *args: str):
        return self.env.execute(["git", "-C", self.path, *args])

    def reset(self) -> None:
        self.git("reset", "--hard", "baseline", "-q")
        self.git("clean", "-fdq")

    def patch_applies(self, patch: str) -> bool:
        return self.git("apply", "--check", "--whitespace=nowarn", patch).returncode == 0

    def apply_patch(self, patch: str) -> tuple[bool, str]:
        result = self.git("apply", "--whitespace=nowarn", patch)
        return result.returncode == 0, result.stderr

    def restore_files(self, files: list[str]) -> None:
        existing = [path for path in files if self.git("cat-file", "-e", f"baseline:{path}").returncode == 0]
        added = [path for path in files if path not in existing]
        if existing:
            self.git("checkout", "baseline", "--", *existing)
        for path in added:
            self.env.remove(str(PurePosixPath(self.path) / path))

    def build(
        self,
        *,
        jobs: str,
        jobs_env: str | None,
        build_jobs_env: tuple[str, ...] | list[str] | None,
        build_jobs_flag: str | None,
        build_cmd: str | None,
        timeout: int,
    ) -> tuple[bool, str]:
        command_env = {name: jobs for name in (build_jobs_env or ((jobs_env,) if jobs_env else ()))}
        command_env["SWESWEEP_BUILD_JOBS"] = jobs
        try:
            result = self.env.execute(
                _build_argv(build_cmd, build_jobs_flag, jobs),
                cwd=self.path,
                env=command_env,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return False, f"build timed out after {timeout}s"
        return result.returncode == 0, result.stderr[-800:]
