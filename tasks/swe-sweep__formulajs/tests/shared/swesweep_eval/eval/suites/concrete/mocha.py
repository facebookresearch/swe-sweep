# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""MochaSuite suite adapter."""

from ..base import ReproductionSuite
from ..utils.javascript import _REPORT, _added_names, _parse_junit, _pattern, _resolve_bin, _run, _spec_files

class MochaSuite(ReproductionSuite):
    """mocha — mongoose and the older Node ecosystem.

    mocha has no built-in JUnit writer, so the xunit reporter writes the same shape to a
    file via ``--reporter-options output=``. ``--exit`` matters here: mongoose's suite holds
    a live database connection, and without it mocha hangs after the last test instead of
    returning, which the census would read as a timeout.
    """

    no_targets = "test patch touched no JavaScript test files"

    def __init__(self, all_files=()):
        self.all_files = list(all_files)

    def targets(self, diff, env=None):
        del env
        return _spec_files(diff), _added_names(diff)

    def run_tests(self, env, repo, files, names, timeout, jobs):
        files = self.all_files if files is None else files
        cmd = _resolve_bin(env, repo, "mocha") + list(files) + [
            "--reporter", "xunit", "--reporter-options", "output=" + _REPORT,
            "--exit", "--timeout", "60000",
        ]
        if names:
            cmd += ["--grep", _pattern(names)]
        rc, timed_out = _run(env, cmd, repo, timeout)
        if timed_out:
            return {}, 0, False, True
        outcomes, n, err = _parse_junit(env, _REPORT)
        if not outcomes and rc:
            return {}, 0, True, False
        return outcomes, n, err, False
