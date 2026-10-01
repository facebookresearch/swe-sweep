# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""LakeModuleSuite suite adapter."""

import os

from ..base import FullSuite
from ..utils.compiled import _all_error, _patched_files, _run
from ..utils.logging import log


class LakeModuleSuite(FullSuite):
    """Lean 4 / lake: one test is one module, and building it *is* running it.

    A Lean test is a source file that must elaborate. mathlib4 collects them in a
    ``lean_lib`` globbed over a directory (``MathlibTest``), so ``lake build
    MathlibTest.Foo`` type-checks that one file and exits non-zero if anything in it —
    or in the part of the library it imports — fails to elaborate. There is no separate
    run step and no report to parse: the exit status is the verdict.

    That also makes the pre-gold case work without any special handling. A test written
    against a fix that is not there does not "fail an assertion", it fails to elaborate,
    and lake says so.

    The build is incremental against the ``.olean`` tree the image downloaded from
    mathlib's own CI, so a subtask rebuilds the module its fix invalidates and that
    module's dependents — not the library.
    """

    no_targets = "test patch touched no Lean test module in the test library"

    def __init__(self, test_lib="MathlibTest", extension=".lean"):
        self.test_lib = test_lib.strip("/")
        self.extension = extension

    def _module(self, path):
        """``MathlibTest/Foo/Bar.lean`` → ``MathlibTest.Foo.Bar``, or ``None``."""
        if not path.endswith(self.extension):
            return None
        if not (path == self.test_lib + self.extension or path.startswith(self.test_lib + "/")):
            return None
        return path[: -len(self.extension)].replace("/", ".")

    # --- resolving the diff --------------------------------------------------

    def targets(self, diff, env=None):
        del env
        files = []
        names = []
        for path in _patched_files(diff):
            module = self._module(path)
            if module is None:
                continue
            files.append(path)
            names.append(module)
        return sorted(set(files)), sorted(set(names))

    # --- running -------------------------------------------------------------

    def _build(self, env, repo, targets, timeout, jobs):
        # No job flag: lake takes none (`lake build -j 8` is "unknown short option"), and
        # its parallelism comes from the environment instead — see `jobs_env` in
        # task.yaml.
        del jobs
        argv = ["lake", "build"] + list(targets)
        res = _run(env, argv, timeout=timeout, cwd=repo)
        if res is None:
            log("lake build TIMEOUT after %ds" % timeout)
            return None
        log("lake build %s rc=%d" % (" ".join(targets), res.returncode))
        return res

    def _run_modules(self, env, repo, names, timeout, jobs):
        """``(outcomes, n_run, timed_out, text)`` — one lake build per module.

        One process per module rather than one for all of them: lake reports a single
        exit status for the whole invocation, so a batch would smear one failing test
        over every other one it was asked to build.
        """
        outcomes = {}
        chunks = []
        for name in names:
            res = self._build(env, repo, [name], timeout, jobs)
            if res is None:
                return outcomes, len(outcomes), True, "\n".join(chunks)
            outcomes[name] = "passed" if res.returncode == 0 else "failed"
            chunks.append("$ lake build %s\n%s" % (name, res.stdout[-4000:]))
        return outcomes, len(outcomes), False, "\n".join(chunks)

    # --- the repro driver's adapter -------------------------------------------

    def run_tests(self, env, repo, files, names, timeout, jobs):
        del files
        if not names:
            return _all_error([]), 0, True, False
        outcomes, n_run, timed_out, _text = self._run_modules(env, repo, names, timeout, jobs)
        return outcomes, n_run, not outcomes, timed_out

    # --- the eval driver's adapters -------------------------------------------

    def run_all(self, env, repo, timeout, cap, jobs):
        """The visible suite: build the whole test library in one go."""
        res = self._build(env, repo, [self.test_lib], timeout, jobs)
        if res is None:
            return None, True, self._capture("lake build " + self.test_lib, "TIMEOUT", cap)
        outcome = "passed" if res.returncode == 0 else "failed"
        return (
            {self.test_lib: outcome},
            False,
            self._capture("lake build " + self.test_lib, res.stdout, cap),
        )

    def run_selected(self, env, repo, files, names, timeout, cap, jobs):
        del files
        outcomes, _n, timed_out, text = self._run_modules(env, repo, names, timeout, jobs)
        return outcomes, timed_out, self._capture("lake build " + " ".join(names), text, cap)

    @staticmethod
    def _capture(command, text, cap):
        clipped, truncated = cap.clip(text)
        return {"command": command, "returncode": None, "text": clipped, "truncated": truncated}
