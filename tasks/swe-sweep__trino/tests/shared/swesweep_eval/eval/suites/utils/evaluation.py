#!/usr/bin/env python3

# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""Shared visible-suite policy, pytest execution, and output capture."""
import os
import re
import subprocess
import xml.etree.ElementTree as ET
from contextlib import redirect_stderr
from io import StringIO

from swesweep_eval.eval.suites.utils.logging import log
from swesweep_eval.eval.suites.utils.pytest import target_tests

ANYFILE_RE = re.compile(r"^(?:\+\+\+ b/|--- a/)(.+)$", re.M)

OVER_BUDGET_TAIL = 2000
_INVALID_XML_CHARS_RE = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]")



def is_test_file(path, test_dirs=()):
    """Whether the agent's edit to ``path`` is an edit to a *test*, which eval reverts
    before scoring (an agent must not be allowed to grade itself).

    The directory check is on path **segments**, not on ``"/tests/" in path``: a repo
    whose suite is a top-level tree, like igraph's ``tests/unit/…``, has no leading slash
    to match, and a substring test would leave those edits in place. ``test_dirs`` adds
    the repos whose test tree is not called ``test``/``tests`` at all (gdal: ``autotest``)
    — the same names its crawler's ``test_globs`` claim.

    The suffix list is per *framework convention*, which is why V and Elixir are in it:
    both keep their test files inline beside the code (``strings/builder_test.v``), so no
    directory rule can reach them. ``.vv`` is there for the same reason — it is V's
    extension for a program that exists only as test data.
    """
    parts = path.split("/")
    base = parts[-1]
    dirs = set(parts[:-1])
    return (bool(dirs & (set(test_dirs) | {"test", "tests", "__tests__"}))
            or base.startswith("test_")
            or base.endswith(("_test.py", "_test.go", "_test.c", "_test.cc", "_test.cpp", "Test.java",
                              "_test.v", "_test.exs", ".vv"))
            or re.search(r"\.(?:test|spec|tests)\.[cm]?[jt]sx?$", base) is not None
            or base == "conftest.py")


def touched_files(diff):
    files = set()
    for m in ANYFILE_RE.finditer(diff):
        f = m.group(1)
        if f != "/dev/null":
            files.add(f)
    return sorted(files)



def parse_xml(text):
    """Parse a report after removing characters XML 1.0 cannot represent."""
    try:
        return ET.fromstring(text)
    except ET.ParseError:
        cleaned = _INVALID_XML_CHARS_RE.sub("", text)
        if cleaned == text:
            raise
        return ET.fromstring(cleaned)


def parse_junit(env, xml):
    outcomes = {}
    if not env.exists(xml):
        return outcomes
    root = parse_xml(env.read_text(xml))
    suites = [root] if root.tag == "testsuite" else list(root)
    for suite in suites:
        for tc in suite.findall("testcase"):
            key = (tc.get("classname", "") + "::" + tc.get("name", "")).strip(":")
            outcome = "passed"
            for k in list(tc):
                if k.tag == "failure":
                    outcome = "failed"
                elif k.tag == "error":
                    outcome = "error"
                elif k.tag == "skipped":
                    outcome = "skipped"
            outcomes[key] = outcome
    return outcomes


def passed_set(outcomes):
    return set(k for k, v in outcomes.items() if v == "passed")



class OutputCapture:
    """Budgeted capture of every pytest invocation's console output.

    We keep the console text because it is often the only diagnostic, but a broken build
    or a mass regression can make the suite dump without limit — and the verdict travels
    as one JSON. So each invocation is capped (head + tail, the informative ends) and the
    whole eval has a budget; past it, later invocations keep only a short tail. Anything
    capped is flagged ``truncated``, so a cut log can never be mistaken for the whole."""

    def __init__(self, limit, budget):
        self.limit = limit
        self.budget = budget
        self.spent = 0

    def clip(self, text):
        text = text or ""
        if self.spent >= self.budget:
            if len(text) <= OVER_BUDGET_TAIL:
                return text, False
            return ("[... output budget for this eval is spent; last %d chars ...]\n" % OVER_BUDGET_TAIL
                    + text[-OVER_BUDGET_TAIL:], True)
        if len(text) > self.limit:
            head, tail = self.limit // 2, self.limit - self.limit // 2
            cut = len(text) - self.limit
            text = text[:head] + "\n\n[... %d chars cut ...]\n\n" % cut + text[-tail:]
            truncated = True
        else:
            truncated = False
        self.spent += len(text)
        return text, truncated


def run_pytest(env, repo, paths, names, timeout, cap, extra_args=()):
    """Run pytest on ``paths`` (narrowed by ``-k`` to ``names``). Returns
    ``(outcomes|None, timed_out, captured)``. ``None`` outcomes means no report was
    produced; ``captured`` is kept even for a timeout or crash, since that is exactly when
    the console output is the only diagnostic.

    ``extra_args`` are repo-specific pytest flags. They are passed only where the caller
    asks for them — in practice only to the visible-suite runs, never to the targeted
    per-subtask runs, since anything that deselects tests must not be able to deselect the
    one test that proves a bug."""
    xml = "/tmp/report.xml"
    if env.exists(xml):
        env.remove(xml)
    cmd = ["python", "-m", "pytest"] + list(paths) + [
        "-p", "no:cacheprovider", "-o", "addopts=", "-q",
        "--continue-on-collection-errors", "--junitxml=" + xml,
    ] + list(extra_args)
    if names:
        cmd += ["-k", " or ".join(names)]
    captured = {"command": " ".join(cmd), "returncode": None, "text": "", "truncated": False}
    try:
        # stderr folded into stdout so the captured text reads like the real console, in
        # order, rather than two streams glued together after the fact.
        r = env.execute(cmd, cwd=repo, timeout=timeout, merge_stderr=True)
    except subprocess.TimeoutExpired as e:
        log("pytest TIMEOUT after %ds" % timeout)
        partial = e.output or ""
        if not isinstance(partial, str):  # bytes when the child died before decoding
            partial = partial.decode("utf-8", "replace")
        captured["text"], captured["truncated"] = cap.clip(
            partial + "\n\n[... pytest timed out after %ds and was killed ...]\n" % timeout)
        return None, True, captured
    log("pytest rc=%d" % r.returncode)
    log(r.stdout[-1200:])
    captured["returncode"] = r.returncode
    captured["text"], captured["truncated"] = cap.clip(r.stdout)
    if not env.exists(xml):
        return None, False, captured
    return parse_junit(env, xml), False, captured
