"""Cargo integration tests plus SQLLogicTest data files.

Targets the datafusion base-commit image (see ``tasks/datafusion/docker/``), which
holds the workspace at ``/repo`` with a source-only ``baseline`` tag and a warm
``target/`` beside it. The four ``repro`` stages are the generic computation — see
shared host reproduction workflow, driven by the suite below.

**datafusion has two test suites, and the second one is the bigger.** Beside the usual
per-crate ``<crate>/tests/*.rs``, most of its regression coverage is *SQL*: a case is a
query and its expected output appended to a ``.slt`` file under
``datafusion/sqllogictest/test_files/``, run by the crate's own ``sqllogictests`` harness.
Over half of all datafusion test patches touch nothing else, so a suite that only knew
about cargo integration tests would report most of the population as unmeasurable.

:class:`CargoSqlLogicSuite` therefore wraps the shared :class:`CargoSuite` and adds the
``.slt`` files as a suite of its own. The granularity is **one ``.slt`` file, not one
query**: ``sqllogictests`` sets ``harness = false``, so it prints no per-case line and
reports only its exit status. That is enough for what the stages ask — the file must fail
before the gold patch and pass after it — because everything in the file other than the
patch's own additions already passes at the baseline.

Selected by the task's declarative runner configuration.
"""
import os

from ..utils.compiled import _patched_files, _run
from ..utils.logging import log
from .cargo import CargoSuite

class CargoSqlLogicSuite(CargoSuite):
    """The cargo suite plus the ``.slt`` files, merged into one outcome set.

    A ``.slt`` file is carried through ``targets``/``run_tests`` as ``("slt", <path>)``,
    so the two halves can be told apart without re-reading the diff."""

    no_targets = "test patch touched no cargo integration-test or .slt file"

    def __init__(self, slt_dir, slt_crate, slt_target, **cargo):
        super().__init__(**cargo)
        self.slt_dir = slt_dir.rstrip("/") + "/"
        self.slt_crate = slt_crate
        self.slt_target = slt_target

    def targets(self, diff, env=None):
        found, names = CargoSuite.targets(self, diff, env=env)
        slt = sorted(
            set(p for p in _patched_files(diff) if p.startswith(self.slt_dir) and p.endswith(".slt"))
        )
        return found + [("slt", p) for p in slt], names

    def run_tests(self, env, repo, files, names, timeout, jobs):
        """Run both halves. The ``.slt`` half runs **one file per invocation** — the
        harness would happily take several filters at once, but then one exit status
        would have to stand for all of them, and a subtask that fixes one file while
        another is broken would be scored wrong."""
        if files is None:
            return CargoSuite.run_tests(self, env, repo, None, names, timeout, jobs)

        cargo_files = [f for f in files if f[0] != "slt"]
        slt_paths = [f[1] for f in files if f[0] == "slt"]

        outcomes, n, error, timed_out = ({}, 0, False, False)
        if cargo_files:
            outcomes, n, error, timed_out = CargoSuite.run_tests(
                self, env, repo, cargo_files, names, timeout, jobs
            )
            if timed_out:
                return outcomes, n, error, True

        for path in slt_paths:
            cmd = ["cargo", "test", "--test", self.slt_target, "--", os.path.basename(path)]
            r = _run(env, cmd, timeout=timeout, cwd=os.path.join(repo, self.slt_crate))
            if r is None:
                log("sqllogictests TIMEOUT after %ds (%s)" % (timeout, path))
                return outcomes, n, error, True
            log("sqllogictests %s rc=%d" % (path, r.returncode))
            log(r.stdout[-2000:])
            # `harness = false`: the exit status is the whole verdict for this file.
            outcomes["slt::" + os.path.basename(path)] = "passed" if r.returncode == 0 else "failed"
            n += 1
        return outcomes, n, error, timed_out
