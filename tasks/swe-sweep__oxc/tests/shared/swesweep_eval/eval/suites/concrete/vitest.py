# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""VitestSuite suite adapter."""

from ..base import ReproductionSuite
from ..utils.javascript import _REPORT, _added_names, _parse_junit, _pattern, _resolve_bin, _run, _spec_files

class VitestSuite(ReproductionSuite):
    """vitest — nuxt and most of the modern TypeScript ecosystem.

    ``vitest run`` is the non-watch mode; the JUnit reporter is built in. Files are passed
    as positional filters (vitest treats them as path substrings, which is what we want:
    the patch's path is relative to the repo root and so is vitest's matching).
    """

    no_targets = "test patch touched no JavaScript test files"

    def targets(self, diff, env=None):
        del env
        return _spec_files(diff), _added_names(diff)

    def run_tests(self, env, repo, files, names, timeout, jobs):
        cmd = _resolve_bin(env, repo, "vitest") + ["run"] + list(files or ()) + [
            "--reporter=junit", "--outputFile=" + _REPORT,
            # One process, no watcher: the census runs one subtask per container and a
            # worker pool only adds startup cost and log interleaving.
            "--pool=forks", "--poolOptions.forks.singleFork=true",
        ]
        if names:
            cmd += ["-t", _pattern(names)]
        rc, timed_out = _run(env, cmd, repo, timeout)
        if timed_out:
            return {}, 0, False, True
        outcomes, n, err = _parse_junit(env, _REPORT)
        # No report at all with a non-zero rc is a whole-suite failure (vitest could not
        # start, or every spec failed to load), not "nothing to run".
        if not outcomes and rc:
            return {}, 0, True, False
        return outcomes, n, err, False
