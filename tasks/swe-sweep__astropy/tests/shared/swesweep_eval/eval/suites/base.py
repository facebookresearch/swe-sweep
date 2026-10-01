# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""Small object-oriented contracts shared by every test-suite adapter."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any, Self

from swesweep_eval.infra.container_session import ContainerSession

Targets = tuple[list[Any], list[str]]
Outcomes = dict[str, str]
ReproductionResult = tuple[Outcomes, int, bool, bool]
EvaluationResult = tuple[Outcomes | None, bool, dict[str, Any]]


class Suite(ABC):
    """A host-side adapter for one repository test framework."""

    no_targets: str

    @classmethod
    def from_config(
        cls,
        values: dict[str, Any],
        *,
        repo: str,
        create_suite: Callable[..., Suite],
    ) -> Self:
        """Construct this adapter from its task-owned YAML values."""
        del repo, create_suite
        return cls(**values)

    def stage(self, env: ContainerSession) -> None:
        """Copy an optional framework helper into the task container."""

    @abstractmethod
    def targets(self, diff: str, env: ContainerSession | None = None) -> Targets:
        """Resolve a hidden-test patch to runnable files and test names."""


class ReproductionSuite(Suite):
    """A suite that can run targeted tests before and after a gold patch."""

    @abstractmethod
    def run_tests(
        self,
        env: ContainerSession,
        repo: str,
        files: list[Any] | None,
        names: list[str],
        timeout: int,
        jobs: str,
    ) -> ReproductionResult:
        """Run the selected tests and return outcomes plus harness status."""


class EvaluationSuite(Suite):
    """A suite with both visible-suite and hidden-test entry points."""

    @abstractmethod
    def run_all(
        self,
        env: ContainerSession,
        repo: str,
        timeout: int,
        capture: Any,
        jobs: str,
    ) -> EvaluationResult:
        """Run the repository's visible regression suite."""

    @abstractmethod
    def run_selected(
        self,
        env: ContainerSession,
        repo: str,
        files: list[Any],
        names: list[str],
        timeout: int,
        capture: Any,
        jobs: str,
    ) -> EvaluationResult:
        """Run the hidden tests selected from one subtask patch."""


class FullSuite(ReproductionSuite, EvaluationSuite):
    """A framework adapter that implements both host runner protocols."""
