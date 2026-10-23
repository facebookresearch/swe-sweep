"""Grade a task's official fixes the way a submission is graded, and report what fails (W8).

The release validated every official fix on its own, against its own bug, with the must-pass
tests run only on the untouched tree. That misses official fixes that break a must-pass test,
fixes that only work alone, bugs credited with no fix, and one bug's fix crediting another's.
`sweep validate` grades, through the same Harbor route as `sweep eval`:

- the empty submission (nothing should be credited);
- every official fix stacked, as one complete submission (everything should be credited, with
  no regression); fixes that do not apply on top of the others are reported;
- with ``--each``, every official fix alone (its own bug only, no regression).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Apply one fix on top of the fixes applied so far: plainly, else with a 3-way merge; if both
# fail, put back exactly the paths this fix touched as they were before it (the snapshot tree),
# so a conflicting fix never undoes or half-applies on top of the earlier ones.
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


def read_verdict(job_dir: Path) -> dict[str, Any] | None:
    """The single trial's eval.json below a Harbor job directory, or None."""
    found = sorted(job_dir.rglob("verifier/eval.json"))
    return json.loads(found[0].read_text()) if found else None


def credited(verdict: dict[str, Any]) -> set[str]:
    if not verdict.get("visible_ok"):
        return set()
    return {s["subtask_id"] for s in verdict.get("subtasks", []) if s.get("resolved")}


def resolved(verdict: dict[str, Any]) -> set[str]:
    return {s["subtask_id"] for s in verdict.get("subtasks", []) if s.get("resolved")}


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
    else:
        free = sorted(resolved(empty))
        report["empty"] = {"resolved": free, "regressions": empty.get("regressions", [])}
        if free:
            findings.append({"check": "empty", "problem": "credited with no fix", "bugs": free})
        if empty.get("regressions"):
            findings.append({"check": "empty", "problem": "must-pass tests fail on the untouched tree"})
    if stacked is None:
        findings.append({"check": "stacked", "problem": "no result"})
    else:
        missing = sorted(set(bugs) - resolved(stacked) - set(skipped))
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
    for bug, verdict in sorted(each.items()):
        if verdict is None:
            findings.append({"check": "alone", "bug": bug, "problem": "no result"})
            continue
        got = resolved(verdict)
        if bug not in got:
            findings.append({"check": "alone", "bug": bug, "problem": "own fix does not resolve it"})
        others = sorted(got - {bug})
        if others:
            findings.append({"check": "alone", "bug": bug, "problem": "fix also credits other bugs", "bugs": others})
        if verdict.get("regressions"):
            findings.append(
                {"check": "alone", "bug": bug, "problem": "fix breaks must-pass tests", "tests": verdict["regressions"]}
            )
    return report
