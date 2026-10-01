# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""Aggregate SWE-sweep rewards from graded Harbor trials."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Any

REWARD_KEYS = ("n_subtasks", "n_resolved", "visible_ok", "reward")


def task_name(reward_path: Path) -> str:
    """Return the task named by a trial config, or fall back to its directory name."""
    trial_dir = reward_path.parent.parent
    config = trial_dir / "config.json"
    if config.is_file():
        try:
            task = json.loads(config.read_text()).get("task") or {}
            path = task.get("path") or task.get("name")
            if path:
                return Path(str(path)).name
        except (OSError, ValueError):
            pass
    return trial_dir.name


def score_paths(roots: Sequence[Path]) -> dict[str, Any]:
    """Collect reward files below roots and return their aggregate report."""
    rows: list[tuple[str, dict[str, Any]]] = []
    for root in roots:
        for path in sorted(root.expanduser().rglob("reward.json")):
            try:
                data = json.loads(path.read_text())
            except (OSError, ValueError):
                continue
            if not isinstance(data, dict) or not all(key in data for key in REWARD_KEYS):
                continue
            rows.append((task_name(path), data))

    if not rows:
        locations = ", ".join(str(root) for root in roots)
        raise ValueError(f"no SWE-sweep reward.json found under {locations}")

    failures = sorted({name for name, data in rows if data.get("grader_failed", 0) >= 1})
    per_task: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for name, data in rows:
        if data.get("grader_failed", 0) < 1:
            per_task[name].append(data)

    tasks: list[dict[str, Any]] = []
    for name in sorted(per_task):
        trials = per_task[name]
        n_subtasks = int(trials[0]["n_subtasks"])
        resolved = [int(trial["n_resolved"]) for trial in trials]
        counted = [
            value if trial["visible_ok"] >= 1 else 0
            for value, trial in zip(resolved, trials, strict=True)
        ]
        tasks.append(
            {
                "task": name,
                "trials": len(trials),
                "n_subtasks": n_subtasks,
                "n_resolved": sum(resolved) / len(trials),
                "resolved_counted": sum(counted) / len(trials),
                "regressed": sum(1 for trial in trials if trial["visible_ok"] < 1),
                "reward": sum(float(trial["reward"]) for trial in trials) / len(trials),
            }
        )

    graded_bugs = sum(task["n_subtasks"] for task in tasks)
    resolved_bugs = sum(task["resolved_counted"] for task in tasks)
    resolved_ignoring_regressions = sum(task["n_resolved"] for task in tasks)
    summary = {
        "graded_tasks": len(tasks),
        "graded_bugs": graded_bugs,
        "resolved_bugs": resolved_bugs,
        "score": resolved_bugs / graded_bugs if graded_bugs else 0.0,
        "score_ignoring_regressions": (
            resolved_ignoring_regressions / graded_bugs if graded_bugs else 0.0
        ),
        "evaluation_failures": failures,
    }
    return {"summary": summary, "tasks": tasks}


def format_report(report: dict[str, Any], *, per_task: bool, as_json: bool) -> str:
    """Format an aggregate report for terminal or JSON output."""
    if as_json:
        return json.dumps(report, indent=1)

    summary = report["summary"]
    tasks = report["tasks"]
    failures = summary["evaluation_failures"]
    zeroed = [task for task in tasks if task["regressed"]]
    raw_resolved = sum(task["n_resolved"] for task in tasks)
    mean_task_reward = sum(task["reward"] for task in tasks) / len(tasks) if tasks else 0.0
    lines = [
        (
            f"SWE-sweep score over {summary['graded_tasks']} graded tasks, "
            f"{summary['graded_bugs']} graded bugs"
            + (
                f"; {len(failures)} evaluation failure(s) excluded: {', '.join(failures)}"
                if failures
                else ""
            )
        ),
        (
            "  bugs resolved in regression-free tasks: "
            f"{summary['resolved_bugs']:g} / {summary['graded_bugs']} = "
            f"{summary['score']:.2%}   <- the benchmark score"
        ),
        (
            f"  resolved ignoring the regression gate:  {raw_resolved:g}"
            + (
                f"  ({raw_resolved - summary['resolved_bugs']:g} in {len(zeroed)} "
                f"zeroed task(s): {', '.join(task['task'] for task in zeroed)})"
                if zeroed
                else ""
            )
        ),
        f"  score ignoring regressions: {summary['score_ignoring_regressions']:.2%}",
        f"  mean task reward (Harbor's `reward` average): {mean_task_reward:.4f}",
    ]
    if per_task:
        lines.extend(
            [
                "",
                f"{'task':40s} {'trials':>6s} {'bugs':>5s} "
                f"{'resolved':>8s} {'counted':>8s} {'reward':>7s}",
            ]
        )
        for task in tasks:
            lines.append(
                f"{task['task']:40s} {task['trials']:>6d} {task['n_subtasks']:>5d} "
                f"{task['n_resolved']:>8g} {task['resolved_counted']:>8g} "
                f"{task['reward']:>7.3f}"
                + ("  regressed" if task["regressed"] else "")
            )
    return "\n".join(lines)


def print_score(roots: Sequence[Path], *, per_task: bool = False, as_json: bool = False) -> int:
    """Score roots and print the requested representation."""
    print(format_report(score_paths(roots), per_task=per_task, as_json=as_json))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the standalone score command used by tasks/score.py."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path, help="graded trial directories")
    parser.add_argument("--per-task", action="store_true", help="show per-task results")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    args = parser.parse_args(argv)
    try:
        return print_score(args.paths, per_task=args.per_task, as_json=args.json)
    except ValueError as exc:
        parser.error(str(exc))
        return 2
