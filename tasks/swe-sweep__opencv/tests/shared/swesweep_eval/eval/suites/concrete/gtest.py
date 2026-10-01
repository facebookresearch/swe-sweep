# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""GTestSuite suite adapter."""

import fnmatch
import os
import re

from ..base import FullSuite
from ..utils.compiled import (
    _ALL_BINARIES, _GTEST_DECL_RE, _GTEST_HUNK_RE, _GTEST_MACROS, _REPORT,
    _all_error, _parse_junit, _per_file_hunks, _run, died_running,
)
from ..utils.logging import log

class GTestSuite(FullSuite):
    """gtest, many cases per compiled binary — the layout networkit and OpenCV share.

    A test here is a ``TEST(Suite, Name)`` macro (or one of its variants) inside a ``.cpp``
    file, so unlike CTest the test ids are read out of the **diff text**, not out of the
    file's name: one patched file can add several cases and a patch that only edits an
    existing case's body adds none.

    Which binary runs them is a property of *where* the file is. ``binary_re`` matches a
    patched path and, if it has a capture group, that group names the module: OpenCV puts
    each module's cases in ``modules/<mod>/test/`` and links them into
    ``opencv_test_<mod>``. With no capture group every case goes to the one binary the
    repo builds (networkit's monolithic ``networkit_tests``)."""

    no_targets = "test patch added no gtest case in a test source this suite builds"

    def __init__(self, build_dir="/build", bin_dir="/build/bin",
                 binary_re=r"^modules/([^/]+)/(?:test|misc/[^/]+/test)/.*\.cpp$",
                 binary_fmt="opencv_test_%s", binary_glob=None):
        self.build_dir = build_dir
        self.bin_dir = bin_dir
        self.binary_re = re.compile(binary_re)
        self.binary_fmt = binary_fmt
        # set instead of binary_fmt when the path does not name the binary: a shell glob,
        # relative to bin_dir, matching every test executable to run (e.g. "*-test").
        self.binary_glob = binary_glob

    # --- resolving the diff --------------------------------------------------

    def _binary(self, path):
        """The gtest binary a patched test file's cases land in, or ``None`` if the file
        is not a test source of this suite.

        In ``binary_glob`` mode there is no such binary to name — the file only has to be
        recognized as a test source — so this answers the truthy sentinel ``ALL`` and
        :meth:`_plan` does the real work."""
        m = self.binary_re.match(path)
        if not m:
            return None
        if self.binary_glob:
            return _ALL_BINARIES
        return self.binary_fmt % m.group(1) if m.groups() else self.binary_fmt

    def _discovered(self, env):
        """Every built test executable ``binary_glob`` finds, by basename."""
        return sorted(
            os.path.basename(p)
            for p in env.find_files(self.bin_dir)
            if fnmatch.fnmatch(os.path.basename(p), self.binary_glob) and env.is_executable(p)
        )

    def targets(self, diff, env=None):
        del env
        """``(files, names)`` — the patched test sources, and the ``Suite.Name`` ids of the
        cases the patch **adds**.

        Read per file, because a diff of several files is one text and a case belongs to
        the file its hunk is in. A case counts whether the patch **adds** it or **edits**
        it — an edit that tightens an existing assertion is as much a fail→pass as a new
        case, and the edited case is named only in the hunk header. A patch that names no
        case at all has no target, which is reported rather than silently graded against
        the whole binary."""
        files = []
        names = []
        for chunk in _per_file_hunks(diff):
            if not self._binary(chunk.path):
                continue
            found = _GTEST_DECL_RE.findall(chunk.text) + _GTEST_HUNK_RE.findall(chunk.text)
            if found:
                files.append(chunk.path)
                names += [_GTEST_MACROS[macro] + suite + "." + case for macro, suite, case in found]
        return sorted(set(files)), sorted(set(names))

    # --- the one real implementation -----------------------------------------

    def _filter(self, names):
        """A ``--gtest_filter`` that matches exactly ``names`` however they were declared.

        gtest's filter matches the **full** name, which a plain ``TEST`` makes
        ``Suite.Name`` but a parameterized one decorates: ``Instantiation/Suite.Name/3``
        for ``TEST_P``, ``Suite/0.Name`` for ``TYPED_TEST``. So each id contributes all
        four shapes rather than one wildcard around the whole thing, which would also
        match a longer case name that merely starts the same."""
        pats = []
        for n in names:
            suite, _, case = n.partition(".")
            pats += [n, "*/" + n + "/*", suite + "/*." + case, "*/" + suite + "/*." + case]
        return ":".join(pats)

    def _build_and_run(self, env, repo, per_binary, timeout, jobs):
        """Build the named binaries, then run each one's cases. ``per_binary`` maps a
        binary to the case ids to select in it, or to ``None`` for all of them.

        The binaries run with ``repo`` as their working directory, because a test that
        loads a fixture from the source tree does it with a **relative** path (networkit's
        ``input/``) — upstream's own ``add_test`` sets the same ``WORKING_DIRECTORY``.
        ``repo`` is not used for anything else: gtest cases are registered by a macro the
        compiler sees, so nothing has to be re-read from the source tree the way CTest has
        to re-read ``CMakeLists.txt``.

        Returns ``(outcomes, n_run, failed_to_build, timed_out, text)`` — the same shape
        CTestSuite returns, and a build failure is likewise every targeted case erroring."""
        every = sorted(set(n for ns in per_binary.values() if ns for n in ns))
        targets = []
        if not self.binary_glob:
            # Name the binaries to build. In binary_glob mode there is nothing to name —
            # the plan is every binary — so the whole tree is built instead, which is the
            # same incremental build with a longer target list.
            for binary in sorted(per_binary):
                targets += ["--target", binary]
        build = _run(env, ["cmake", "--build", self.build_dir, "-j", str(jobs)] + targets, timeout=timeout)
        if build is None:
            log("test build TIMEOUT")
            return _all_error(every), 0, True, True, "test build TIMEOUT"
        if build.returncode != 0:
            # Expected pre-gold whenever the fix is what makes the test compile.
            log("test build failed:\n" + build.stdout[-1500:])
            return _all_error(every), 0, True, False, build.stdout

        outcomes = {}
        n_run = 0
        reported = 0
        text = []
        for binary in sorted(per_binary):
            if env.exists(_REPORT):
                env.remove(_REPORT)
            argv = [os.path.join(self.bin_dir, binary), "--gtest_output=xml:" + _REPORT]
            names = per_binary[binary]
            if names:
                argv.append("--gtest_filter=" + self._filter(names))
            res = _run(env, argv, timeout=timeout, cwd=repo)
            if res is None:
                log("%s TIMEOUT after %ds" % (binary, timeout))
                return None, 0, False, True, "\n".join(text + [binary + " TIMEOUT"])
            log("%s rc=%d" % (binary, res.returncode))
            log(res.stdout[-1500:])
            text.append(res.stdout)
            if not env.exists(_REPORT):
                log("%s wrote no report" % binary)
                if died_running(res):
                    # It got as far as running cases and then died — a crash takes the
                    # whole process with it, since every case shares one address space,
                    # and gtest writes its report at exit. That IS the pre-gold failure
                    # the census is looking for, so the targeted cases count as erroring.
                    # Without this a crash is indistinguishable from a clean run of
                    # nothing, and the subtask yields no F2P at all.
                    outcomes.update(_all_error(names or []))
                    reported += 1
                    continue
                # Otherwise the program ran nothing. In binary_glob mode that is expected
                # noise — the plan is deliberately every binary in the directory and some
                # are not gtest programs at all (arrow's `arrow-json-integration-test` is
                # a gflags tool that rejects the flags) — so it is skipped, and only a run
                # where NOTHING reported is a suite-level failure. With the binary named
                # from the patched path there is no such slack.
                if not self.binary_glob:
                    return None, 0, False, False, "\n".join(text)
                continue
            reported += 1
            got, ran = _parse_junit(env, _REPORT, qualified=True)
            outcomes.update(got)
            n_run += ran
        if per_binary and not reported:
            return None, 0, False, False, "\n".join(text)
        return outcomes, n_run, False, False, "\n".join(text)

    def _plan(self, env, files, names):
        """Which cases to run in which binary. A case id says nothing about where it
        lives, so it is attributed to the binaries the patched files belong to; with one
        binary — the common case — that is exact.

        In ``binary_glob`` mode the patched files name no binary, so the plan is every
        built one; the filter is what makes that cheap."""
        if self.binary_glob:
            return dict((b, list(names)) for b in self._discovered(env)) if files else {}
        binaries = sorted({b for b in (self._binary(f) for f in files) if b})
        return dict((b, list(names)) for b in binaries)

    # --- the drivers' adapters ------------------------------------------------

    def run_tests(self, env, repo, files, names, timeout, jobs):
        outcomes, n_run, build_failed, timed_out, _text = self._build_and_run(
            env, repo, self._plan(env, files, names), timeout, jobs
        )
        if outcomes is None:
            return {}, 0, not timed_out, timed_out
        return outcomes, n_run, build_failed or not outcomes, timed_out

    def run_all(self, env, repo, timeout, cap, jobs):
        """The visible suite: every gtest binary the image built, all cases.

        The binaries are discovered in ``bin_dir`` rather than listed, so the suite is
        whatever this image actually holds. Note this is the **expensive** end of the
        protocol for a repo with OpenCV's test volume — the regression gate runs it twice
        per eval.
        """
        binaries = self._discovered(env) if self.binary_glob else sorted(
            os.path.basename(path)
            for path in env.find_files(self.bin_dir)
            if os.path.dirname(path) == self.bin_dir
            and os.path.basename(path).startswith(self.binary_fmt.split("%")[0])
        )
        if not binaries:
            return None, False, {"command": "gtest (whole suite)", "returncode": None,
                                 "text": "no gtest binaries in " + self.bin_dir, "truncated": False}
        outcomes, _n, _bf, timed_out, text = self._build_and_run(
            env, repo, dict((b, None) for b in binaries), timeout, jobs
        )
        clipped, truncated = cap.clip(text)
        return outcomes, timed_out, {"command": "gtest (whole suite)", "returncode": None,
                                     "text": clipped, "truncated": truncated}

    def run_selected(self, env, repo, files, names, timeout, cap, jobs):
        outcomes, _n, _bf, timed_out, text = self._build_and_run(
            env, repo, self._plan(env, files, names), timeout, jobs
        )
        clipped, truncated = cap.clip(text)
        return outcomes, timed_out, {
            "command": "gtest " + " ".join(names), "returncode": None,
            "text": clipped, "truncated": truncated,
        }
