from __future__ import annotations

import importlib.util
import os
import stat
import sys
from pathlib import Path

import pytest


def session_class():
    path = Path(__file__).resolve().parents[1] / (
        "tasks/swe-sweep__click/tests/shared/swesweep_eval/infra/container_session.py"
    )
    spec = importlib.util.spec_from_file_location("sweep_session_copy_permissions", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.ContainerSession


@pytest.mark.skipif(os.name != "posix", reason="Unix staging permissions")
def test_staging_expands_destination_access_without_changing_source(tmp_path):
    source = tmp_path / "source"
    source.mkdir(mode=0o700)
    private = source / "file.txt"
    private.write_text("synthetic fixture")
    private.chmod(0o600)
    destination = tmp_path / "destination"
    with session_class()() as session:
        session.copy_dir(source, str(destination))
    assert stat.S_IMODE(source.stat().st_mode) == 0o700
    assert stat.S_IMODE(private.stat().st_mode) == 0o600
    assert stat.S_IMODE((destination / "file.txt").stat().st_mode) == 0o644
    assert stat.S_IMODE(destination.stat().st_mode) == 0o755
    assert (destination / "file.txt").read_text() == "synthetic fixture"


@pytest.mark.skipif(os.name != "posix", reason="Unix symlink staging permissions")
def test_staging_does_not_chmod_symlink_targets_outside_the_tree(tmp_path):
    external = tmp_path / "external.txt"
    external.write_text("outside synthetic fixture")
    external.chmod(0o600)
    source = tmp_path / "source"
    source.mkdir()
    (source / "link.txt").symlink_to(external)
    destination = tmp_path / "destination"
    with session_class()() as session:
        session.copy_dir(source, str(destination))
    assert stat.S_IMODE(external.stat().st_mode) == 0o600
    assert (destination / "link.txt").is_symlink()
    assert (destination / "link.txt").readlink() == external


@pytest.mark.skipif(os.name != "posix", reason="Unix staging permissions")
def test_merge_preserves_permissions_of_unrelated_destination_files(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "staged.txt").write_text("copied")
    destination = tmp_path / "destination"
    destination.mkdir()
    unrelated = destination / "unrelated.txt"
    unrelated.write_text("not part of this staging operation")
    unrelated.chmod(0o600)
    with session_class()() as session:
        session.copy_dir(source, str(destination))
    assert stat.S_IMODE(unrelated.stat().st_mode) == 0o600
    assert unrelated.read_text() == "not part of this staging operation"
    assert (destination / "staged.txt").read_text() == "copied"
