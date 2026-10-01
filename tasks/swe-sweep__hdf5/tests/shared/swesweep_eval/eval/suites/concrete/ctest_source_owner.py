# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""CTestSourceOwnerSuite suite adapter."""

import os
import re

from ..base import FullSuite
from ..utils.compiled import _REPORT, _all_error, _parse_junit, _patched_files, _run
from ..utils.logging import log

#: ``  Test  #12: H5TEST-dsets`` — one line of ``ctest -N``.
_LISTED = re.compile(r"^\s*Test\s+#(\d+): (\S+)\s*$", re.M)

#: ``set (testhdf5_SOURCES`` … ``)`` — a CMake list of the sources of one program. The
#: body is captured up to the closing paren, which cannot appear inside it: the entries
#: are bare paths and ``${VAR}`` references.
_SOURCES_BLOCK = re.compile(r"\bset\s*\(\s*(\w+)_SOURCES\b([^)]*)\)", re.I)

#: A test program's own sources.
_SOURCE_EXTS = (".c", ".cpp", ".cc", ".h")


class CTestSourceOwnerSuite(FullSuite):
    """CTest where the case is named after the **program that owns** the patched source —
    hdf5's layout.

    Every other ctest adapter here reads the case id off the path: one program per source
    (:class:`CTestSuite`), the directory as a prefix (:class:`CTestDirPrefixedSuite`), or a
    static route table (:class:`CTestPathMapSuite`). hdf5 breaks all three at once:

    * a case's prefix is **per subtree**, not per repo — ``H5TEST-``, ``HL_``, ``H5DUMP-``;
    * most of the ``test/`` corpus is not one program per source. ``testhdf5`` links two
      dozen sources (``tattr.c``, ``th5s.c``, ``tselect.c``, …) into one binary, and CMake
      registers that binary as **several** cases that each run a slice of it
      (``H5TEST-testhdf5-base``, ``-heap``, ``-file``, ``-select``). ``tattr.c`` therefore
      names no case at all under a path rule, and the bug in it is lost;
    * the tool tests are shell-driven output comparisons whose case name is the
      *expectation file's* stem (``tall-1.ddl`` → ``H5DUMP-tall-1``), with no source
      involved.

    So the mapping is **asked of the build system** rather than guessed, in two steps, the
    same principle as :class:`BazelSuite`:

    1. ``ctest -N`` on the (re)configured tree gives every case name that actually exists.
       Nothing outside that list is ever selected, so a wrong guess costs nothing.
    2. the ``<program>_SOURCES`` lists in each root's ``CMakeLists.txt`` say which program
       a patched source belongs to; a source in no such list is its own program, which is
       the one-source-per-test case.

    A case is then selected when it reads ``<prefix><program>`` or
    ``<prefix><program>-<slice>`` for one of the declared ``prefixes``. The optional
    ``-<slice>`` suffix is what picks up all four ``testhdf5`` cases from one patched
    source, and it also drags in the ``-clear-objects`` fixture cases CMake registers
    beside them — which is correct, since they are what leaves the working directory in
    the state the real case expects.

    ``data_roots`` are the directories of expectation files, matched on the stem alone
    against the same prefix list.

    The build tree is reconfigured on every run, as in :class:`CTestSuite`: a test patch
    that adds a case adds it to a ``CMakeLists.txt``, and an already-configured tree does
    not know about it until cmake re-reads that file. Everything is built rather than the
    owning target, because a shell-driven comparison case has no target of its own — it
    needs whatever binaries its script invokes.
    """

    no_targets = "test patch touched no source or expectation owned by a CTest case"

    def __init__(self, repo="/", build_dir="/build", source_roots=(), data_roots=(),
                 prefixes=(), all_target="all", configure_args=()):
        self.repo = repo
        self.build_dir = build_dir
        #: Directories whose sources resolve through ``<program>_SOURCES``.
        self.source_roots = tuple(source_roots)
        #: Directories whose file *stems* are case names.
        self.data_roots = tuple(data_roots)
        self.prefixes = tuple(prefixes)
        self.all_target = all_target
        self.configure_args = list(configure_args)
        self._cases = None
        self._owner = None
        self._configured = None

    @classmethod
    def from_config(cls, values, *, repo, create_suite):
        """Unlike most adapters this one keeps ``repo``: both halves of the mapping are
        read out of the container (``ctest -N`` and the ``CMakeLists.txt`` files), and
        ``targets`` is handed an environment but no path."""
        del create_suite
        values.setdefault("repo", repo)
        return cls(**values)

    # --- what the build system says -------------------------------------------

    def _configure(self, env, timeout):
        """``cmake -S <repo> -B <build_dir>``, run **from inside the build directory**, at
        most once per applied test patch.

        The working directory is not cosmetic here. hdf5's ``ConfigureChecks.cmake``
        determines the maximum decimal precision with a ``try_run`` whose program writes
        ``pac_Cconftest.out`` into *its own* working directory — which CMake inherits from
        the ``cmake`` process — and then reads it back from ``${CMAKE_BINARY_DIR}``. Every
        upstream recipe does ``cd build && cmake ..``, so the two coincide; configuring
        from anywhere else drops the file somewhere the read cannot find it and the whole
        configure aborts.

        The result is cached because a reproduction pays for this **three** times over
        otherwise — once resolving the targets, once before the pre-gold run and once
        before the post-gold one — and a full hdf5 configure is minutes, against a
        per-subtask container budget measured in tens of them. Only a *test* patch can
        register a new case, and :meth:`targets` drops the cache when one is applied; the
        gold patch is source-only and cannot change what CMake registers.
        """
        if self._configured is None:
            _run(env, ["mkdir", "-p", self.build_dir], timeout=60)
            self._configured = _run(
                env, ["cmake", "-S", self.repo, "-B", self.build_dir] + self.configure_args,
                timeout=timeout, cwd=self.build_dir)
        return self._configured

    def _registered(self, env):
        """Every case name CMake registers, from ``ctest -N``, memoised for this run.

        The tree is configured first — an unconfigured build directory lists nothing, and
        one configured before the test patch was applied does not know a newly added
        case."""
        if self._cases is None:
            self._configure(env, 3600)
            res = _run(env, ["ctest", "--test-dir", self.build_dir, "-N"], timeout=600)
            self._cases = [] if res is None else [n for _num, n in _LISTED.findall(res.stdout)]
            log("ctest -N: %d registered case(s)" % len(self._cases))
        return self._cases

    def _owner_of(self, env):
        """``{source basename: program}`` from every root's ``CMakeLists.txt``.

        Only multi-source programs appear: a test that is one source has no
        ``<program>_SOURCES`` list, and its program is its own stem."""
        if self._owner is None:
            owner = {}
            for root in self.source_roots:
                path = os.path.join(self.repo, root, "CMakeLists.txt")
                try:
                    text = env.read_text(path)
                except Exception as exc:  # noqa: BLE001 - a missing root is not an error
                    log("cannot read %s: %s" % (path, exc))
                    continue
                for program, body in _SOURCES_BLOCK.findall(text):
                    for entry in body.split():
                        base = os.path.basename(entry.strip().strip('"'))
                        if base.endswith(_SOURCE_EXTS):
                            owner[base] = program
            self._owner = owner
            log("CMake owner map: %d multi-source entries" % len(owner))
        return self._owner

    # --- resolving the diff ---------------------------------------------------

    def _cases_for(self, cases, name):
        """The registered cases named after ``name`` — ``<prefix><name>`` and every
        ``<prefix><name>-<slice>`` beside it."""
        pattern = re.compile(
            "^(?:" + "|".join(re.escape(p) for p in self.prefixes) + ")"
            + re.escape(name) + r"(?:-[A-Za-z0-9_.+-]+)?$"
        )
        return [c for c in cases if pattern.match(c)]

    def _under(self, path, roots):
        head = os.path.dirname(path)
        return any(head == root for root in roots)

    def targets(self, diff, env=None):
        """``(files, names)`` — the patched test material, and the CTest cases that own
        it.

        This is the one point where the tree is known to have just changed — the driver
        applies a subtask's test patch and then asks what it targets — so it is where the
        configure and case-list caches are dropped. The evaluation driver reuses one suite
        over many subtasks in one container, and without this the second subtask would be
        resolved against the first one's registered cases."""
        self._configured = None
        self._cases = None
        self._owner = None
        cases = self._registered(env) if env is not None else []
        owner = self._owner_of(env) if env is not None else {}
        files = []
        names = set()
        for path in _patched_files(diff):
            base = os.path.basename(path)
            stem, ext = os.path.splitext(base)
            matched = []
            if self._under(path, self.source_roots) and ext in _SOURCE_EXTS:
                matched = self._cases_for(cases, owner.get(base, stem))
            elif self._under(path, self.data_roots):
                matched = self._cases_for(cases, stem)
            if matched:
                files.append(path)
                names.update(matched)
        return sorted(set(files)), sorted(names)

    # --- the one real implementation ------------------------------------------

    def _build_and_run(self, env, repo, names, timeout, jobs):
        """Configure, build everything, run. ``names=None`` means the whole suite.

        Returns ``(outcomes, n_run, failed_to_build, timed_out, text)`` — the shape every
        other ctest adapter returns, so the drivers need no special case."""
        del repo  # self.repo is the source dir; the drivers pass the same path
        conf = self._configure(env, timeout)
        if conf is None:
            return _all_error(names or []), 0, True, True, "cmake configure TIMEOUT"
        if conf.returncode != 0:
            log("cmake configure failed:\n" + conf.stdout[-1500:])
            return _all_error(names or []), 0, True, False, conf.stdout

        build = _run(
            env,
            ["cmake", "--build", self.build_dir, "-j", str(jobs), "--target", self.all_target],
            timeout=timeout,
        )
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

    # --- the repro driver's adapter -------------------------------------------

    def run_tests(self, env, repo, files, names, timeout, jobs):
        outcomes, n_run, build_failed, timed_out, _text = self._build_and_run(env, repo, names, timeout, jobs)
        if outcomes is None:
            return {}, 0, not timed_out, timed_out
        # No case matched the selector: the patch names a test the build system does not
        # register. Nothing ran, which is a suite-level failure, not a pass.
        return outcomes, n_run, build_failed or not outcomes, timed_out

    # --- the eval driver's adapters -------------------------------------------

    def run_all(self, env, repo, timeout, cap, jobs):
        outcomes, _n, _bf, timed_out, text = self._build_and_run(env, repo, None, timeout, jobs)
        return outcomes, timed_out, self._capture("ctest (whole suite)", text, cap)

    def run_selected(self, env, repo, files, names, timeout, cap, jobs):
        outcomes, _n, _bf, timed_out, text = self._build_and_run(env, repo, names, timeout, jobs)
        return outcomes, timed_out, self._capture("ctest -R " + " ".join(names), text, cap)

    @staticmethod
    def _capture(command, text, cap):
        clipped, truncated = cap.clip(text)
        return {"command": command, "returncode": None, "text": clipped, "truncated": truncated}
