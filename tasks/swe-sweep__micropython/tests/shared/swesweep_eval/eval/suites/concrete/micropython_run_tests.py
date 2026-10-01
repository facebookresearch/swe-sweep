"""MicropythonRunTestsSuite suite adapter."""

import os
import re

from ..base import ReproductionSuite
from ..utils.compiled import _patched_files, _run
from ..utils.logging import log

# One result line of a run-tests run. The harness prints with `print("pass ", test_file)`,
# so the separator is two spaces, and a pass may carry a trailing note:
#     pass  basics/andor.py
#     FAIL  extmod/vfs_lfs.py
#     skip  basics/async_await.py
#     lrge  basics/bytearray_add.py            (target refused it as too large)
_RESULT = re.compile(r"^(pass|FAIL|skip|lrge)\s+(\S+)")
_OUTCOME = {"pass": "passed", "FAIL": "failed", "skip": "skipped", "lrge": "skipped"}


class MicropythonRunTestsSuite(ReproductionSuite):
    """MicroPython's ``tests/run-tests.py``: a script, and the output it must produce.

    A case is a ``.py`` file under the test root. The harness runs it on the MicroPython
    binary and compares stdout against either a checked-in ``<case>.py.exp`` or — when
    there is none — **against CPython's own output for the same file**. So the CPython in
    the image is part of the environment under test, not a build tool, and an expectation
    file is as much a test change as the script: a patch that only edits ``foo.py.exp``
    resolves to ``foo.py`` beside it.

    ``names`` stays empty. run-tests addresses a whole file; there is nothing smaller for
    it to select, because a case is a script and its output, not a collection of
    assertions.

    ``test_dirs`` is the allowlist of directories this image can actually run. The
    repository's test root also holds suites for hardware ports (``pyb``, ``esp32``,
    ``renesas-ra``, ``wipy``), for networking against a live peer (``net_inet``,
    ``multi_net``), and documentation of intended CPython differences (``cpydiff``) that
    is not a suite at all. A patch that only touches those selects nothing and the subtask
    reports "no targets" rather than failing — which is the honest verdict, since the unix
    build cannot observe those bugs.
    """

    no_targets = "test patch touched no run-tests case this build can run"

    def __init__(
        self,
        test_root="tests",
        runner="run-tests.py",
        test_dirs=(
            "basics",
            "cmdline",
            "extmod",
            "float",
            "import",
            "io",
            "micropython",
            "misc",
            "stress",
            "unicode",
            "unix",
        ),
        jobs_flag=None,
        extra_args=(),
    ):
        self.test_root = test_root.strip("/")
        self.runner = runner
        self.test_dirs = tuple(test_dirs)
        self.jobs_flag = jobs_flag
        self.extra_args = list(extra_args)

    # --- resolving the diff --------------------------------------------------

    def _target_for(self, rel):
        """The run-tests case one patched path names, or ``None``.

        ``rel`` is relative to the test root. ``.exp`` is the expectation beside a case;
        strip it and the case is what is left."""
        head = rel.split("/")[0]
        if head not in self.test_dirs:
            return None
        if rel.endswith(".exp"):
            rel = rel[: -len(".exp")]
        return rel if rel.endswith(".py") else None

    def targets(self, diff, env=None):
        """``([case paths relative to the test root], [])`` — see the class docstring."""
        del env
        prefix = self.test_root + "/"
        found = []
        for path in _patched_files(diff):
            if not path.startswith(prefix):
                continue
            target = self._target_for(path[len(prefix) :])
            if target and target not in found:
                found.append(target)
        return sorted(found), []

    # --- running -------------------------------------------------------------

    def run_tests(self, env, repo, files, names, timeout, jobs):
        """Run the selected cases in one run-tests invocation and read its result lines.

        With ``files=None`` — the visible-suite run — no paths are passed and run-tests
        discovers its own default set for the platform, which is what the evaluation half
        wants. The exit code is ignored: it is non-zero whenever anything failed, which
        for the census is the *expected* pre-gold state."""
        del names
        argv = ["./" + self.runner]
        if self.jobs_flag and jobs:
            argv += [self.jobs_flag, str(jobs)]
        argv += self.extra_args + list(files or [])
        result = _run(env, argv, timeout=timeout, cwd=os.path.join(repo, self.test_root))
        if result is None:
            log("run-tests TIMEOUT after %ds" % timeout)
            return {}, 0, False, True
        log("run-tests rc=%d" % result.returncode)
        log(result.stdout[-3000:])

        outcomes = {}
        for line in result.stdout.splitlines():
            match = _RESULT.match(line.strip())
            if match:
                outcomes[match.group(2)] = _OUTCOME[match.group(1)]

        # A selected case with no result line never ran — run-tests did not recognise the
        # path, or it died before reporting. That is the harness `error` flag, not a
        # failed assertion: post-gold, "the test does not run" and "the test fails" have
        # to be told apart, or a vacuous pass sinks the census.
        error = bool(files) and any(name not in outcomes for name in files)
        if error:
            log("no run-tests result for: %s" % ", ".join(sorted(set(files) - set(outcomes))))
        n = len([value for value in outcomes.values() if value != "skipped"])
        return outcomes, n, error, False
