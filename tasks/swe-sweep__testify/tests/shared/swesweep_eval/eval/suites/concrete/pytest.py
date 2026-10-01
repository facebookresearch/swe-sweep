# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""PytestSuite suite adapter."""

from ..base import ReproductionSuite
from ..utils.pytest import run_pytest, target_tests

class PytestSuite(ReproductionSuite):
    """The default test suite: pytest over the ``.py`` files the test patch touches.

    A *suite* is the pair of things :func:`run` cannot know on its own — **which** tests
    a test patch targets, and **how** to run them — bundled behind two methods:

    - ``targets(diff)`` → ``(files, names)``. ``files`` is what is handed back to
      ``run_tests`` (and what an empty value means "this patch targets no test of mine",
      which ends the check); ``names`` are the individual test ids, counted as
      ``n_target_tests``.
    - ``run_tests(repo, files, names, timeout, jobs)`` → ``(outcomes, n_run, error,
      timed_out)``, where ``outcomes`` maps a test id to ``passed`` / ``failed`` /
      ``error`` / ``skipped`` and ``error`` flags a whole-suite failure (a collection
      error here, a compile error for a compiled suite) — which counts as failing
      pre-gold and as *not* passing post-gold.

    ``jobs`` is the build parallelism; pytest has no use for it, but a compiled suite
    has to build the test binaries itself (see the compiled-suite helpers)."""

    no_targets = "test patch touched no .py test files"

    def targets(self, diff, env=None):
        del env
        return target_tests(diff)

    def run_tests(self, env, repo, files, names, timeout, jobs):
        return run_pytest(env, repo, files, names, timeout)
