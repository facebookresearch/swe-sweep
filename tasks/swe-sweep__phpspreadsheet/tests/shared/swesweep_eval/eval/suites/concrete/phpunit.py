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

    ``qualified`` keys outcomes by ``classname.name`` instead of the bare method name:
    PHPUnit runs are merged across files, and two files can hold a same-named method —
    with bare keys the later file's outcome silently overwrites the earlier one. The
    class name is read from the report's ``classname`` attribute (PHPUnit 9 writes it
    Java-style, backslashes replaced by dots).

    ``nested`` reads the report's nested suites (PHPUnit 9 nests each class and each
    data-provider method; see ``_parse_junit``).

    ``phpunit_args`` are the repo's own flags, and ``config`` names its ``phpunit.xml`` when
    the default lookup does not find one.

    ``visible_globs`` splits the visible (pathless) run into one invocation per matched
    directory: a single whole-suite invocation keeps every result in one process and is
    OOM-killed on suites past a few tens of thousands of cases (symfony's is ~44k), and
    PHPUnit 9 executes only the first positional path, so the directories cannot share one
    invocation. The globs should mirror the configuration's own ``<directory>`` entries so
    the split selects exactly the same test files the pathless run would.
    """

    no_targets = "test patch touched no PHPUnit test file"

    def __init__(
        self, phpunit_args=(), config=None, binary="vendor/bin/phpunit", qualified=False, visible_globs=(), nested=False
    ):
        self.phpunit_args = list(phpunit_args)
        self.config = config
        self.binary = binary
        self.qualified = qualified
        self.visible_globs = list(visible_globs)
        self.nested = nested

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
        # Run selected files one at a time, merging their reports on the host. The
        # visible-suite call is one pathless invocation, unless `visible_globs` splits it
        # into one invocation per matched directory (see the class docstring).
        targets = [None] if files is None else list(files)
        if files is None and self.visible_globs:
            probe = _run(
                env,
                ["sh", "-c", "ls -d " + " ".join(self.visible_globs) + " 2>/dev/null"],
                cwd=repo,
            )
            if probe is not None and probe.stdout.split():
                targets = sorted(set(probe.stdout.split()))
                log(f"phpunit visible run split into {len(targets)} directories")
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
            found, ran = _parse_junit(env, _PHPUNIT_XML, qualified=self.qualified, nested=self.nested)
            outcomes.update(found)
            n += ran
            error = error or (r.returncode != 0 and not found)
        return outcomes, n, error, False
