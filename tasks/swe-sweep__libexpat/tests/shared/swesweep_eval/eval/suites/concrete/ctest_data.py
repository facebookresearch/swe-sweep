# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""CTestDataSuite suite adapter."""

import re

from ..base import FullSuite
from ..utils.compiled import _REPORT, _all_error, _parse_junit, _patched_files, _run
from ..utils.logging import log

class CTestDataSuite(FullSuite):
    """CTest over a **data corpus** — doxygen's ``testing/`` layout.

    :class:`CTestSuite` assumes one compiled program per test, so it builds
    ``<target_prefix><name>`` for each case. A data-driven corpus has no such target: the
    case is a set of *input files* that one already-built program is run against, and CMake
    registers a CTest case per input by globbing the directory. doxygen is the shape —
    ``testing/012_cite.dox`` is the test ``012_cite``, and ``testing/012/`` beside it holds
    the expected output — but so is any harness that drives fixtures through a single binary.

    Two consequences, and they are the whole class:

    - **One build target**, ``all_target``, however many cases are selected.
    - **The case id comes out of the path**, by ``id_re`` against the first segment below
      ``corpus_dir``. Both the input file and the expected-output directory carry the same
      id, so either half of a patch names the test, and the selector is anchored on the id
      rather than on the full name (``012`` matches ``012_cite``, which is what a patch to
      ``testing/012/`` has to do).

    The build tree is reconfigured on every run, as in :class:`CTestSuite`: a test patch that
    adds an input file adds a CTest case, and an already-configured tree does not know about
    it until cmake re-globs.
    """

    no_targets = "test patch touched no case in the CTest data corpus"

    def __init__(self, build_dir="/build", corpus_dir="testing",
                 id_re=r"^(\d{3})", all_target="doxygen", source_subdir=""):
        self.build_dir = build_dir
        self.corpus_dir = corpus_dir.rstrip("/")
        self.id_re = re.compile(id_re)
        self.all_target = all_target
        #: Where ``CMakeLists.txt`` lives, relative to the repo root. Empty for the usual
        #: layout; a repo that keeps its project one directory down (libexpat's
        #: ``expat/``) needs it, or cmake is pointed at a directory with no project in it.
        self.source_subdir = source_subdir.strip("/")

    def targets(self, diff, env=None):
        del env
        files = []
        ids = []
        prefix = self.corpus_dir + "/"
        for path in _patched_files(diff):
            if not path.startswith(prefix):
                continue
            m = self.id_re.match(path[len(prefix):])
            if not m:
                continue
            files.append(path)
            ids.append(m.group(1))
        return sorted(set(files)), sorted(set(ids))

    def _build_and_run(self, env, repo, ids, timeout, jobs):
        """Configure, build the one target, run the selected cases.

        Returns ``(outcomes, n_run, failed_to_build, timed_out, text)`` — the same shape
        :class:`CTestSuite` returns, so the drivers need no special case.
        """
        source = repo + "/" + self.source_subdir if self.source_subdir else repo
        conf = _run(env, ["cmake", "-S", source, "-B", self.build_dir], timeout=timeout)
        if conf is None:
            return _all_error(ids or []), 0, True, True, "cmake configure TIMEOUT"
        if conf.returncode != 0:
            log("cmake configure failed:\n" + conf.stdout[-1500:])
            return _all_error(ids or []), 0, True, False, conf.stdout

        build = _run(env, ["cmake", "--build", self.build_dir, "-j", str(jobs),
                      "--target", self.all_target], timeout=timeout)
        if build is None:
            log("build TIMEOUT")
            return _all_error(ids or []), 0, True, True, "build TIMEOUT"
        if build.returncode != 0:
            # Expected pre-gold whenever the fix is what makes the program compile.
            log("build failed:\n" + build.stdout[-1500:])
            return _all_error(ids or []), 0, True, False, build.stdout

        if env.exists(_REPORT):
            env.remove(_REPORT)
        argv = ["ctest", "--test-dir", self.build_dir, "-j", str(jobs), "--output-on-failure",
                "--output-junit", _REPORT]
        if ids is not None:
            argv += ["-R", "^(" + "|".join(re.escape(i) for i in ids) + ")"]
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

    def run_tests(self, env, repo, files, names, timeout, jobs):
        outcomes, n_run, build_failed, timed_out, _text = self._build_and_run(
            env, repo, names, timeout, jobs)
        if outcomes is None:
            return {}, 0, not timed_out, timed_out
        # No case matched the selector: the patch names an input CMake does not register.
        return outcomes, n_run, build_failed or not outcomes, timed_out

    def run_all(self, env, repo, timeout, cap, jobs):
        outcomes, _n, _bf, timed_out, text = self._build_and_run(env, repo, None, timeout, jobs)
        return outcomes, timed_out, self._capture("ctest (whole corpus)", text, cap)

    def run_selected(self, env, repo, files, names, timeout, cap, jobs):
        outcomes, _n, _bf, timed_out, text = self._build_and_run(env, repo, names, timeout, jobs)
        return outcomes, timed_out, self._capture("ctest -R " + " ".join(names), text, cap)

    @staticmethod
    def _capture(command, text, cap):
        clipped, truncated = cap.clip(text)
        return {"command": command, "returncode": None, "text": clipped, "truncated": truncated}
