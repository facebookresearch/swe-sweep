# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""AgdaTastySuite suite adapter."""

from __future__ import annotations

import os
import re
import subprocess

from ..base import ReproductionSuite
from ..utils.compiled import _patched_files
from ..utils.logging import log

# What Agda's own driver counts as belonging to a golden case. The Agda program is the
# test; the recorded compiler output beside it (``.err`` for Fail, ``.warn`` for Succeed,
# ``.expected`` for Interactive) is the expectation, and rewriting only the expectation is
# a complete test patch. ``.flags`` carries the case's command line.
_GOLDEN_EXTS = (".agda", ".lagda", ".err", ".warn", ".out", ".flags", ".in", ".expected")

# ``all/Internal`` is not a golden corpus: its cases are Haskell modules, and each one
# names its own tasty group after the module ("Internal.Utils.List"), not after its path.
_INTERNAL_RE = re.compile(r"^test/Internal/(?P<mod>.+)\.hs$")

# POSIX ERE metacharacters. Python's ``re.escape`` is the wrong tool: it also escapes ``-``,
# and ``\-`` is undefined in ERE.
_ERE_META = set(".^$*+?()[]{}|" + chr(92))

# tasty's console summary, the only place the number of tests it actually selected is
# reported. A ``--regex-include`` that matches nothing still exits 0, so the count is what
# separates "the case passed" from "there was no such case".
_ALL_PASSED_RE = re.compile(r"^All (\d+) tests? passed", re.M)
_SOME_FAILED_RE = re.compile(r"^(\d+) out of (\d+) tests? failed", re.M)

# A leaf of tasty's console tree: ``    ExecAgda:            FAIL (0.69s)``. Group headers
# are the same shape without the verdict. A failure prints its golden diff underneath, and
# those lines are indistinguishable from tree lines, so a parsed name counts only when the
# corpus listing also has it (see ``_failures``).
_TREE_LEAF_RE = re.compile(r"^(?P<indent> +)(?P<name>\S[^:]*):\s+(?P<verdict>OK|FAIL)\b")
_TREE_GROUP_RE = re.compile(r"^(?P<indent> *)(?P<name>\S[^:]*?) *$")

# Stands in for a failure the tree parser could not attribute to a case. Constant, so the
# baseline run carries it too and it never reads as a fresh regression on its own.
_UNNAMED = "__unattributed_failures__"

# Column of the first group *below* the suite: ``all`` sits at 0, the suite at 2, and a
# golden case at 4. Only ``Internal`` nests further, and only its groups belong in a name.
_NESTED = 4


def _resolve(suite, groups, leaf, known):
    """The corpus name of one failing tree leaf, or ``None`` if it has none.

    Every candidate is checked against ``known`` because the surrounding golden diff is
    plain text that the tree grammar also accepts, so a group stack can carry junk. A
    golden case is just the leaf; ``Internal`` needs the module groups above it; and a leaf
    whose ancestry got lost is still recoverable when the corpus names it exactly once.
    """
    for candidate in ("all/%s/%s" % (suite, leaf),
                      "all/%s/%s" % (suite, ".".join(groups + [leaf]))):
        if candidate in known:
            return candidate
    matches = [name for name in known if name.endswith("." + leaf)]
    return matches[0] if len(matches) == 1 else None


class AgdaTastySuite(ReproductionSuite):
    """Agda's tasty-silver corpus: ``test/<Suite>/<Case>.agda`` plus its golden output.

    Agda's regression tests are *data*. A case is an Agda program under ``test/Succeed``,
    ``test/Fail`` and friends, and the driver — the ``agda-tests`` executable — discovers
    them by walking those directories at start-up, so there is no test function anywhere
    for a name-based suite to find. The name tasty gives a case is its path below the
    suite directory with the separators turned into ``-`` (``Utils.asTestName``), sitting
    under ``all/<Suite>/``.

    Selection is by ``--regex-include``, and the case is run **one invocation per case**
    rather than one batched run: tasty reports its verdict in the exit code, and the
    census wants an outcome per test rather than one for the batch.

    A regex that selects nothing still exits 0, which would read as a pass and silently
    turn an unmeasurable case into a reproduced bug. So the verdict comes from tasty's
    summary line, not from the exit code, and a case that selected zero tests is reported
    ``error`` — the same way a pytest collection error is.

    The **whole visible population** (``files=None``, what evaluation grades P2P against)
    is a different job: naming a suite selects a thousand cases at once, so the verdict has
    to come apart into one outcome per case or a regression in any single test would be
    invisible inside its suite's verdict. There the corpus is enumerated with ``-l`` and the
    run reports only its failures (``--hide-successes``), which are subtracted from it.

    Only the suites in ``suites`` are addressed. Agda's other corpora are out of scope for
    the image: ``LibSucceed``/``CubicalSucceed`` need the standard library and cubical
    library checkouts, ``LaTeXAndHTML`` (and ``HTMLOnly``/``LaTeXOnly``/``QuickLaTeXOnly``/
    ``UserManual``) need a TeX installation, ``Compiler`` needs the backends' runtimes, and
    ``test/interaction`` is driven by its own Makefile rather than by tasty. Those cases
    report "no targets" instead of failing.

    Every invocation pins ``-j 1``. Golden cases share scratch state — interface files, a
    temp dir, ``AGDA_DIR`` — so running them concurrently manufactures failures (on this
    corpus, 64 instead of 12), and tasty otherwise sizes its pool from the host.
    """

    no_targets = "test patch touched no addressable tasty case"

    def __init__(self, suites=None, tests_bin="agda-tests", agda_bin="agda", extra_args=None):
        self.suites = list(suites or ["Succeed", "Fail", "Bugs", "BuildFail", "BuildSucceed", "Interactive"])
        self.tests_bin = tests_bin
        self.agda_bin = agda_bin
        self.extra_args = list(extra_args or [])

    # --- target resolution --------------------------------------------------

    @staticmethod
    def _ere(text):
        return "".join("\\" + c if c in _ERE_META else c for c in text)

    def _golden_case(self, path):
        """``test/Fail/Issue1234.agda`` -> ``all/Fail/Issue1234``; nested cases join with
        ``-`` the way ``Utils.asTestName`` does."""
        stem, ext = os.path.splitext(path)
        if ext not in _GOLDEN_EXTS:
            return None
        parts = stem.split("/")
        if len(parts) < 3 or parts[0] != "test" or parts[1] not in self.suites:
            return None
        return "all/%s/%s" % (parts[1], "-".join(parts[2:]))

    def _internal_case(self, path):
        """``test/Internal/Utils/List.hs`` -> ``all/Internal/Internal.Utils.List``: the
        module names its own group, so the whole module's properties are the unit."""
        m = _INTERNAL_RE.match(path)
        if not m:
            return None
        return "all/Internal/Internal.%s/" % m.group("mod").replace("/", ".")

    def targets(self, diff, env=None):
        """``([case paths], [case paths])`` — the same list twice: for this harness the
        data file *is* the test, so there is no second, finer level to narrow to."""
        del env
        cases = []
        for path in _patched_files(diff):
            case = self._golden_case(path) or self._internal_case(path)
            if case and case not in cases:
                cases.append(case)
        return sorted(cases), sorted(cases)

    # --- execution ----------------------------------------------------------

    def _run(self, env, repo, args, timeout):
        cmd = [self.tests_bin] + args + ["--color", "never", "-j", "1"] + self.extra_args
        log("$ AGDA_BIN=%s %s" % (self.agda_bin, " ".join(cmd)))
        return env.execute(
            cmd, cwd=repo, timeout=timeout, env={"AGDA_BIN": self.agda_bin}, merge_stderr=True)

    def _population(self, env, repo, timeout):
        """``{suite: [case name]}`` for the addressable suites, from tasty's own listing.

        ``-l`` walks the corpus and prints every case as a dotted path without running
        anything, so this is the one authority on what exists in *this* tree — the suites
        agda ships change between versions, and several of the ones it does ship have no
        cases in an image without TeX or a backend runtime.
        """
        by_suite = {}
        for line in self._run(env, repo, ["-l"], timeout).stdout.splitlines():
            parts = line.strip().split(".")
            if len(parts) < 3 or parts[0] != "all" or parts[1] not in self.suites:
                continue
            by_suite.setdefault(parts[1], []).append(
                "all/%s/%s" % (parts[1], ".".join(parts[2:])))
        return by_suite

    @staticmethod
    def _failures(output, suite, known):
        """The failing case names in one suite's ``--hide-successes`` transcript.

        A golden failure prints its diff below the tree line, and diff text can look like
        any part of the tree, so a reconstructed name is trusted only when ``known`` — the
        ``-l`` listing — contains it. Anything left over is reported under one synthetic
        name instead of being dropped: a failure this parser cannot place still has to
        register as a failure.
        """
        stack, found = [], set()
        for line in output.splitlines():
            leaf = _TREE_LEAF_RE.match(line)
            if leaf:
                indent = len(leaf.group("indent"))
                stack = [(i, n) for i, n in stack if i < indent]
                if leaf.group("verdict") == "FAIL":
                    name = _resolve(suite, [n for i, n in stack if i >= _NESTED],
                                    leaf.group("name").strip(), known)
                    if name:
                        found.add(name)
                continue
            group = _TREE_GROUP_RE.match(line)
            if group:
                indent = len(group.group("indent"))
                stack = [(i, n) for i, n in stack if i < indent]
                stack.append((indent, group.group("name")))
        reported = _SOME_FAILED_RE.search(output)
        missed = (int(reported.group(1)) if reported else 0) - len(found)
        if missed > 0:
            log("could not name %d of the failures in %s" % (missed, suite))
            found.add("all/%s/%s" % (suite, _UNNAMED))
        return found

    def run_all(self, env, repo, timeout, jobs):
        """One outcome per case over every addressable suite.

        Enumerate, then run each suite once and subtract the failures it reports. Running
        the cases one invocation apiece instead would be correct too, and pay agda's corpus
        walk thousands of times over.
        """
        del jobs
        outcomes = {}
        for suite, cases in sorted(self._population(env, repo, timeout).items()):
            try:
                r = self._run(env, repo, ["--regex-include", "all/%s/" % self._ere(suite),
                                          "--hide-successes"], timeout)
            except subprocess.TimeoutExpired:
                log("agda-tests TIMEOUT after %ds" % timeout)
                return outcomes, len(outcomes), True, True
            log(r.stdout[-1500:])
            failed = self._failures(r.stdout, suite, set(cases))
            outcomes.update((case, "failed" if case in failed else "passed") for case in cases)
            outcomes.update((case, "failed") for case in failed if case not in outcomes)
        return outcomes, len(outcomes), not outcomes, False

    def run_tests(self, env, repo, files, names, timeout, jobs):
        del names
        if files is None:
            return self.run_all(env, repo, timeout, jobs)
        outcomes = {}
        had_error = False
        deadline_hit = False
        for case in files:
            # Anchored at the *end* only. tasty-silver matches its filter against a path
            # that carries a prefix before ``all/``, so a leading ``^`` selects nothing at
            # all — and an unanchored name would let ``all/Fail/Issue123`` also drag in
            # ``all/Fail/Issue1234``. A trailing ``/`` (the Internal-module form) is left
            # unanchored on purpose: it selects every property in the module.
            selector = self._ere(case) if case.endswith("/") else self._ere(case) + "$"
            try:
                r = self._run(env, repo, ["--regex-include", selector], timeout)
            except subprocess.TimeoutExpired:
                log("agda-tests TIMEOUT after %ds" % timeout)
                deadline_hit = True
                break
            log(r.stdout[-1500:])
            outcome = self._verdict(r.stdout)
            if outcome == "error":
                had_error = True
            outcomes[case] = outcome
        n = len([o for o in outcomes.values() if o != "skipped"])
        return outcomes, n, had_error, deadline_hit

    @staticmethod
    def _verdict(output):
        """tasty's summary, not the exit code. Zero selected tests is ``error``: the case
        the patch names does not exist in this tree, so nothing was measured."""
        failed = _SOME_FAILED_RE.search(output)
        if failed:
            return "failed"
        passed = _ALL_PASSED_RE.search(output)
        if passed:
            return "passed" if int(passed.group(1)) else "error"
        return "error"
