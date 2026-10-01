# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""JuliaEvaluationSuite suite adapter."""

from ..base import EvaluationSuite
from ..utils.julia import run_julia, target_tests

class JuliaEvaluationSuite(EvaluationSuite):
    """Julia implementation of the evaluation-suite protocol.

    ``run_all`` names no target files, which is the driver's "run everything" branch — the
    visible suite is whatever the package's own ``runtests.jl`` declares. There is no
    ``suite_args`` analogue: ``Pkg.test()`` has no flag that deselects a slow tail."""

    no_targets = "test patch touched no .jl test files"

    def targets(self, diff, env=None):
        del env
        return target_tests(diff)

    def run_all(self, env, repo, timeout, cap, jobs):
        return self._captured(env, repo, [], [], timeout, cap)

    def run_selected(self, env, repo, files, names, timeout, cap, jobs):
        return self._captured(env, repo, files, names, timeout, cap)

    def _captured(self, env, repo, files, names, timeout, cap):
        outcomes, timed_out, text, loaderror = run_julia(env, repo, files, names, timeout)
        clipped, truncated = cap.clip(text)
        captured = {
            "command": "julia -e 'Pkg.activate(...); Pkg.test()' targets=%s" % (":".join(files) or "<all>"),
            "returncode": None,
            "text": clipped,
            "truncated": truncated,
        }
        # A load error means the suite never really ran, so it must not read as
        # "0 regressions" against the baseline pass-set.
        return (None if loaderror else outcomes), timed_out, captured
