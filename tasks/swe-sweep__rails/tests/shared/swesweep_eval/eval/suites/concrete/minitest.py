# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""MinitestSuite suite adapter."""

from ..base import ReproductionSuite
from ..utils.minitest import minitest_targets, run_minitest, run_minitest_all

class MinitestSuite(ReproductionSuite):
    """minitest over the ``*_test.rb`` files a test patch touches.

    Written for a monorepo of gems: Rails gives each gem its own ``bin/test``, load path and
    test helper, so a test only runs from inside its own gem and the touched files are
    grouped by that before anything is invoked.

    Each requested test gets its own process. That is not a stylistic choice — minitest's
    stock output is dots and a totals line, so a batched run can say how many tests failed
    but never which, and adding a reporting gem would change what the image ships. A patch
    adds a handful of tests, so this is a handful of processes.

    ``runner`` is the per-gem entry point and ``bundler`` prefixes ``bundle exec`` so the
    gems resolve to the versions the image installed.
    """

    no_targets = "test patch touched no _test.rb file"

    def __init__(self, runner="bin/test", bundler=True, all_command=None):
        self.runner = runner
        self.bundler = bundler
        self.all_command = list(all_command or ())

    def targets(self, diff, env=None):
        del env
        return minitest_targets(diff)

    def run_tests(self, env, repo, files, names, timeout, jobs):
        del jobs
        if files is None:
            if not self.all_command:
                raise ValueError("minitest evaluation requires an all_command for the visible suite")
            return run_minitest_all(env, repo, self.all_command, timeout)
        return run_minitest(env, repo, files, names, timeout, runner=self.runner, bundler=self.bundler)
