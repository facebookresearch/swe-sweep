"""IdrisGoldenSuite suite adapter."""

from __future__ import annotations

import re
import subprocess

from ..base import ReproductionSuite
from ..utils.compiled import _patched_files
from ..utils.logging import log

# ``Test.Golden`` prints one line per case, ``<test name>: success`` or ``<test name>:
# FAILURE``, where the name is the case directory relative to ``tests/``. Colour codes are
# only emitted when stdout is a tty, which it never is under ``container exec``, but the
# pattern tolerates them rather than silently reading every case as unmeasured. With
# ``--timing`` the verdict is followed by padding and a duration, so the match is a prefix.
_RESULT_RE = re.compile(r"^(?P<name>[^\s:]+): (?:\x1b\[[0-9;]*m)?(?P<verdict>success|FAILURE)", re.M)

# The runner's closing line. Its presence is what separates "the corpus ran and selected
# nothing" from "the runner died before it got there".
_SUMMARY_RE = re.compile(r"^(\d+)/(\d+) tests successful", re.M)


class IdrisGoldenSuite(ReproductionSuite):
    """Idris 2's golden corpus: ``tests/<pool>/<case>/`` holding ``run``, ``expected`` and
    the Idris sources.

    A case is a **directory**, not a function. ``Test.Golden`` discovers the cases by
    listing the pool directories at start-up and calling a directory a test iff it holds a
    ``run`` script; the recorded ``expected`` file beside it is the assertion. So a test
    patch that only rewrites ``expected`` is a complete test patch, and there is no test
    name anywhere in the sources for a name-based suite to find — the path *is* the name.

    That is also why resolving a patched file to its case walks **up** the tree rather than
    dropping the last component: a case can carry a whole directory of fixtures
    (``tests/idris2/pkg/pkg001/depends/…``), and the case is the nearest ancestor holding a
    ``run``. The walk needs the container, so ``targets`` uses ``env`` when it has one and
    falls back to "drop the file name" when it does not (the host-only ``patch-applies``
    path, which never runs anything).

    **The invocation lives in the image, not here.** Running the corpus by hand means
    reproducing what the repository's own ``make test`` sets up — the test prefix the cases
    install into, the ``NAME_VERSION`` that ``testutils.sh`` builds its library paths from,
    and a rebuild of the ``runtests`` driver, without which a case added by a test patch is
    invisible in the trees whose ``tests/Main.idr`` still lists its pools by hand. All of
    that is version-specific, so the image ships a small makefile that ``include``\\ s the
    repository's own and this suite only chooses the cases and reads the report.

    Selection is ``--only``, and it is **one invocation per case**. Not for tidiness: the
    two eras of the flag disagree about how it takes several names — the 0.5 driver takes
    every remaining argument, the 0.7 one takes a single space-separated argument and then
    keeps parsing — and a single name is the only form both read the same way. Passing the
    wrong one does not error, it selects nothing.

    ``--only`` matches its name as an *infix*, so a request for ``basic001`` also drags in
    ``basic0011`` where such a case exists. The verdict therefore comes from the per-case
    result lines rather than from the exit code, and only the case actually asked for is
    reported. A name that never appears in the output selected nothing — it does not exist
    in this tree — and is reported ``error`` rather than silently read as a pass.

    Pools with an unmet ``Requirement`` (the Racket, Gambit and Node backends, which this
    image does not install) are skipped by the runner itself, so their cases report "no
    targets" instead of failing.
    """

    no_targets = "test patch touched no addressable golden test case"

    @classmethod
    def from_config(cls, values, *, repo, create_suite):
        """Unlike most adapters this one keeps ``repo``: resolving a patched fixture to the
        case that owns it is a walk up the container tree, and ``targets`` is handed no
        path."""
        del create_suite
        return cls(repo, **values)

    def __init__(
        self,
        repo,
        tests_dir="tests",
        makefile="/usr/local/share/swesweep/tests.mk",
        target="swesweep-run",
        setup_target="swesweep-testenv",
    ):
        self.repo = repo
        self.tests_dir = tests_dir
        self.makefile = makefile
        self.target = target
        self.setup_target = setup_target

    # --- target resolution --------------------------------------------------

    def _case_from_path(self, path, env, added):
        """``tests/idris2/basic/basic001/expected`` -> ``idris2/basic/basic001``.

        The case is the nearest ancestor directory holding a ``run`` script, and that
        script is looked for in two places: ``added`` is the set the *diff itself* creates,
        and the container is asked about the rest.
        """
        prefix = self.tests_dir + "/"
        if not path.startswith(prefix):
            return None
        parts = path[len(prefix) :].split("/")
        if len(parts) < 2:
            return None
        for end in range(len(parts) - 1, 0, -1):
            candidate = "/".join(parts[:end])
            if candidate in added:
                return candidate
            if env is not None and env.is_file("%s/%s/%s/run" % (self.repo, self.tests_dir, candidate)):
                return candidate
        # Nothing confirmed it: assume the file sits directly in its case directory, which
        # is the shape of all but a handful of cases. Guessing beats giving up — a name
        # that does not exist selects nothing and is reported ``error``, never as a pass.
        return "/".join(parts[:-1])

    def targets(self, diff, env=None):
        """``([case names], [case names])`` — the same list twice: the directory *is* the
        test, so there is no finer level to narrow to.

        **The diff has to be able to answer this by itself.** Reproduction applies the test
        patch before asking, but evaluation asks *first* and applies afterwards, and it
        restores the tree between subtasks — so a case the patch creates is not on disk at
        the moment the question is put, and a walk that only consults the container finds
        nothing and silently reports every subtask as having no tests. The diff does know:
        a new golden case always brings its own ``run`` script, and that is what names it.
        """
        paths = _patched_files(diff)
        prefix, suffix = self.tests_dir + "/", "/run"
        added = {
            path[len(prefix) : -len(suffix)] for path in paths if path.startswith(prefix) and path.endswith(suffix)
        }
        cases = []
        for path in paths:
            case = self._case_from_path(path, env, added)
            if case and case not in cases:
                cases.append(case)
        return sorted(cases), sorted(cases)

    # --- execution ----------------------------------------------------------

    def _run(self, env, repo, only, timeout, jobs):
        """One ``runtests`` invocation; ``only`` is a single case name or ``None`` for the
        whole corpus. Returns the parsed ``{name: outcome}`` plus the raw text."""
        cmd = ["make", "-f", self.makefile, self.target, "SWESWEEP_THREADS=%s" % jobs]
        if only is not None:
            cmd.append("SWESWEEP_ONLY=%s" % only)
        log("$ (cd %s && %s)" % (repo, " ".join(cmd)))
        r = env.execute(cmd, cwd=repo, timeout=timeout, env={"NO_COLOR": "1"}, merge_stderr=True)
        text = r.stdout or ""
        log(text[-2000:])
        seen = {}
        for m in _RESULT_RE.finditer(text):
            seen[m.group("name")] = "passed" if m.group("verdict") == "success" else "failed"
        return seen, text

    def run_tests(self, env, repo, files, names, timeout, jobs):
        del names
        try:
            # `testenv` is run once rather than as a prerequisite of every invocation: it
            # reinstalls the runtime support and rebuilds the driver, and repeating that
            # per case would dominate a run that selects a handful of them. It is inside
            # the try: eval calls this once per subtask and lets an exception abort the
            # whole run, so a single slow rebuild must report a timeout for its own
            # subtask rather than void everyone else's.
            setup = env.execute(
                ["make", "-f", self.makefile, self.setup_target],
                cwd=repo,
                timeout=timeout,
                merge_stderr=True,
            )
            if setup.returncode != 0:
                log("testenv failed (rc=%s): %s" % (setup.returncode, (setup.stdout or "")[-1500:]))

            if files is None:
                # The whole visible corpus: whatever the runner reported *is* the
                # population. No result lines and no summary means the driver never ran,
                # which is an error rather than an empty suite.
                seen, text = self._run(env, repo, None, timeout, jobs)
                if not seen and not _SUMMARY_RE.search(text):
                    return {}, 0, True, False
                return seen, len(seen), False, False

            outcomes = {}
            had_error = False
            for case in files:
                seen, _text = self._run(env, repo, case, timeout, jobs)
                outcome = seen.get(case)
                if outcome is None:
                    outcome = "error"
                    had_error = True
                outcomes[case] = outcome
        except subprocess.TimeoutExpired:
            log("runtests TIMEOUT after %ds" % timeout)
            return {}, 0, False, True
        return outcomes, len(outcomes), had_error, False
