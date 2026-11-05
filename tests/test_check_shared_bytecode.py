from __future__ import annotations

import py_compile
import subprocess
import sys
from pathlib import Path

import pytest


CHECKER = Path(__file__).resolve().parents[1] / "tasks" / "check_shared.py"


def check_shared(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(CHECKER), str(root)], capture_output=True, text=True)


def shared_copies(root: Path) -> list[Path]:
    paths = [root / name / "tests" / "shared" for name in ("alpha", "beta")]
    for path in paths:
        path.mkdir(parents=True)
        (path / "helper.py").write_text("VALUE = 42\n")
    return paths


def test_import_cache_does_not_make_identical_sources_differ(tmp_path):
    copies = shared_copies(tmp_path)
    caches = [Path(py_compile.compile(str(path / "helper.py"), doraise=True)) for path in copies]
    # CPython embeds the source filename, so identical source copies produce different bytecode.
    assert caches[0].read_bytes() != caches[1].read_bytes()
    result = check_shared(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout == "2 tasks, 1 shared files\n"


def test_legacy_bytecode_is_ignored(tmp_path):
    copies = shared_copies(tmp_path)
    for path in copies:
        py_compile.compile(str(path / "helper.py"), cfile=str(path / "helper.pyc"), doraise=True)
    result = check_shared(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout == "2 tasks, 1 shared files\n"


@pytest.mark.parametrize("filename", ["helper.py", "fixture.bin"])
def test_source_and_data_mismatches_are_still_rejected(tmp_path, filename):
    copies = shared_copies(tmp_path)
    for index, path in enumerate(copies):
        (path / filename).write_bytes(bytes([index]))
    result = check_shared(tmp_path)
    assert result.returncode == 1
    assert f"{filename}: beta != alpha" in result.stdout
