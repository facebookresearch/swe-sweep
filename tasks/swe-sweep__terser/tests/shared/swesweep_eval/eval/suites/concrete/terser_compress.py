"""TerserCompressSuite suite adapter."""

import os
import re

from ..base import ReproductionSuite
from ..utils.compiled import _run
from ..utils.javascript import _REPORT, _parse_junit, _pattern, _resolve_bin
from ..utils.logging import log
from ..utils.pytest import PLUSFILE_RE

# `--- collapse_vars.js` — the driver entering a corpus file.
_FILE_RE = re.compile(r"^--- (?P<file>\S+)\s*$")
# `    Running test [issue_1758]` — the driver starting one case.
_CASE_RE = re.compile(r"^\s*Running test \[(?P<name>.+)\]\s*$")
# `!!! Cannot parse input`, `!!! Failed 3 test cases.` — every diagnostic the driver prints
# for a failure starts with this, and nothing else it prints does.
_FAIL_PREFIX = "!!!"
# A case in a corpus file is a top-level *labelled statement*: `issue_1758: { ... }`.
_ADD_CASE_RE = re.compile(r"^\+([A-Za-z_$][\w$]*)\s*:\s*\{")

class TerserCompressSuite(ReproductionSuite):
    """terser's compress corpus, plus its mocha suite beside it.

    terser keeps its regressions in ``test/compress/*.js``. A file is a series of top-level
    labelled blocks — ``issue_1758: { options {...} input {...} expect {...} }`` — and they
    are run by terser's **own** driver, ``test/compress.js``, not by mocha. There is no
    reporter and no report file: the driver prints ``--- <file>`` when it enters a corpus
    file, ``Running test [<name>]`` when it starts a case, and a block starting ``!!!`` when
    one fails. So the per-case outcomes this class returns are read out of that console
    output, keyed ``<file>::<case>``, which is what lets one added case be graded on its own
    rather than the whole file passing or failing together.

    Two details of the driver decide how it is invoked:

    - **Files are selected by base name, not path.** ``find_test_files`` keeps a file whose
      *name* appears in ``process.argv.slice(2)``, so the argument is ``collapse_vars.js``
      and never ``test/compress/collapse_vars.js``.
    - **``GREP`` is one substring, not a pattern.** The driver filters case names with
      ``name.includes(process.env.GREP)``, so it cannot express the alternation a patch that
      adds several cases needs. Selection therefore narrows to the *files* and reads the
      cases back out of the output — which costs the rest of the file's runtime and nothing
      in correctness.

    A patch that touches ``test/mocha/`` as well is handled by the other half: those are
    ordinary mocha specs and run through mocha with an xunit reporter.
    """

    no_targets = "test patch touched no compress corpus file and no mocha spec"

    def __init__(self, corpus_dir="test/compress", driver="test/compress.js",
                 mocha_dir="test/mocha", timeout_ms=120000):
        self.corpus_dir = corpus_dir.rstrip("/")
        self.driver = driver
        self.mocha_dir = mocha_dir.rstrip("/")
        self.timeout_ms = timeout_ms

    def targets(self, diff, env=None):
        del env
        files = []
        names = []
        for path in PLUSFILE_RE.findall(diff):
            if path == "/dev/null":
                continue
            if path.startswith(self.corpus_dir + "/") and path.endswith(".js"):
                files.append(path)
            elif path.startswith(self.mocha_dir + "/") and path.endswith(".js"):
                files.append(path)
        for line in diff.splitlines():
            m = _ADD_CASE_RE.match(line)
            if m:
                names.append(m.group(1))
        return sorted(set(files)), sorted(set(names))

    def _split(self, files):
        corpus = [f for f in files if f.startswith(self.corpus_dir + "/")]
        mocha = [f for f in files if f.startswith(self.mocha_dir + "/")]
        return corpus, mocha

    def run_tests(self, env, repo, files, names, timeout, jobs):
        del jobs
        whole_suite = files is None
        corpus, mocha = self._split(list(files or ()))
        if whole_suite:
            corpus, mocha = [os.path.join(self.corpus_dir, "")], [self.mocha_dir]

        outcomes = {}
        total = 0
        error = False

        if corpus or whole_suite:
            # Base names only — the driver matches argv against the file's name.
            argv = ["node", self.driver] + ([] if whole_suite else [os.path.basename(f) for f in corpus])
            log("$ " + " ".join(argv))
            result = _run(env, argv, timeout=timeout, cwd=repo)
            if result is None:
                log("terser compress driver TIMEOUT after %ds" % timeout)
                return {}, 0, False, True
            log("terser compress driver rc=%d" % result.returncode)
            log(result.stdout[-2000:])
            parsed = self._parse(result.stdout)
            if not parsed:
                # The driver prints a `Running test [...]` line for every case it reaches, so
                # no cases at all with a non-zero rc means it never started — a bad argument
                # or a tree that will not import — rather than "nothing to run".
                if result.returncode:
                    error = True
            outcomes.update(parsed)
            total += len(parsed)

        if mocha:
            cmd = _resolve_bin(env, repo, "mocha") + list(mocha) + [
                "--reporter", "xunit", "--reporter-options", "output=" + _REPORT,
                "--exit", "--timeout", str(self.timeout_ms),
            ]
            if names:
                cmd += ["--grep", _pattern(names)]
            log("$ " + " ".join(cmd))
            if env.exists(_REPORT):
                env.remove(_REPORT)
            result = _run(env, cmd, timeout=timeout, cwd=repo)
            if result is None:
                log("mocha TIMEOUT after %ds" % timeout)
                return outcomes, total, error, True
            mocha_outcomes, n, mocha_error = _parse_junit(env, _REPORT)
            outcomes.update(mocha_outcomes)
            total += n
            error = error or mocha_error or (not mocha_outcomes and bool(result.returncode))

        return outcomes, total, error, False

    @staticmethod
    def _parse(output):
        """Per-case outcomes from the compress driver's console output.

        A case is failing if any ``!!!`` diagnostic appears between its ``Running test``
        line and the next case (or the end of the run). The trailing ``!!! Failed N test
        cases.`` summary comes after the last case's line, so it would otherwise mark that
        last case failed on every run that failed anywhere — it is recognised and skipped.
        """
        outcomes = {}
        current = None
        current_file = ""
        for line in output.splitlines():
            m = _FILE_RE.match(line)
            if m:
                current_file = m.group("file")
                current = None
                continue
            m = _CASE_RE.match(line)
            if m:
                current = (current_file + "::" if current_file else "") + m.group("name")
                outcomes[current] = "passed"
                continue
            stripped = line.strip()
            if current and stripped.startswith(_FAIL_PREFIX):
                if stripped.startswith("!!! Failed ") and stripped.endswith("test cases."):
                    current = None  # the run summary, not this case's diagnostic
                    continue
                outcomes[current] = "failed"
        return outcomes
