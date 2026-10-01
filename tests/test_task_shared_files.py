from __future__ import annotations

import json
import subprocess
import sys
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TASKS_ROOT = ROOT / "tasks"
TASK_PREFIX = "swe-sweep__"

FORBIDDEN_ACTIVE_NAMES = (
    "pandora-bench__",
    "pandora_eval",
    "pandora_grade",
    "PANDORA_",
    "/opt/pandora",
    "/usr/local/share/pandora",
    ".pandora_",
    "pandora-src",
    "pandora-python",
    "pandora-extra",
    "pandora-testenv",
    "pandora-run",
    "pandora_iers",
    "pandora_julia",
    "pandora-write",
    "PandoraRun",
    "from pandorabench",
    "import pandorabench",
)


def task_directories() -> list[Path]:
    return sorted(path for path in TASKS_ROOT.iterdir() if (path / "task.toml").is_file())


def test_task_packages_use_canonical_swe_sweep_names():
    tasks = task_directories()
    assert len(tasks) == 100

    for task in tasks:
        assert task.name.startswith(TASK_PREFIX)
        assert "pandora" not in task.relative_to(ROOT).as_posix().lower()

        with (task / "task.toml").open("rb") as stream:
            config = tomllib.load(stream)
        assert config["name"] == task.name
        assert config["metadata"]["benchmark"] == "swe-sweep"
        assert "swe-sweep" in config["metadata"]["tags"]
        assert "upstream_commit" in config["metadata"]
        assert "pandorabench_commit" not in config["metadata"]

        tests_dir = task / "tests"
        bundle = json.loads((tests_dir / "swesweep_eval.json").read_text())
        assert "upstream_commit" in bundle
        assert "upstream_image" in bundle
        assert "pandorabench_commit" not in bundle
        assert "image" not in bundle
        assert (tests_dir / "shared" / "swesweep_grade.py").is_file()
        assert (tests_dir / "shared" / "swesweep_eval" / "__init__.py").is_file()


def test_no_active_pandora_runtime_contracts_remain():
    candidates = []
    for path in TASKS_ROOT.rglob("*"):
        if not path.is_file():
            continue
        if path.name == "Dockerfile" or path.suffix in {".json", ".md", ".py", ".sh", ".toml"}:
            candidates.append(path)

    failures = []
    for path in candidates:
        text = path.read_text(errors="surrogateescape")
        for legacy_name in FORBIDDEN_ACTIVE_NAMES:
            if legacy_name in text:
                failures.append(f"{path.relative_to(ROOT)}: {legacy_name}")

    assert not failures, "active Pandora runtime names remain:\n" + "\n".join(failures)


def test_shared_files_are_identical_across_tasks():
    result = subprocess.run(
        [sys.executable, str(ROOT / "tasks" / "check_shared.py"), str(ROOT / "tasks")],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.startswith("100 tasks, ")
