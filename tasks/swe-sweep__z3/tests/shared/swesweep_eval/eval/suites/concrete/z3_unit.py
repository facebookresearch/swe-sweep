# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""Z3UnitSuite suite adapter."""

import os
import re

from ..base import FullSuite
from ..utils.compiled import _all_error, _patched_files, _run
from ..utils.logging import log

# `src/test/main.cpp` registers every unit test through an X-macro list:
# `X(bit_vector)` for a plain one, `X_ARGV(smt2print_parse)` for one that reads argv.
_REGISTER_RE = re.compile(r"^\s*X(?:_ARGV)?\(\s*(\w+)\s*\)", re.M)
# The same line as the *test patch* adds it.
_ADDED_RE = re.compile(r"^\+\s*X(?:_ARGV)?\(\s*(\w+)\s*\)", re.M)

# Files that sit in `src/test/` without being a test: the driver itself and the two
# helpers the cases share.
_NOT_A_TEST = frozenset({"main", "memory", "for_each_file"})


class Z3UnitSuite(FullSuite):
    """z3: one ``test-z3`` program, dispatching on the test names given in ``argv``.

    Every in-tree unit test is one ``src/test/<name>.cpp`` defining ``tst_<name>()``, and
    ``src/test/main.cpp`` lists the names in an X-macro table. ``test-z3 <name>`` runs
    just that one; a test that fails does so by asserting, so it takes the process down.

    Two things about that driver decide the shape of this adapter:

    - **A name it does not know is silently ignored** — the dispatch is a chain of
      ``strcmp``s and ``main`` returns 0 when none matches, so an exit status of 0 alone
      does not mean a test ran. It prints ``PASS`` after each case it does run, so a
      verdict needs *both*.
    - **The binary is ``EXCLUDE_FROM_ALL``** (``src/test/CMakeLists.txt``), so it is a
      target of its own and never comes along with a plain ``cmake --build``.

    Only the top-level ``src/test/*.cpp`` files are tests. ``src/test/lp/`` and
    ``src/test/fuzzing/`` are helper components linked into the same program, and a patch
    that touches only those has no addressable case — reported as no target rather than
    scored on nothing.
    """

    no_targets = "test patch touched no z3 unit test (src/test/*.cpp)"

    def __init__(self, build_dir="/build", binary=None, target="test-z3", repo=None):
        self.build_dir = build_dir
        self.binary = binary or os.path.join(build_dir, "test-z3")
        self.target = target
        self.repo = repo or "/z3"

    @classmethod
    def from_config(cls, values, *, repo, create_suite):
        del create_suite
        return cls(repo=repo, **values)

    # --- resolving the diff --------------------------------------------------

    def _registered(self, env):
        """The names ``src/test/main.cpp`` registers, read out of the container."""
        if env is None:
            return set()
        try:
            text = env.read_text(os.path.join(self.repo, "src/test/main.cpp"))
        except Exception as exc:  # noqa: BLE001 - treated as "no table to check against"
            log("z3: cannot read src/test/main.cpp: %s" % exc)
            return set()
        return set(_REGISTER_RE.findall(text))

    def targets(self, diff, env=None):
        """``(files, names)`` — the patched unit-test sources and the cases they register.

        A patch that adds a whole test contributes its file's stem; a patch that adds a
        *second* case to an existing file registers a new name in ``main.cpp`` and never
        touches that stem, so the names the diff adds there are collected too.
        """
        known = self._registered(env)
        files = []
        names = []
        for path in _patched_files(diff):
            head, tail = os.path.split(path)
            if head != "src/test" or not tail.endswith(".cpp"):
                continue
            stem = tail[:-4]
            if stem in _NOT_A_TEST:
                continue
            if known and stem not in known:
                log("z3: %s registers no test named %r — dropped" % (path, stem))
                continue
            files.append(path)
            names.append(stem)
        for name in _ADDED_RE.findall(diff):
            if not known or name in known:
                names.append(name)
        if names and not files:
            files.append("src/test/main.cpp")
        return sorted(set(files)), sorted(set(names))

    # --- building ------------------------------------------------------------

    def _build(self, env, timeout, jobs):
        argv = ["cmake", "--build", self.build_dir, "-j", str(jobs), "--target", self.target]
        res = _run(env, argv, timeout=timeout)
        if res is None:
            log("test build TIMEOUT")
            return "test build TIMEOUT", True
        if res.returncode != 0:
            # Expected pre-gold whenever the fix is what makes the test compile.
            log("test build failed:\n" + res.stdout[-1500:])
            return res.stdout, False
        return None, False

    def _run_names(self, env, names, timeout, jobs):
        error, timed_out = self._build(env, timeout, jobs)
        if error is not None:
            return _all_error(names), 0, True, timed_out, error
        outcomes = {}
        chunks = []
        for name in names:
            res = _run(env, [self.binary, name], timeout=timeout)
            if res is None:
                log("z3: %s TIMEOUT after %ds" % (name, timeout))
                return outcomes, len(outcomes), False, True, "\n".join(chunks)
            # Both conditions are needed: an unknown name also exits 0, having run nothing.
            outcomes[name] = "passed" if (res.returncode == 0 and "PASS" in res.stdout) else "failed"
            log("z3: %s rc=%d" % (name, res.returncode))
            chunks.append("$ test-z3 %s\n%s" % (name, res.stdout[-4000:]))
        return outcomes, len(outcomes), False, False, "\n".join(chunks)

    # --- the repro driver's adapter -------------------------------------------

    def run_tests(self, env, repo, files, names, timeout, jobs):
        del repo, files
        outcomes, n_run, build_failed, timed_out, _text = self._run_names(env, names, timeout, jobs)
        return outcomes, n_run, build_failed or not outcomes, timed_out

    # --- the eval driver's adapters -------------------------------------------

    def run_all(self, env, repo, timeout, cap, jobs):
        """The visible suite: ``test-z3 /a``, which runs the whole registered table."""
        del repo
        error, timed_out = self._build(env, timeout, jobs)
        if error is not None:
            return None, timed_out, self._capture("cmake --build test-z3", error, cap)
        res = _run(env, [self.binary, "/a"], timeout=timeout)
        if res is None:
            return None, True, self._capture("test-z3 /a", "test-z3 TIMEOUT", cap)
        # The driver reports no per-case status, only a `PASS` line per case it finished,
        # so the whole run is one outcome — which is what the regression gate needs.
        outcome = "passed" if res.returncode == 0 else "failed"
        return {"test-z3": outcome}, False, self._capture("test-z3 /a", res.stdout, cap)

    def run_selected(self, env, repo, files, names, timeout, cap, jobs):
        del repo, files
        outcomes, _n, _bf, timed_out, text = self._run_names(env, names, timeout, jobs)
        return outcomes, timed_out, self._capture("test-z3 " + " ".join(names), text, cap)

    @staticmethod
    def _capture(command, text, cap):
        clipped, truncated = cap.clip(text)
        return {"command": command, "returncode": None, "text": clipped, "truncated": truncated}
