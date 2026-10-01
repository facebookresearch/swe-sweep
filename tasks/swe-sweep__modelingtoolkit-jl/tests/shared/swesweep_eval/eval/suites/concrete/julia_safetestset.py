"""JuliaSafeTestsetSuite suite adapter."""

from ..utils.julia import run_julia_files
from .julia import JuliaSuite


class JuliaSafeTestsetSuite(JuliaSuite):
    """A Julia package whose ``runtests.jl`` is a list of ``@safetestset`` includes.

    ``@safetestset`` runs every test file in a module of its own, so the plain
    :class:`JuliaSuite` cannot select anything: its driver intercepts ``include`` inside
    its own module, and the modules the macro creates do not route through it — the whole
    suite runs whatever the targets say. This adapter includes each target file into a
    fresh module directly instead, which is the contract those files already meet."""

    def run_tests(self, env, repo, files, names, timeout, jobs):
        outcomes, timed_out, _text, loaderror = run_julia_files(env, repo, files, names, timeout)
        if timed_out:
            return {}, 0, False, True
        if outcomes is None:
            return {}, 0, True, False
        return outcomes, len(outcomes), loaderror, False
