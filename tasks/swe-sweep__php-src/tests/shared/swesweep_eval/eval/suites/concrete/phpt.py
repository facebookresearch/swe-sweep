# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""PhptSuite suite adapter."""

import os
import re

from ..base import ReproductionSuite
from ..utils.compiled import _patched_files, _run
from ..utils.logging import log

# run-tests.php colours its status word unconditionally — even into a pipe — so every line
# is stripped of ANSI escapes before it is matched.
_ANSI = re.compile(r"\033\[[0-9;]*m")

# run-tests.php draws a live progress counter and rubs it out with a **carriage return**,
# not a newline, so a result arrives as `TEST 12/515 [...]\r\033[1;32mPASS\033[0m …` — one
# `\n`-delimited line holding both. Splitting on either character is what puts the status
# word back at the start of its own line, which is where `_RESULT` expects it.
_LINES = re.compile(r"[\r\n]")

# One result line: `PASS Test description [ext/standard/tests/strings/str_pad.phpt]`.
# The path in brackets is the unit — the description is free text and is not unique.
_RESULT = re.compile(r"^([A-Z]+(?:&[A-Z]+)*)\s+.*\[([^\]]+\.phpt)\]")

# What each of run-tests.php' statuses means in this benchmark's vocabulary.
#
# `XFAIL`/`XLEAK` are tests the suite *expects* to fail — a `--XFAIL--` section names the
# open bug — so they carry no signal either way and are treated as not run. `BORK` is the
# harness saying the `.phpt` is malformed and it never ran the code; that is an error, not
# a failed assertion. `WARN` is likewise a harness complaint, not a verdict.
_OUTCOME = {
    "PASS": "passed",
    "FAIL": "failed",
    "LEAK": "failed",
    "LEAK&FAIL": "failed",
    "SKIP": "skipped",
    "XFAIL": "skipped",
    "XLEAK": "skipped",
    "XFAIL&LEAK": "skipped",
    "BORK": "error",
    "WARN": "error",
    "REDIRECT": "skipped",
}


class PhptSuite(ReproductionSuite):
    """PHP's ``.phpt`` format, driven by the in-tree ``run-tests.php``.

    A ``.phpt`` file **is** a test case: one script, one expected output, compared whole.
    So the file is both the selector and the outcome key, ``names`` is always empty, and
    there is nothing smaller to narrow to. It is also why a fix's test half is almost
    always a *new* file rather than an edit — the convention is one regression file per
    tracker issue.

    The harness runs each case in its own PHP process, which is what makes the commonest
    bug shape in this repo survivable: a segfault in the engine fails one case instead of
    taking the report down with it.

    ``run-tests.php`` is invoked *by the built interpreter* rather than by a system PHP,
    because it defaults to testing ``PHP_BINARY`` — the binary running it. That keeps the
    suite honest without threading a path through the configuration.

    **A fixture is not a target.** ``ext/*/tests/*.inc`` files are shared helpers that any
    number of cases include, so a patch confined to them resolves to nothing rather than
    to a guess.
    """

    no_targets = "test patch touched no .phpt file"

    def __init__(self, runner="run-tests.php", php="sapi/cli/php", extra_args=("-q", "--offline")):
        self.runner = runner
        self.php = php
        self.extra_args = list(extra_args)

    def targets(self, diff, env=None):
        """``([.phpt paths], [])`` — the file is the case, so there is no name to narrow
        to."""
        del env
        found = [path for path in _patched_files(diff) if path.endswith(".phpt")]
        return sorted(set(found)), []

    def run_tests(self, env, repo, files, names, timeout, jobs):
        """Run the selected cases in one ``run-tests.php`` invocation.

        ``files is None`` is eval's "the whole visible suite": run-tests.php with no paths
        walks the tree and runs everything it finds.
        """
        del names
        argv = [self.php, self.runner] + self.extra_args
        if jobs:
            argv.append("-j%s" % jobs)
        argv += list(files or [])
        result = _run(env, argv, timeout=timeout, cwd=repo)
        if result is None:
            log("run-tests.php TIMEOUT after %ds" % timeout)
            return {}, 0, False, True
        log("run-tests.php rc=%d" % result.returncode)
        log(result.stdout[-3000:])

        outcomes = self._parse(result.stdout, repo)
        # A selected case that produced no result line never ran: run-tests.php did not
        # recognise the path, or the interpreter it was told to use is not there. That is
        # the harness `error` flag, not a failed assertion — "the test does not run" and
        # "the test fails" have to differ post-gold.
        missing = [path for path in (files or []) if path not in outcomes]
        if missing:
            log("no run-tests.php result for: %s" % ", ".join(sorted(missing)))
        error = bool(missing)
        n = len([value for value in outcomes.values() if value != "skipped"])
        return outcomes, n, error, False

    @staticmethod
    def _parse(text, repo):
        """``{repo-relative .phpt path: outcome}`` from one run-tests.php transcript.

        The path it prints is whatever it was handed, which for the whole-suite walk is an
        absolute path inside the container — normalised back to repo-relative so the two
        run modes produce the same keys.
        """
        prefix = repo.rstrip("/") + "/"
        outcomes = {}
        for raw in _LINES.split(text):
            match = _RESULT.match(_ANSI.sub("", raw).strip())
            if not match:
                continue
            status, path = match.group(1), match.group(2)
            if os.path.isabs(path) and path.startswith(prefix):
                path = path[len(prefix) :]
            outcomes[path] = _OUTCOME.get(status, "failed")
        return outcomes
