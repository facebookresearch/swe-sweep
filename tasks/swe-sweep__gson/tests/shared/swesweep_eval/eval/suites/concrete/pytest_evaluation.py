"""PytestEvaluationSuite suite adapter."""

from ..base import EvaluationSuite
from ..utils.evaluation import run_pytest
from ..utils.pytest import target_tests

class PytestEvaluationSuite(EvaluationSuite):
    """The default eval suite: pytest, with the visible suite collected from ``pkg``.

    Mirrors :class:`ReproductionSuite` for the eval protocol, which needs one
    thing the repro protocol does not — a notion of **the whole suite**, the regression
    gate's reference. Three methods:

    - ``targets(diff)`` → ``(files, names)``, as in the repro suite.
    - ``run_all(repo, timeout, cap, jobs)`` → ``(outcomes|None, timed_out, captured)``
      for the visible suite.
    - ``run_selected(repo, files, names, timeout, cap, jobs)`` → the same triple, for
      one subtask's hidden tests.

    ``suite_args`` reach ``run_all`` only, never ``run_selected``: a flag that
    deselects tests must not be able to deselect the test that proves a bug."""

    no_targets = "test patch touched no .py test files"

    @classmethod
    def from_config(cls, values, *, repo, create_suite):
        target_spec = values.pop("target_suite", None)
        target_suite = create_suite(target_spec, repo=repo) if target_spec else None
        return cls(
            pkg=values.pop("paths"),
            suite_args=values.pop("visible_args", ()),
            target_suite=target_suite,
            **values,
        )

    def __init__(self, pkg, suite_args=(), target_suite=None):
        self.paths = [pkg] if isinstance(pkg, str) else list(pkg)
        self.suite_args = tuple(suite_args)
        self.target_suite = target_suite
        if target_suite is not None:
            self.no_targets = target_suite.no_targets

    def targets(self, diff, env=None):
        if self.target_suite is not None:
            return self.target_suite.targets(diff, env=env)
        return target_tests(diff)

    def run_all(self, env, repo, timeout, cap, jobs):
        return run_pytest(env, repo, self.paths, [], timeout, cap, self.suite_args)

    def run_selected(self, env, repo, files, names, timeout, cap, jobs):
        return run_pytest(env, repo, files, names, timeout, cap)
