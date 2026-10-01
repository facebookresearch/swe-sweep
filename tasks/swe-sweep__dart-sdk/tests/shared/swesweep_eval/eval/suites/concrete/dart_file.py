# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""DartFileSuite suite adapter."""

import json
import posixpath
import re
import shlex

from ..base import ReproductionSuite
from ..utils.compiled import _patched_files, _run
from ..utils.logging import log

# Where `tools/test.py --write-results` is told to put its one-JSON-object-per-line report.
_RESULTS = "/tmp/swesweep-dart-results.json"

# The flags a Dart test file declares for itself, in a comment marker the SDK's own runner
# reads. Without them a `tests/language/` file that exercises an in-progress language
# feature does not fail — it does not *compile*, before and after the gold patch alike.
_OPTION_MARKER = re.compile(r"^//\s*(?:VMOptions|SharedOptions|DartOptions)\s*=(.*)$", re.M)


class DartFileSuite(ReproductionSuite):
    """One `dart <test file>` per test file the patch touches.

    **The outcome key is the file, not the case.** The Dart SDK holds two incompatible
    kinds of test in one tree: the `package:test` suites under `pkg/<name>/test/`, whose
    cases are closures registered at run time and have no signature a diff reader could
    name, and the plain assert programs under `tests/`, which have no cases at all — the
    file *is* the test. The one invocation that drives both is running the file with the
    built SDK's `dart`, and its exit status is the verdict. That is coarser than the
    per-case suites, and exactly right for a fail→pass census: the file must fail before
    the gold patch and pass after it.

    **A `pkg/` fix needs no rebuild.** The analyzer, the CFE and dart2js are Dart source
    that the built SDK reads at run time, so only a `runtime/` fix has to pay for ninja.
    The task therefore drives the build itself (`build_cmd`) rather than folding it into
    the test command the way the .NET and JVM adapters do.

    ``dart`` is the built SDK's binary inside the image; ``dart_args`` are the flags the
    repository's own runner passes (``--enable-asserts`` is not optional — half of the
    corpus asserts rather than throwing).

    ``visible_selectors`` is the *evaluation* gate's whole-suite mode, and it is the one
    part of this adapter that does not share a code path with reproduction: running every
    `_test.dart` in the tree one process at a time is not a suite, it is a week, so the
    gate delegates to the repository's own runner (`tools/test.py`) and reads the
    machine-readable report it writes.
    """

    no_targets = "test patch touched no Dart test file"

    def __init__(self, dart="out/ReleaseX64/dart-sdk/bin/dart", dart_args=("--enable-asserts",),
                 visible_selectors=(), test_py="tools/test.py", mode="release", arch="x64"):
        self.dart = dart
        self.dart_args = list(dart_args)
        self.visible_selectors = list(visible_selectors)
        self.test_py = test_py
        self.mode = mode
        self.arch = arch

    def targets(self, diff, env=None):
        """``([test file paths], [])`` — no names: the file is the unit."""
        del env
        found = []
        for path in _patched_files(diff):
            if path.endswith("_test.dart") and path not in found:
                found.append(path)
        return sorted(found), []

    @staticmethod
    def declared_options(text):
        """The flags the test file asks for in its own comment markers.

        A Dart test that exercises an in-progress language feature carries
        ``// SharedOptions=--enable-experiment=records``, and one that needs a particular
        VM configuration carries ``// VMOptions=…``. The SDK's own runner reads those and
        passes them on. Running the file bare does not, and the result is not a failing
        test but a file that does not *compile* — identically before and after the gold
        patch, so the bug silently does not reproduce.
        """
        args = []
        for m in _OPTION_MARKER.finditer(text):
            try:
                args += shlex.split(m.group(1).strip())
            except ValueError:
                continue
        # A file may carry several VMOptions lines to request several *runs*; the census
        # only needs one, and the union is the closest single run to what they ask for.
        seen = set()
        return [a for a in args if not (a in seen or seen.add(a))]

    def _run_one(self, env, repo, path, timeout):
        full = posixpath.join(repo, path)
        declared = self.declared_options(env.read_text(full))
        cmd = [self.dart] + self.dart_args + declared + [path]
        res = _run(env, cmd, timeout=timeout, cwd=repo)
        if res is None:
            return None
        log("dart %s rc=%d" % (path, res.returncode))
        log(res.stdout[-2000:])
        return res

    def _run_all(self, env, repo, timeout):
        """The repository's own runner over the configured selectors, read back from the
        JSON report it writes (one object per line, ``{"name": …, "result": "Pass"|…}``)."""
        env.remove(_RESULTS)
        cmd = ["python3", self.test_py, "--mode", self.mode, "--arch", self.arch,
               "--progress", "status", "--write-results", _RESULTS] + self.visible_selectors
        res = _run(env, cmd, timeout=timeout, cwd=repo)
        if res is None:
            log("tools/test.py TIMEOUT after %ds" % timeout)
            return {}, 0, False, True
        log("tools/test.py rc=%d" % res.returncode)
        log(res.stdout[-2500:])
        return self._read_report(env)

    @staticmethod
    def _read_report(env):
        """``(outcomes, n_run, error, timed_out)`` from the runner's JSON report."""
        outcomes = {}
        if not env.exists(_RESULTS):
            # No report at all: the runner never got as far as running, which is the
            # `error` flag rather than a tree full of failing tests.
            return {}, 0, True, False
        for line in env.read_text(_RESULTS).splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            name = row.get("name")
            result = (row.get("result") or "").lower()
            if not name:
                continue
            outcomes[name] = "passed" if result == "pass" else "skipped" if result == "skip" else "failed"
        return outcomes, len([o for o in outcomes.values() if o != "skipped"]), False, False

    def run_tests(self, env, repo, files, names, timeout, jobs):
        del names, jobs
        if files is None:
            return self._run_all(env, repo, timeout)
        outcomes = {}
        error = False
        for path in files:
            if not env.is_file(posixpath.join(repo, path)):
                # The test patch deleted it, or it lives in a suite this image does not
                # build. Not a failure — there is simply nothing to run.
                outcomes[path] = "skipped"
                continue
            res = self._run_one(env, repo, path, timeout)
            if res is None:
                log("dart TIMEOUT after %ds (%s)" % (timeout, path))
                return {}, 0, False, True
            outcomes[path] = "passed" if res.returncode == 0 else "failed"
        ran = len([o for o in outcomes.values() if o != "skipped"])
        if not ran:
            error = False  # every target was skipped; the driver reads that off the counts
        return outcomes, ran, error, False
