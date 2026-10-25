"""TestamentSuite suite adapter."""

import json
import os
import re

from ..base import ReproductionSuite
from ..utils.compiled import _patched_files, _run
from ..utils.logging import log

# Testament prints one line per result. The name it prints is the whole identity of the
# run — `tests/stdlib/tmarshal.nim c --mm:orc` — because one case is compiled once per
# backend *and* once per extra option set, and those runs have different outcomes. It is
# padded to 60 columns and followed by ` ( N.NN sec)`; the skip forms carry no duration.
_RESULT_RE = re.compile(r"^(?P<verdict>PASS|FAIL|SKIP|NOTINBATCH|JOINED):\s+(?P<name>\S.*?)\s*$")
# The duration testament appends to a non-skipped result.
_DURATION_RE = re.compile(r"\(\s*[\d.]+ sec\)$")
# Testament's `all` re-spawns per category without --colors:off, so verdict lines arrive wrapped in SGR escapes.
# Strip them (`\e[32mPASS: ...`) before the verdict regex sees the line.
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
# Testament prints progress without a newline, so one case's name can arrive glued to the next case's verdict marker.
# Split at every embedded marker (`PASS: ` etc. never occurs inside a testament id): each fragment is a full record.
_GLUE_RE = re.compile(r"(?<!^)(?=(?:PASS|FAIL|SKIP|NOTINBATCH|JOINED): )")
# Byte-level interleaving can also truncate an SGR sequence, leaving an introducer that
# _ANSI_RE cannot match (`\x1b[PASS:` with the color bytes lost). Drop those leftovers.
_STRAY_ANSI_RE = re.compile(r"\x1b\[?")
# Verdicts in testament's results JSON (`TResultEnum`): anything but success, disabled or joined is a failure.
_JSON_SKIPPED = ("reDisabled", "reJoined")
_VERDICTS = {
    "PASS": "passed",
    "FAIL": "failed",
    "SKIP": "skipped",
    "NOTINBATCH": "skipped",
    "JOINED": "skipped",
}


class TestamentSuite(ReproductionSuite):
    """One ``testament r <file>`` process per touched test file.

    Nim's corpus is **one program per case**: ``tests/<category>/t<name>.nim`` is a
    complete Nim program whose expected compiler output, expected stdout and exit code are
    written in a spec comment at the top of the file itself. Testament compiles it, runs
    it, and diffs both against the spec. There is no test *function* below the file, so
    ``names`` is always empty and the file is the unit — the same shape as the Perl and
    Rust UI corpora.

    Three flags are not optional:

    - ``--backendLogging:off``. The result-log backend shells out to
      ``git symbolic-ref --short HEAD`` and **quits** when that fails. The census container
      sits on a detached baseline commit, so with logging on testament dies before running
      anything and every subtask looks unmeasurable.
    - ``--megatest:off``. Testament's default is to concatenate every *joinable* case into
      one generated program and run that instead. A joined case then reports ``JOINED:``
      and its real outcome is buried in the megatest's, which is unusable when the point is
      one case's verdict.
    - ``--colors:off``, or verdict markers come wrapped in ANSI escapes. It does not reach ``testament all``'s
      per-category children (see ``_ANSI_RE``), so ``_parse`` also strips escapes itself.

    ``targets`` only accepts files testament itself would run: a case's basename starts
    with ``t``. Everything else under ``tests/`` is a helper module a case imports, and
    handing one to ``testament r`` makes it compile a module with no spec.

    ``nim`` is the compiler binary the cases are compiled with, relative to the repo — the
    per-subtask rebuild refreshes exactly that path.

    The whole-suite run reads verdicts from the ``testresults/<category>.json`` each per-category child writes,
    because the children share one stdout and their lines interleave; stdout is the fallback when no file was written.
    """

    no_targets = "test patch touched no testament case"

    def __init__(self, test_roots=("tests",), nim="bin/nim", testament="testament/testament", targets=()):
        self.test_roots = list(test_roots)
        self.nim = nim
        self.testament = testament
        self.targets_flag = list(targets)

    def _under_test_root(self, path):
        return any(path == root or path.startswith(root + "/") for root in self.test_roots)

    def targets(self, diff, env=None):
        """``([test file paths], [])`` — see the class docstring on why names stay empty."""
        del env
        found = []
        for path in _patched_files(diff):
            if not path.endswith(".nim") or not self._under_test_root(path):
                continue
            if not os.path.basename(path).startswith("t"):
                continue
            if path not in found:
                found.append(path)
        return sorted(found), []

    def _command(self, case):
        """``testament r <case>``, or ``testament all`` for the whole corpus.

        The visible suite is **one** process, not one per case: the corpus is some twenty
        thousand programs and testament already walks it itself, so spawning a process each
        would spend the whole timeout on process startup."""
        cmd = [
            "./" + self.testament,
            "--nim:" + self.nim,
            "--backendLogging:off",
            "--colors:off",
            "--megatest:off",
        ]
        if self.targets_flag:
            cmd.append("--targets:" + " ".join(self.targets_flag))
        return cmd + (["all"] if case is None else ["r", case])

    def run_tests(self, env, repo, files, names, timeout, jobs):
        """Run each case in its own testament process and parse the verdicts it prints."""
        del names, jobs
        cases = [None] if files is None else list(files)
        outcomes = {}
        error = False
        results_dir = os.path.join(repo, "testresults")
        for case in cases:
            if case is None:  # git-ignored, so `git clean` keeps a previous run's files
                for path in env.find_files(results_dir):
                    env.remove(path)
            result = _run(env, self._command(case), timeout=timeout, cwd=repo)
            if result is None:
                log("testament %s TIMEOUT after %ds" % (case or "all", timeout))
                return outcomes, 0, False, True
            log("testament %s rc=%d" % (case or "all", result.returncode))
            log(result.stdout[-2500:])
            found = self._json_outcomes(env, results_dir) if case is None else {}
            if found:
                outcomes.update(found)
                seen = len(found)
            else:
                seen = self._parse(case, result.stdout, outcomes)
            # No verdict at all means testament never got as far as the case — a missing
            # compiler, a broken spec parse. That is the `error` flag, not a failure:
            # "the harness did not run" and "the test failed" differ post-gold.
            if not seen and result.returncode != 0:
                error = True
        n = len([value for value in outcomes.values() if value != "skipped"])
        return outcomes, n, error, False

    @staticmethod
    def _id(name):
        """The id `_parse` keys on: the printed name up to any ` (` (`(allowed to fail)`, a duration); None if not a case."""
        name = name.split(" (", 1)[0].strip()
        return name if ".nim" in name.split(" ")[0] else None

    @classmethod
    def _json_outcomes(cls, env, results_dir):
        """Verdicts from every ``testresults/*.json``; an entry per line, so a file a crashed child left unclosed still reads."""
        outcomes = {}
        for path in env.find_files(results_dir):
            if not path.endswith(".json"):
                continue
            for line in env.read_text(path).splitlines():
                line = line.strip().lstrip("[,").rstrip("],")  # the closing `]` follows the last entry on its line
                if not line.startswith("{"):
                    continue
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                key = cls._id(str(entry.get("name", "")))
                if key:
                    result = entry.get("result")
                    outcomes[key] = "passed" if result == "reSuccess" else "skipped" if result in _JSON_SKIPPED else "failed"
        return outcomes

    @staticmethod
    def _parse(case, text, outcomes):
        """Fold one testament run's verdicts into ``outcomes``; return how many it printed.

        The key is testament's own name for the run, not the file: one case is compiled
        once per backend and once per extra option set, and `--mm:orc` failing while
        `--mm:refc` passes is the ordinary shape of a memory-management fix. Keying on the
        path alone would let the last line win and hide the failure."""
        seen = 0
        for line in text.splitlines():
            for fragment in _GLUE_RE.split(_STRAY_ANSI_RE.sub("", _ANSI_RE.sub("", line))):
                match = _RESULT_RE.match(fragment.strip())
                if match is None:
                    continue
                name = _DURATION_RE.sub("", match.group("name")).strip()
                # A fragment truncated mid-duration keeps a tail like `... c ( 1.75 se`; ids never contain "(", so cut there.
                # A name truncated mid-option stays as is: it can never match a recorded id, which is the safe direction.
                name = name.split(" (", 1)[0].strip()
                if ".nim" not in name.split(" ")[0]:
                    continue
                seen += 1
                outcomes[name] = _VERDICTS[match.group("verdict")]
        return seen
