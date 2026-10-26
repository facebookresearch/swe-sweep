"""Validation tooling: official fixes applied as a submission would be."""

from __future__ import annotations

import json
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


def verdict(resolved, visible_ok=None, regressions=(), **extra):
    return {
        **extra,
        "visible_ok": not regressions if visible_ok is None else visible_ok,
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


def test_a_grading_that_measured_nothing_is_reported_not_read_as_unresolved():
    from swesweep.validate import validation_report

    report = validation_report(
        ["a", "b"],
        empty=verdict([], agent_build_ok=False, build_error="compile error"),
        stacked=verdict([], agent_patch_applied=False, agent_patch_error="hunk failed"),
        skipped=[],
        each={"a": verdict([], error="timeout")},
    )
    assert [f["problem"] for f in report["findings"]] == [
        "not graded: build failed: compile error",
        "not graded: patch did not apply: hunk failed",
        "not graded: grader error: timeout",
    ]


def test_nothing_counts_as_credited_when_a_must_pass_test_fails():
    from swesweep.validate import resolved

    assert resolved(verdict(["a"])) == {"a"}
    assert resolved(verdict(["a"], regressions=["t::green"])) == set()


def test_credit_with_no_fix_is_reported_when_must_pass_tests_also_fail():
    from swesweep.validate import validation_report

    report = validation_report(
        ["a"], empty=verdict(["a"], regressions=["t::flaky"]), stacked=verdict(["a"]), skipped=[], each={}
    )
    assert [f["problem"] for f in report["findings"]] == [
        "credited with no fix",
        "must-pass tests fail on the untouched tree",
    ]


def test_a_must_pass_run_that_timed_out_is_reported():
    """The grader scores 0 with no regression listed when the must-pass run times out or writes no report."""
    from swesweep.validate import validation_report

    timed_out = verdict(["a"], visible_ok=False)
    report = validation_report(
        ["a"], empty=verdict([], visible_ok=False), stacked=timed_out, skipped=[], each={"a": timed_out}
    )
    assert [(f["check"], f["problem"]) for f in report["findings"]] == [
        ("empty", "must-pass run timed out or wrote no report"),
        ("stacked", "must-pass run timed out or wrote no report"),
        ("alone", "must-pass run timed out or wrote no report"),
    ]


def test_hidden_test_results_are_reported_when_must_pass_tests_fail():
    """duckdb's stack breaks 5 must-pass tests: it scores 0, but the report still shows its 105/109."""
    from swesweep.validate import validation_report

    report = validation_report(
        ["a", "b", "c", "d"],
        empty=verdict([]),
        stacked=verdict(["a", "b", "c"], regressions=["t::broken"]),
        skipped=[],
        each={"d": verdict([], regressions=["t::other"])},
    )
    assert report["stacked"]["resolved"] == 0
    assert report["stacked"]["hidden_tests_pass"] == 3
    assert report["stacked"]["unresolved"] == ["d"]
    assert [(f["check"], f["problem"]) for f in report["findings"]] == [
        ("stacked", "not resolved by all fixes together"),
        ("stacked", "all fixes together break must-pass tests"),
        ("alone", "fix breaks must-pass tests"),
        ("alone", "own fix does not resolve it"),
    ]


def test_validate_takes_bugs_build_jobs_and_timeout(tmp_path, monkeypatch):
    import argparse

    from swesweep import cli

    task = tmp_path / "swe-sweep__x"
    (task / "tests").mkdir(parents=True)
    (task / "task.toml").write_text("[verifier]\ntimeout_sec = 600\n")
    bundle = {"build_jobs": 4, "subtasks": [{"id": "a"}, {"id": "b"}, {"id": "c"}]}
    (task / "tests" / "swesweep_eval.json").write_text(json.dumps(bundle))
    runs = []

    def harbor(command, check=False):
        graded = json.loads((Path(command[command.index("--path") + 1]) / "tests" / "swesweep_eval.json").read_text())
        fixes = next(arg for arg in command if arg.startswith("fixes="))
        multiplier = command[command.index("--verifier-timeout-multiplier") + 1]
        runs.append((fixes, [s["id"] for s in graded["subtasks"]], graded["build_jobs"], multiplier))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(cli.subprocess, "run", harbor)
    args = argparse.Namespace(
        task=str(task), output=tmp_path / "out", each=True, bugs="a,c", build_jobs=2, timeout=1200.0, dry_run=True
    )
    assert cli._validate(args) == 0
    assert runs == [
        ("fixes=", ["a", "c"], 2, "2.0"),
        ("fixes=all", ["a", "c"], 2, "2.0"),
        ("fixes=a", ["a", "c"], 2, "2.0"),
        ("fixes=c", ["a", "c"], 2, "2.0"),
    ]
    assert json.loads((task / "tests" / "swesweep_eval.json").read_text()) == bundle  # the task itself is untouched


def write_job(job_dir: Path, name: str, resolved) -> None:
    path = job_dir / name / "trial" / "verifier" / "eval.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(verdict(resolved)))


def test_a_rerun_reads_only_the_job_it_made(tmp_path):
    from swesweep.validate import new_job, read_verdict

    write_job(tmp_path, "2026-10-01__10-00-00", ["old"])
    before = set(tmp_path.iterdir())
    assert new_job(tmp_path, before) is None  # the rerun failed before Harbor made a job
    (tmp_path / "2026-10-02__10-00-00").mkdir()
    assert read_verdict(new_job(tmp_path, before)) is None  # it made a job but wrote no result
    write_job(tmp_path, "2026-10-03__10-00-00", ["new"])
    assert resolved_ids(read_verdict(new_job(tmp_path, before))) == {"new"}


def test_a_failed_rerun_is_reported_as_missing_not_as_the_old_result(tmp_path, monkeypatch):
    import argparse

    from swesweep import cli

    task = tmp_path / "swe-sweep__x"
    (task / "tests").mkdir(parents=True)
    (task / "task.toml").write_text("")
    (task / "tests" / "swesweep_eval.json").write_text(json.dumps({"subtasks": [{"id": "a"}]}))
    runs = []

    def harbor(command, check=False):
        runs.append(command)
        if len(runs) <= 2:  # the first validate: both gradings write a clean result
            jobs_dir = Path(command[command.index("--jobs-dir") + 1])
            write_job(jobs_dir, "2026-10-01__10-00-00", ["a"] if jobs_dir.name == "stacked" else [])
            return subprocess.CompletedProcess(command, 0)
        return subprocess.CompletedProcess(command, 1)  # the rerun fails before writing anything

    monkeypatch.setattr(cli.subprocess, "run", harbor)
    args = argparse.Namespace(
        task=str(task), output=tmp_path / "out", each=False, bugs=None, build_jobs=4, timeout=None, dry_run=False
    )
    assert cli._validate(args) == 0
    assert cli._validate(args) == 1
    report = json.loads((tmp_path / "out" / "swe-sweep__x" / "validation.json").read_text())
    assert report["findings"] == [
        {"check": "empty", "problem": "no result"},
        {"check": "stacked", "problem": "no result"},
    ]


def resolved_ids(v):
    return {s["subtask_id"] for s in v["subtasks"] if s["resolved"]}
