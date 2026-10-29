from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from pathlib import Path

import pytest


# Keep interpreter caches out of the vendored-source synchronization check.
sys.dont_write_bytecode = True


@pytest.mark.skipif(os.name != "posix", reason="verifier process groups require POSIX")
def test_timeout_bounds_writing_to_a_child_that_does_not_read(tmp_path):
    shared = Path(__file__).resolve().parents[1] / "tasks/swe-sweep__click/tests/shared"
    pid_path = tmp_path / "child.pid"
    driver = """
import json,subprocess,sys
sys.path.insert(0,sys.argv[1])
from swesweep_eval.infra.container_session import ContainerSession
with ContainerSession() as session:
    try:
        session.execute([sys.executable,'-c',
            'import os,time;from pathlib import Path;Path('+repr(sys.argv[2])+').write_text(str(os.getpid()));time.sleep(30)'],
            input='x'*(2<<20),timeout=0.2)
    except subprocess.TimeoutExpired:
        print(json.dumps({'timed_out':True}))
    else:
        raise AssertionError('the child exceeded its budget without a timeout')
"""
    process = subprocess.Popen(
        [sys.executable, "-c", driver, str(shared), str(pid_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=4)
        assert process.returncode == 0, stderr
        assert json.loads(stdout) == {"timed_out": True}
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate()
        if pid_path.exists():
            try:
                os.killpg(int(pid_path.read_text()), signal.SIGKILL)
            except ProcessLookupError:
                pass


def test_stdin_is_delivered_and_closed_for_normal_commands():
    import importlib.util

    path = Path(__file__).resolve().parents[1] / (
        "tasks/swe-sweep__click/tests/shared/swesweep_eval/infra/container_session.py"
    )
    spec = importlib.util.spec_from_file_location("sweep_session_stdin_controls", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    with module.ContainerSession() as session:
        for text in ("", "hello", "h\u00e9llo"):
            result = session.execute(
                [sys.executable, "-c", "import sys;sys.stdout.buffer.write(sys.stdin.buffer.read())"],
                input=text,
                timeout=3,
            )
            assert result.returncode == 0
            assert result.stdout == text
            assert result.stderr == ""
