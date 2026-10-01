# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""DoctestSuite suite adapter."""

import fnmatch
import os
import re

from ..base import FullSuite
from ..utils.compiled import _REPORT, _all_error, _parse_junit, _per_file_hunks, _run, died_running
from ..utils.logging import log

# A doctest case is declared with a **string literal**, not an identifier:
# ``TEST_CASE("[Vector2] Angle methods")``. That literal is the whole test id — it is
# what the JUnit report calls the case and what ``--test-case=`` selects — so the reader
# has to capture the string, escapes and all, rather than a C symbol.
#
# ``TEST_CASE_PENDING`` / ``TEST_CASE_MAY_FAIL`` are Godot's wrappers around the same
# macro (``tests/test_macros.h``); ``TEST_CASE_TEMPLATE`` is doctest's own. All of them
# name the case in the first argument, which is why one alternation covers the set.
_DOCTEST_MACROS = r"TEST_CASE(?:_PENDING|_MAY_FAIL|_TEMPLATE|_FIXTURE|_TEMPLATE_DEFINE)?"
_DOCTEST_CALL = r'\s*\(\s*"((?:[^"\\]|\\.)*)"'
# A case the patch ADDS.
_DOCTEST_DECL_RE = re.compile(r"^\+\s*" + _DOCTEST_MACROS + _DOCTEST_CALL, re.M)
# A case the patch EDITS: git puts the enclosing declaration in the hunk header, which is
# the only place an unchanged ``TEST_CASE("…")`` line shows up in the diff. Every other
# compiled suite here reads its enclosing declaration the same way, and without it a
# patch that only strengthens an existing assertion has no target at all.
_DOCTEST_HUNK_RE = re.compile(r"^@@ .*@@.*\b" + _DOCTEST_MACROS + _DOCTEST_CALL, re.M)

# Characters that would change the meaning of a ``--test-case=`` value: doctest splits
# the value on commas and treats ``*``/``?`` as wildcards. A case whose *name* contains
# one cannot be selected exactly, so the whole run goes unfiltered instead (see
# :meth:`DoctestSuite._filter`) — slower, never wrong.
_UNSELECTABLE = re.compile(r"[,*?]")

# The same declaration read out of a FILE rather than a diff — used to recover the case a
# hunk sits inside when git's hunk header did not carry it.
_DOCTEST_FILE_RE = re.compile(r"^\s*" + _DOCTEST_MACROS + _DOCTEST_CALL, re.M)
# Where a hunk lands in the patched file: ``@@ -a,b +c,d @@``, ``c`` being the 1-based
# first line of the post-image.
_HUNK_START_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)", re.M)


class DoctestSuite(FullSuite):
    """doctest, every case linked into **one** program — the layout Godot uses.

    Two things make this different from the gtest adapter next door, and both come from
    doctest rather than from any one repo:

    * **A case is named by a string, not a symbol.** ``TEST_CASE("[String] Assign")`` is
      the id end to end, so the ids are read out of the *diff text* (one patched file can
      declare several) and passed back verbatim as a selector. Nothing about the file's
      path names the case, and nothing about the case names a binary.
    * **There is one binary.** doctest links every translation unit's cases into the
      program under test, so there is nothing to attribute a case to — ``binary`` is a
      single path (a shell glob is allowed, for a build whose file name carries the
      configuration, as Godot's ``godot.linuxbsd.editor.dev.x86_64`` does).

    The program is built by ``build_cmd`` with the repository as the working directory,
    because SCons — the build system of the repo this was written for — has no
    out-of-source mode and resolves everything relative to the tree. ``{jobs}`` in the
    command is replaced by the job count.

    ``extra_args`` are passed before doctest's own flags; Godot needs ``--test`` there,
    which its ``Main::test_entrypoint`` consumes before any of the engine's own argument
    parsing runs, handing the rest of ``argv`` straight to ``doctest::Context``.

    Outcomes are restricted to the cases the patch named. The driver treats *every*
    returned outcome as evidence (``fails_pre_gold`` is true if any of them failed), so a
    suite that reported its neighbours would call an unrelated flake a reproduction.

    ``corpus_cases`` covers the other shape a doctest repo uses: a **directory of data
    files driven by one case**. Godot's GDScript tests are a script and its expected
    output (``foo.gd`` beside ``foo.out``) under a corpus directory, and a single
    ``TEST_CASE("Script compilation and runtime")`` walks the whole directory — so a patch
    that adds a script declares no macro at all and would otherwise have no target, which
    is what half of Godot's test-carrying bug fixes look like. Each entry maps a shell
    glob to the case name that runs it.
    """

    no_targets = "test patch declared no doctest TEST_CASE this suite builds"

    @classmethod
    def from_config(cls, values, *, repo, create_suite):
        """``repo`` is not a declared value — it comes from the task's ``container_repo``
        — but :meth:`_enclosing_case` has to read the patched file off the tree, and
        ``targets`` is handed a diff and an environment, never a path."""
        del create_suite
        return cls(repo=repo, **values)

    def __init__(
        self,
        repo="/",
        binary="bin/godot.linuxbsd.editor.dev.x86_64",
        build_cmd="scons platform=linuxbsd target=editor dev_build=yes tests=yes -j {jobs}",
        test_re=r"^(?:tests/|modules/[^/]+/tests/)",
        extra_args=("--test",),
        corpus_cases=(),
    ):
        self.repo = repo
        self.binary = binary
        self.build_cmd = build_cmd
        self.test_re = re.compile(test_re)
        self.extra_args = list(extra_args)
        self.corpus_cases = [(entry["glob"], entry["case"]) for entry in corpus_cases]

    # --- resolving the diff --------------------------------------------------

    def _corpus_case(self, path):
        """The case that runs ``path`` as corpus data, or ``None``."""
        for glob, case in self.corpus_cases:
            if fnmatch.fnmatch(path, glob):
                return case
        return None

    def _enclosing_case(self, env, path, chunk_text):
        """The cases whose bodies this file's hunks fall inside, read off the **patched
        tree**.

        git puts the enclosing declaration in a hunk header only when it can find one, and
        for a case whose body is long — or whose opening line is styled in a way git's
        heuristic does not recognize — it cannot. The file itself always can: the hunk
        header gives the line the change lands on, and the nearest ``TEST_CASE`` above it
        is the case that change belongs to."""
        try:
            text = env.read_text(path if os.path.isabs(path) else os.path.join(self.repo, path))
        except OSError:
            return []
        decls = [(text.count("\n", 0, m.start()) + 1, m.group(1)) for m in _DOCTEST_FILE_RE.finditer(text)]
        if not decls:
            return []
        found = []
        for match in _HUNK_START_RE.finditer(chunk_text):
            line = int(match.group(1))
            above = [name for start, name in decls if start <= line]
            if above:
                found.append(above[-1])
        return found

    def targets(self, diff, env=None):
        """``(files, names)`` — the patched test sources, and the names of the cases the
        patch declares, edits, or feeds as corpus data.

        Read per file so a declaration is attributed to the file its hunk sits in, the
        same way the gtest reader works. A patch that names no case has no target, which
        is reported rather than silently graded against the whole program."""
        files = []
        names = []
        for chunk in _per_file_hunks(diff):
            corpus = self._corpus_case(chunk.path)
            if corpus:
                files.append(chunk.path)
                names.append(corpus)
                continue
            if not self.test_re.match(chunk.path):
                continue
            found = _DOCTEST_DECL_RE.findall(chunk.text) + _DOCTEST_HUNK_RE.findall(chunk.text)
            if not found and env is not None:
                found = self._enclosing_case(env, chunk.path, chunk.text)
            if found:
                files.append(chunk.path)
                names += found
        return sorted(set(files)), sorted(set(names))

    # --- the one real implementation -----------------------------------------

    def _resolve_binary(self, env, repo):
        """The absolute path of the test program, resolving ``binary`` as a glob if it is
        one. Returns ``None`` when the build produced nothing that matches."""
        path = self.binary if os.path.isabs(self.binary) else os.path.join(repo, self.binary)
        if not any(ch in path for ch in "*?["):
            return path if env.is_file(path) else None
        head = os.path.dirname(path)
        found = sorted(p for p in env.find_files(head) if fnmatch.fnmatch(p, path) and env.is_executable(p))
        return found[0] if found else None

    def _filter(self, names):
        """A ``--test-case=`` value selecting exactly ``names``, or ``None`` for "run
        everything and pick the results apart afterwards".

        doctest reads the value as a comma-separated list of wildcard patterns, so a name
        holding a comma or a wildcard character cannot be expressed. That is rare and the
        fallback is only slower, so it is preferred over quoting games that would
        silently select the wrong set."""
        if any(_UNSELECTABLE.search(n) for n in names):
            return None
        return ",".join(names)

    def _select(self, outcomes, names):
        """The subset of a whole report that belongs to ``names``.

        doctest's JUnit reporter appends the active SUBCASE path to the case name
        (``"[String] Assign/utf8"``), so a targeted case can be reported under several
        keys; all of them are that case's evidence and all are kept."""
        wanted = set(names)
        return {
            key: value for key, value in outcomes.items() if key in wanted or key.split("/", 1)[0] in wanted
        }

    def _build_and_run(self, env, repo, names, timeout, jobs):
        """Build the program, then run it. ``names=None`` means the whole suite.

        Returns ``(outcomes, n_run, failed_to_build, timed_out, text)`` — the same shape
        the gtest and CTest adapters return."""
        command = self.build_cmd.format(jobs=jobs)
        build = _run(env, ["/bin/sh", "-c", command], timeout=timeout, cwd=repo)
        if build is None:
            log("test build TIMEOUT")
            return _all_error(names or []), 0, True, True, "test build TIMEOUT"
        if build.returncode != 0:
            # Expected pre-gold whenever the fix is what makes the test compile.
            log("test build failed:\n" + build.stdout[-1500:])
            return _all_error(names or []), 0, True, False, build.stdout

        binary = self._resolve_binary(env, repo)
        if binary is None:
            log("no test binary matching %s" % self.binary)
            return None, 0, False, False, "no test binary matching " + self.binary

        if env.exists(_REPORT):
            env.remove(_REPORT)
        argv = [binary] + self.extra_args + ["--reporters=junit", "--out=" + _REPORT]
        selector = self._filter(names) if names else None
        if selector:
            argv.append("--test-case=" + selector)
        # The program runs with the repository as its working directory: a case that
        # loads a fixture from the tree does it with a relative path, and upstream's own
        # CI runs the binary from the checkout root.
        res = _run(env, argv, timeout=timeout, cwd=repo)
        if res is None:
            log("doctest TIMEOUT after %ds" % timeout)
            return None, 0, False, True, "doctest TIMEOUT after %ds" % timeout
        log("doctest rc=%d" % res.returncode)
        log(res.stdout[-1500:])
        if not env.exists(_REPORT):
            if died_running(res):
                # A crash takes the whole process down before the reporter writes, and
                # every case shares one address space — which is the commonest bug shape
                # in a compiled repo. That IS the pre-gold failure the census looks for,
                # so the targeted cases count as erroring rather than as unmeasurable.
                return _all_error(names or []), 0, False, False, res.stdout
            return None, 0, False, False, res.stdout
        outcomes, n_run = _parse_junit(env, _REPORT)
        if names is not None:
            outcomes = self._select(outcomes, names)
            n_run = len([o for o in outcomes.values() if o != "skipped"])
        return outcomes, n_run, False, False, res.stdout

    # --- the drivers' adapters ------------------------------------------------

    def run_tests(self, env, repo, files, names, timeout, jobs):
        del files
        outcomes, n_run, build_failed, timed_out, _text = self._build_and_run(env, repo, names, timeout, jobs)
        if outcomes is None:
            return {}, 0, not timed_out, timed_out
        # No case matched the selector: the patch names a case the program does not
        # register. Nothing ran, which is a suite-level failure, not a pass.
        return outcomes, n_run, build_failed or not outcomes, timed_out

    def run_all(self, env, repo, timeout, cap, jobs):
        outcomes, _n, _bf, timed_out, text = self._build_and_run(env, repo, None, timeout, jobs)
        clipped, truncated = cap.clip(text)
        return outcomes, timed_out, {
            "command": "doctest (whole suite)", "returncode": None,
            "text": clipped, "truncated": truncated,
        }

    def run_selected(self, env, repo, files, names, timeout, cap, jobs):
        del files
        outcomes, _n, _bf, timed_out, text = self._build_and_run(env, repo, names, timeout, jobs)
        clipped, truncated = cap.clip(text)
        return outcomes, timed_out, {
            "command": "doctest " + " ".join(names), "returncode": None,
            "text": clipped, "truncated": truncated,
        }
