# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""CargoFlatSnapshotSuite suite adapter."""

from .cargo_snapshot import CargoSnapshotSuite


class CargoFlatSnapshotSuite(CargoSnapshotSuite):
    """A snapshot-tested cargo workspace whose snapshots live in **one flat directory**.

    :class:`CargoSnapshotSuite` reads the group out of a *directory* segment
    (``resources/test/fixtures/<group>/...``), which is ruff's layout. oxc keeps every
    linter snapshot in a single directory instead, and encodes the two path components in
    the *filename*: ``src/snapshots/jsx_a11y_alt_text.snap`` is the rule ``alt_text`` of
    the category ``jsx_a11y``. The rule source beside it is
    ``src/rules/jsx_a11y/alt_text.rs`` (or ``.../alt_text/mod.rs``), whose inline
    ``#[test] fn test()`` is the case, so the full libtest path is
    ``rules::jsx_a11y::alt_text::test`` and selection is **per rule**, not per category —
    finer than the ruff variant, not coarser.

    Splitting the filename needs the category list, because both the category and the rule
    contain underscores and ``react_perf_jsx_no_new_array_as_prop`` is ambiguous otherwise.
    ``categories`` is matched longest-first for exactly that reason: ``react_perf`` has to
    win over ``react``. The list is task-owned config rather than a scan of the tree, so
    ``targets()`` stays a pure function of the diff — it is called without a container.

    Anything this does not resolve falls back to :class:`CargoSnapshotSuite`, so a patch
    touching an ordinary ``crates/<crate>/tests/`` integration target still works.
    """

    no_targets = "test patch touched no rule, snapshot or integration test"

    def __init__(
        self,
        crate,
        rules_prefix,
        snapshots_prefix,
        categories,
        module="rules::{category}::{rule}::",
        groups=(),
        cargo_args=(),
        lib_only=True,
    ):
        super().__init__(groups=groups, cargo_args=cargo_args, lib_only=lib_only)
        self.crate = crate
        self.rules_prefix = rules_prefix.rstrip("/")
        self.snapshots_prefix = snapshots_prefix.rstrip("/")
        # Longest first: `react_perf` must be tried before `react`.
        self.categories = sorted(categories, key=len, reverse=True)
        self.module = module

    def _split_category(self, stem):
        """``jsx_a11y_alt_text`` → ``("jsx_a11y", "alt_text")``, or ``None``."""
        for category in self.categories:
            if stem.startswith(category + "_"):
                return category, stem[len(category) + 1 :]
        return None

    def _group_of(self, path):
        if path.startswith(self.snapshots_prefix + "/") and path.endswith(".snap"):
            stem = path[len(self.snapshots_prefix) + 1 : -len(".snap")]
            # A snapshot nested one level deeper is not a rule snapshot.
            if "/" not in stem:
                hit = self._split_category(stem)
                if hit is not None:
                    category, rule = hit
                    return self.crate, self.module.format(category=category, rule=rule)
        if path.startswith(self.rules_prefix + "/"):
            rest = path[len(self.rules_prefix) + 1 :].split("/")
            # `<category>/<rule>.rs` and `<category>/<rule>/mod.rs` (or any file inside the
            # rule's own directory) both name the same rule module.
            if len(rest) >= 2 and rest[0] in self.categories:
                rule = rest[1][:-3] if rest[1].endswith(".rs") else rest[1]
                if rule:
                    return self.crate, self.module.format(category=rest[0], rule=rule)
        return super()._group_of(path)
