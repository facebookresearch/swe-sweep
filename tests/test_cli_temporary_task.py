from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from swesweep.cli import configured_task


@pytest.mark.parametrize("linked_directory", [False, True], ids=["bundle-link", "tests-link"])
@pytest.mark.parametrize("relative", [False, True], ids=["absolute", "relative"])
def test_task_overrides_do_not_follow_links_back_to_source(tmp_path, linked_directory, relative):
    task = tmp_path / "synthetic-task"
    task.mkdir()
    shared = tmp_path / "shared-tests"
    shared.mkdir()
    bundle = shared / "swesweep_eval.json"
    bundle.write_text(json.dumps({"build_jobs": 4, "subtasks": [{"id": "one"}, {"id": "two"}]}))
    if linked_directory:
        link = task / "tests"
        target = shared
    else:
        (task / "tests").mkdir()
        link = task / "tests" / "swesweep_eval.json"
        target = bundle
    target = Path(os.path.relpath(target, link.parent)) if relative else target
    try:
        link.symlink_to(target, target_is_directory=linked_directory)
    except OSError as exc:
        pytest.skip(f"symlinks are unavailable: {exc}")
    original = bundle.read_bytes()

    with configured_task(task, bug_ids=("two",), build_jobs=7) as selected:
        assert selected != task
        selected_bundle = selected / "tests" / "swesweep_eval.json"
        assert selected_bundle.resolve().is_relative_to(selected.resolve())
        assert json.loads(selected_bundle.read_text()) == {"build_jobs": 7, "subtasks": [{"id": "two"}]}
        assert bundle.read_bytes() == original

    assert bundle.read_bytes() == original
    assert link.is_symlink()
    assert not selected.exists()
