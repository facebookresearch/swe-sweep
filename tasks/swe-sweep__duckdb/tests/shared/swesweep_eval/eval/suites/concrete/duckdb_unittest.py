# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""DuckdbUnittestSuite suite adapter."""

import os
import re

from ..base import FullSuite
from ..utils.compiled import _REPORT, _parse_junit, _patched_files, _per_file_hunks, _run, died_running
from ..utils.logging import log

# A Catch2 case a patch ADDS, and one it EDITS. duckdb's C++ tests are Catch2 v2
# (`third_party/catch/catch.hpp`), where a case is declared `TEST_CASE("name", "[tags]")`
# — the id is the quoted *string*, not an identifier, which is what makes this different
# from the gtest/Boost readers in ``compiled``. The edit form reads the declaration out of
# git's hunk header, the same trick the pytest and gtest suites use: a patch that only
# strengthens an existing case never repeats its `TEST_CASE(` line anywhere else.
_CATCH_CALL = r'\s*\(\s*"([^"]+)"'
_CATCH_DECL_RE = re.compile(r"^\+\s*TEST_CASE" + _CATCH_CALL, re.M)
_CATCH_HUNK_RE = re.compile(r"^@@ .*@@.*\bTEST_CASE" + _CATCH_CALL, re.M)

# Catch2 test specs give `[`, `]`, `,`, `*` and `~` their own meaning. A sqllogictest path
# never contains one; a `TEST_CASE` string occasionally does, and Catch has no escape for
# it, so such a case is skipped rather than silently selecting the wrong thing.
_UNSELECTABLE = set("[],*~")


class DuckdbUnittestSuite(FullSuite):
    """duckdb's single Catch2 ``unittest`` binary — sqllogictest files and C++ cases.

    **87% of duckdb's test patches touch nothing but sqllogictest files** (a query and its
    expected result table in one ``.test`` file under ``test/`` — as close to a ready-made
    fail→pass artifact as a repo gets), and the remainder are Catch2 C++ cases. Both are
    the *same* suite here: ``test/unittest.cpp`` calls ``RegisterSqllogictests()``, which
    walks ``test/`` and registers every ``.test`` / ``.test_slow`` / ``.test_coverage``
    file as a Catch case **named by its path relative to the repo root**. So one binary and
    one reporter cover the whole population, and a target is either a path or a quoted
    ``TEST_CASE`` string.

    Two things follow from that registration:

    - A new ``.test`` file needs no build-system change — it is discovered by directory
      listing at startup. A new C++ case does, which is why the build step runs ``make``
      (re-configuring cmake) rather than just re-linking.
    - ``.test_slow`` is registered under Catch's ``[.]`` hidden tag, so it never runs in a
      whole-suite pass but **does** run when named explicitly. Naming every target
      explicitly is what makes those subtasks measurable.

    Targets are run **one per invocation**. duckdb's commonest defect shape crashes the
    process, and a crash takes the JUnit report down with it — batching several targets
    into one run would lose the verdict for the ones that were fine.

    Selected by the task's declarative runner configuration.
    """

    no_targets = "test patch touched no sqllogictest file or Catch2 test case"

    def __init__(
        self,
        binary="build/release/test/unittest",
        slt_root="test/",
        slt_exts=(".test", ".test_slow", ".test_coverage"),
        cpp_re=r"^test/.*\.cpp$",
    ):
        self.binary = binary
        self.slt_root = slt_root.rstrip("/") + "/"
        self.slt_exts = tuple(slt_exts)
        self.cpp_re = re.compile(cpp_re)

    # --- resolving the diff --------------------------------------------------

    def targets(self, diff, env=None):
        """``(names, names)`` — the Catch case ids the patch touches. Both halves are the
        same list: a target here *is* its test id, so there is nothing extra for
        :meth:`run_tests` to look up."""
        del env
        names = [p for p in _patched_files(diff) if p.startswith(self.slt_root) and p.endswith(self.slt_exts)]
        for chunk in _per_file_hunks(diff):
            if not self.cpp_re.match(chunk.path):
                continue
            names += _CATCH_DECL_RE.findall(chunk.text) + _CATCH_HUNK_RE.findall(chunk.text)
        selectable = sorted({n for n in names if not (_UNSELECTABLE & set(n))})
        return selectable, selectable

    # --- the one real implementation -----------------------------------------

    def _run_one(self, env, repo, name, timeout):
        """Run a single Catch case. ``(outcomes, n_run, timed_out, text)``."""
        if env.exists(_REPORT):
            env.remove(_REPORT)
        # cwd is the repo: a sqllogictest resolves the fixture paths it loads (`test/…csv`,
        # `data/…parquet`) relative to the working directory, not to the binary.
        res = _run(env, [os.path.join(repo, self.binary), "-r", "junit", "-o", _REPORT, name], timeout=timeout, cwd=repo)
        if res is None:
            text = "unittest TIMEOUT after %ds (%s)" % (timeout, name)
            log(text)
            return {}, 0, True, text
        log("unittest %s rc=%d" % (name, res.returncode))
        log(res.stdout[-1500:])
        if env.exists(_REPORT):
            outcomes = _parse_junit(env, _REPORT)[0]
            if outcomes:
                return outcomes, 1, False, res.stdout
        # No usable report — either none was written, or the one that was is truncated,
        # which is the same thing: a crash took the reporter down with it. Either the case
        # crashed the process — the commonest defect shape in a database engine, and a real
        # failing test — or the binary never got going, which is an unmeasurable run and
        # must not be scored.
        if died_running(res):
            return {name: "failed"}, 1, False, res.stdout
        return {}, 0, False, res.stdout

    def _run_named(self, env, repo, names, timeout):
        """``(outcomes, n_run, error, timed_out, text)`` over ``names``, one invocation each."""
        outcomes, n_run, texts = {}, 0, []
        for name in names:
            got, ran, timed_out, text = self._run_one(env, repo, name, timeout)
            texts.append("$ unittest %s\n%s" % (name, text))
            if timed_out:
                return outcomes, n_run, False, True, "\n".join(texts)
            outcomes.update(got)
            n_run += ran
        # Nothing ran at all: the patch names a case the binary does not register. That is
        # a suite-level failure, not a pass.
        return outcomes, n_run, not outcomes, False, "\n".join(texts)

    def _run_whole(self, env, repo, timeout):
        """The default (non-hidden) suite, for the eval driver's visible run."""
        if env.exists(_REPORT):
            env.remove(_REPORT)
        res = _run(env, [os.path.join(repo, self.binary), "-r", "junit", "-o", _REPORT], timeout=timeout, cwd=repo)
        if res is None:
            return None, True, "unittest (whole suite) TIMEOUT after %ds" % timeout
        if not env.exists(_REPORT):
            return None, False, res.stdout
        # An unreadable report is no report: the gate cannot be established from half a file.
        return _parse_junit(env, _REPORT)[0] or None, False, res.stdout

    # --- the drivers' adapters ------------------------------------------------

    def run_tests(self, env, repo, files, names, timeout, jobs):
        del jobs
        if files is None:
            outcomes, timed_out, _text = self._run_whole(env, repo, timeout)
            if outcomes is None:
                return {}, 0, not timed_out, timed_out
            return outcomes, len(outcomes), False, timed_out
        outcomes, n_run, error, timed_out, _text = self._run_named(env, repo, files, timeout)
        return outcomes, n_run, error, timed_out

    def run_all(self, env, repo, timeout, cap, jobs):
        del jobs
        outcomes, timed_out, text = self._run_whole(env, repo, timeout)
        return outcomes, timed_out, self._capture("unittest (whole suite)", text, cap)

    def run_selected(self, env, repo, files, names, timeout, cap, jobs):
        del jobs
        outcomes, _n, _error, timed_out, text = self._run_named(env, repo, files, timeout)
        return outcomes, timed_out, self._capture("unittest " + " ".join(files), text, cap)

    @staticmethod
    def _capture(command, text, cap):
        clipped, truncated = cap.clip(text)
        return {"command": command, "returncode": None, "text": clipped, "truncated": truncated}
