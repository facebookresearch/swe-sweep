"""TarantoolTestRunSuite suite adapter."""

import os
import re

from ..base import ReproductionSuite
from ..utils.compiled import _patched_files, _run
from ..utils.logging import log

# One result line of a test-run run:
#     [001] box-luatest/gh_6036_qsync_test.lua                            [ pass ]
#
# The name is printed into a fixed-width column and **truncated with a trailing `>`** when
# it does not fit, which most of Tarantool's `gh_<issue>_<what>_test.lua` names do not:
#     [001] box-luatest/gh_7539_mvcc_dirty_data_written_to>                 [ fail ]
# So a reported name is a prefix of the requested one, not necessarily equal to it — see
# `_resolve`.
_RESULT = re.compile(r"^\[\d+\]\s+(\S+)\s+.*\[\s*(pass|fail|skip|new|updated|disabled)\s*\]\s*$")
# Everything test-run's own statuses mean in this benchmark's vocabulary. `new` and
# `updated` only appear under --update-result, which is never passed, but they say "the
# output differed and I overwrote the expectation", which is a failure here.
_OUTCOME = {
    "pass": "passed",
    "fail": "failed",
    "new": "failed",
    "updated": "failed",
    "skip": "skipped",
    "disabled": "skipped",
}


class TarantoolTestRunSuite(ReproductionSuite):
    """Tarantool's own ``test-run`` harness, which runs three unrelated kinds of test.

    The harness is the unit of selection because there is nothing smaller: test-run takes
    a **test path** relative to the test root and runs it whole. It also decides *how*,
    from the ``suite.ini`` next to the test, and the three kinds do not resemble each
    other:

    - a **diff test** is a ``.test.lua`` (or ``.test.sql``, ``.test.py``) script beside a
      checked-in ``.result``, and passing means the output matched byte for byte. So a
      patch that only edits the ``.result`` is still a complete test change, and the
      target is its script sibling;
    - a **luatest test** is a ``*_test.lua`` module of xUnit cases, in a ``*-luatest``
      suite;
    - a **unit test** is a C or C++ program under ``unit/``, which cmake builds as
      ``<stem>.test`` — so the target is named after the *binary*, not the source.

    ``names`` stays empty. Even in the luatest suites, test-run addresses the file; the
    per-case selector belongs to luatest, which test-run does not expose.

    ``--retries 0`` is not a detail. test-run re-runs a failed test by default, and the
    census *wants* the pre-gold failure — retrying it turns every reproducing bug into
    several minutes of re-running a test that will fail again.
    """

    no_targets = "test patch touched no test-run test"

    # A script test-run can be handed directly.
    _DIFF_TEST = (".test.lua", ".test.sql", ".test.py")
    # A file that belongs to a diff test but is not the script: the expectation, and the
    # per-test skip condition. Both resolve to the script beside them.
    _DIFF_SIDECAR = (".result", ".skipcond")
    _UNIT_SOURCE = (".c", ".cc", ".cpp", ".m")

    def __init__(self, repo, test_root="test", runner="./test-run.py", unit_suites=("unit",), extra_args=()):
        self.repo = repo
        self.test_root = test_root.strip("/")
        self.runner = runner
        self.unit_suites = tuple(unit_suites)
        self.extra_args = list(extra_args)

    @classmethod
    def from_config(cls, values, *, repo, create_suite):
        """Unlike most adapters this one keeps ``repo``: resolving a ``.result`` to the
        script beside it is a lookup in the container, and ``targets`` is handed no path."""
        del create_suite
        return cls(repo, **values)

    # --- resolving the diff --------------------------------------------------

    def _target_for(self, rel, env):
        """The test-run name for one patched file under the test root, or ``None``."""
        suite, _, tail = rel.partition("/")
        if not tail:
            return None  # a file at the test root: CMakeLists, the runner itself
        stem, ext = os.path.splitext(os.path.basename(tail))

        if suite in self.unit_suites:
            return f"{suite}/{stem}.test" if ext in self._UNIT_SOURCE else None
        if rel.endswith(self._DIFF_TEST):
            return rel
        if ext in self._DIFF_SIDECAR:
            base = rel[: -len(ext)]
            for script_ext in self._DIFF_TEST:
                candidate = base + script_ext
                if env is None or env.exists(os.path.join(self.repo, self.test_root, candidate)):
                    return candidate
            return None
        if stem.endswith("_test") and ext == ".lua":
            return rel
        return None  # a helper module, suite.ini, a fixture

    def targets(self, diff, env=None):
        """``([test-run names], [])`` — see the class docstring on why names stay empty."""
        prefix = self.test_root + "/"
        found = []
        for path in _patched_files(diff):
            if not path.startswith(prefix):
                continue
            target = self._target_for(path[len(prefix) :], env)
            if target and target not in found:
                found.append(target)
        return sorted(found), []

    @staticmethod
    def _resolve(reported, requested):
        """The requested test a result line names, undoing the column truncation.

        A truncated name ends in ``>`` and is a prefix of the real one. It is ambiguous in
        principle — two tests in one suite can share a long prefix — but only when both
        were selected by the same patch, and then either one's failure is the same verdict
        for the same subtask. Falls back to the reported string so an unrecognised line is
        still recorded rather than silently dropped."""
        if not reported.endswith(">"):
            return reported
        prefix = reported[:-1]
        for name in requested or ():
            if name.startswith(prefix):
                return name
        return prefix

    # --- running -------------------------------------------------------------

    def run_tests(self, env, repo, files, names, timeout, jobs):
        """Run the selected tests in one test-run invocation and read its result lines.

        ``--force`` keeps it going past the first failure — the census routinely selects
        several tests and needs a verdict for each, not just the first."""
        del names
        argv = [self.runner, f"--builddir={repo}", "--retries", "0", "--force"]
        if jobs:
            argv += ["-j", str(jobs)]
        argv += self.extra_args + list(files or [])
        result = _run(env, argv, timeout=timeout, cwd=os.path.join(repo, self.test_root))
        if result is None:
            log("test-run TIMEOUT after %ds" % timeout)
            return {}, 0, False, True
        log("test-run rc=%d" % result.returncode)
        log(result.stdout[-3000:])

        outcomes = {}
        for line in result.stdout.splitlines():
            match = _RESULT.match(line.strip())
            if match:
                outcomes[self._resolve(match.group(1), files)] = _OUTCOME[match.group(2)]

        # A selected test that produced no result line never ran: test-run did not
        # recognise the path, or the server died before reporting. That is the harness
        # `error` flag, not a failed assertion — "the test does not run" and "the test
        # fails" have to differ post-gold.
        error = bool(files) and any(name not in outcomes for name in files)
        if error:
            log("no test-run result for: %s" % ", ".join(sorted(set(files) - set(outcomes))))
        n = len([value for value in outcomes.values() if value != "skipped"])
        return outcomes, n, error, False
