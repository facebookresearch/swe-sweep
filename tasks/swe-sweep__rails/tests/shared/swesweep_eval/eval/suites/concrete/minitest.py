"""MinitestSuite suite adapter."""

from ..base import ReproductionSuite
from ..utils.minitest import minitest_targets, run_minitest, run_minitest_all, run_minitest_per_test

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
    gems resolve to the versions the image installed. ``per_test`` runs the visible suite as
    ``runner -v`` in each gem, one outcome per test, in place of ``all_command``.
    """

    no_targets = "test patch touched no _test.rb file"

    def __init__(self, runner="bin/test", bundler=True, all_command=None, per_test=False):
        self.runner = runner
        self.bundler = bundler
        self.all_command = list(all_command or ())
        self.per_test = bool(per_test)

    def targets(self, diff, env=None):
        del env
        return minitest_targets(diff)

    def run_tests(self, env, repo, files, names, timeout, jobs):
        del jobs
        if files is None:
            if self.per_test:
                return run_minitest_per_test(env, repo, timeout, runner=self.runner, bundler=self.bundler)
            if not self.all_command:
                raise ValueError("minitest evaluation requires an all_command for the visible suite")
            return run_minitest_all(env, repo, self.all_command, timeout)
        return run_minitest(env, repo, files, names, timeout, runner=self.runner, bundler=self.bundler)
