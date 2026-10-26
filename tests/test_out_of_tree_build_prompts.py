"""Out-of-tree /build tasks must document the prebuilt tree in agent prompts."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASKS_ROOT = ROOT / "tasks"

REQUIRED_SNIPPETS = (
    "/build",
    "Do NOT re-run configure",
)


def out_of_tree_task_dirs() -> list[Path]:
    dirs: list[Path] = []
    for eval_path in sorted(TASKS_ROOT.glob("swe-sweep__*/tests/swesweep_eval.json")):
        data = json.loads(eval_path.read_text())
        if '"build_dir": "/build"' in json.dumps(data):
            dirs.append(eval_path.parents[1])
    return dirs


def test_out_of_tree_build_tasks_exist():
    assert out_of_tree_task_dirs(), "expected at least one task with build_dir=/build"


def test_instruction_and_yaml_document_prebuilt_build():
    for task_dir in out_of_tree_task_dirs():
        instr = (task_dir / "instruction.md").read_text()
        for snippet in REQUIRED_SNIPPETS:
            assert snippet in instr, f"{task_dir.name}/instruction.md missing {snippet!r}"

        yaml_path = task_dir / "agent" / "mini_swe_agent.yaml"
        yaml_text = yaml_path.read_text()
        for snippet in REQUIRED_SNIPPETS:
            assert snippet in yaml_text, (
                f"{task_dir.name}/agent/mini_swe_agent.yaml system_template missing {snippet!r}"
            )

        # Keep instruction Settings body aligned with the yaml system_template.
        instr_settings = re.search(
            r"## Settings\n.*?\n## Fairplay", instr, flags=re.S
        )
        assert instr_settings, task_dir.name
        escaped_settings = instr_settings.group(0).replace("\n", r"\n")
        assert escaped_settings in yaml_text, (
            f"{task_dir.name}: instruction.md Settings != mini_swe_agent.yaml Settings"
        )
