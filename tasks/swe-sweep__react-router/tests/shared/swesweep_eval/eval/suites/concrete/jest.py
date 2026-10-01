# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""JestSuite suite adapter."""

import re

from ..base import ReproductionSuite
from ..utils.javascript import _JSON_REPORT, _added_names, _parse_jest_json, _pattern, _resolve_bin, _run, _spec_files

class JestSuite(ReproductionSuite):
    """jest — babel, aws-cdk, prisma, and jest's own suite.

    Two things differ from the other two runners. **File selection is by regex**: jest's
    positional arguments are patterns matched against the full path, not paths, so each file
    is escaped before it is passed — an unescaped ``.`` in ``foo.test.js`` would otherwise
    also match ``fooXtest.js``. And **the report is jest's own JSON** rather than JUnit (see
    ``_parse_jest_json``).

    ``--runInBand`` keeps everything in one process: the census already runs one subtask per
    container, so jest's worker pool would only add startup cost, and several of these repos'
    suites are not safe to run in parallel against a shared fixture directory.

    ``config`` names a jest config file when the repo does not put its config where jest
    looks by default. That is a jest feature rather than a per-repo value: a repo with
    several environments keeps one config per environment and selects with ``--config``
    (ant-design has ``.jest.js`` for jsdom beside ``.jest.node.js`` and ``.jest.image.js``,
    and jest finds none of them on its own).

    ``spec_patterns`` widens what counts as a spec file, for a repo whose naming jest's
    default ``testMatch`` accepts but ``_SPEC_RE`` does not — see ``_spec_files``.
    """

    no_targets = "test patch touched no JavaScript test files"

    def __init__(self, config=None, spec_patterns=()):
        self.config = config
        self.spec_res = tuple(re.compile(p) for p in spec_patterns)

    def targets(self, diff, env=None):
        del env
        return _spec_files(diff, self.spec_res), _added_names(diff)

    def run_tests(self, env, repo, files, names, timeout, jobs, extra_args=(), command_env=None):
        files = list(files or ())
        cmd = _resolve_bin(env, repo, "jest") + list(extra_args)
        if self.config:
            cmd += ["--config", self.config]
        cmd += [re.escape(f) for f in files] + [
            # `--ci` is load-bearing beyond turning off the interactive UI: a test the patch
            # adds has no stored snapshot, and outside CI mode jest *writes* the missing
            # snapshot and passes — which would make the pre-gold run pass too.
            "--ci", "--runInBand", "--json", "--outputFile=" + _JSON_REPORT,
            # The census reads per-test outcomes, never coverage, and a repo whose config
            # turns coverage on (aws-cdk's packages do) pays for instrumenting the whole
            # package on every subtask — and then exits non-zero on an unmet global
            # threshold, which has nothing to do with the bug.
            "--coverage=false",
        ]
        if names:
            cmd += ["-t", _pattern(names)]
        rc, timed_out = _run(env, cmd, repo, timeout, command_env=command_env)
        if timed_out:
            return {}, 0, False, True
        outcomes, n, err = _parse_jest_json(env, _JSON_REPORT)
        # No report at all with a non-zero rc is a whole-suite failure (jest could not start,
        # or the config is unusable), not "nothing to run".
        if not outcomes and rc:
            return {}, 0, True, False
        return outcomes, n, err, False
