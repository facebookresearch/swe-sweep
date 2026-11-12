"""The verifier must re-apply the same binary diffs the agent produces."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]


class _Env:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def execute(self, argv, **_kwargs):
        self.calls.append(list(argv))
        return SimpleNamespace(returncode=0, stderr="")


def test_apply_and_check_pass_binary_diffs():
    shared = ROOT / "tasks" / "swe-sweep__agda" / "tests" / "shared"
    sys.path.insert(0, str(shared))
    try:
        from swesweep_eval.eval.repository import ContainerRepository
    finally:
        sys.path.remove(str(shared))

    env = _Env()
    repo = ContainerRepository(env, "/repo")

    assert repo.patch_applies("gold.patch") is True
    applied, error = repo.apply_patch("model.patch")

    assert applied is True
    assert error == ""
    assert env.calls == [
        ["git", "-C", "/repo", "apply", "--binary", "--check", "--whitespace=nowarn", "gold.patch"],
        ["git", "-C", "/repo", "apply", "--binary", "--whitespace=nowarn", "model.patch"],
    ]
