# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""Paths used by the evaluation wrapper."""

from __future__ import annotations

import os
from pathlib import Path


def _find_root() -> Path:
    configured = os.environ.get("SWESWEEP_ROOT", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()

    source_root = Path(__file__).resolve().parents[2]
    if (source_root / "tasks").is_dir():
        return source_root

    for candidate in (Path.cwd(), *Path.cwd().parents):
        if (candidate / "tasks").is_dir():
            return candidate
    return source_root


ROOT = _find_root()
TASKS_DIR = ROOT / "tasks"
TASK_PREFIX = "swe-sweep__"
HARBOR_SOURCE_REVISION = "58789aad577f432a4590209a8fd901f8c894f382"
