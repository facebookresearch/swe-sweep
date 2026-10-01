# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""Closed registry that constructs concrete suites from task declarations."""

from __future__ import annotations

from typing import Any

from .base import Suite
from .concrete import SUITE_TYPES


class SuiteRegistry:
    """Resolve a declared suite name to its concrete host-side class."""

    def create(self, spec: str | dict[str, Any] | None, *, repo: str) -> Suite | None:
        if spec is None:
            return None
        if isinstance(spec, str):
            spec = {"type": spec}
        if not isinstance(spec, dict) or not isinstance(spec.get("type"), str):
            raise ValueError(f"suite must be a string or mapping with a type: {spec!r}")

        values = dict(spec)
        suite_type = values.pop("type")
        suite_class = SUITE_TYPES.get(suite_type)
        if suite_class is None:
            raise ValueError(f"unknown suite type: {suite_type}")
        return suite_class.from_config(values, repo=repo, create_suite=self.create)


SUITES = SuiteRegistry()
