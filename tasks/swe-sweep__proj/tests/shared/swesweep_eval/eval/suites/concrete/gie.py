# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""GieSuite suite adapter."""

import os

from ..base import FullSuite
from ..utils.compiled import _run
from ..utils.logging import log


class GieSuite(FullSuite):
    """PROJ's ``gie``, one test case per data file.

    ``gie`` ("geospatial integrity investigation environment") is PROJ's own regression
    harness: a ``.gie`` file is a list of coordinate transformations with the answer each
    one is supposed to give, and ``gie <file>`` checks them and exits non-zero if any
    disagree. It is where most transform regressions in PROJ are actually expressed —
    "this pipeline is wrong by two metres" is a three-line ``.gie`` case and no C++ at
    all.

    The file *is* the test case, so there is nothing to parse out of the diff: a patched
    ``.gie`` path is a name, and the outcome is that one run's exit status.

    Why this rather than driving the same files through CTest, which does register one
    case per ``.gie``: CMake registers them under **hand-written labels**
    (``gie/builtins.gie`` is the test ``Builtins``), so the case cannot be derived from
    the path the way :class:`CTestPathNamesSuite` derives geos's. Running the program
    directly needs no name at all — and no JUnit report, which a period-correct PROJ
    image's ctest is too old to write.

    Nothing is built here. ``gie`` links the library the task's ``build_cmd`` has already
    rebuilt, and the data files are read at run time.
    """

    no_targets = "test patch touched no .gie case"

    def __init__(self, binary="/build/bin/gie", roots=("test/gie", "test/gigs"), ext=".gie"):
        self.binary = binary
        self.roots = tuple(r.rstrip("/") for r in roots)
        self.ext = ext

    # --- resolving the diff --------------------------------------------------

    def _is_case(self, path):
        return path.endswith(self.ext) and any(path.startswith(r + "/") for r in self.roots)

    def targets(self, diff, env=None):
        del env
        from ..utils.compiled import _patched_files

        files = sorted({path for path in _patched_files(diff) if self._is_case(path)})
        return files, list(files)

    # --- the one real implementation -----------------------------------------

    def _discover(self, env, repo):
        """Every ``.gie`` case in the tree, repo-relative."""
        found = []
        for root in self.roots:
            for path in env.find_files(os.path.join(repo, root)):
                if path.endswith(self.ext):
                    found.append(os.path.relpath(path, repo))
        return sorted(found)

    def _run_cases(self, env, repo, names, timeout):
        """``(outcomes, n_run, error, timed_out, text)``.

        Each case is one ``gie`` invocation, from the ``test/`` directory — the working
        directory upstream's own ``add_test`` uses, because a ``.gie`` file may reference
        a grid beside it by relative path."""
        if not env.exists(self.binary):
            log("gie binary missing: " + self.binary)
            return {}, 0, True, False, "gie binary missing: " + self.binary
        outcomes = {}
        chunks = []
        timed_out = False
        cwd = os.path.join(repo, "test")
        for name in names:
            res = _run(env, [self.binary, os.path.join(repo, name)], timeout=timeout, cwd=cwd)
            if res is None:
                log("gie TIMEOUT on %s" % name)
                timed_out = True
                break
            outcomes[name] = "passed" if res.returncode == 0 else "failed"
            chunks.append("$ gie %s -> rc=%d\n%s" % (name, res.returncode, res.stdout[-1500:]))
        return outcomes, len(outcomes), False, timed_out, "\n".join(chunks)

    # --- the repro driver's adapter -------------------------------------------

    def run_tests(self, env, repo, files, names, timeout, jobs):
        del jobs
        outcomes, n_run, error, timed_out, _text = self._run_cases(env, repo, names, timeout)
        return outcomes, n_run, error or (not outcomes and not timed_out), timed_out

    # --- the eval driver's adapters -------------------------------------------

    def run_all(self, env, repo, timeout, cap, jobs):
        del jobs
        outcomes, _n, _e, timed_out, text = self._run_cases(env, repo, self._discover(env, repo), timeout)
        return outcomes, timed_out, self._capture("gie (whole corpus)", text, cap)

    def run_selected(self, env, repo, files, names, timeout, cap, jobs):
        del jobs
        outcomes, _n, _e, timed_out, text = self._run_cases(env, repo, names, timeout)
        return outcomes, timed_out, self._capture("gie " + " ".join(names), text, cap)

    @staticmethod
    def _capture(command, text, cap):
        clipped, truncated = cap.clip(text)
        return {"command": command, "returncode": None, "text": clipped, "truncated": truncated}
