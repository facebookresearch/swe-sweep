# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""DmdTestsuiteSuite suite adapter."""

import re
import subprocess

from ..base import ReproductionSuite
from ..utils.compiled import _patched_files
from ..utils.logging import log

# One case of dmd's compiler corpus. The category directory *is* the assertion: a file
# under `compilable/` must compile, one under `fail_compilation/` must not (and must emit
# exactly the diagnostics written into its `TEST_OUTPUT:` comment block), one under
# `runnable/` must compile, link and exit zero.
#
# `compiler/` is the post-2023 prefix, added when the repo absorbed druntime and the
# compiler moved down a level; before that the same corpus sat at the top level. Both
# spellings are matched so one suite serves every anchor.
_CASE_RE = re.compile(
    r"^(?P<root>(?:compiler/)?test)/"
    r"(?P<category>compilable|fail_compilation|runnable|runnable_cxx|dshell)/"
    r"(?P<name>[^/]+\.(?:d|c|i|sh))$"
)

# The support files a case pulls in (`extra-files/`, `imports/`) are *not* cases: run.d
# has no selector for them, and the case that imports one is somewhere else in the
# corpus. They are matched only so they can be dropped knowingly rather than by falling
# off the end of `_CASE_RE`.
_SUPPORT_RE = re.compile(
    r"^(?:compiler/)?test/(?:compilable|fail_compilation|runnable|runnable_cxx|dshell)/"
    r"(?:extra-files|imports)/"
)


class DmdTestsuiteSuite(ReproductionSuite):
    """dmd's own compiler corpus, driven by ``test/run.d``.

    A dmd bug fix ships its test as **one D source file** dropped into one of the corpus
    directories, with the diagnostics it must produce written into a comment block inside
    that same file. There is no test function to name and no report file to read: the
    corpus runner compiles the case, compares what came out against what the comment says,
    and reports the verdict in its exit status.

    So this suite resolves a test patch to *file names* and runs ``run.d`` once per name.
    Per case rather than one batched invocation because the census wants an outcome per
    test rather than one for the batch; the first invocation pays for building the
    ``d_do_test`` helper and the rest are cheap.

    Two things are deliberately out of scope, and both report as "no targets" rather than
    as failures:

    * ``druntime/test/`` — the runtime library's own tests are per-directory makefiles
      with their own variable protocol, not corpus files, and ``run.d`` cannot address
      them.
    * ``compiler/test/unit/`` — dmd's in-compiler unit tests are one binary built by a
      separate ``run.d unit_tests`` target, so a patch touching them has no per-case
      selector either.
    """

    no_targets = "test patch touched no dmd corpus case"

    def targets(self, diff, env=None):
        """``([repo-relative case paths], [the same paths])`` — for this harness the file
        *is* the test, so there is no second, finer level to narrow to.

        The path is kept whole rather than reduced to a ``category/name`` selector because
        it also carries which test root the case lives under, and that moved in 2023."""
        del env
        cases = []
        for path in _patched_files(diff):
            if _SUPPORT_RE.match(path):
                continue
            if _CASE_RE.match(path) and path not in cases:
                cases.append(path)
        return sorted(cases), sorted(cases)

    def _selector(self, path):
        """``(test root, run.d selector)`` for one repo-relative case path."""
        m = _CASE_RE.match(path)
        return m.group("root"), "%s/%s" % (m.group("category"), m.group("name"))

    def _run(self, env, repo, root, args, timeout, jobs):
        # `./run.d` carries dmd's own rdmd shebang, so it is executed directly rather than
        # through an `rdmd run.d` that would need rdmd's own flags spelled out here.
        #
        # run.d defaults to twice the machine's core count, which is the wrong number on a
        # shared Batch node; `-j` is its own flag rather than an environment variable.
        cmd = ["./run.d"] + (["-j%s" % jobs] if jobs else []) + list(args)
        log("$ " + " ".join(cmd))
        try:
            return env.execute(
                cmd,
                cwd="%s/%s" % (repo, root),
                timeout=timeout,
                merge_stderr=True,
            )
        except subprocess.TimeoutExpired:
            log("run.d TIMEOUT after %ds" % timeout)
            return None

    def run_tests(self, env, repo, files, names, timeout, jobs):
        if files is None:
            return self._run_whole_suite(env, repo, timeout, jobs)

        outcomes = {}
        had_error = False
        deadline_hit = False
        for path in files:
            root, selector = self._selector(path)
            r = self._run(env, repo, root, [selector], timeout, jobs)
            if r is None:
                deadline_hit = True
                break
            log(r.stdout[-1500:])
            if r.returncode == 0:
                outcomes[path] = "passed"
                continue
            if self._ran_the_case(r.stdout):
                outcomes[path] = "failed"
            else:
                log("run.d never reached %s — reporting as harness error" % selector)
                outcomes[path] = "error"
                had_error = True
        n = len([o for o in outcomes.values() if o != "skipped"])
        return outcomes, n, had_error, deadline_hit

    @staticmethod
    def _ran_the_case(stdout):
        """Did run.d actually run the case, or did it give up before reaching it?

        run.d exits non-zero for both, and the two need opposite treatment. It announces
        every case it ran and lost with ``>>> TARGET FAILED:`` and repeats the set under
        ``FAILED targets:``; everything else that makes it exit non-zero happens *before*
        any case runs — no compiler at the expected path, a test tool that would not
        build — and prints neither.

        Reading the marker rather than the exit code is what keeps a crashed compiler a
        **failing test**: an ICE or a segfault in codegen is the commonest bug shape in
        this repo, and run.d reports it exactly like any other lost comparison.
        """
        return ">>> TARGET FAILED:" in stdout or "FAILED targets:" in stdout

    def _run_whole_suite(self, env, repo, timeout, jobs):
        """The visible regression gate: the whole corpus in one run.

        Which root the corpus lives under is decided by the tree, not by the config, so it
        is probed rather than declared — the same suite then serves a pre-2023 anchor and
        a post-2023 one."""
        root = "compiler/test" if env.is_dir("%s/compiler/test" % repo) else "test"
        r = self._run(env, repo, root, [], timeout, jobs)
        if r is None:
            return {}, 0, False, True
        log(r.stdout[-3000:])
        return {"dmd-testsuite::<suite>": "passed" if r.returncode == 0 else "failed"}, 1, False, False
