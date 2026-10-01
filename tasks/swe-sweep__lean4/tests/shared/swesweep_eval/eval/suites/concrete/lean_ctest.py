# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""LeanCTestSuite suite adapter."""

import os
import re

from ..base import FullSuite
from ..utils.compiled import _REPORT, _parse_junit, _patched_files, _run
from ..utils.logging import log

# One entry per `file(GLOB …)` + `add_test(NAME …)` pair in `src/shell/CMakeLists.txt`:
# the directory the corpus is globbed out of, and the CTest name prefix its files get.
# Longest directory first — `tests/lean/run` has to win over `tests/lean`.
#
# `tests/compiler` is registered *twice*, compiled and interpreted, so a patch there names
# two CTest cases and both must run: the fix may only show up under one of them.
_FILE_CORPORA = (
    ("tests/lean/run/", ("leanruntest_",)),
    ("tests/lean/trust0/", ("leant0test_",)),
    ("tests/lean/server/", ("leanservertest_",)),
    ("tests/lean/interactive/", ("leaninteractivetest_",)),
    ("tests/lean/", ("leantest_",)),
    ("tests/compiler/", ("leancomptest_", "leaninterptest_")),
    ("tests/plugin/", ("leanplugintest_",)),
    ("tests/bench/", ("leanbenchtest_",)),
    ("doc/examples/", ("leandocex_",)),
)

# The two corpora whose unit is a *directory*, not a file: everything under one
# subdirectory is one CTest case named after that subdirectory.
_DIR_CORPORA = (
    ("tests/pkg/", "leanpkgtest_"),
    ("src/lake/tests/", "leanlaketest_"),
)

# A golden file sits beside its test and shares its stem: `foo.lean` is the test and
# `foo.lean.expected.out` is what it must print. Changing only the expectation is a
# complete test patch, and it names the same case.
_EXPECTED_SUFFIX = ".expected.out"


class LeanCTestSuite(FullSuite):
    """Lean 4's CTest corpus, keyed on which directory a test file lives in.

    Lean registers its tests by globbing at cmake *configure* time — one ``add_test`` per
    ``.lean`` file, with a prefix per corpus (``tests/lean/run/foo.lean`` becomes
    ``leanruntest_foo.lean``). Two consequences shape this adapter:

    - **the CTest name is derivable from the path alone**, extension included, so a patch
      resolves to its test ids without reading anything; and
    - **cmake has to run again before a test patch's new file exists as a test.** So this
      suite runs the build script itself rather than leaving it to the driver's build
      step, which only happens after the gold patch. Without that, every subtask that
      *adds* a test file would report "nothing ran" pre-gold for a reason that has nothing
      to do with the bug.

    The build script is the same one the image built with, so the per-subtask rebuild is
    an incremental ``make`` in the standing ``build/release`` tree — which Lean's own
    ``.gitignore`` covers, so the runner's ``git clean`` leaves it alone.
    """

    no_targets = "test patch touched no file in a registered Lean test corpus"

    def __init__(
        self,
        build_dir="/lean4/build/release/stage1",
        build_cmd="lean4-build",
        build_timeout=7200,
    ):
        self.build_dir = build_dir
        self.build_cmd = build_cmd
        self.build_timeout = build_timeout

    # --- resolving the diff ------------------------------------------------

    @staticmethod
    def _names_for(path):
        """Every CTest case a patched file belongs to (usually one, sometimes none)."""
        for root, prefix in _DIR_CORPORA:
            if path.startswith(root):
                rest = path[len(root) :].split("/", 1)
                if len(rest) == 2 and rest[0]:
                    return [prefix + rest[0]]
                return []
        for root, prefixes in _FILE_CORPORA:
            if not path.startswith(root):
                continue
            # only the directory itself, not a nested corpus that did not match above
            if "/" in path[len(root) :]:
                return []
            name = os.path.basename(path)
            if name.endswith(_EXPECTED_SUFFIX):
                name = name[: -len(_EXPECTED_SUFFIX)]
            if not name.endswith(".lean"):
                return []
            return [prefix + name for prefix in prefixes]
        return []

    def targets(self, diff, env=None):
        """``(files, ctest names)``."""
        del env
        files = []
        names = []
        for path in _patched_files(diff):
            found = self._names_for(path)
            if found:
                files.append(path)
                names.extend(found)
        return sorted(set(files)), sorted(set(names))

    # --- the one real implementation ---------------------------------------

    def _build_and_run(self, env, repo, names, timeout, jobs):
        """Reconfigure + build, then run ``names`` (or the whole corpus when ``None``).

        Returns ``(outcomes, n_run, build_failed, timed_out, text)``. A build failure is
        reported as such rather than as a set of failed tests: pre-gold it is the ordinary
        case where the fix is what makes the tree compile, and the driver reads it the same
        way it reads a pytest collection error.
        """
        del repo
        build = _run(env, [self.build_cmd], timeout=self.build_timeout)
        if build is None:
            log("lean build TIMEOUT after %ds" % self.build_timeout)
            return None, 0, True, True, "lean build TIMEOUT"
        if build.returncode != 0:
            log("lean build failed:\n" + build.stdout[-1500:])
            return None, 0, True, False, build.stdout

        if env.exists(_REPORT):
            env.remove(_REPORT)
        argv = [
            "ctest", "--test-dir", self.build_dir, "-j", str(jobs),
            "--output-on-failure", "--output-junit", _REPORT,
        ]
        if names is not None:
            argv += ["-R", "^(" + "|".join(re.escape(n) for n in names) + ")$"]
        res = _run(env, argv, timeout=timeout)
        if res is None:
            log("ctest TIMEOUT after %ds" % timeout)
            return None, 0, False, True, "ctest TIMEOUT after %ds" % timeout
        log("ctest rc=%d" % res.returncode)
        log(res.stdout[-1500:])
        if not env.exists(_REPORT):
            return None, 0, False, False, res.stdout
        outcomes, n_run = _parse_junit(env, _REPORT)
        return outcomes, n_run, False, False, res.stdout

    # --- the repro driver's adapter ----------------------------------------

    def run_tests(self, env, repo, files, names, timeout, jobs):
        outcomes, n_run, build_failed, timed_out, _text = self._build_and_run(
            env, repo, names if files is not None else None, timeout, jobs
        )
        if outcomes is None:
            return {}, 0, not timed_out, timed_out
        # No case matched the selector: the patch names a test cmake did not register.
        return outcomes, n_run, build_failed or not outcomes, timed_out

    # --- the eval driver's adapters ----------------------------------------

    def run_all(self, env, repo, timeout, cap, jobs):
        outcomes, _n, _bf, timed_out, text = self._build_and_run(env, repo, None, timeout, jobs)
        return outcomes, timed_out, self._capture("ctest (whole corpus)", text, cap)

    def run_selected(self, env, repo, files, names, timeout, cap, jobs):
        del files
        outcomes, _n, _bf, timed_out, text = self._build_and_run(env, repo, names, timeout, jobs)
        return outcomes, timed_out, self._capture("ctest -R " + " ".join(names), text, cap)

    @staticmethod
    def _capture(command, text, cap):
        clipped, truncated = cap.clip(text)
        return {"command": command, "returncode": None, "text": clipped, "truncated": truncated}
