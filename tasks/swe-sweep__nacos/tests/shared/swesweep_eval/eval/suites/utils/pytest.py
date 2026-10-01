#!/usr/bin/env python3

# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""Shared target discovery and execution for pytest adapters."""

import re
import subprocess
import xml.etree.ElementTree as ET

from swesweep_eval.eval.suites.utils.logging import log

ADD_TEST_RE = re.compile(r"^\+\s*def\s+(test_[A-Za-z0-9_]+)")
HUNK_FN_RE = re.compile(r"^@@ .*@@.*\bdef\s+(test_[A-Za-z0-9_]+)")
PLUSFILE_RE = re.compile(r"^\+\+\+ b/(.+)$", re.M)


def target_tests(diff):
    """Test files the patch touches + the added/enclosing test function names."""
    files = [f for f in PLUSFILE_RE.findall(diff) if f != "/dev/null" and f.endswith(".py")]
    names = []
    for line in diff.splitlines():
        m = ADD_TEST_RE.match(line)
        if m:
            names.append(m.group(1))
        h = HUNK_FN_RE.match(line)
        if h:
            names.append(h.group(1))
    return sorted(set(files)), sorted(set(names))


def run_pytest(env, repo, files, names, timeout):
    """Run pytest on ``files``, narrowed by ``-k`` to ``names``. Returns
    ``(outcomes {nodeid: passed|failed|error|skipped}, n_collected, collection_error,
    timed_out)``.

    ``files=None`` is the runner protocol's whole-suite call (the eval driver's visible
    baseline): pass no paths and let pytest discover from the repo root."""
    xml = "/tmp/report.xml"
    if env.exists(xml):
        env.remove(xml)
    cmd = ["python", "-m", "pytest"] + list(files or []) + [
        "-p",
        "no:cacheprovider",
        "-o",
        "addopts=",
        "-q",
        "--continue-on-collection-errors",
        "--junitxml=" + xml,
    ]
    if names:
        cmd += ["-k", " or ".join(names)]
    try:
        r = env.execute(cmd, cwd=repo, timeout=timeout)
    except subprocess.TimeoutExpired:
        log(f"pytest TIMEOUT after {timeout}s")
        return {}, 0, False, True
    log(f"pytest rc={r.returncode}")
    log(r.stdout[-1500:])
    if not env.exists(xml):
        return {}, 0, True, False
    outcomes = {}
    coll_err = False
    try:
        root = ET.fromstring(env.read_text(xml))
    except ET.ParseError as exc:
        # An unterminated report means the process died mid-run, which is the same
        # unmeasurable outcome as never writing one — not a reason to sink the whole eval.
        log(f"unparseable pytest report {xml}: {exc}")
        return {}, 0, True, False
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
                    coll_err = True
                elif k.tag == "skipped":
                    outcome = "skipped"
            outcomes[key] = outcome
    n = len([o for o in outcomes.values() if o != "skipped"])
    return outcomes, n, coll_err, False
