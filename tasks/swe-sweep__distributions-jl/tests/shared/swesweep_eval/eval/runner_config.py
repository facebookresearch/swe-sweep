"""Load declarative task runner configuration and construct host-side suites."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from swesweep_eval.eval.suites.base import EvaluationSuite, ReproductionSuite
from swesweep_eval.eval.suites.concrete.pytest import PytestSuite
from swesweep_eval.eval.suites.concrete.pytest_evaluation import PytestEvaluationSuite
from swesweep_eval.eval.suites.concrete.reproduction_evaluation import ReproductionEvaluationSuite
from swesweep_eval.eval.suites.registry import SUITES


@dataclass(frozen=True)
class EvalRunnerConfig:
    repo: str
    paths: str | tuple[str, ...] | list[str] | None = None
    jobs_env: str | None = None
    build_jobs_env: tuple[str, ...] | list[str] | None = None
    build_jobs_flag: str | None = None
    build_cmd: str | None = None
    setup_cmd: str | None = None
    setup_timeout: int = 600
    visible_timeout: int = 3600
    test_timeout: int = 900
    build_timeout: int = 7200
    needs_build: bool = True
    visible_args: tuple[str, ...] | list[str] = ()
    suite: EvaluationSuite | None = None
    test_dirs: tuple[str, ...] | list[str] = ()

    def resolved_suite(self) -> EvaluationSuite:
        return self.suite or PytestEvaluationSuite(self.paths, self.visible_args)


@dataclass(frozen=True)
class ReproRunnerConfig:
    repo: str
    jobs_env: str | None = None
    build_jobs_env: tuple[str, ...] | list[str] | None = None
    build_jobs_flag: str | None = None
    build_cmd: str | None = None
    setup_cmd: str | None = None
    setup_timeout: int = 600
    test_timeout: int = 600
    build_timeout: int = 3600
    needs_build: bool = True
    suite: ReproductionSuite | None = None

    def resolved_suite(self) -> ReproductionSuite:
        return self.suite or PytestSuite()


def _section(values: Mapping[str, Any] | None, name: str) -> dict[str, Any]:
    if not isinstance(values, Mapping):
        raise ValueError(f"task.yaml must contain a {name} mapping")
    return dict(values)


def load_repro_config(values: Mapping[str, Any] | None, container_repo: str) -> ReproRunnerConfig:
    """Construct one task's reproduction runner from its ``task.yaml`` section."""
    values = _section(values, "reproduction")
    suite_spec = values.pop("suite", None)
    suite = SUITES.create(suite_spec, repo=container_repo)
    if suite is not None and not isinstance(suite, ReproductionSuite):
        raise ValueError("reproduction must select a reproduction suite")
    return ReproRunnerConfig(repo=container_repo, suite=suite, **values)


def load_eval_config(
    reproduction: Mapping[str, Any] | None,
    evaluation: Mapping[str, Any] | None,
    container_repo: str,
) -> EvalRunnerConfig:
    """Construct one task's evaluation runner from its ``task.yaml`` sections."""
    repro_values = _section(reproduction, "reproduction")
    values = _section(evaluation, "evaluation")
    for key in (
        "jobs_env",
        "build_jobs_env",
        "build_jobs_flag",
        "build_cmd",
        "setup_cmd",
        "setup_timeout",
        "test_timeout",
        "build_timeout",
        "needs_build",
    ):
        if key not in values and key in repro_values:
            values[key] = repro_values[key]
    suite_spec = values.pop("suite", None)
    reproduction = SUITES.create(repro_values.get("suite"), repo=container_repo)
    if suite_spec == "reproduction":
        if not isinstance(reproduction, ReproductionSuite):
            raise ValueError("evaluation suite 'reproduction' requires a reproduction suite")
        suite = ReproductionEvaluationSuite(reproduction)
    else:
        suite = SUITES.create(suite_spec, repo=container_repo)
    if suite is not None and not isinstance(suite, EvaluationSuite):
        raise ValueError("evaluation must select an evaluation suite")
    return EvalRunnerConfig(repo=container_repo, suite=suite, **values)
