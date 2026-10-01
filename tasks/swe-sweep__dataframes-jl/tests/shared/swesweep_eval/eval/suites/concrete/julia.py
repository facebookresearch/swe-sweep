"""JuliaSuite suite adapter."""

from ..base import ReproductionSuite
from ..utils.julia import run_julia, target_tests

class JuliaSuite(ReproductionSuite):
    """Julia implementation of the reproduction-suite protocol."""

    no_targets = "test patch touched no .jl test files"

    def targets(self, diff, env=None):
        del env
        return target_tests(diff)

    def run_tests(self, env, repo, files, names, timeout, jobs):
        outcomes, timed_out, _text, loaderror = run_julia(env, repo, files, names, timeout)
        if timed_out:
            return {}, 0, False, True
        if outcomes is None:
            return {}, 0, True, False
        return outcomes, len(outcomes), loaderror, False
