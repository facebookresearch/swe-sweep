"""The README's example commands have to name a task that exists."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_readme_harbor_paths_are_real_tasks():
    readme = (ROOT / "README.md").read_text()
    paths = re.findall(r"--path\s+(\S+)", readme)
    assert paths
    for path in paths:
        assert (ROOT / path).is_dir(), path
