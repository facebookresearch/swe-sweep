"""Real subprocess output must drain even when the caller has many open files."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

SESSION = (
    Path(__file__).resolve().parents[1]
    / "tasks/swe-sweep__optuna/tests/shared/swesweep_eval/infra/container_session.py"
)

PROBE = r"""
import importlib.util
import json
import os
import resource
import sys

sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("session_output_probe", sys.argv[1])
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
high_fd = sys.argv[2] == "high"
merge = sys.argv[3] == "merged"
held = []
try:
    if high_fd:
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        if soft < 1200:
            if hard < 1200:
                print(json.dumps({"unsupported": "RLIMIT_NOFILE is below 1200"}))
                raise SystemExit(0)
            # This changes only the isolated probe process, never the pytest caller.
            resource.setrlimit(resource.RLIMIT_NOFILE, (1200, hard))
        while not held or held[-1] < 1100:
            held.append(os.open(os.devnull, os.O_RDONLY))
    stdout = "stdout:" + "x" * 200000
    stderr = "stderr:" + "y" * 70000
    command = [sys.executable, "-c",
               "import sys; sys.stdout.write('stdout:' + 'x' * 200000); "
               "sys.stdout.flush(); sys.stderr.write('stderr:' + 'y' * 70000)"]
    with module.ContainerSession() as session:
        result = session.execute(command, timeout=2, merge_stderr=merge)
    assert result.returncode == 0, result.returncode
    assert result.stdout == stdout + (stderr if merge else "")
    assert result.stderr == ("" if merge else stderr)
    print(json.dumps({"returncode": result.returncode,
                      "stdout_length": len(result.stdout),
                      "stderr_length": len(result.stderr)}))
finally:
    for descriptor in held:
        os.close(descriptor)
"""


@pytest.mark.parametrize("high_fd", [False, True], ids=["ordinary-fds", "high-fds"])
@pytest.mark.parametrize("merge", [False, True], ids=["separate-streams", "merged-streams"])
def test_command_output_survives_high_descriptors(high_fd, merge):
    probe = subprocess.run(
        [sys.executable, "-c", PROBE, str(SESSION), "high" if high_fd else "low", "merged" if merge else "separate"],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert probe.returncode == 0, probe.stderr
    result = json.loads(probe.stdout)
    if "unsupported" in result:
        pytest.skip(result["unsupported"])
    assert result == {
        "returncode": 0,
        "stdout_length": 270014 if merge else 200007,
        "stderr_length": 0 if merge else 70007,
    }
