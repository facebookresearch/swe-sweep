# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""ReproductionEvaluationSuite suite adapter."""

from contextlib import redirect_stderr
from io import StringIO

from ..base import EvaluationSuite, ReproductionSuite

class ReproductionEvaluationSuite(EvaluationSuite):
    """Adapt a reproduction suite to the eval protocol.

    Reproduction suites already know how to map a hidden patch to tests and how to run
    those tests. Eval adds one convention: ``run_tests(..., files=None, names=[])`` means
    the suite's complete visible-test population. The adapter captures the suite's normal
    stderr transcript so eval retains diagnostics without duplicating every framework's
    runner in this module.
    """

    def __init__(self, suite):
        self.suite = suite
        self.no_targets = suite.no_targets

    @classmethod
    def from_config(cls, values, *, repo, create_suite):
        suite = create_suite(values.pop("suite"), repo=repo)
        if values:
            raise ValueError(f"repro-eval suite has unknown keys: {', '.join(sorted(values))}")
        if not isinstance(suite, ReproductionSuite):
            raise ValueError("repro-eval must wrap a reproduction suite")
        return cls(suite)

    def targets(self, diff, env=None):
        return self.suite.targets(diff, env=env)

    def stage(self, env):
        self.suite.stage(env)

    def _run(self, env, repo, files, names, timeout, cap, jobs):
        transcript = StringIO()
        with redirect_stderr(transcript):
            outcomes, _n, error, timed_out = self.suite.run_tests(
                env, repo, files, names, timeout, jobs)
        if error and not outcomes:
            keys = list(names) or ["<suite>"]
            outcomes = dict((key, "error") for key in keys)
        text = transcript.getvalue()
        clipped, truncated = cap.clip(text)
        captured = {
            "command": "suite.run_tests (whole suite)" if files is None else "suite.run_tests (selected)",
            # The reproduction-suite protocol exposes a semantic error flag, not the
            # child process's exact exit code. Do not invent one in the eval log.
            "returncode": None,
            "text": clipped,
            "truncated": truncated,
        }
        return (None if timed_out else outcomes), timed_out, captured

    def run_all(self, env, repo, timeout, cap, jobs):
        return self._run(env, repo, None, [], timeout, cap, jobs)

    def run_selected(self, env, repo, files, names, timeout, cap, jobs):
        return self._run(env, repo, files, names, timeout, cap, jobs)
