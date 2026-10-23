"""Validation tooling: official fixes applied as a submission would be (W8)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from swesweep.validate import APPLY_ONE


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout


def make_patch(repo: Path, edit, name: str, out: Path) -> Path:
    """A patch from the baseline for one edit, then back to the baseline."""
    edit(repo)
    git(repo, "add", "-A")
    patch = out / f"{name}.patch"
    patch.write_text(git(repo, "diff", "--cached", "--binary", "baseline"))
    git(repo, "reset", "-q", "--hard", "baseline")
    git(repo, "clean", "-qfd")
    return patch


def test_a_conflicting_fix_is_skipped_without_undoing_earlier_fixes(tmp_path):
    repo, out = tmp_path / "repo", tmp_path / "patches"
    repo.mkdir()
    out.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "t@t")
    git(repo, "config", "user.name", "t")
    (repo / "a.txt").write_text("one\ntwo\nthree\n")
    (repo / "b.txt").write_text("alpha\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "base")
    git(repo, "tag", "baseline")

    first = make_patch(repo, lambda r: (r / "a.txt").write_text("one\nTWO\nthree\n"), "first", out)

    def conflicting(r):
        (r / "a.txt").write_text("one\n2\nthree\n")
        (r / "new.txt").write_text("added by the conflicting fix\n")

    second = make_patch(repo, conflicting, "second", out)
    third = make_patch(repo, lambda r: (r / "b.txt").write_text("beta\n"), "third", out)

    codes = [
        subprocess.run(["bash", "-c", APPLY_ONE.format(patch=p)], cwd=repo, capture_output=True, check=False).returncode
        for p in (first, second, third)
    ]

    assert codes == [0, 1, 0]
    assert (repo / "a.txt").read_text() == "one\nTWO\nthree\n"  # the first fix survives
    assert (repo / "b.txt").read_text() == "beta\n"
    assert not (repo / "new.txt").exists()  # the skipped fix left nothing behind
    status = git(repo, "status", "--porcelain")
    assert "new.txt" not in status
    assert "<<<<<<<" not in (repo / "a.txt").read_text()


def verdict(resolved, visible_ok=True, regressions=()):
    return {
        "visible_ok": visible_ok,
        "regressions": list(regressions),
        "subtasks": [{"subtask_id": bug, "resolved": True} for bug in resolved],
    }


def test_validation_report_names_each_kind_of_failure():
    from swesweep.validate import validation_report

    report = validation_report(
        ["a", "b", "c"],
        empty=verdict(["c"]),
        stacked=verdict(["a", "c"], visible_ok=False, regressions=["t::green"]),
        skipped=["b"],
        each={"a": verdict(["a", "c"]), "b": verdict([]), "c": verdict(["c"], regressions=["t::other"])},
    )
    problems = {(f["check"], f.get("bug"), f["problem"]) for f in report["findings"]}
    assert problems == {
        ("empty", None, "credited with no fix"),
        ("stacked", None, "official fixes do not stack"),
        ("stacked", None, "all fixes together break must-pass tests"),
        ("alone", "a", "fix also credits other bugs"),
        ("alone", "b", "own fix does not resolve it"),
        ("alone", "c", "fix breaks must-pass tests"),
    }


def test_a_clean_task_has_no_findings():
    from swesweep.validate import validation_report

    report = validation_report(["a"], empty=verdict([]), stacked=verdict(["a"]), skipped=[], each={})
    assert report["findings"] == []


def test_validate_runs_the_official_fix_agent(tmp_path):
    from swesweep.cli import harbor_fix_command

    command = harbor_fix_command(tmp_path / "swe-sweep__x", "all", tmp_path / "out", dry_run=True)
    assert "swesweep.patch_agent:OfficialFixAgent" in command
    assert "fixes=all" in command
    assert command[-1] == "--dry-run"
