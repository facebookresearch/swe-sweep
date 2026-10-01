"""Command-line interface for evaluating SWE-sweep patches with Harbor."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import shutil
import subprocess
import sys
import tempfile
import tomllib
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

from swesweep.constants import HARBOR_SOURCE_REVISION, TASK_PREFIX, TASKS_DIR
from swesweep.scoring import print_score


def task_directories() -> tuple[Path, ...]:
    if not TASKS_DIR.is_dir():
        return ()
    return tuple(sorted(path for path in TASKS_DIR.iterdir() if (path / "task.toml").is_file()))


def resolve_task(name: str) -> Path:
    candidate = Path(name).expanduser()
    if candidate.is_dir() and (candidate / "task.toml").is_file():
        return candidate.resolve()

    directory_name = name if name.startswith(TASK_PREFIX) else f"{TASK_PREFIX}{name}"
    candidate = TASKS_DIR / directory_name
    if not (candidate / "task.toml").is_file():
        known = ", ".join(path.name.removeprefix(TASK_PREFIX) for path in task_directories())
        raise ValueError(f"unknown task {name!r}; known tasks: {known}")
    return candidate.resolve()


def _selected_bug_ids(raw: str | None) -> tuple[str, ...] | None:
    if raw is None:
        return None
    selected = tuple(dict.fromkeys(part.strip() for part in raw.split(",") if part.strip()))
    if not selected:
        raise ValueError("--bugs must contain at least one bug id")
    return selected


@contextmanager
def configured_task(
    task_dir: Path,
    *,
    bug_ids: tuple[str, ...] | None,
    build_jobs: int,
) -> Iterator[Path]:
    """Yield the original task or a temporary task with evaluation-only overrides."""
    bundle_path = task_dir / "tests" / "swesweep_eval.json"
    bundle = json.loads(bundle_path.read_text())
    current_build_jobs = int(bundle.get("build_jobs", 4))
    if bug_ids is None and build_jobs == current_build_jobs:
        yield task_dir
        return

    with tempfile.TemporaryDirectory(prefix="swe-sweep-task-") as temporary:
        copied = Path(temporary) / task_dir.name
        shutil.copytree(task_dir, copied, symlinks=True)
        copied_bundle_path = copied / "tests" / "swesweep_eval.json"
        copied_bundle = json.loads(copied_bundle_path.read_text())
        copied_bundle["build_jobs"] = build_jobs

        if bug_ids is not None:
            by_id = {bug["id"]: bug for bug in copied_bundle["subtasks"]}
            unknown = sorted(set(bug_ids) - set(by_id))
            if unknown:
                raise ValueError(f"unknown bug id(s) for {task_dir.name}: {', '.join(unknown)}")
            copied_bundle["subtasks"] = [by_id[bug_id] for bug_id in bug_ids]

        copied_bundle_path.write_text(json.dumps(copied_bundle, indent=2) + "\n")
        yield copied


def harbor_eval_command(
    task_dir: Path,
    patch: Path,
    output: Path,
    *,
    timeout: float | None,
    dry_run: bool,
) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "harbor.cli.main",
        "run",
        "--path",
        str(task_dir),
        "--agent",
        "swesweep.patch_agent:PatchAgent",
        "--agent-kwarg",
        f"patch_path={patch}",
        "--jobs-dir",
        str(output),
        "--n-concurrent",
        "1",
    ]
    if timeout is not None:
        with (task_dir / "task.toml").open("rb") as stream:
            task_config = tomllib.load(stream)
        configured_timeout = float(task_config.get("verifier", {}).get("timeout_sec", timeout))
        if configured_timeout <= 0:
            raise ValueError(f"{task_dir / 'task.toml'} has an invalid verifier timeout")
        command.extend(("--verifier-timeout-multiplier", str(timeout / configured_timeout)))
    if dry_run:
        command.append("--dry-run")
    return command


def _eval(args: argparse.Namespace) -> int:
    task_dir = resolve_task(args.task)
    patch = args.patch.expanduser().resolve()
    if not patch.is_file():
        raise ValueError(f"submission patch does not exist: {patch}")
    output = args.output.expanduser().resolve()
    bug_ids = _selected_bug_ids(args.bugs)

    with configured_task(task_dir, bug_ids=bug_ids, build_jobs=args.build_jobs) as selected_task:
        command = harbor_eval_command(selected_task, patch, output, timeout=args.timeout, dry_run=args.dry_run)
        return subprocess.run(command, check=False).returncode


def _info(args: argparse.Namespace) -> int:
    return print_score(args.paths, per_task=args.per_task, as_json=args.json)


def _docker_info() -> tuple[bool, str]:
    docker = shutil.which("docker")
    if docker is None:
        return False, "docker executable not found"
    result = subprocess.run(
        [docker, "info", "--format", "{{.OSType}}/{{.Architecture}}"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        return False, (result.stderr or result.stdout or "Docker daemon unavailable").strip()
    return True, result.stdout.strip()


def _doctor(_args: argparse.Namespace) -> int:
    failures = 0

    print(f"python  {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")

    try:
        distribution = importlib.metadata.distribution("harbor")
        direct_url_text = distribution.read_text("direct_url.json")
        direct_url = json.loads(direct_url_text) if direct_url_text else {}
        installed_revision = direct_url.get("vcs_info", {}).get("commit_id")
        if installed_revision == HARBOR_SOURCE_REVISION:
            print(f"harbor  {distribution.version} (source revision {installed_revision[:12]})")
        else:
            print(
                f"harbor  ERROR: expected source revision {HARBOR_SOURCE_REVISION[:12]}, "
                f"found {installed_revision or distribution.version}"
            )
            failures += 1
    except importlib.metadata.PackageNotFoundError:
        print("harbor  ERROR: not installed; run `uv sync`")
        failures += 1

    git = shutil.which("git")
    print(f"git     {git or 'ERROR: executable not found'}")
    failures += git is None

    docker_ok, docker_detail = _docker_info()
    print(f"docker  {docker_detail}")
    failures += not docker_ok

    tasks = task_directories()
    print(f"tasks   {len(tasks)} Harbor task packages")
    if not tasks:
        failures += 1
    return 1 if failures else 0


def _task_images(task_dir: Path) -> set[str]:
    with (task_dir / "task.toml").open("rb") as stream:
        config = tomllib.load(stream)
    images: set[str] = set()
    environment_image = config.get("environment", {}).get("docker_image")
    if environment_image:
        images.add(environment_image)
    verifier_image = config.get("verifier", {}).get("environment", {}).get("docker_image")
    if verifier_image:
        images.add(verifier_image)
    return images


def _docker_pull(args: argparse.Namespace) -> int:
    if args.all:
        selected = task_directories()
    else:
        selected = tuple(resolve_task(task) for task in args.tasks)

    images = sorted({image for task_dir in selected for image in _task_images(task_dir)})
    if not images:
        print(
            "No prebuilt task images are configured yet. Harbor will build the selected "
            "tasks from their checked-in Dockerfiles during evaluation.",
            file=sys.stderr,
        )
        return 1

    docker = shutil.which("docker")
    if docker is None:
        print("docker executable not found", file=sys.stderr)
        return 1
    failures: list[str] = []
    for image in images:
        command = [docker, "pull", image]
        if args.dry_run:
            print(" ".join(command))
        elif subprocess.run(command, check=False).returncode:
            failures.append(image)
    if failures:
        print(f"failed to pull {len(failures)} image(s): {', '.join(failures)}", file=sys.stderr)
        return 1
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sweep", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    evaluate = commands.add_parser("eval", help="evaluate one patch against one SWE-sweep task")
    evaluate.add_argument("task", help="task name, for example dateutil")
    evaluate.add_argument("patch", type=Path, help="unified diff against the task's base commit")
    evaluate.add_argument(
        "-o", "--output", type=Path, default=Path("jobs"), help="Harbor jobs directory (default: jobs/)"
    )
    evaluate.add_argument("--bugs", help="comma-separated bug ids to score (default: all)")
    evaluate.add_argument("--build-jobs", type=int, default=4, help="build parallelism (default: 4)")
    evaluate.add_argument("--timeout", type=float, help="verifier timeout in seconds")
    evaluate.add_argument("--dry-run", action="store_true", help="validate without running containers")
    evaluate.set_defaults(func=_eval)

    info = commands.add_parser("info", help="summarize graded SWE-sweep trials")
    info.add_argument("paths", nargs="+", type=Path, help="graded trial directories")
    info.add_argument("--per-task", action="store_true", help="show per-task results")
    info.add_argument("--json", action="store_true", help="emit JSON")
    info.set_defaults(func=_info)

    infra = commands.add_parser("infra", help="check and prepare local infrastructure")
    infra_commands = infra.add_subparsers(dest="infra_command", required=True)
    doctor = infra_commands.add_parser("doctor", help="check the local evaluation setup")
    doctor.set_defaults(func=_doctor)

    dockerhub = infra_commands.add_parser("dockerhub", help="manage Docker Hub task images")
    dockerhub_commands = dockerhub.add_subparsers(dest="dockerhub_command", required=True)
    pull = dockerhub_commands.add_parser("pull", help="pull configured prebuilt task images")
    selection = pull.add_mutually_exclusive_group(required=True)
    selection.add_argument("--all", action="store_true", help="pull images for all tasks")
    selection.add_argument("--tasks", nargs="+", metavar="TASK", help="pull images for selected tasks")
    pull.add_argument("--dry-run", action="store_true", help="print docker commands without running them")
    pull.set_defaults(func=_docker_pull)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if getattr(args, "build_jobs", 1) < 1:
        parser.error("--build-jobs must be at least 1")
    if getattr(args, "timeout", 1) is not None and getattr(args, "timeout", 1) <= 0:
        parser.error("--timeout must be greater than 0")
    try:
        return args.func(args)
    except (FileNotFoundError, ValueError) as exc:
        parser.error(str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
