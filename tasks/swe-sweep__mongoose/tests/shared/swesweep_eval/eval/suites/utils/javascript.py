#!/usr/bin/env python3
"""Shared target, process, and report helpers for JavaScript adapters."""
import json
import os
import re
import subprocess
import xml.etree.ElementTree as ET

from swesweep_eval.eval.suites.utils.logging import log
from swesweep_eval.eval.suites.utils.pytest import PLUSFILE_RE
from swesweep_eval.eval.suites.utils.evaluation import parse_xml

# What a JavaScript test file is called. Both ecosystems mark specs by suffix rather than by
# directory, and both TypeScript and plain JS appear in the same repo (nuxt's suite is .ts,
# mongoose's is .js), so the suffix list carries both.
_SPEC_RE = re.compile(r"\.(test|spec)\.[cm]?[jt]sx?$")
# mongoose keeps unsuffixed test files in test/ (test/model.query.test.js is the norm, but
# test/index.test.js and test/common.js coexist); a path under a test dir counts too.
_TEST_DIR_RE = re.compile(r"(^|/)(test|tests|__tests__)/")
_JS_EXT_RE = re.compile(r"\.[cm]?[jt]sx?$")

# An added test: `it('name', ...)`, `test("name", ...)`, `it.each(...)('name')`, with any of
# the three quote styles. Only *added* lines (the diff's `+`) are considered — a test the
# patch merely moves is not what it is testing.
_ADD_TEST_RE = re.compile(
    r"^\+\s*(?:it|test)"          # the call
    r"(?:\.\w+)*"                  # .only / .each / .skip / .concurrent
    r"(?:\([^)]*\))?"              # .each(table) argument list
    r"\s*\(\s*"                    # opening paren of the test call
    r"(['\"`])(.+?)\1"             # the name, in any quote style
)

_REPORT = "/tmp/js-report.xml"
_JSON_REPORT = "/tmp/js-report.json"
_QUNIT_REPORT = "/tmp/qunit-report.json"
_QUNIT_FILE_RE = re.compile(r"^test/unit/(?:src|addons)/.+\.tests\.js$")
_ADD_QUNIT_TEST_RE = re.compile(
    r"^\+\s*QUnit\.(?:test|todo|skip)\s*\(\s*(['\"])(.+?)\1"
)


# jest stores a spec's snapshots beside it as `__snapshots__/<the spec's filename>.snap`, so
# the snapshot file names its own spec. A patch that only updates a stored snapshot is a real
# fail→pass test change — the assertion lives in the .snap — and without this it resolves to
# no spec at all.
_SNAP_RE = re.compile(r"(^|/)__snapshots__/(?P<spec>[^/]+)\.snap$")


def _spec_of_snapshot(path):
    """The spec a ``__snapshots__/*.snap`` file belongs to, or None."""
    m = _SNAP_RE.search(path)
    if not m:
        return None
    return path[: m.start(0) + 1].lstrip("/") + m.group("spec") if m.start(0) else m.group("spec")


def _spec_files(diff, extra_spec_res=()):
    """The JS/TS test files the patch touches.

    ``extra_spec_res`` are additional compiled patterns a task's suite declares for a repo
    whose spec naming the two defaults above do not cover. jest's own default ``testMatch``
    is ``**/?(*.)+(spec|test).[jt]s?(x)`` — the ``*.`` is *optional* — so a file named plainly
    ``test.js`` beside the module it tests is a spec to jest even though ``_SPEC_RE`` wants
    a dot before the word. date-fns is laid out that way throughout. Keeping it opt-in
    rather than widening ``_SPEC_RE`` leaves every already-measured task's target set
    exactly as it was.
    """
    out = []
    for f in PLUSFILE_RE.findall(diff):
        if f == "/dev/null":
            continue
        snap = _spec_of_snapshot(f)
        if snap:
            out.append(snap)
            continue
        if not _JS_EXT_RE.search(f):
            continue
        if _SPEC_RE.search(f) or _TEST_DIR_RE.search(f) or any(r.search(f) for r in extra_spec_res):
            out.append(f)
    return sorted(set(out))


def _added_names(diff):
    """The names of the tests the patch adds."""
    names = []
    for line in diff.splitlines():
        m = _ADD_TEST_RE.match(line)
        if m:
            names.append(m.group(2))
    return sorted(set(names))


def _pattern(names):
    """One regex alternation matching any of ``names``, literally.

    ``re.escape`` is the right escaping for both runners: vitest builds a JS ``RegExp`` from
    ``-t`` and mocha does the same with ``--grep``, and the character classes that need
    escaping are the same in both dialects. A name containing a slash is fine — neither
    treats it specially inside a pattern built from a plain string.
    """
    return "(" + "|".join(re.escape(n) for n in names) + ")"


def _resolve_bin(env, cwd, name):
    """The argv prefix that runs ``name``, resolved from ``cwd`` upwards.

    ``npx --no-install`` looks only in the *current* directory's ``node_modules``, which is
    wrong in a workspace: yarn and pnpm hoist the runners to the repo root, so running jest
    from inside a package answers ``not found: jest`` and the census reads it as a suite that
    could not start. Walking up for ``node_modules/.bin/<name>`` is what npx should do and is
    what every one of these repos actually needs; npx stays as the fallback so a layout
    without a hoisted binary still works.
    """
    d = os.path.abspath(cwd)
    while True:
        candidate = os.path.join(d, "node_modules", ".bin", name)
        if env.exists(candidate):
            return [candidate]
        # pnpm with no hoisting installs the package but sometimes writes no `.bin` shim for
        # it (prisma's tree has `packages/client/node_modules/jest` and no `.bin/jest`), so
        # fall back to the package's own entry point.
        for rel in (os.path.join(name, "bin", name + ".js"),
                    os.path.join(name, "bin", name)):
            direct = os.path.join(d, "node_modules", rel)
            if env.exists(direct):
                return ["node", direct]
        parent = os.path.dirname(d)
        if parent == d:
            return ["npx", "--no-install", name]
        d = parent


def _parse_junit(env, path):
    """``(outcomes {name: passed|failed|error|skipped}, n_run, error)`` from a JUnit file.

    Same shape the pytest suite reports, so the drivers need no special case: a JS runner
    that fails to load a spec at all (a syntax error, a missing import) records it as an
    ``error`` testcase, which is the collection-error equivalent and counts as failing
    pre-gold *and* as not passing post-gold.
    """
    if not env.exists(path):
        return {}, 0, True
    try:
        root = parse_xml(env.read_text(path))
    except ET.ParseError:
        log("could not parse the JUnit report")
        return {}, 0, True
    outcomes = {}
    had_error = False
    suites = [root] if root.tag == "testsuite" else root.iter("testsuite")
    for suite in suites:
        for tc in suite.findall("testcase"):
            key = (tc.get("classname", "") + " " + tc.get("name", "")).strip()
            outcome = "passed"
            for k in list(tc):
                if k.tag == "failure":
                    outcome = "failed"
                elif k.tag == "error":
                    outcome = "error"
                    had_error = True
                elif k.tag == "skipped":
                    outcome = "skipped"
            outcomes[key] = outcome
    n = len([o for o in outcomes.values() if o != "skipped"])
    return outcomes, n, had_error


def _parse_jest_json(env, path):
    """``(outcomes, n_run, error)`` from jest's own ``--json`` report.

    jest writes JUnit only through the third-party ``jest-junit`` reporter, which the
    base-commit image would have to have installed — a dependency the repo does not have and
    we cannot add without changing the tree under test. Its native ``--json`` carries strictly
    more: every assertion with its full title path *and* the per-file status, which is what
    tells a suite that failed to load apart from a suite whose tests failed.

    A file that never ran (a syntax error in the patch, an import that does not resolve) has
    ``status == "failed"`` with no assertions; that is the collection-error equivalent and is
    reported as ``error``, so it counts as failing pre-gold and as not passing post-gold.
    """
    if not env.exists(path):
        return {}, 0, True
    try:
        report = json.loads(env.read_text(path))
    except ValueError:
        log("could not parse the jest report")
        return {}, 0, True
    outcomes = {}
    had_error = False
    for suite in report.get("testResults", []):
        assertions = suite.get("assertionResults", []) or []
        if not assertions and suite.get("status") == "failed":
            outcomes[suite.get("name", "<unknown file>")] = "error"
            had_error = True
            continue
        for a in assertions:
            key = " ".join((a.get("ancestorTitles") or []) + [a.get("title", "")]).strip()
            status = a.get("status", "failed")
            outcomes[key] = {
                "passed": "passed",
                "failed": "failed",
                "pending": "skipped",
                "todo": "skipped",
                "skipped": "skipped",
                "disabled": "skipped",
            }.get(status, "failed")
    n = len([o for o in outcomes.values() if o != "skipped"])
    return outcomes, n, had_error


def _run(env, cmd, repo, timeout, command_env=None):
    """Run one runner invocation, returning ``(rc, timed_out)``."""
    if env.exists(_REPORT):
        env.remove(_REPORT)
    full_env = {}
    full_env["CI"] = "true"          # both runners drop interactive/watch behaviour under CI
    full_env["NO_COLOR"] = "1"
    if command_env:
        full_env.update(command_env)
    if env.exists(_JSON_REPORT):
        env.remove(_JSON_REPORT)
    log("$ " + " ".join(cmd))
    try:
        r = env.execute(cmd, cwd=repo, timeout=timeout, env=full_env, merge_stderr=True)
    except subprocess.TimeoutExpired:
        log("js runner TIMEOUT after %ds" % timeout)
        return None, True
    log("js runner rc=%d" % r.returncode)
    log(r.stdout[-2000:])
    return r.returncode, False
