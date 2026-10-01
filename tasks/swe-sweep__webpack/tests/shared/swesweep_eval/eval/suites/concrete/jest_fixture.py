# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""JestFixtureSuite suite adapter."""

import os
import re

from ..utils.javascript import _added_names, _spec_files
from ..utils.logging import log
from ..utils.pytest import PLUSFILE_RE
from .jest import JestSuite

class JestFixtureSuite(JestSuite):
    """jest over a **fixture corpus** — webpack's ``test/configCases``, babel's
    ``packages/*/test/fixtures``.

    These repos do not write one spec file per test. A case is a *directory* of inputs under
    a conventional root, and a single driver spec walks that root and generates a
    ``describe``/``it`` per directory it finds. So a patch that adds or edits a case touches
    no spec file at all: plain file selection returns nothing and the census reports "no
    targets" for a bug that reproduces perfectly well.

    ``fixture_roots`` closes that gap. Each entry is ``(pattern, drivers, depth)``:

    - **pattern** — a regex anchored at the start of the path. A path it matches belongs to
      this corpus. A regex rather than a literal prefix because the corpus root is often
      per-package (babel has one under every ``packages/*``), and the driver has to be built
      from the same match.
    - **drivers** — the spec(s) that walk this corpus, as ``re`` replacement templates, so a
      group captured by the pattern can be substituted into them (``\\1/test/index.js``).
    - **depth** — which path segment names the case, indexing ``path.split("/")``. Negative
      counts from the end, which is what a corpus of ``<case>/input.js`` files wants::

        test/configCases/dll-plugin/0-create-dll/webpack.config.js   depth=3  -> 0-create-dll
        └───── pattern ─┘└─ category ┘└─ depth 3 ─┘

        packages/babel-parser/test/fixtures/es2015/let/input.js      depth=-2 -> let

    - **transform** (optional 4th element) — a callable applied to that segment, for a driver
      that prettifies the directory name before it reaches ``describe``. babel's
      ``@babel/helper-fixtures`` "humanizes" every fixture name by turning hyphens into
      spaces, so the directory ``issue-7742`` is the test ``typescript/regression/issue 7742``
      and an untransformed ``-t issue-7742`` selects nothing at all.

    The case name is what the driver passes to ``describe``, so it is what jest's ``-t``
    matches.

    Only the *representative* driver is named per root, never all of them. webpack registers
    twenty variants of ``TestCases.template`` (devtool, cache, production, …) over the same
    corpus; running them all would multiply every subtask's census by twenty for no extra
    fail→pass signal.

    Selection stays a narrowing, exactly as in :class:`JestSuite`: two cases whose directory
    names share a substring both match, which costs runtime rather than correctness.
    """

    no_targets = "test patch touched no JavaScript test file and no known fixture corpus"

    @classmethod
    def from_config(cls, values, *, repo, create_suite):
        del repo, create_suite
        transforms = {None: None, "hyphens-to-spaces": lambda value: value.replace("-", " ")}
        roots = []
        for value in values.pop("fixture_roots"):
            transform = value.get("name_transform")
            if transform not in transforms:
                raise ValueError(f"unknown fixture name transform: {transform}")
            roots.append(
                (
                    value["pattern"],
                    value["drivers"],
                    value["case_segment"],
                    transforms[transform],
                )
            )
        return cls(fixture_roots=roots, **values)

    def __init__(self, fixture_roots, config=None, spec_patterns=()):
        super().__init__(config=config, spec_patterns=spec_patterns)
        roots = []
        for root in fixture_roots:
            pat, drivers, depth = root[:3]
            transform = root[3] if len(root) > 3 else None
            roots.append((re.compile(pat), tuple(drivers), depth, transform))
        self.fixture_roots = tuple(roots)

    def _match(self, path):
        for root in self.fixture_roots:
            m = root[0].match(path)
            if m:
                return (m,) + root[1:]
        return None

    def targets(self, diff, env=None):
        del env
        # A fixture case's own files live under a `test/` dir, so `_spec_files` claims them.
        # Drop those: they are inputs to a driver, not specs, and passing them to jest as
        # positional patterns only risks matching an unrelated spec by substring.
        files = [f for f in _spec_files(diff) if self._match(f) is None]
        names = list(_added_names(diff))
        for path in PLUSFILE_RE.findall(diff):
            if path == "/dev/null":
                continue
            hit = self._match(path)
            if hit is None:
                continue
            m, drivers, depth, transform = hit
            parts = path.split("/")
            try:
                name = parts[depth]
            except IndexError:
                continue  # a file directly in the corpus root is harness, not a case
            if name == parts[-1]:
                continue  # the "case" resolved to the file itself, so there is no case dir
            files.extend(m.expand(d) for d in drivers)
            names.append(transform(name) if transform else name)
        return sorted(set(files)), sorted(set(names))

    def run_tests(self, env, repo, files, names, timeout, jobs):
        if files is None:
            return JestSuite.run_tests(self, env, repo, None, names, timeout, jobs)
        # A driver template can expand to a spec a given package does not have (not every
        # babel package drives its fixtures from `test/index.js`). Passing jest a pattern
        # that matches no file makes it exit "no tests found", which reads as a whole-suite
        # failure rather than as the miss it is — so drop those here, where the repo is
        # in hand.
        present = [f for f in files if env.exists(os.path.join(repo, f))]
        if files and not present:
            log("none of the resolved specs exist in the tree: " + ", ".join(files))
        return JestSuite.run_tests(self, env, repo, present, names, timeout, jobs)
