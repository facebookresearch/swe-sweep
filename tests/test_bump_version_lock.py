from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


UV = shutil.which("uv")


@pytest.mark.skipif(UV is None, reason="uv is used by the project development and CI workflow")
def test_version_bump_keeps_the_committed_lock_current(tmp_path):
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / ".github").mkdir()
    source_script = Path(__file__).resolve().parents[1] / ".github/bump_version.py"
    shutil.copyfile(source_script, repository / ".github/bump_version.py")
    (repository / "pyproject.toml").write_text(
        '[project]\nname="release-fixture"\nversion="0.1.0"\nrequires-python=">=3.12"\n'
        "dependencies=[]\n[tool.uv]\npackage=false\n"
    )
    env = dict(os.environ, UV_PYTHON=sys.executable, UV_OFFLINE="1")
    subprocess.run([UV, "lock"], cwd=repository, env=env, capture_output=True, check=True)
    for args in [
        ("init", "-q"),
        ("config", "user.name", "Fixture"),
        ("config", "user.email", "fixture@example.test"),
        ("add", "."),
        ("commit", "-qm", "initial"),
    ]:
        subprocess.run(["git", *args], cwd=repository, capture_output=True, check=True)
    bumped = subprocess.run(
        [sys.executable, ".github/bump_version.py"],
        cwd=repository,
        input="0.2.0\n",
        capture_output=True,
        text=True,
        env=env,
        timeout=15,
    )
    assert bumped.returncode == 0, bumped.stderr
    checked = subprocess.run(
        [UV, "lock", "--check"], cwd=repository, env=env, capture_output=True, text=True, timeout=15
    )
    assert checked.returncode == 0, checked.stderr
    files = subprocess.check_output(
        ["git", "show", "--pretty=format:", "--name-only", "HEAD"], cwd=repository, text=True
    ).splitlines()
    assert "pyproject.toml" in files
    assert "uv.lock" in files
    assert not subprocess.check_output(["git", "status", "--porcelain"], cwd=repository)
