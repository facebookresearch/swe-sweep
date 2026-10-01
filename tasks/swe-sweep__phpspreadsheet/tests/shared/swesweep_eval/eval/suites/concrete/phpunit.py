"""PhpUnitSuite suite adapter."""

import os
import re

from ..base import ReproductionSuite
from ..utils.compiled import _parse_junit, _patched_files, _run
from ..utils.logging import log
from ..utils.scripting import (
    _PHPUNIT_XML,
    _PHP_ANY_METHOD_RE,
    _PHP_HUNK_RE,
    _PHP_TEST_ANNOT_RE,
    _PHP_TEST_METHOD_RE,
)


class PhpUnitSuite(ReproductionSuite):
    """PHPUnit, one invocation per test file the patch touches.

    PHPUnit is run out of the repo's own ``vendor/bin``, never off ``PATH``: the version
    under test is the one composer installed into the base-commit image, which is what keeps
    it period-correct — the same reason the JS suites go through ``npx --no-install``.

    It writes the **same JUnit XML** surefire and CTest do, so the report is parsed by the
    shared reader. ``--filter`` narrows within the selected files by method name, the same
    narrowing (not identity) the JS suites' ``-t`` gives.

    ``phpunit_args`` are the repo's own flags, and ``config`` names its ``phpunit.xml`` when
    the default lookup does not find one.
    """

    no_targets = "test patch touched no PHPUnit test file"

    def __init__(self, phpunit_args=(), config=None, binary="vendor/bin/phpunit"):
        self.phpunit_args = list(phpunit_args)
        self.config = config
        self.binary = binary

    def targets(self, diff, env=None):
        del env
        """``([test file paths], [test method names])``.

        An annotated method (``@test`` / ``#[Test]``) does not have to be named ``test*``,
        so an annotation arms the next added signature. A method whose body alone changes
        is recovered from the diff hunk header.
        """
        found = [p for p in _patched_files(diff) if p.endswith("Test.php")]
        names = []
        armed = False
        for line in diff.splitlines():
            if _PHP_TEST_ANNOT_RE.match(line):
                armed = True
                continue
            m = _PHP_TEST_METHOD_RE.match(line) or _PHP_HUNK_RE.match(line)
            if m:
                names.append(m.group(1))
                armed = False
                continue
            if armed:
                other = _PHP_ANY_METHOD_RE.match(line)
                if other:
                    names.append(other.group(1))
                    armed = False
                elif line.startswith("+") and line[1:].strip() and not line[1:].lstrip().startswith(
                    ("*", "/", "#[")
                ):
                    armed = False
        return sorted(set(found)), sorted(set(names))

    @staticmethod
    def _filter(names):
        """PHPUnit's ``--filter`` regex: the selected methods, or the whole file."""
        if not names:
            return None
        alternatives = "|".join(re.escape(name) for name in sorted(set(names)))
        return "/::(" + alternatives + ")( |$)/"

    def run_tests(self, env, repo, files, names, timeout, jobs):
        del jobs
        cmd = [os.path.join(repo, self.binary)]
        if self.config:
            cmd += ["--configuration", self.config]
        cmd += ["--log-junit", _PHPUNIT_XML] + self.phpunit_args
        test_filter = self._filter(names)
        if test_filter:
            cmd += ["--filter", test_filter]

        # PHPUnit 9 accepts several positional paths but silently executes only the first.
        # Keep the visible-suite call as one pathless invocation and run selected files one
        # at a time, merging their reports on the host.
        targets = [None] if files is None else list(files)
        outcomes = {}
        n = 0
        error = False
        for path in targets:
            if env.exists(_PHPUNIT_XML):
                env.remove(_PHPUNIT_XML)
            selected = cmd + ([path] if path is not None else [])
            r = _run(env, selected, timeout=timeout, cwd=repo)
            if r is None:
                suffix = f" ({path})" if path is not None else ""
                log(f"phpunit TIMEOUT after {timeout}s{suffix}")
                return {}, 0, False, True
            suffix = f" ({path})" if path is not None else ""
            log(f"phpunit rc={r.returncode}{suffix}")
            log(r.stdout[-2000:])
            # No report means the test process never reached PHPUnit's reporter (a PHP
            # fatal error or broken bootstrap), not "nothing to run". Continue so one bad
            # target does not hide the remaining selected files.
            if not env.exists(_PHPUNIT_XML):
                error = True
                continue
            found, ran = _parse_junit(env, _PHPUNIT_XML)
            outcomes.update(found)
            n += ran
            error = error or (r.returncode != 0 and not found)
        return outcomes, n, error, False
