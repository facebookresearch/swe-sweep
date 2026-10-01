"""ClippyUiSuite suite adapter."""

import subprocess

from ..base import ReproductionSuite
from ..utils.compiled import _patched_files
from ..utils.logging import log
from ..utils.managed import _UI_DIR_RE

class ClippyUiSuite(ReproductionSuite):
    """clippy's ``tests/ui`` corpus, driven by ``ui_test`` through one cargo test target.

    A clippy bug is a lint firing wrongly, and its test is a source file under ``tests/ui/``
    paired with the exact diagnostics it must produce (``.stderr``) and, for a lint that
    suggests a rewrite, the rewritten source (``.fixed``). :class:`CargoSuite` cannot address
    these: they are *data* for the ``compile-test`` target, not cargo test targets, so cargo's
    own ``--exact`` name filter never sees them.

    ``ui_test`` filters instead on **file name**, through the ``TESTNAME`` environment
    variable, so this suite resolves the patch to case stems and runs one invocation per
    stem. Per-stem rather than one comma-separated run because the harness reports its
    verdict in the exit code, and the census wants an outcome per test rather than one for
    the batch — the first invocation pays for the build and the rest are cheap.
    """

    no_targets = "test patch touched no tests/ui case"

    def targets(self, diff, env=None):
        del env
        """``([stems], [stems])`` — the same list twice: for this harness the file *is* the
        test, so there is no second, finer level to narrow to."""
        stems = []
        for path in _patched_files(diff):
            m = _UI_DIR_RE.match(path)
            if m:
                stem = m.group("stem")
                if stem not in stems:
                    stems.append(stem)
        return sorted(stems), sorted(stems)

    def run_tests(self, env, repo, files, names, timeout, jobs):
        if files is None:
            cmd = ["cargo", "test", "-q", "--test", "compile-test"]
            log("$ " + " ".join(cmd))
            try:
                r = env.execute(cmd, cwd=repo, timeout=timeout, merge_stderr=True)
            except subprocess.TimeoutExpired:
                log("cargo test TIMEOUT after %ds" % timeout)
                return {}, 0, False, True
            log(r.stdout[-1500:])
            return {"clippy-ui::<suite>": "passed" if r.returncode == 0 else "failed"}, 1, False, False
        outcomes = {}
        had_error = False
        deadline_hit = False
        for stem in files:
            command_env = {"TESTNAME": stem}
            # `--test compile-test` is the ui_test harness; `-q` keeps cargo's own progress
            # out of the log without hiding the harness's failure output.
            cmd = ["cargo", "test", "-q", "--test", "compile-test"]
            log("$ TESTNAME=%s %s" % (stem, " ".join(cmd)))
            try:
                r = env.execute(cmd, cwd=repo, timeout=timeout, env=command_env, merge_stderr=True)
            except subprocess.TimeoutExpired:
                log("cargo test TIMEOUT after %ds" % timeout)
                deadline_hit = True
                break
            log(r.stdout[-1500:])
            if r.returncode == 0:
                outcomes[stem] = "passed"
                continue
            # A build failure is not a failed case: nothing ran, and the driver has to treat
            # it the way a pytest collection error is treated. ui_test prints its own summary
            # line for a real test failure, so the absence of one means the crate did not
            # compile.
            if "error: could not compile" in r.stdout or "error[E" in r.stdout:
                outcomes[stem] = "error"
                had_error = True
            else:
                outcomes[stem] = "failed"
        n = len([o for o in outcomes.values() if o != "skipped"])
        return outcomes, n, had_error, deadline_hit
