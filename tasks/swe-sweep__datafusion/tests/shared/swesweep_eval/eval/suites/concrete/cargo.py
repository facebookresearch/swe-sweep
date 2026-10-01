# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""CargoSuite suite adapter."""

import os
import re

from ..base import ReproductionSuite
from ..utils.compiled import _patched_files, _run
from ..utils.logging import log
from ..utils.managed import _CARGO_RESULT_RE, _CARGO_STATUS, _FN_RE, _TEST_ATTR_RE, cargo_target_of


class CargoSuite(ReproductionSuite):
    """``cargo test``, one invocation per integration-test target.

    ``cargo_args`` are the crate's own test flags. A workspace does not share one feature
    vocabulary — tokio's tests need ``--features full``, which no sibling crate even
    declares — so it may be a ``{crate: [flags]}`` mapping with a ``"*"`` default as well
    as one flat list.

    ``exact`` is libtest's exact-match filter, and it is on by default because a target
    is usually one file whose cases are top-level functions. It has to be **off** for a
    target that is a *directory*: ``tests/all/traps.rs`` is a module of the ``all``
    target, so the case is ``traps::backtrace_through_empty_frames`` and matching the
    bare function name exactly selects nothing at all. Without ``--exact`` libtest
    matches on substring, which finds it.

    ``fixture_targets`` covers the other Rust test convention: a corpus of **data files**
    walked by one ``.rs`` driver. ``cargo_target_of`` reads the target out of the path,
    which only works when the patched file *is* Rust — a wasmtime fix that adds
    ``tests/disas/simd.wat`` or ``cranelift/filetests/filetests/isa/x64/shuffle.clif``
    resolves to nothing and the subtask reports no target at all. Each entry is a
    ``{pattern, crate, target}`` mapping (``pattern`` a regex matched against the path)
    that says which driver runs that corpus. Test *names* are not passed to a target reached
    this way: a data file usually has no libtest case name, and forwarding the names scraped
    from a sibling ``.rs`` hunk would filter the run down to nothing.

    Both ``crate`` and ``target`` may be **backreferences** into ``pattern`` (``\\1``,
    ``\\g<crate>``), which is what a workspace with dozens of corpora needs. biome keeps each
    corpus under the crate that owns it (``crates/<crate>/tests/specs/``), so the ``crate``
    half alone saves one entry per crate; swc additionally names every corpus after its
    driver — ``crates/swc_ecma_parser/tests/jsx/`` is walked by ``tests/jsx.rs``, some forty
    such pairs — so both halves together say what forty literal entries would, and keep
    saying it when the next corpus is added.

    ``fixture_case_names`` is the exception to not passing names, for a corpus walked by
    ``testing_macros::fixture!`` — there the case name IS the path, so it can be derived (see
    :meth:`fixture_case_name`) and passed. That is not an optimisation. ``passes_post_gold``
    demands the *whole* selected target come back green, so a driver that walks a corpus
    upstream itself does not pass can never satisfy it: swc's ``compress`` target is red on
    97 of its 2460 cases in the pristine tree, because it walks the imported terser corpus
    alongside swc's own fixtures. Selecting the case the patch added is what makes those
    subtasks measurable at all.

    ``target_aliases`` renames a target after ``cargo_target_of`` has guessed it. The guess
    is that the first path component under ``tests/`` names the target, which is right for
    both of cargo's own layouts — ``tests/foo.rs`` and ``tests/foo/main.rs``. It is wrong
    for the third layout crates actually use: one entry point, ``tests/tests.rs``, that
    ``mod``-declares sibling *directories* which are therefore not targets at all
    (raft-rs: ``tests/integration_cases/`` and ``tests/failpoint_cases/`` are both part of
    target ``tests``). Nothing in the diff distinguishes the two, so the crate says which
    is which — ``{integration_cases: tests}``.
    """

    no_targets = "test patch touched no cargo integration-test file"

    def __init__(
        self,
        cargo_args=(),
        eval_args=None,
        fixture_targets=(),
        exact=True,
        target_aliases=None,
        fixture_case_names=False,
    ):
        self.cargo_args = cargo_args
        self.eval_args = eval_args
        self.target_aliases = dict(target_aliases or {})
        self.exact = exact
        self.fixture_case_names = fixture_case_names
        self.fixture_targets = [
            (re.compile(f["pattern"]), (f.get("crate", "."), f["target"])) for f in fixture_targets
        ]
        # Every (crate, target) a `fixture_targets` entry has resolved to. Literal entries
        # are known up front; a backreferenced one is only known once a path has matched
        # it, so `_fixture_target_of` adds to this as it goes. `target_cmd` reads it to
        # decide whether to forward test names, and a fixture-reached target never gets
        # them.
        self._fixture_ids = {
            (crate, self.target_aliases.get(target, target))
            for _, (crate, target) in self.fixture_targets
            if "\\" not in crate and "\\" not in target
        }

    def args_for(self, crate):
        if isinstance(self.cargo_args, dict):
            return list(self.cargo_args.get(crate, self.cargo_args.get("*", ())))
        return list(self.cargo_args)

    def target_cmd(self, crate, target, names):
        """Everything after ``cargo test`` for one selected target.

        A hook rather than inline, so a subclass can select something other than an
        integration-test binary — see :class:`CargoUnitSuite`."""
        cmd = ["--test", target] + self.args_for(crate)
        if names and (self.fixture_case_names or (crate, target) not in self._fixture_ids):
            cmd += ["--"] + list(names) + (["--exact"] if self.exact else [])
        return cmd

    @staticmethod
    def fixture_case_name(path):
        """The libtest case name ``testing_macros::fixture!`` generates for a corpus file.

        The macro names each case after the path it walked, with every non-alphanumeric run
        collapsed to ``_`` and the separators doubled:
        ``tests/terser/compress/async/issue-87/input.js`` becomes
        ``…tests__terser__compress__async__issue_87__input_js``. The ``…`` is the annotated
        function's own name, which differs per driver (``fixture_tests__``,
        ``references_tests__``, ``run_fixture_test_tests__``), so only the path-derived
        suffix is returned — with substring matching that selects the case whatever the
        driver calls itself.
        """
        head, _, tail = path.partition("tests/")
        del head
        if not tail:
            return None
        return "tests__" + "__".join(re.sub(r"[^0-9a-zA-Z]+", "_", part) for part in tail.split("/") if part)

    def _fixture_target_of(self, path):
        for pattern, (crate, target) in self.fixture_targets:
            m = pattern.search(path)
            if m is None:
                continue
            # Either half may be a backreference into the pattern. A workspace that keeps
            # each corpus under the crate that owns it — biome's
            # `crates/<crate>/tests/specs/` — would otherwise need one entry per crate to
            # say the same thing twenty times, and swc needs the `target` half too because
            # its corpora are named after the drivers that walk them.
            if "\\" in crate or "\\" in target:
                crate, target = m.expand(crate), m.expand(target)
                self._fixture_ids.add((crate, self.target_aliases.get(target, target)))
            return crate, target
        return None

    def targets(self, diff, env=None):
        del env
        """``([(crate, target), ...], [test fn names])``. An added ``fn`` counts when a
        test attribute precedes it; anything else in between breaks the pair."""
        found = []
        names = []
        for path in _patched_files(diff):
            t = cargo_target_of(path)
            if t is None:
                t = self._fixture_target_of(path)
                if t is not None and self.fixture_case_names:
                    case = self.fixture_case_name(path)
                    if case:
                        names.append(case)
            if t is not None:
                crate, target = t
                t = (crate, self.target_aliases.get(target, target))
                if t not in found:
                    found.append(t)
        armed = False
        for line in diff.splitlines():
            if _TEST_ATTR_RE.match(line):
                armed = True
                continue
            m = _FN_RE.match(line)
            if m:
                if armed:
                    names.append(m.group(1))
                armed = False
            elif line.startswith("+") and line[1:].strip() and not line[1:].lstrip().startswith("#["):
                armed = False
        return sorted(set(found)), sorted(set(names))

    def run_tests(self, env, repo, files, names, timeout, jobs):
        """One ``cargo test`` per target, run from the crate's own directory so the
        workspace does not have to be named. ``--exact`` plus the names is libtest's
        exact-match filter; with no names the whole target runs, which is the same
        fallback pytest gets.

        A compile error is the ``error`` flag rather than a failed test — nothing ran —
        which the driver counts as failing pre-gold and as not passing post-gold, exactly
        like a pytest collection error."""
        outcomes = {}
        error = False
        if files is None:
            args = self.eval_args
            if args is None:
                args = self.args_for("*")
            cmd = ["cargo", "test", "--workspace"] + list(args)
            r = _run(env, cmd, timeout=timeout, cwd=repo)
            if r is None:
                log("cargo test TIMEOUT after %ds (whole workspace)" % timeout)
                return {}, 0, False, True
            log("cargo test whole workspace rc=%d" % r.returncode)
            log(r.stdout[-2000:])
            for line in r.stdout.splitlines():
                m = _CARGO_RESULT_RE.match(line)
                if m:
                    outcomes[m.group(1)] = _CARGO_STATUS[m.group(2)]
            n = len([o for o in outcomes.values() if o != "skipped"])
            return outcomes, n, r.returncode != 0 and not outcomes, False
        for crate, target in files:
            selected = ["cargo", "test"] + self.target_cmd(crate, target, names)
            unfiltered = ["cargo", "test"] + self.target_cmd(crate, target, [])
            cwd = os.path.join(repo, crate) if crate != "." else repo
            attempts = [selected]
            # **The name filter is a best effort, not the contract.** libtest's `--exact`
            # matches the case's *full path* — `parse::bare_url`, not `bare_url` — so a
            # repo whose integration target is a directory of modules (gitoxide:
            # `gix-url/tests/url/parse.rs` is target `url`) filters everything out and the
            # run reports zero cases, which reads as "no bug here". Falling back to the
            # whole target is the same fallback pytest and go get when the patch names no
            # test, and it is safe: the extra cases have to pass either way.
            if selected != unfiltered:
                attempts.append(unfiltered)
            for cmd in attempts:
                r = _run(env, cmd, timeout=timeout, cwd=cwd)
                if r is None:
                    log("cargo test TIMEOUT after %ds (%s/%s)" % (timeout, crate, target))
                    return {}, 0, False, True
                log("cargo test %s/%s rc=%d" % (crate, target, r.returncode))
                log(r.stdout[-2000:])
                seen = 0
                found = {}
                for line in r.stdout.splitlines():
                    m = _CARGO_RESULT_RE.match(line)
                    if m:
                        seen += 1
                        found[target + "::" + m.group(1)] = _CARGO_STATUS[m.group(2)]
                # rc!=0 with no case reported = it never got to running: a compile error,
                # or a panic that took the harness with it. Retrying unfiltered would not
                # help and would only pay for the same compile twice.
                if r.returncode != 0 and seen == 0:
                    error = True
                    break
                if seen:
                    outcomes.update(found)
                    break
        n = len([o for o in outcomes.values() if o != "skipped"])
        return outcomes, n, error, False
