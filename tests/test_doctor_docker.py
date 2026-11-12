from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest

from swesweep import cli


def _docker_program(tmp_path: Path, monkeypatch, source: str) -> None:
    program = tmp_path / "synthetic-docker.py"
    program.write_text(source)
    real_run = subprocess.run
    real_which = cli.shutil.which

    def find_executable(name):
        return str(program) if name == "docker" else real_which(name)

    def run_program(command, **kwargs):
        assert command == [str(program), "info", "--format", "{{.OSType}}/{{.Architecture}}"]
        # Bound the unfixed implementation too; subprocess.run kills and reaps
        # its child when the outer watchdog expires.
        kwargs.setdefault("timeout", 2)
        return real_run([sys.executable, *command], **kwargs)

    monkeypatch.setattr(cli.shutil, "which", find_executable)
    monkeypatch.setattr(cli.subprocess, "run", run_program)


def test_docker_probe_times_out_and_reports_doctor_failure(tmp_path, monkeypatch, capsys):
    _docker_program(tmp_path, monkeypatch, "import time\ntime.sleep(10)\n")
    monkeypatch.setattr(cli, "_DOCKER_INFO_TIMEOUT_SEC", 0.1, raising=False)

    start = time.monotonic()
    assert cli.main(["infra", "doctor"]) == 1
    assert time.monotonic() - start < 1.5
    assert "docker  Docker daemon did not respond within 0.1 seconds" in capsys.readouterr().out


def test_docker_probe_accepts_a_responsive_daemon(tmp_path, monkeypatch):
    _docker_program(tmp_path, monkeypatch, 'print("linux/amd64")\n')
    assert cli._docker_info() == (True, "linux/amd64")


@pytest.mark.parametrize(
    ("source", "detail"),
    [
        ('import sys\nprint("daemon unavailable", file=sys.stderr)\nsys.exit(1)\n', "daemon unavailable"),
        ('import sys\nprint("stdout fallback")\nsys.exit(1)\n', "stdout fallback"),
        ("raise SystemExit(1)\n", "Docker daemon unavailable"),
    ],
)
def test_docker_probe_retains_error_details(tmp_path, monkeypatch, source, detail):
    _docker_program(tmp_path, monkeypatch, source)
    assert cli._docker_info() == (False, detail)


def test_docker_probe_reports_a_missing_executable(monkeypatch):
    monkeypatch.setattr(cli.shutil, "which", lambda _name: None)
    assert cli._docker_info() == (False, "docker executable not found")
