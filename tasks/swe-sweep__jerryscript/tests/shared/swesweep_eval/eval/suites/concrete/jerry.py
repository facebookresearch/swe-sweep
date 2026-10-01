"""JerrySuite suite adapter."""

import os
import posixpath

from ..base import FullSuite
from ..utils.compiled import _all_error, _patched_files, _run
from ..utils.logging import log


class JerrySuite(FullSuite):
    """JerryScript's own two-part suite: a JavaScript corpus and a set of C programs.

    JerryScript has no test framework. A case is a **process exit code**, and there are
    two kinds of case, which is the whole reason this adapter exists:

    - a **script case** is a ``.js`` (or ``.mjs``) file under ``js_dirs``, run by the
      built ``jerry`` binary. Exit 0 means pass — *except* under the ``fail/`` subtree,
      where the script is supposed to be rejected and exit 1 is the pass. That inversion
      is not a detail: nearly a seventh of the corpus lives there, and reading it the
      normal way turns every one of those cases into a permanent failure;
    - a **unit case** is a ``test-<stem>.c`` under one of ``unit_dirs``, which that
      directory's ``CMakeLists.txt`` compiles into one executable ``unit-<stem>`` under
      ``<build_dir>/<unit_out>``. Exit 0 means pass. Every unit tree in the repo shares
      that naming and that output directory, which is why one prefix covers them all.

    Both need the same cmake tree, so both are built in one invocation and the adapter
    keeps a single list of cases: a script case is spelled as its repo-relative path and a
    unit case as its target name, which is unambiguous because only the first contains a
    ``/``.

    Two consequences worth stating.

    **A crashed engine is a failing test.** The commonest bug shape here takes the whole
    process down with a segfault or an assertion, so a non-zero exit is read as the test's
    verdict rather than as an unmeasurable run. Only a *build* failure errors the cases.

    **The tree is reconfigured on every run.** A test patch that adds a unit test also adds
    its filename to ``CMakeLists.txt``, and an already-configured tree does not know about
    it until cmake re-reads that file. Script cases need no reconfigure, but the cost is a
    second or two, so it is not worth branching on.
    """

    no_targets = "test patch touched no JerryScript test script or unit test"

    _SCRIPT_EXTS = (".js", ".mjs")
    _UNIT_EXTS = (".c",)

    def __init__(
        self,
        build_dir="/build",
        engine="bin/jerry",
        js_dirs=("tests/jerry",),
        unit_dirs=("tests/unit-core", "tests/unit-ext"),
        unit_prefix="unit-",
        unit_out="tests",
        unit_all_targets=("unittests-core", "unittests-ext"),
        engine_target="jerry",
        cmake_args=("-DUNITTESTS=ON", "-DJERRY_CMDLINE=ON"),
        call_on_exit="__checkAsync",
        fail_dir="fail",
    ):
        self.build_dir = build_dir
        self.engine = engine
        self.js_dirs = tuple(d.strip("/") for d in js_dirs)
        self.unit_dirs = tuple(d.strip("/") for d in unit_dirs)
        self.unit_prefix = unit_prefix
        self.unit_out = unit_out.strip("/")
        self.unit_all_targets = tuple(unit_all_targets)
        self.engine_target = engine_target
        self.cmake_args = list(cmake_args)
        self.call_on_exit = call_on_exit
        self.fail_dir = fail_dir

    # --- resolving the diff --------------------------------------------------

    def _is_script(self, case):
        return "/" in case

    def targets(self, diff, env=None):
        """``([case ids], [])`` — see the class docstring on the two spellings.

        ``names`` stays empty: neither kind of case has anything smaller than itself to
        select, because the unit of execution is a whole process."""
        del env
        cases = []
        for path in _patched_files(diff):
            ext = os.path.splitext(path)[1]
            if ext in self._SCRIPT_EXTS and path.startswith(tuple(d + "/" for d in self.js_dirs)):
                cases.append(path)
            elif ext in self._UNIT_EXTS and os.path.dirname(path) in self.unit_dirs:
                stem = os.path.splitext(os.path.basename(path))[0]
                cases.append(self.unit_prefix + stem)
        return sorted(set(cases)), []

    # --- running -------------------------------------------------------------

    def _configure_and_build(self, env, repo, cases, timeout, jobs):
        """Configure the tree and build what ``cases`` needs.

        ``cases=None`` means the whole suite. Returns ``(text, failed)``."""
        conf = _run(env, ["cmake", "-S", repo, "-B", self.build_dir] + self.cmake_args, timeout=timeout)
        if conf is None:
            return "cmake configure TIMEOUT", True
        if conf.returncode != 0:
            log("cmake configure failed:\n" + conf.stdout[-1500:])
            return conf.stdout, True

        targets = ["--target", self.engine_target]
        if cases is None:
            for target in self.unit_all_targets:
                targets += ["--target", target]
        else:
            for case in cases:
                if not self._is_script(case):
                    targets += ["--target", case]
        build = _run(
            env, ["cmake", "--build", self.build_dir, "-j", str(jobs)] + targets, timeout=timeout
        )
        if build is None:
            log("build TIMEOUT")
            return "build TIMEOUT", True
        if build.returncode != 0:
            # Expected pre-gold whenever the fix is what makes the test compile.
            log("build failed:\n" + build.stdout[-1500:])
            return build.stdout, True
        return build.stdout, False

    def _script_argv(self, repo, case):
        argv = [posixpath.join(self.build_dir, self.engine)]
        if self.call_on_exit:
            argv += ["--call-on-exit", self.call_on_exit]
        if case.endswith(".mjs"):
            argv += ["-m"]
        return argv + [posixpath.join(repo, case)]

    def _expects_failure(self, case):
        """Is this script case one the engine is supposed to reject?"""
        return ("/" + self.fail_dir + "/") in ("/" + case)

    def _run_case(self, env, repo, case, timeout):
        """``(outcome, text)`` for one case."""
        if self._is_script(case):
            argv = self._script_argv(repo, case)
            expected = 1 if self._expects_failure(case) else 0
        else:
            argv = [posixpath.join(self.build_dir, self.unit_out, case)]
            expected = 0
        result = _run(env, argv, timeout=timeout, cwd=repo)
        if result is None:
            log("%s TIMEOUT after %ds" % (case, timeout))
            return None, "%s TIMEOUT after %ds" % (case, timeout)
        return ("passed" if result.returncode == expected else "failed"), result.stdout

    def _run_cases(self, env, repo, cases, timeout):
        """``(outcomes, timed_out, text)`` over ``cases``, sharing one budget.

        The budget is shared rather than per-case because the eval driver's whole-suite run
        is over a thousand scripts: a per-case slice of a whole-suite timeout would be
        meaningless, and a whole-suite slice given to each case would let one hang eat the
        run. Once the budget is gone the remaining cases are left unreported, which the
        drivers read as the harness not finishing."""
        outcomes = {}
        output = []
        for case in cases:
            outcome, text = self._run_case(env, repo, case, timeout)
            if outcome is None:
                return outcomes, True, "\n".join(output + [text])
            outcomes[case] = outcome
            if outcome == "failed":
                output.append("=== %s ===\n%s" % (case, text[-2000:]))
        return outcomes, False, "\n".join(output)

    def _all_cases(self, env, repo):
        """Every case in the tree, for the eval driver's visible run."""
        cases = []
        for js_dir in self.js_dirs:
            found = env.execute(
                ["find", posixpath.join(repo, js_dir), "-name", "*.js", "-o", "-name", "*.mjs"],
                merge_stderr=True,
            )
            for line in found.stdout.splitlines():
                line = line.strip()
                if line.startswith(repo + "/"):
                    cases.append(line[len(repo) + 1 :])
        found = env.execute(
            ["find", posixpath.join(self.build_dir, self.unit_out), "-name", self.unit_prefix + "*"],
            merge_stderr=True,
        )
        for line in found.stdout.splitlines():
            name = posixpath.basename(line.strip())
            if name.startswith(self.unit_prefix):
                cases.append(name)
        return sorted(set(cases))

    # --- the repro driver's adapter -------------------------------------------

    def run_tests(self, env, repo, files, names, timeout, jobs):
        del names
        cases = files if files is not None else None
        text, build_failed = self._configure_and_build(env, repo, cases, timeout, jobs)
        if build_failed:
            return _all_error(cases or []), 0, True, text.endswith("TIMEOUT")
        if cases is None:
            cases = self._all_cases(env, repo)
        outcomes, timed_out, _text = self._run_cases(env, repo, cases, timeout)
        n = len([v for v in outcomes.values() if v != "skipped"])
        return outcomes, n, not outcomes, timed_out

    # --- the eval driver's adapters -------------------------------------------

    def run_all(self, env, repo, timeout, cap, jobs):
        text, build_failed = self._configure_and_build(env, repo, None, timeout, jobs)
        if build_failed:
            return None, text.endswith("TIMEOUT"), self._capture("cmake --build", text, cap)
        outcomes, timed_out, text = self._run_cases(env, repo, self._all_cases(env, repo), timeout)
        return outcomes or None, timed_out, self._capture("jerry (whole suite)", text, cap)

    def run_selected(self, env, repo, files, names, timeout, cap, jobs):
        del names
        text, build_failed = self._configure_and_build(env, repo, files, timeout, jobs)
        if build_failed:
            return _all_error(files), text.endswith("TIMEOUT"), self._capture("cmake --build", text, cap)
        outcomes, timed_out, text = self._run_cases(env, repo, files, timeout)
        return outcomes, timed_out, self._capture("jerry " + " ".join(files), text, cap)

    @staticmethod
    def _capture(command, text, cap):
        clipped, truncated = cap.clip(text)
        return {"command": command, "returncode": None, "text": clipped, "truncated": truncated}
