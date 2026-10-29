from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]


def shared_modules():
    sys.path.insert(0, str(ROOT / "tasks/swe-sweep__click/tests/shared"))
    return (
        importlib.import_module("swesweep_grade"),
        importlib.import_module("swesweep_eval.eval.suites.utils.evaluation"),
        importlib.import_module("swesweep_eval.eval.repository"),
        importlib.import_module("swesweep_eval.infra.container_session"),
    )


def synthetic_git_patch(tmp_path, filename, quote):
    repo = tmp_path / "repo"
    (repo / "tests").mkdir(parents=True)
    test_file = repo / "tests" / filename
    test_file.write_text("baseline fixture\n")
    (repo / "module.py").write_text("old production\n")
    commands = [
        ("init", "-q"),
        ("config", "user.name", "Fixture"),
        ("config", "user.email", "fixture@example.test"),
        ("config", "core.quotePath", str(quote).lower()),
        ("add", "."),
        ("commit", "-qm", "baseline"),
        ("tag", "baseline"),
    ]
    for args in commands:
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)
    test_file.write_text("agent-edited test\n")
    (repo / "module.py").write_text("fixed production\n")
    patch = subprocess.check_output(["git", "-C", str(repo), "diff", "--binary"])
    subprocess.run(["git", "-C", str(repo), "reset", "--hard", "baseline"], check=True, capture_output=True)
    return repo, test_file, patch


@pytest.mark.parametrize("filename", ["test_caf\u00e9.py", "test_tab\tname.py", 'test_quote"name.py'])
@pytest.mark.parametrize("quote", [True, False])
def test_real_git_quoted_names_are_identified_and_test_edits_reverted(tmp_path, filename, quote):
    grader, evaluation, repository, session = shared_modules()
    repo, test_file, patch = synthetic_git_patch(tmp_path, filename, quote)
    assert set(evaluation.touched_files(patch.decode())) == {"module.py", "tests/" + filename}
    with session.ContainerSession() as env:
        target = repository.ContainerRepository(env, str(repo))
        out = {"detail": {}, "timings": {}}
        assert grader._apply_agent_patch(
            target, None, SimpleNamespace(test_dirs=(), needs_build=False), patch, "1", out
        )
    assert test_file.read_text() == "baseline fixture\n"
    assert (repo / "module.py").read_text() == "fixed production\n"


def test_unified_header_timestamps_are_not_part_of_file_names():
    _, evaluation, _, _ = shared_modules()
    assert evaluation.touched_files("--- a/tests/old.py\t2026-01-01\n+++ b/tests/new.py\t2026-01-01\n") == [
        "tests/new.py",
        "tests/old.py",
    ]
