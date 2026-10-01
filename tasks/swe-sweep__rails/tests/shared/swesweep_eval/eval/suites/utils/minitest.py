#!/usr/bin/env python3
"""Shared helpers for minitest suite adapters.

minitest has no machine-readable reporter in a stock checkout — its output is dots and a
counts line — so a per-test verdict is read the only way that is reliable without adding a
gem to the image: run each requested test on its own and read the counts line. Patches add
a handful of tests, so that is a handful of processes, not hundreds.
"""
import re

from swesweep_eval.eval.suites.utils.compiled import _patched_files, _run
from swesweep_eval.eval.suites.utils.logging import log

_TEST_SUFFIX = "_test.rb"

# A test the patch ADDS, spelled the two ways minitest allows in a Rails suite: a plain
# `def test_*` method, or the `test "..." do` macro.
_MINITEST_DEF_RE = re.compile(r"^\+\s*def\s+(?P<name>test_\w+)")
_MINITEST_MACRO_RE = re.compile(r"^\+\s*test\s+(['\"])(?P<desc>.+?)\1\s+do\b")
# The same two in a hunk header, which is where an *edited* test's declaration shows up
# when the patch only changes the body. The pytest, gtest and rspec suites read their
# enclosing declaration from the hunk header the same way.
_MINITEST_DEF_HUNK_RE = re.compile(r"^@@ .*@@.*\bdef\s+(?P<name>test_\w+)")
_MINITEST_MACRO_HUNK_RE = re.compile(r"^@@ .*@@.*\btest\s+(['\"])(?P<desc>.+?)\1\s+do\b")

# minitest's own summary, the only structured thing it prints:
# "12 runs, 34 assertions, 0 failures, 0 errors, 0 skips"
_MINITEST_COUNTS_RE = re.compile(
    r"(\d+)\s+runs?,\s*\d+\s+assertions?,\s*(\d+)\s+failures?,\s*(\d+)\s+errors?,\s*(\d+)\s+skips?"
)


def macro_method_name(description):
    """The method `test "..." do` actually defines.

    ActiveSupport::TestCase.test builds it as ``"test_" + name.gsub(/\\s+/, "_")`` — no
    downcasing and no punctuation stripping, so anything cleverer than this would be wrong.
    """
    return "test_" + re.sub(r"\s+", "_", description)


def minitest_targets(diff):
    """``([test files], [test method names])`` for one test patch.

    The hunk header is only read when the patch adds no test of its own: in a patch that
    *adds* tests the header names the preceding, unrelated test.
    """
    files = [p for p in _patched_files(diff) if p.endswith(_TEST_SUFFIX)]
    added, edited = [], []
    for line in diff.splitlines():
        m = _MINITEST_DEF_RE.match(line)
        if m:
            added.append(m.group("name"))
            continue
        m = _MINITEST_MACRO_RE.match(line)
        if m:
            added.append(macro_method_name(m.group("desc")))
            continue
        m = _MINITEST_DEF_HUNK_RE.match(line)
        if m:
            edited.append(m.group("name"))
            continue
        m = _MINITEST_MACRO_HUNK_RE.match(line)
        if m:
            edited.append(macro_method_name(m.group("desc")))
    return sorted(set(files)), sorted(set(added or edited))


def _counts(text):
    """The last counts line minitest printed, as ``(runs, bad)``, or ``None``."""
    matches = _MINITEST_COUNTS_RE.findall(text)
    if not matches:
        return None
    runs, failures, errors, _skips = matches[-1]
    return int(runs), int(failures) + int(errors)


def component_of(path):
    """The Rails gem a test path belongs to.

    Rails is a monorepo of gems and each one has its own ``bin/test``, its own load path
    and its own test helper — a test can only be run from inside its own gem.
    """
    return path.split("/")[0]


def all_components(env, repo, runner="bin/test"):
    """Every gem in the monorepo that carries its own ``runner``, sorted.

    The whole-suite call has no paths to group by, and a monorepo has no single command
    that runs everything, so the population is discovered the way the runner defines it:
    one gem per directory that has a ``bin/test``.
    """
    depth = str(1 + len(runner.strip("/").split("/")))
    result = env.execute(
        ["find", repo, "-mindepth", depth, "-maxdepth", depth, "-type", "f", "-path", "*/" + runner]
    )
    if result.returncode != 0:
        return []
    found = []
    for line in result.stdout.splitlines():
        component = line.strip()[len(repo) + 1 : -(len(runner) + 1)]
        if component and "/" not in component:
            found.append(component)
    return sorted(set(found))


def run_minitest(env, repo, files, names, timeout, runner="bin/test", bundler=True):
    """Run the selected minitest tests, one process per test name.

    Returns ``(outcomes, n, error, timed_out)``, the reproduction-suite protocol.

    One process per name is what buys a per-test verdict: minitest reports only totals, so
    a batched run says *how many* failed but never *which*. `-n` takes the method name and
    compares it for equality, so each run is exactly one test.

    A patch that named no test at all falls back to running its whole file, which is one
    verdict for the file.

    ``files=None`` is the runner protocol's whole-suite call (the eval driver's visible
    baseline). There is no one command that runs a monorepo, so it becomes one bare
    ``runner`` invocation per gem — and, minitest printing only totals, one pass/fail
    verdict per gem. That is the coarsest gate of any suite here: a regression anywhere in
    a gem shows up, but not which test it broke.
    """
    by_component = {}
    if files is None:
        by_component = {component: [] for component in all_components(env, repo, runner)}
    for path in files or []:
        by_component.setdefault(component_of(path), []).append(path)

    outcomes = {}
    total = 0
    prefix = ["bundle", "exec"] if bundler else []
    for component, paths in sorted(by_component.items()):
        selectors = [["-n", name] for name in names] or [[]]
        for selector in selectors:
            # The paths are repo-relative but `bin/test` runs from inside its own gem.
            local = [p[len(component) + 1 :] for p in paths]
            cmd = prefix + [runner] + local + selector
            result = _run(env, cmd, timeout=timeout, cwd="%s/%s" % (repo, component))
            if result is None:
                log("minitest TIMEOUT after %ds" % timeout)
                return {}, 0, False, True
            log("minitest %s rc=%d" % (" ".join(cmd), result.returncode))
            log(result.stdout[-2000:])
            counts = _counts(result.stdout)
            key = "%s::%s" % (component, selector[1]) if selector else (paths[0] if paths else component)
            if counts is None:
                # minitest never got as far as printing a summary: the file failed to load,
                # which is the same thing a pytest collection error is.
                log("no minitest summary for %s" % key)
                return {}, 0, True, False
            runs, bad = counts
            total += runs
            # `runs == 0` means `-n` matched nothing. The test patch is applied at this
            # point, so the name should exist — if it does not, the name was derived wrong
            # and nothing was measured. Reporting "passed" here would silently sink the
            # subtask, so it is an error.
            if selector and runs == 0:
                log("no test matched -n %s" % selector[1])
                return {}, 0, True, False
            outcomes[key] = "failed" if bad else "passed"
    return outcomes, total or len(outcomes), False, False


def run_minitest_all(env, repo, command, timeout):
    """Run a task's declared aggregate minitest command for the visible-suite gate."""
    result = _run(env, list(command), timeout=timeout, cwd=repo)
    if result is None:
        log("minitest visible suite TIMEOUT after %ds" % timeout)
        return {}, 0, False, True
    log("minitest visible suite rc=%d" % result.returncode)
    log(result.stdout[-2000:])
    counts = _counts(result.stdout)
    if counts is None:
        return {}, 0, True, False
    runs, bad = counts
    outcome = "failed" if result.returncode or bad else "passed"
    return {"<suite>": outcome}, runs, False, False
