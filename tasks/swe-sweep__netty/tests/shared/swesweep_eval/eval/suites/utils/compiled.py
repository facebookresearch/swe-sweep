#!/usr/bin/env python3

# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""Shared diff, process, and JUnit helpers for compiled suite adapters."""

import re
import subprocess
import xml.etree.ElementTree as ET

from swesweep_eval.eval.suites.utils.evaluation import parse_xml
from swesweep_eval.eval.suites.utils.logging import log
from swesweep_eval.eval.suites.utils.pytest import PLUSFILE_RE

# A compiled test's sources: the program itself plus, for CTest's output-comparison
# tests, the expected-output file beside it (changing only the expectation is a complete
# test patch — the program is unchanged and the recorded output is what moves).
_CTEST_EXTS = (".c", ".cpp", ".cc", ".out")

_REPORT = "/tmp/ctest.xml"
# _binary()'s answer in binary_glob mode: "a test source, but its binary is not named by
# its path". Never used as a binary name — _plan() replaces it with the discovered set.
_ALL_BINARIES = "*"


def _patched_files(diff):
    """Every non-deleted file the diff writes to."""
    return [f for f in PLUSFILE_RE.findall(diff) if f != "/dev/null"]


class _FileHunks:
    """One file's slice of a unified diff: the path it writes to, and the diff text for
    it. Splitting first is what lets a per-hunk reader attribute what it finds to the
    right file — a whole diff is one text, and a gtest macro in it belongs to whichever
    file's hunks it sits in."""

    def __init__(self, path, text):
        self.path = path
        self.text = text


def _per_file_hunks(diff):
    """Split a unified diff into one :class:`_FileHunks` per written file (deletions
    dropped — a removed test is not a target)."""
    out = []
    path = None
    lines = []
    for line in diff.splitlines(True):
        if line.startswith("diff --git "):
            if path:
                out.append(_FileHunks(path, "".join(lines)))
            path, lines = None, []
        elif line.startswith("+++ b/"):
            candidate = line[6:].rstrip("\n")
            path = None if candidate == "/dev/null" else candidate
        elif path:
            lines.append(line)
    if path:
        out.append(_FileHunks(path, "".join(lines)))
    return out


def _run(env, argv, timeout=None, cwd=None):
    """Run ``argv``, folding stderr into stdout so the captured text reads like the real
    console. Returns the completed process, or ``None`` if it timed out."""
    try:
        return env.execute(argv, cwd=cwd, timeout=timeout, merge_stderr=True)
    except subprocess.TimeoutExpired:
        return None


def _all_error(names):
    """The outcome map for "the build failed, so none of these ran"."""
    return {n: "error" for n in names}


# The line a test harness prints when it starts a case. gtest and Boost.Test both write
# one, which is what lets a crashed run be told apart from a program that never ran.
_STARTED_A_CASE = ("[ RUN ", "Entering test case", "Test case ")


def died_running(res):
    """Did this test program start running cases and then die?

    A test binary that produces no report is either a crash — a segfault or an abort in a
    case takes the whole process down before the report is written — or a program that
    never ran at all, which for a compiled suite means it rejected the flags or failed to
    start. The two need opposite treatment (the first is a real failing test, the second
    is noise), and the signature of the first is that it was killed by a signal, or that
    it announced a case before dying.
    """
    return res.returncode < 0 or any(marker in res.stdout for marker in _STARTED_A_CASE)


def _parse_junit(env, path, qualified=False):
    """``(outcomes, n_run)`` from a JUnit XML report — the format CTest
    (``--output-junit``), gtest (``--gtest_output=xml``) and pytest all write, so the
    verdict shape stays identical across suites. A skipped test is recorded but not
    counted as run.

    ``qualified`` joins the case's ``classname`` to its name. CTest's names are already
    whole (``test::foo``); gtest splits them, and only the joined ``Suite.Name`` is the id
    a ``--gtest_filter`` and a reader would recognize.

    A report that does not parse is an *unreadable* report, not a broken evaluation: a test
    binary that dies mid-run leaves the XML unterminated. It reads as no outcomes, which is
    what a missing report reads as, so the caller's existing "did it crash?" branch decides
    that one target — instead of a single truncated file aborting the whole eval."""
    outcomes = {}
    try:
        root = parse_xml(env.read_text(path))
    except ET.ParseError as exc:
        log(f"unparseable JUnit report {path}: {exc}")
        return {}, 0
    suites = [root] if root.tag == "testsuite" else list(root)
    for suite in suites:
        for tc in suite.findall("testcase"):
            outcome = "passed"
            for kid in list(tc):
                if kid.tag == "failure":
                    outcome = "failed"
                elif kid.tag == "error":
                    outcome = "error"
                elif kid.tag == "skipped":
                    outcome = "skipped"
            name = tc.get("name", "")
            if qualified:
                name = (tc.get("classname", "") + "." + name).strip(".")
            outcomes[name] = outcome
    return outcomes, len([o for o in outcomes.values() if o != "skipped"])


# The gtest macros that declare a test case, and what they do to the suite name. OpenCV's
# OpenCL variants are the only ones that rewrite it (modules/ts/include/.../ocl_test.hpp:
# `OCL_TEST` and `OCL_TEST_F` prefix the suite with `OCL_`, `OCL_TEST_P` does not).
_GTEST_MACROS = {
    "TEST": "",
    "TEST_F": "",
    "TEST_P": "",
    "TYPED_TEST": "",
    "TYPED_TEST_P": "",
    "OCL_TEST_P": "",
    "OCL_TEST": "OCL_",
    "OCL_TEST_F": "OCL_",
}
_GTEST_MACRO_ALT = "|".join(sorted(_GTEST_MACROS, key=len, reverse=True))
_GTEST_CALL = r"\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*,\s*([A-Za-z_][A-Za-z0-9_]*)\s*[,)]"
# A case the patch ADDS.
_GTEST_DECL_RE = re.compile(r"^\+\s*(" + _GTEST_MACRO_ALT + r")" + _GTEST_CALL, re.M)
# A case the patch EDITS: git puts the enclosing declaration in the hunk header, which is
# the only place an unchanged `TEST(...)` line shows up in the diff. The pytest suite
# reads its enclosing `def test_*` from a hunk header the same way, and
# without it every patch that only strengthens an existing case has no target at all —
# on OpenCV that is a fifth of the population.
_GTEST_HUNK_RE = re.compile(r"^@@ .*@@.*\b(" + _GTEST_MACRO_ALT + r")" + _GTEST_CALL, re.M)


# A case the patch ADDS, and one it EDITS (named only in git's hunk header — the same
# trick the gtest and pytest readers use). Boost's fixture variant takes the fixture as a
# second argument, so only the leading name is captured.
_BOOST_CASE = r"BOOST_(?:AUTO|FIXTURE)_TEST_CASE\s*\(\s*([A-Za-z_]\w*)"
_BOOST_DECL_RE = re.compile(r"^\+\s*" + _BOOST_CASE, re.M)
_BOOST_HUNK_RE = re.compile(r"^@@ .*@@.*\b" + _BOOST_CASE, re.M)
# The enclosing suite, read out of the FILE rather than the diff: it is declared once at
# the top and a hunk in the middle of the file never shows it.
_BOOST_SUITE_RE = re.compile(r"^\s*BOOST_(?:AUTO|FIXTURE)_TEST_SUITE\s*\(\s*([A-Za-z_]\w*)", re.M)


# --- cppcheck's own harness -----------------------------------------------------

# A case the patch ADDS. cppcheck registers one with `TEST_CASE(name);` inside the
# fixture's `run()`, and defines `void name()` further down the same file.
_TESTRUNNER_DECL_RE = re.compile(r"^\+\s*TEST_CASE\s*\(\s*([A-Za-z_]\w*)\s*\)", re.M)
# A case the patch EDITS: git puts the enclosing function signature in the hunk header,
# which is the only place an unchanged case body shows up in the diff. Every other suite
# here reads its enclosing declaration the same way.
_TESTRUNNER_HUNK_RE = re.compile(r"^@@ .*@@.*\bvoid\s+([A-Za-z_]\w*)\s*\(\s*\)", re.M)
# The fixture a file declares. Not in the diff -- it is written once at the top of the
# file and a hunk in the middle never repeats it -- so it is read off the patched tree.
_TESTFIXTURE_CLASS_RE = re.compile(r"^class\s+([A-Za-z_]\w*)\s*:\s*public\s+TestFixture\b", re.M)

# What the harness prints. A case announces itself as `TestClass::testcase` on its own
# line before it runs (this is the non-quiet default, and the reason the suite does not
# pass `-q`); an assertion failure is reported as `file:line(TestClass::testcase)`; an
# escaped exception as `TestClass::testcase - Exception: ...`.
_TR_QNAME = r"([A-Za-z_]\w*::[A-Za-z_]\w*)"
_TR_RAN_RE = re.compile(r"^" + _TR_QNAME + r"\s*$", re.M)
_TR_ASSERT_FAIL_RE = re.compile(r"\(" + _TR_QNAME + r"\)")
_TR_EXC_FAIL_RE = re.compile(r"^" + _TR_QNAME + r" - (?:InternalError|Exception|Unknown exception)", re.M)
_TR_COUNT_RE = re.compile(r"^Number of tests: (\d+)", re.M)
