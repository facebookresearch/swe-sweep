# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""SWE-sweep `ContainerSession` that runs inside the evaluation container.

Upstream `swesweep_eval.infra.container_session.ContainerSession` drives one docker/podman
container from the host with `docker exec` / `docker cp`. In the Harbor-format tasks the
evaluator itself runs inside the verifier container (`tests/test.sh`), so the "container" is
the local machine: every method keeps upstream's exact command semantics (`sh -c` for
`shell=True`, an argv otherwise, per-command `cwd` / `env`, `errors="replace"` decoding, a
`subprocess.TimeoutExpired` when a command outlives its budget) on top of `subprocess`.

The converter (`pandora_bench.py`) copies this file into each task as
`tests/swesweep_eval/infra/container_session.py`, replacing the upstream module, so the
unmodified upstream `eval/host.py` (`evaluate_in_container`) runs unchanged. It must stay
stdlib-only and importable on a stock Python 3.12 (the standalone interpreter shipped in the
verifier image).
"""

from __future__ import annotations

import os
import select
import shutil
import signal
import stat
import subprocess
import tempfile
import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path


class ContainerSessionError(RuntimeError):
    """The evaluation environment could not be prepared."""


@dataclass(frozen=True)
class CommandResult:
    args: str | Sequence[str]
    returncode: int
    stdout: str
    stderr: str


class ContainerSession:
    """Upstream's session contract executed locally.

    Example (what `swesweep_grade.py` does)::

        with ContainerSession(image="local", runtime="local", sudo=False) as env:
            result = env.execute(["git", "-C", "/repo", "status"], timeout=60)

    `image` / `runtime` / `sudo` are accepted for signature compatibility with upstream's
    `evaluate_in_container()` and ignored. `timeout` bounds the whole session like upstream:
    once it is spent every `execute` raises `subprocess.TimeoutExpired`.
    """

    def __init__(
        self,
        *,
        image: str = "local",
        runtime: str = "local",
        sudo: bool = False,
        environment: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> None:
        del image, runtime, sudo
        self.environment = dict(environment or {})
        self.timeout = timeout
        self.container_id: str | None = None
        self._started_at: float | None = None

    def __enter__(self) -> ContainerSession:
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.cleanup()

    @property
    def remaining_s(self) -> float | None:
        if self.timeout is None or self._started_at is None:
            return None
        return max(0.0, self.timeout - (time.monotonic() - self._started_at))

    def start(self) -> None:
        if self.container_id is not None:
            raise ContainerSessionError("container session already started")
        self.container_id = "local"
        self._started_at = time.monotonic()

    def copy_dir(self, host_dir: str | Path, container_dir: str) -> None:
        """Copy a directory into place, world-readable like upstream's `docker cp` staging."""
        self._require_started()
        _make_world_readable(host_dir)
        try:
            shutil.copytree(host_dir, container_dir, symlinks=True, dirs_exist_ok=True)
        except OSError as exc:
            raise ContainerSessionError(
                f"staging {container_dir} failed: {exc}"
            ) from exc

    def execute(
        self,
        args: str | Sequence[str],
        *,
        cwd: str | None = None,
        env: Mapping[str, str] | None = None,
        timeout: float | None = None,
        input: str | None = None,
        shell: bool = False,
        merge_stderr: bool = False,
    ) -> CommandResult:
        """Execute one command and kill its whole process group if it outlives `timeout`."""
        self._require_started()
        effective_timeout = self._effective_timeout(timeout)
        if shell:
            command: list[str] = ["/bin/sh", "-c", str(args)]
        elif isinstance(args, str):
            command = [args]
        else:
            command = [str(part) for part in args]
        command_env = dict(os.environ)
        command_env.update(self.environment)
        command_env.update(env or {})
        # The command's stdout/stderr are pipes, as under `docker exec`: php's
        # `sapi/cli/tests/std_streams.phpt` (ftell() on std streams) passes on a pipe and
        # fails on a regular file, and upstream's recorded base runs saw pipes. Each pipe is
        # drained to a file by a thread that stops once the command has exited, so a
        # background child that keeps the pipe open (black's blackd tests once the fd limit
        # bites) cannot hold the call past the command's own exit, which is when `docker
        # exec` returns too.
        out_drain = _PipeDrain()
        err_drain = out_drain if merge_stderr else _PipeDrain()
        try:
            proc = subprocess.Popen(
                command,
                cwd=cwd or None,
                env=command_env,
                stdin=subprocess.PIPE if input is not None else subprocess.DEVNULL,
                stdout=out_drain.write_fd,
                stderr=err_drain.write_fd,
                start_new_session=True,
            )
        except OSError as exc:
            out_drain.close()
            if not merge_stderr:
                err_drain.close()
            # `docker exec` reports an unrunnable command (a directory, a missing binary, a
            # file without the x bit) as exit 126 / 127 with a message; a suite reads that
            # as one failed case. Raising here would abort the whole evaluation instead.
            code = 127 if isinstance(exc, FileNotFoundError) else 126
            message = f"{command[0]}: {exc.strerror or exc}\n"
            return CommandResult(
                args=args,
                returncode=code,
                stdout=message if merge_stderr else "",
                stderr="" if merge_stderr else message,
            )
        out_drain.close_writer()
        if not merge_stderr:
            err_drain.close_writer()
        try:
            if proc.stdin is not None:
                try:
                    proc.stdin.write(
                        (input or "").encode("utf-8", errors="surrogateescape")
                    )
                except BrokenPipeError:
                    pass
                proc.stdin.close()
            try:
                proc.wait(timeout=effective_timeout)
            except subprocess.TimeoutExpired as exc:
                _kill_process_group(proc)
                proc.wait()
                stdout, stderr = _read_captures(out_drain, err_drain, merge_stderr)
                raise subprocess.TimeoutExpired(
                    args, effective_timeout or 0, output=stdout, stderr=stderr
                ) from exc
            stdout, stderr = _read_captures(out_drain, err_drain, merge_stderr)
        finally:
            out_drain.close()
            if not merge_stderr:
                err_drain.close()
        return CommandResult(
            args=args, returncode=proc.returncode, stdout=stdout, stderr=stderr
        )

    def exists(self, path: str) -> bool:
        return self.execute(["test", "-e", path]).returncode == 0

    def is_file(self, path: str) -> bool:
        return self.execute(["test", "-f", path]).returncode == 0

    def is_dir(self, path: str) -> bool:
        return self.execute(["test", "-d", path]).returncode == 0

    def is_executable(self, path: str) -> bool:
        return self.execute(["test", "-x", path]).returncode == 0

    def read_text(self, path: str) -> str:
        result = self.execute(["cat", path])
        if result.returncode != 0:
            raise OSError(result.stderr or f"cannot read {path}")
        return result.stdout

    def write_text(self, path: str, content: str) -> None:
        parent = str(Path(path).parent)
        made = self.execute(["mkdir", "-p", parent])
        if made.returncode != 0:
            raise OSError(made.stderr or f"cannot create {parent}")
        result = self.execute(
            ["/bin/sh", "-c", 'cat > "$1"', "swesweep-write", path], input=content
        )
        if result.returncode != 0:
            raise OSError(result.stderr or f"cannot write {path}")

    def remove(self, path: str) -> None:
        result = self.execute(["rm", "-f", path])
        if result.returncode != 0:
            raise OSError(result.stderr or f"cannot remove {path}")

    def rename(self, source: str, destination: str) -> None:
        result = self.execute(["mv", source, destination])
        if result.returncode != 0:
            raise OSError(result.stderr or f"cannot rename {source} to {destination}")

    def find_files(self, root: str) -> list[str]:
        result = self.execute(["find", root, "-type", "f", "-print"])
        if result.returncode != 0:
            return []
        return [line for line in result.stdout.splitlines() if line]

    def cleanup(self) -> None:
        self.container_id = None

    def _effective_timeout(self, requested: float | None) -> float | None:
        remaining = self.remaining_s
        if remaining is not None and remaining <= 0:
            raise subprocess.TimeoutExpired("container evaluation", self.timeout or 0)
        if requested is None:
            return remaining
        return min(requested, remaining) if remaining is not None else requested

    def _require_started(self) -> None:
        if self.container_id is None:
            raise ContainerSessionError("container session is not started")


class _PipeDrain:
    """A pipe whose read end a thread copies into a temp file until told to stop.

    `finish()` waits briefly for EOF (every writer closed) and then stops the pump even if a
    lingering child still holds the write end, so the caller never blocks on a process the
    command left behind.
    """

    def __init__(self) -> None:
        self.read_fd, self.write_fd = os.pipe()
        self._writer_open = True
        self.file = tempfile.TemporaryFile()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._pump, daemon=True)
        self._thread.start()

    def _pump(self) -> None:
        try:
            while not self._stop.is_set():
                ready, _, _ = select.select([self.read_fd], [], [], 0.1)
                if not ready:
                    continue
                chunk = os.read(self.read_fd, 1 << 16)
                if not chunk:
                    return
                self.file.write(chunk)
        except OSError:
            return

    def close_writer(self) -> None:
        """Close the parent's copy of the write end (the child keeps its own)."""
        if self._writer_open:
            os.close(self.write_fd)
            self._writer_open = False

    def finish(self, grace: float = 2.0) -> None:
        """Stop pumping: at EOF, or `grace` seconds after the command exited."""
        self._thread.join(grace)
        self._stop.set()
        self._thread.join(1.0)

    def text(self) -> str:
        self.file.seek(0)
        return self.file.read().decode("utf-8", errors="replace")

    def close(self) -> None:
        self.close_writer()
        self._stop.set()
        self._thread.join(1.0)
        try:
            os.close(self.read_fd)
        except OSError:
            pass
        self.file.close()


def _read_captures(out_drain, err_drain, merge_stderr: bool) -> tuple[str, str]:
    """Decode the captured streams; a test harness is free to print bytes that are not UTF-8,
    and decoding strictly would lose the whole run (upstream's rationale, kept verbatim)."""
    out_drain.finish()
    if not merge_stderr:
        err_drain.finish()
    return out_drain.text(), ("" if merge_stderr else err_drain.text())


def _kill_process_group(proc: subprocess.Popen) -> None:
    """SIGKILL the command and everything it spawned (it runs in its own session)."""
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except OSError:
        proc.kill()


def _make_world_readable(path: str | Path) -> None:
    """`a+rX` over a tree: read for everything, plus traverse for directories."""
    root = Path(path)
    for p in (root, *root.rglob("*")):
        try:
            mode = p.stat().st_mode
            extra = stat.S_IRGRP | stat.S_IROTH
            if stat.S_ISDIR(mode):
                extra |= stat.S_IXGRP | stat.S_IXOTH
            os.chmod(p, stat.S_IMODE(mode) | extra)
        except OSError:  # a symlink to nowhere, or a path we do not own
            continue
