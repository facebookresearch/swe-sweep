"""CTestPathSuite suite adapter."""

import os
import re

from ..base import FullSuite
from ..utils.compiled import _REPORT, _all_error, _parse_junit, _patched_files, _run
from ..utils.logging import log

class CTestPathSuite(FullSuite):
    """CTest where a case is **named after its path** under a corpus directory.

    The two adapters that already exist assume the name comes from somewhere else:
    :class:`CTestSuite` builds one program per test and takes the *basename*
    (``test::foo``), and :class:`CTestDataSuite` pulls a numeric id out of the first path
    segment (doxygen's ``012_cite``). Neither can address a corpus that is a *tree*, where
    two files with the same basename in different directories are different tests and the
    directory is part of the id — which is how any large fixture corpus registered with
    ``add_test(<relative path> ...)`` is laid out. cvc5 is the shape: a solver regression
    is ``add_test(regress0/arith/issue1399.smt2 ...)``, and its unit tests are
    ``add_test(unit/theory/theory_bv_black ...)`` from
    ``test/unit/theory/theory_bv_black.cpp``.

    A suite is declared as a list of ``corpora``, because one repository routinely has
    more than one and they do not share a naming rule. Each corpus says:

    - ``dir`` — the path prefix under which its cases live, relative to the repo root;
    - ``exts`` — which files in it are cases at all (the corpus also holds the
      ``CMakeLists.txt`` that registers them, and that is not a test);
    - ``prefix`` / ``strip_ext`` — how the corpus-relative path becomes the CTest name;
    - ``target`` — what has to be built before the case can run, with ``{stem}``
      substituted by the case file's basename. A fixture corpus builds *one* program and
      runs every case through it (cvc5's regressions: ``cvc5``), while a compiled test
      builds its own (``{stem}``). Getting this right is what keeps a subtask's rebuild
      incremental: building the umbrella ``build-tests`` target instead would relink every
      unit-test binary in the tree for a one-line fix.

    The build tree is reconfigured on every run, as in the other CTest adapters: a test
    patch that adds a case also adds it to a ``CMakeLists.txt``, and an already-configured
    tree does not know about it until cmake re-reads that file. ``cmake -S <repo> -B
    <build_dir>`` reuses everything in the existing ``CMakeCache.txt``, so the options the
    image configured with — cvc5's whole ``configure.sh`` line — survive untouched.
    """

    no_targets = "test patch touched no case in the CTest path corpora"

    def __init__(self, build_dir="/build", corpora=(), all_target=None, all_args=()):
        self.build_dir = build_dir
        self.corpora = [self._corpus(c) for c in corpora]
        self.all_target = all_target
        self.all_args = list(all_args)

    @staticmethod
    def _corpus(spec):
        return {
            "dir": spec["dir"].rstrip("/"),
            "exts": tuple(spec.get("exts", (".cpp",))),
            "prefix": spec.get("prefix", ""),
            "strip_ext": bool(spec.get("strip_ext", False)),
            "target": spec.get("target", "{stem}"),
        }

    # --- resolving the diff --------------------------------------------------

    def _cases(self, diff):
        """``[(ctest_name, build_target)]`` for every corpus case the diff writes to."""
        out = []
        for path in _patched_files(diff):
            for corpus in self.corpora:
                prefix = corpus["dir"] + "/"
                if not path.startswith(prefix):
                    continue
                rel = path[len(prefix):]
                if not rel.endswith(corpus["exts"]):
                    continue
                stem = os.path.splitext(os.path.basename(rel))[0]
                name = os.path.splitext(rel)[0] if corpus["strip_ext"] else rel
                out.append((corpus["prefix"] + name, corpus["target"].format(stem=stem)))
                break
        return out

    def targets(self, diff, env=None):
        del env
        """``(files, names)``. ``files`` carries the build targets rather than the paths:
        the drivers hand it straight back to :meth:`run_tests`, and what the run needs to
        know about a patched file is what to build for it, not where it lived."""
        cases = self._cases(diff)
        return sorted({target for _name, target in cases}), sorted({name for name, _t in cases})

    # --- the one real implementation -----------------------------------------

    def _build_and_run(self, env, repo, build_targets, names, timeout, jobs):
        """Configure, build, run. ``names=None`` means the whole suite.

        Returns ``(outcomes, n_run, failed_to_build, timed_out, text)`` — the shape the
        other CTest adapters return, so the drivers need no special case."""
        conf = _run(env, ["cmake", "-S", repo, "-B", self.build_dir], timeout=timeout)
        if conf is None:
            return _all_error(names or []), 0, True, True, "cmake configure TIMEOUT"
        if conf.returncode != 0:
            log("cmake configure failed:\n" + conf.stdout[-1500:])
            return _all_error(names or []), 0, True, False, conf.stdout

        targets = []
        for target in (build_targets or []):
            targets += ["--target", target]
        build = _run(env, ["cmake", "--build", self.build_dir, "-j", str(jobs)] + targets,
                     timeout=timeout)
        if build is None:
            log("test build TIMEOUT")
            return _all_error(names or []), 0, True, True, "test build TIMEOUT"
        if build.returncode != 0:
            # Expected pre-gold whenever the fix is what makes the test compile.
            log("test build failed:\n" + build.stdout[-1500:])
            return _all_error(names or []), 0, True, False, build.stdout

        if env.exists(_REPORT):
            env.remove(_REPORT)
        argv = ["ctest", "--test-dir", self.build_dir, "-j", str(jobs), "--output-on-failure",
                "--output-junit", _REPORT]
        if names is None:
            argv += self.all_args
        else:
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

    # --- the repro driver's adapter -------------------------------------------

    def run_tests(self, env, repo, files, names, timeout, jobs):
        outcomes, n_run, build_failed, timed_out, _text = self._build_and_run(
            env, repo, files, names, timeout, jobs)
        if outcomes is None:
            return {}, 0, not timed_out, timed_out
        # No case matched the selector: the patch names a test the build system does not
        # register. Nothing ran, which is a suite-level failure, not a pass.
        return outcomes, n_run, build_failed or not outcomes, timed_out

    # --- the eval driver's adapters -------------------------------------------

    def run_all(self, env, repo, timeout, cap, jobs):
        targets = [self.all_target] if self.all_target else []
        outcomes, _n, _bf, timed_out, text = self._build_and_run(
            env, repo, targets, None, timeout, jobs)
        return outcomes, timed_out, self._capture("ctest (whole suite)", text, cap)

    def run_selected(self, env, repo, files, names, timeout, cap, jobs):
        outcomes, _n, _bf, timed_out, text = self._build_and_run(
            env, repo, files, names, timeout, jobs)
        return outcomes, timed_out, self._capture("ctest -R " + " ".join(names), text, cap)

    @staticmethod
    def _capture(command, text, cap):
        clipped, truncated = cap.clip(text)
        return {"command": command, "returncode": None, "text": clipped, "truncated": truncated}
