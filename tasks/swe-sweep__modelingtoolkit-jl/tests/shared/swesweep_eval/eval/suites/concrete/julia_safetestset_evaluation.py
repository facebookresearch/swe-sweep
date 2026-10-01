"""JuliaSafeTestsetEvaluationSuite suite adapter."""

from ..utils.julia import run_julia_files
from .julia_evaluation import JuliaEvaluationSuite


class JuliaSafeTestsetEvaluationSuite(JuliaEvaluationSuite):
    """The evaluation half of :class:`~.julia_safetestset.JuliaSafeTestsetSuite`.

    ``run_all`` names no target files, which the file driver resolves to every file the
    repo's own ``runtests.jl`` includes — the same files, named the same way, as a
    ``run_selected`` pass, so the visible-suite pass-set and the hidden-test outcomes are
    directly comparable. Unlike the monolithic Julia driver, this driver isolates every
    file and records a ``<load>`` error outcome for a file that raises, so those errors do
    not invalidate the structured outcomes from all other files."""

    def _captured(self, env, repo, files, names, timeout, cap):
        outcomes, timed_out, text, loaderror = run_julia_files(env, repo, files, names, timeout)
        clipped, truncated = cap.clip(text)
        captured = {
            "command": "julia -e 'Pkg.activate(...); Pkg.test()' files=%s" % (":".join(files) or "<all>"),
            "returncode": None,
            "text": clipped,
            "truncated": truncated,
        }
        # ``run_julia_files`` records each load error as ``<file>/<load>: error``. The
        # report therefore remains complete and useful even when one independent file
        # cannot load; the error is a normal non-passed outcome, not silently discarded.
        return outcomes, timed_out, captured
