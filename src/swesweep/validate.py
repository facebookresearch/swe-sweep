"""Grade a task's official fixes the way a submission is graded, through the same Harbor route as `sweep eval`.
Grades the empty submission, all fixes stacked and, with ``--each``, each fix alone, and reports what fails."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Apply one fix on top of the earlier ones: plainly, else with a 3-way merge.
# If both fail, restore the paths it touched from the snapshot, so a conflicting fix never undoes earlier fixes.
APPLY_ONE = """set -u
snap=$(git add -A && git write-tree) || exit 2
git apply --binary --whitespace=nowarn {patch} && exit 0
git apply --3way --binary --whitespace=nowarn {patch} && exit 0
git apply --numstat {patch} | cut -f3- | while IFS= read -r path; do
  if git cat-file -e "$snap:$path" 2>/dev/null; then git checkout "$snap" -- "$path"
  else rm -f -- "$path"; git rm -q --cached --ignore-unmatch -- "$path"; fi
done
exit 1
"""


def newest_first(paths: list[Path]) -> list[Path]:
    return sorted(paths, key=lambda path: path.stat().st_mtime, reverse=True)


def new_job(job_dir: Path, before: set[Path]) -> Path | None:
    """The job a run added under `job_dir` (not in `before`), or None if it added none.

    A rerun adds a job next to the old ones. If it fails before writing a result, the newest result there
    is the old job's, so only the job this run made may be read. Harbor names jobs by start time.
    """
    if not job_dir.is_dir():
        return None
    jobs = sorted(path for path in job_dir.iterdir() if path.is_dir() and path not in before)
    return jobs[-1] if jobs else None


def read_verdict(job: Path | None) -> dict[str, Any] | None:
    """The newest trial's eval.json in one Harbor job, or None."""
    found = newest_first(list(job.rglob("verifier/eval.json"))) if job is not None else []
    return json.loads(found[0].read_text()) if found else None


def hidden_tests_pass(verdict: dict[str, Any]) -> set[str]:
    """Bugs whose hidden tests pass, whatever the must-pass tests did."""
    return {s["subtask_id"] for s in verdict.get("subtasks", []) if s.get("resolved")}


def resolved(verdict: dict[str, Any]) -> set[str]:
    """Bugs a submission is credited with: none when a must-pass test failed (the task then scores 0)."""
    return hidden_tests_pass(verdict) if verdict.get("visible_ok") else set()


def not_graded(verdict: dict[str, Any]) -> str | None:
    """Why a grading measured nothing (the patch did not apply, the build failed, the grader errored), or None."""
    if verdict.get("agent_patch_applied") is False:
        return f"patch did not apply: {verdict.get('agent_patch_error') or 'no detail'}"
    if verdict.get("agent_build_ok") is False:
        return f"build failed: {verdict.get('build_error') or 'no detail'}"
    if verdict.get("error"):
        return f"grader error: {verdict['error']}"
    return None


NO_REPORT = "must-pass run timed out or wrote no report"


def no_must_pass_report(verdict: dict[str, Any]) -> bool:
    """The must-pass run timed out or wrote no report: the task scores 0, but no regression is listed."""
    return not verdict.get("visible_ok") and not verdict.get("regressions")


def validation_report(
    bugs: list[str],
    empty: dict[str, Any] | None,
    stacked: dict[str, Any] | None,
    skipped: list[str],
    each: dict[str, dict[str, Any] | None],
) -> dict[str, Any]:
    """Findings from the empty, stacked and per-fix gradings of one task."""
    report: dict[str, Any] = {"bugs": len(bugs), "findings": []}
    findings = report["findings"]
    if empty is None:
        findings.append({"check": "empty", "problem": "no result"})
    elif not_graded(empty):
        findings.append({"check": "empty", "problem": f"not graded: {not_graded(empty)}"})
    else:
        # a bug credited with no fix is a defect even when must-pass tests also fail on the untouched tree
        free = sorted(hidden_tests_pass(empty))
        report["empty"] = {"resolved": free, "regressions": empty.get("regressions", [])}
        if free:
            findings.append({"check": "empty", "problem": "credited with no fix", "bugs": free})
        if empty.get("regressions"):
            findings.append({"check": "empty", "problem": "must-pass tests fail on the untouched tree"})
        if no_must_pass_report(empty):
            findings.append({"check": "empty", "problem": NO_REPORT})
    if stacked is None:
        findings.append({"check": "stacked", "problem": "no result"})
    elif not_graded(stacked):
        findings.append({"check": "stacked", "problem": f"not graded: {not_graded(stacked)}"})
    else:
        # with a must-pass test failing nothing is credited; that finding says why, not one entry per bug
        missing = sorted(set(bugs) - resolved(stacked) - set(skipped)) if stacked.get("visible_ok") else []
        report["stacked"] = {
            "resolved": len(resolved(stacked)),
            "skipped_fixes": skipped,
            "unresolved": missing,
            "regressions": stacked.get("regressions", []),
        }
        if skipped:
            findings.append({"check": "stacked", "problem": "official fixes do not stack", "bugs": skipped})
        if missing:
            findings.append({"check": "stacked", "problem": "not resolved by all fixes together", "bugs": missing})
        if stacked.get("regressions"):
            findings.append(
                {
                    "check": "stacked",
                    "problem": "all fixes together break must-pass tests",
                    "tests": stacked["regressions"],
                }
            )
        if no_must_pass_report(stacked):
            findings.append({"check": "stacked", "problem": NO_REPORT})
    for bug, verdict in sorted(each.items()):
        if verdict is None:
            findings.append({"check": "alone", "bug": bug, "problem": "no result"})
            continue
        if not_graded(verdict):
            findings.append({"check": "alone", "bug": bug, "problem": f"not graded: {not_graded(verdict)}"})
            continue
        if no_must_pass_report(verdict):
            findings.append({"check": "alone", "bug": bug, "problem": NO_REPORT})
            continue
        if not verdict.get("visible_ok"):
            findings.append(
                {
                    "check": "alone",
                    "bug": bug,
                    "problem": "fix breaks must-pass tests",
                    "tests": verdict.get("regressions", []),
                }
            )
            continue
        got = resolved(verdict)
        if bug not in got:
            findings.append({"check": "alone", "bug": bug, "problem": "own fix does not resolve it"})
        others = sorted(got - {bug})
        if others:
            findings.append({"check": "alone", "bug": bug, "problem": "fix also credits other bugs", "bugs": others})
    return report
