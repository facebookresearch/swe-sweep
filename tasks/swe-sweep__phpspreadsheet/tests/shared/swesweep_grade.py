"""In-container SWE-sweep grader: `tests/test.sh` runs this inside the verifier sandbox.

The task's `tests/shared/` directory carries this script and the upstream evaluator modules its
suites need, adapted from upstream PandoraBench (`shared/swesweep_eval/eval/**`, see `pandora_bench.py`); `tests/`
itself carries the accepted subtasks' hidden
`test.patch` files, the task's runner declarations (`swesweep_eval.json`) and upstream's stored
base results (`base_tests.json.gz`: the visible tests that passed in every pristine base run).
This script drives those upstream primitives through the evaluation SWE-sweep specifies, then
folds the verdict the way upstream `eval/runner.py`'s `_verdict_to_result()` does. The
"container" is the local machine (`swesweep_eval/infra/container_session.py` is the local
session, `swesweep_session.py`):

1. the agent patch is `/logs/artifacts/model.patch`, captured by the task's
   `[[verifier.collect]]` hook and handed to the separate verifier; in a shared-container run
   it is extracted here with upstream's exact command, `git add -A && git diff --cached
   --binary baseline`. A verifier image (`SWESWEEP_VERIFIER_IMAGE` set) that was handed no
   patch is a harness failure, not an empty submission;
2. `run_evaluation` resets the tree, applies the patch (reverting test files it touched),
   rebuilds, runs the visible suite once and counts as a regression every stored base-passing
   test that does not pass now, then applies every subtask's hidden tests one at a time. There
   is no pre-patch visible run: the stored base results stand in for it;
3. the verdict is folded into upstream's `eval.json` / `eval_output.json` schema and the
   the reward file: `reward` = resolved / subtasks, 0 on any visible regression; per-
   subtask pass/fail stays in `eval.json` so the run can be re-scored offline if subtasks
   are later excluded.

Oracle runs take a different path. Upstream validated every gold fix on its own and some overlap,
so the golds cannot be stacked into one patch. `solution/solve.sh` instead leaves a marker file
carrying the fixture's `oracle_digest`. When the patch adds that marker, the pristine
tree's visible run must pass every stored base-passing test (a miss is an evaluation error,
the environment sentinel: it would count against every agent) and each
subtask is graded on its own gold
patch (`tests/oracle/<id>.patch`), the way upstream accepted it.

An evaluator error (setup failure, unmeasurable baseline gate) is not a 0: `reward.json`
carries `grader_failed = 1` (Harbor accepts only numbers in it; harnesses read that marker as a
verifier infrastructure error) and the message goes to `grader_error.txt`. A patch that does not
apply or build is the agent's outcome and scores 0, as upstream.

Stdlib only; runs on the standalone Python 3.12 the verifier image ships at
`/opt/swesweep/python`. Usage inside the container: `python3 /tests/shared/swesweep_grade.py`.
"""

from __future__ import annotations

import argparse
import gzip
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

logger: logging.Logger = logging.getLogger("swesweep_grade")

BUNDLE_FILENAME = "swesweep_eval.json"
SUBTASKS_DIRNAME = "subtasks"
BASE_TESTS_FILENAME = "base_tests.json.gz"
# `tests/shared/`: this script and the upstream evaluator modules, byte-identical in every task.
SHARED_DIRNAME = "shared"
ORACLE_DIRNAME = "oracle"
# Written into the repo by `solution/solve.sh`; its one line is the fixture's `oracle_digest`,
# which an agent cannot know (it sees neither `tests/` nor `solution/`).
ORACLE_MARKER = ".swesweep_oracle"
DEFAULT_TESTS_DIR = "/tests"
DEFAULT_MODEL_PATCH = "/logs/artifacts/model.patch"
DEFAULT_VERIFIER_DIR = "/logs/verifier"
# Set by tests/Dockerfile: this container is the separate verifier, never the agent's.
VERIFIER_IMAGE_ENV = "SWESWEEP_VERIFIER_IMAGE"
# Upstream `eval_patch(build_jobs=4)` default; the fixture may override it.
DEFAULT_BUILD_JOBS = 4
# Upstream `storage/subtask.py`: a subtask whose reproduction could identify only the
# failing target invocation, not the individual test node that ended the process.
PROCESS_LEVEL_FAILURE_NODE = "__process_level_failure__"

_DIFF_GIT_RE = re.compile(r"^diff --git a/(.+?) b/(.+)$")
_PLUSFILE_RE = re.compile(r"^\+\+\+ b/(.+?)(?:\t.*)?$")
_MINUSFILE_RE = re.compile(r"^--- a/(.+?)(?:\t.*)?$")


class FixtureError(ValueError):
    """The task's `tests/` directory is not a valid SWE-sweep evaluation bundle."""


def load_bundle(tests_dir: Path) -> dict[str, Any]:
    """Read and sanity-check `tests/swesweep_eval.json`."""
    path = tests_dir / BUNDLE_FILENAME
    if not path.is_file():
        raise FixtureError(f"missing {path}")
    bundle = json.loads(path.read_text())
    for key in (
        "task",
        "version",
        "container_repo",
        "reproduction",
        "evaluation",
        "subtasks",
    ):
        if key not in bundle:
            raise FixtureError(f"{path} lacks {key!r}")
    for subtask in bundle["subtasks"]:
        patch = tests_dir / SUBTASKS_DIRNAME / subtask["id"] / "test.patch"
        if not patch.is_file() or not patch.read_text(errors="surrogateescape").strip():
            raise FixtureError(
                f"subtask {subtask['id']!r} has no hidden test patch at {patch}"
            )
    if not (tests_dir / BASE_TESTS_FILENAME).is_file():
        raise FixtureError(f"missing {tests_dir / BASE_TESTS_FILENAME}")
    return bundle


def load_base_tests(tests_dir: Path) -> frozenset[str]:
    """The visible tests that passed in every one of upstream's pristine base runs."""
    with gzip.open(tests_dir / BASE_TESTS_FILENAME, "rt") as f:
        return frozenset(json.load(f)["passing"])


# Test ids the task declares unreliable (upstream's `base_test_ignore` plus the reviewed
# environment-dependent ones), loaded per evaluation. Matched by exact id after
# `canonical_test_id`, never by the bare test name: go-git names every gocheck suite `Test`,
# so a name match on three ignored packages swallowed all 23 golds' `.::Test`.
_IGNORED_TESTS: set[str] = set()
_GO_MODULE_ROOT: str | None = None


def load_ignored_tests(tests_dir: Path) -> frozenset[str]:
    """The task's unreliable test ids (`base_tests.json.gz` `ignored`)."""
    with gzip.open(tests_dir / BASE_TESTS_FILENAME, "rt") as f:
        return frozenset(json.load(f).get("ignored", []))


def normalize_test_id(test_id: str) -> str:
    """Spell a test id the way upstream's recorded lists do.

    jest cuts long titles in the middle of a surrogate pair and writes the lone surrogate as a
    JSON escape (webpack's `BinaryMiddleware ... 😀😀\ud83d ... `); upstream stored those ids
    through a UTF-8 round trip that turns the lone surrogate into three replacement characters.
    A valid string is unchanged.
    """
    try:
        test_id.encode("utf-8")
        return test_id
    except UnicodeEncodeError:
        return test_id.encode("utf-8", "surrogatepass").decode("utf-8", "replace")


def go_module_root(test_ids: Iterable[str]) -> str | None:
    """The import-path prefix shared by every `pkg::name` id, when the ids are go packages.

    `github.com/valyala/fasthttp` for fasthttp's `github.com/valyala/fasthttp::TestX` and
    `github.com/valyala/fasthttp/fasthttpproxy::TestY`; None when the packages share no
    leading path segment (the go repo's `time`, `database/sql`) or the ids are not `pkg::name`.
    """
    packages = {i.split("::", 1)[0] for i in test_ids if "::" in i}
    if not packages or any(p.startswith(".") for p in packages):
        return None
    root = min(packages, key=lambda pkg: len(pkg)).split("/")
    for pkg in packages:
        segments = pkg.split("/")
        while root and segments[: len(root)] != root:
            root.pop()
    return "/".join(root) if len(root) > 1 else None


def canonical_test_id(test_id: str) -> str:
    """Spell a package-scoped go id (`.::TestX`, `sub/pkg::TestX`) with its import path.

    The go suite keys a package-scoped run by the package's relative directory, while the
    visible run and the recorded lists carry the full import path; with no module root known
    (`_GO_MODULE_ROOT` is None) the id is returned unchanged.
    """
    if _GO_MODULE_ROOT is None or "::" not in test_id:
        return test_id
    pkg, name = test_id.split("::", 1)
    if pkg == ".":
        return f"{_GO_MODULE_ROOT}::{name}"
    if pkg == _GO_MODULE_ROOT or pkg.startswith(_GO_MODULE_ROOT + "/"):
        return test_id
    return f"{_GO_MODULE_ROOT}/{pkg}::{name}"


def _is_ignored(test_id: str) -> bool:
    return test_id in _IGNORED_TESTS or canonical_test_id(test_id) in _IGNORED_TESTS


def extract_agent_patch(container_repo: str) -> bytes:
    """Upstream `infer/base.py`'s extraction, for a shared-container run with no `model.patch`."""
    subprocess.run(
        ["git", "-C", container_repo, "add", "-A"], check=True, capture_output=True
    )
    result = subprocess.run(
        ["git", "-C", container_repo, "diff", "--cached", "--binary", "baseline"],
        check=True,
        capture_output=True,
    )
    return result.stdout


def decode_patch(data: bytes) -> str:
    """Upstream `infer/storage.py`: lossless enough to round-trip the string-based APIs."""
    return data.decode("utf-8", errors="surrogateescape")


def oracle_requested(agent_patch: str, bundle: dict[str, Any]) -> bool:
    """Whether the patch adds `solve.sh`'s marker, `ORACLE_MARKER` holding the fixture's digest.

    Other files in the patch are ignored: the collect hook's `git add -A` also picks up whatever
    the image's own build left untracked in the tree (cvc5's `.pyc` caches, numpy's generated
    `.c` sources), and the digest alone proves the submission is the oracle.
    """
    digest = bundle.get("oracle_digest")
    if not digest or ORACLE_MARKER not in edited_files(agent_patch):
        return False
    section = agent_patch.split(f"diff --git a/{ORACLE_MARKER} b/{ORACLE_MARKER}", 1)[1]
    section = section.split("\ndiff --git ", 1)[0]
    return f"+{digest}" in section.splitlines()


def run_evaluation(
    bundle: dict[str, Any], tests_dir: Path, agent_patch: bytes | None
) -> dict[str, Any]:
    """Evaluate one submission in one session; `agent_patch=None` is the oracle.

    Returns a verdict shaped like upstream `evaluate_in_container`'s. Both modes share setup,
    one visible-suite run and the stored base comparison; they differ in what the visible run
    sees (the agent's patched tree vs the pristine one) and in how each subtask is graded (the
    hidden tests on top of the agent's tree vs `_grade_on_gold`).
    """
    shared = str(tests_dir / SHARED_DIRNAME)
    if shared not in sys.path:
        sys.path.insert(0, shared)
    from swesweep_eval.eval.repository import (  # pyrefly: ignore[missing-import]
        ContainerRepository,
    )
    from swesweep_eval.eval.runner_config import (  # pyrefly: ignore[missing-import]
        load_eval_config,
    )
    from swesweep_eval.eval.suites.utils.evaluation import (  # pyrefly: ignore[missing-import]
        OutputCapture,
        passed_set,
    )
    from swesweep_eval.infra.container_session import (  # pyrefly: ignore[missing-import]
        ContainerSession,
    )

    oracle = agent_patch is None
    config = load_eval_config(
        bundle["reproduction"], bundle["evaluation"], bundle["container_repo"]
    )
    suite = config.resolved_suite()
    visible_timeout = int(
        os.environ.get("SWESWEEP_VISIBLE_SUITE_TIMEOUT", str(config.visible_timeout))
    )
    capture = OutputCapture(
        int(os.environ.get("SWESWEEP_PYTEST_OUTPUT_LIMIT", "200000")),
        int(os.environ.get("SWESWEEP_PYTEST_OUTPUT_BUDGET", "20000000")),
    )
    jobs = str(int(bundle.get("build_jobs", DEFAULT_BUILD_JOBS)))
    base_pass = load_base_tests(tests_dir)
    _IGNORED_TESTS.clear()
    _IGNORED_TESTS.update(load_ignored_tests(tests_dir))
    global _GO_MODULE_ROOT
    _GO_MODULE_ROOT = go_module_root(base_pass | _IGNORED_TESTS)
    started = time.monotonic()
    out: dict[str, Any] = {
        "visible_ok": True,
        "regressions": [],
        "subtasks": {},
        "detail": {"oracle": oracle, "base_pass": len(base_pass)},
        "timings": {},
        "output": {},
    }
    try:
        with ContainerSession(image="local", runtime="local", sudo=False) as env:
            repo = ContainerRepository(env, config.repo)
            suite.stage(env)
            setup_error = _run_setup(env, config)
            if setup_error:
                return {"error": setup_error, "stderr_tail": "", "rc": None}
            repo.reset()
            if agent_patch is not None and not _apply_agent_patch(
                repo, suite, config, agent_patch, jobs, out
            ):
                out["timings"]["total_s"] = round(time.monotonic() - started, 3)
                return out
            drop_bytecode_caches(env, config.repo)
            phase = time.monotonic()
            post, timed_out, out["output"]["post_suite"] = suite.run_all(
                env, config.repo, visible_timeout, capture, jobs
            )
            out["timings"]["post_suite_s"] = round(time.monotonic() - phase, 3)
            error = _compare_visible(
                post, timed_out, base_pass, oracle, out, passed_set
            )
            if error:
                return {"error": error, "rc": None}
            # The oracle's visible run is on the pristine tree, so a reproduced regression there is
            # the grading environment disagreeing with the reference, not a submission's doing:
            # an evaluation error, reported after the golds are still graded for diagnosis.
            sentinel = (
                _sentinel_error(out["regressions"])
                if oracle and out["regressions"]
                else ""
            )
            snapshot = (
                _snapshot_pristine(
                    env, config.repo, bundle.get("oracle_pristine_paths")
                )
                if oracle
                else None
            )
            phase = time.monotonic()
            for subtask in bundle["subtasks"]:
                sid = subtask["id"]
                if oracle:
                    result, output = _grade_on_gold(
                        env,
                        repo,
                        suite,
                        config,
                        tests_dir,
                        sid,
                        capture,
                        jobs,
                        snapshot,
                        f2p=frozenset(subtask.get("f2p", [])),
                    )
                else:
                    result, output = _run_hidden_tests(
                        env,
                        repo,
                        suite,
                        config,
                        tests_dir,
                        sid,
                        capture,
                        jobs,
                        f2p=frozenset(subtask.get("f2p", [])),
                    )
                out["subtasks"][sid] = result
                if output is not None:
                    out["output"][sid] = output
            out["timings"]["subtasks_total_s"] = round(time.monotonic() - phase, 3)
    except subprocess.TimeoutExpired as exc:
        return {"error": f"evaluation timed out: {exc}", "rc": None}
    except Exception as exc:  # noqa: BLE001 - reported as a grader failure, as upstream does
        return {
            "error": f"evaluation failed: {exc}",
            "stderr_tail": traceback.format_exc().strip(),
            "rc": None,
        }
    out["timings"]["total_s"] = round(time.monotonic() - started, 3)
    if sentinel:
        out["error"] = sentinel
        out["sentinel"] = True
    return out


def _sentinel_error(regressions: list[str]) -> str:
    shown = ", ".join(regressions[:5]) + (" ..." if len(regressions) > 5 else "")
    return (
        f"environment sentinel: the pristine tree fails {len(regressions)} reference test(s) "
        f"(passed in every recorded base run): {shown}"
    )


def _compare_visible(
    post: dict[str, str] | None,
    timed_out: bool,
    base_pass: frozenset[str],
    oracle: bool,
    out: dict[str, Any],
    passed_set: Any,
) -> str:
    """Record the visible run against the stored base; returns a grader error or "".

    A regression is a stored base-passing test that does not pass now (missing counts). An
    unmeasurable run is the agent's outcome (not visible_ok), except on the pristine oracle tree,
    where it is an evaluator failure.
    """
    if timed_out or post is None:
        failure = "timed out" if timed_out else "produced no report"
        if oracle:
            return f"pristine visible suite {failure}"
        out["visible_ok"] = False
        out["detail"]["visible"] = f"post-agent suite {failure}"
        return ""
    post = {normalize_test_id(k): v for k, v in post.items()}
    passed = passed_set(post)
    regressions = sorted(base_pass - passed)
    out["visible_ok"] = not regressions
    out["regressions"] = regressions
    # Every visible test's outcome, not just the regressions: re-scoring after a test or a
    # subtask is excluded later needs the full pass/fail map of the post-patch run.
    out["visible_tests"] = dict(post)
    out["detail"].update(post_pass=len(passed), n_regressions=len(regressions))
    if oracle and regressions:
        out["detail"]["visible"] = (
            f"environment drift: the pristine tree fails {len(regressions)} test(s) that "
            "passed in every upstream base run"
        )
    return ""


def drop_bytecode_caches(env: Any, repo: str) -> None:
    """Delete `__pycache__` under the repo so stale bytecode cannot shadow a patch.

    CPython trusts a `.pyc` whose recorded source mtime (whole seconds) and size match the file.
    A gold that leaves a module at the same byte size, applied within the second of the reset
    that rewrote it, keeps both equal, and the targeted run executes the pristine code:
    sqlglot's `Table.name` gold failed 4 of 4 runs that way in
    `drydock-pandora-oracle-perbug-full100-v5` and passed with the cache dropped. Upstream grades
    one patch per container and never meets a cache left by a previous gold.
    """
    env.execute(
        [
            "find",
            repo,
            "-name",
            "__pycache__",
            "-type",
            "d",
            "-prune",
            "-exec",
            "rm",
            "-rf",
            "{}",
            "+",
        ],
        merge_stderr=True,
    )


def _snapshot_pristine(env: Any, repo: str, paths: list[str] | None) -> str | None:
    """Archive the build outputs a self-hosting build overwrites, before any gold is built.

    nim's and v's rebuilds compile the compiler with the compiler binary the last build left in
    the (gitignored) tree, so without a restore every gold after the first is built by the
    previous gold's compiler. Upstream grades one patch per container and never sees this.
    """
    if not paths:
        return None
    archive = "/tmp/swesweep_oracle_pristine.tar"
    result = env.execute(["tar", "-C", repo, "-cf", archive, *paths], merge_stderr=True)
    if result.returncode != 0:
        raise RuntimeError(f"cannot snapshot {paths}: {result.stdout[-300:]}")
    return archive


def _run_setup(env: Any, config: Any) -> str:
    """Upstream `eval/host.py::_setup`: the task's once-per-session command; "" or the failure."""
    if not config.setup_cmd:
        return ""
    result = env.execute(
        config.setup_cmd,
        cwd=config.repo,
        timeout=config.setup_timeout,
        shell=True,
        merge_stderr=True,
    )
    if result.returncode == 0:
        return ""
    return (
        f"setup command failed (rc={result.returncode}): {(result.stdout or '')[-500:]}"
    )


_HEADER_RE = re.compile(r"\.(h|hh|hpp|hxx)$")
_CSOURCE_RE = re.compile(r"\.(c|cc|cpp|cxx)$")
_SOURCE_RE = re.compile(r"\.(c|cc|cpp|cxx|h|hh|hpp|hxx)$")


def added_files(diff_text: str) -> list[str]:
    """The repo-relative paths a unified diff creates (`new file mode` entries)."""
    added: list[str] = []
    current = None
    for line in (diff_text or "").splitlines():
        m = _DIFF_GIT_RE.match(line)
        if m:
            current = m.group(2)
        elif line.startswith("new file mode") and current:
            added.append(current)
            current = None
    return sorted(set(added))


_REGLOB_PENDING: set[str] = set()


def prepare_incremental_build(repo: Any, suite: Any, diffs: list[str]) -> None:
    """Make an incremental rebuild see what the applied patches changed.

    The tree is built once in the image and rebuilt in place after each patch, and the build
    systems' change detection misses three things a fresh build would not:
    * mtimes: distutils/setuptools compare seconds, so a source patched within the second the
      previous build wrote its object files is "not newer" and never recompiled (numpy's golds
      passed or failed depending on timing). Every file a patch edits, and the C/C++ sources
      beside every header it edits (setuptools tracks only the listed sources, matplotlib's
      `src/*.h` golds), get an mtime two seconds in the future.
    * CMake trees that glob their sources at configure time (opencv's test modules) do not
      compile a file a patch adds until configure runs again: `cmake <build dir>`, and remember
      to run it again once that file is gone (`refresh_build_graph`).
    Both are no-ops for patches that do neither.
    """
    root = Path(repo.path)
    future = time.time() + 2
    touched: set[Path] = set()
    for diff in diffs:
        for f in edited_files(diff):
            touched.add(root / f)
            if _HEADER_RE.search(f):
                parent = root / Path(f).parent
                if parent.is_dir():
                    touched.update(
                        p
                        for p in parent.iterdir()
                        if p.is_file() and _CSOURCE_RE.search(p.name)
                    )
    for path in touched:
        try:
            os.utime(path, (future, future))
        except OSError:
            pass
    build_dir = getattr(suite, "build_dir", None)
    if build_dir and any(_SOURCE_RE.search(f) for d in diffs for f in added_files(d)):
        _reconfigure(repo, str(build_dir))
        _REGLOB_PENDING.add(str(build_dir))


def refresh_build_graph(repo: Any, suite: Any) -> None:
    """After a reset: re-run configure if a previous patch made CMake glob a file now gone."""
    build_dir = getattr(suite, "build_dir", None)
    if build_dir and str(build_dir) in _REGLOB_PENDING:
        _reconfigure(repo, str(build_dir))
        _REGLOB_PENDING.discard(str(build_dir))


def _reconfigure(repo: Any, build_dir: str) -> None:
    result = repo.env.execute(["cmake", build_dir], merge_stderr=True)
    if result.returncode != 0:
        raise RuntimeError(f"cmake reconfigure failed: {result.stdout[-300:]}")


def _apply_agent_patch(
    repo: Any,
    suite: Any,
    config: Any,
    agent_patch: bytes,
    jobs: str,
    out: dict[str, Any],
) -> bool:
    """Apply the patch, revert the test files it touched and build; False = stop (build failed).

    Upstream semantics: a patch that does not apply is recorded and grading continues on the
    unpatched tree (its hidden tests then fail); a failed build ends the evaluation at score 0.
    """
    from swesweep_eval.eval.suites.utils.evaluation import (  # pyrefly: ignore[missing-import]
        is_test_file,
        touched_files,
    )

    phase = time.monotonic()
    applied = True
    agent_diff = decode_patch(agent_patch)
    if agent_diff.strip():
        with tempfile.NamedTemporaryFile(suffix=".patch") as f:
            f.write(agent_patch)
            f.flush()
            applied, error = repo.apply_patch(f.name)
        if applied:
            repo.restore_files(
                [
                    p
                    for p in touched_files(agent_diff)
                    if is_test_file(p, config.test_dirs)
                ]
            )
        else:
            out["detail"]["agent_patch_error"] = error.strip()[:300]
    out["detail"]["agent_patch_applied"] = applied
    out["timings"]["agent_apply_s"] = round(time.monotonic() - phase, 3)
    if not config.needs_build:
        return True
    if applied:
        prepare_incremental_build(repo, suite, [agent_diff])
    phase = time.monotonic()
    built, build_error, build_output = _build(repo, config, jobs)
    out["timings"]["build_s"] = round(time.monotonic() - phase, 3)
    out["output"]["build"] = {"returncode": 0 if built else 1, "text": build_output}
    if not built:
        out["visible_ok"] = False
        out["detail"]["agent_build_ok"] = False
        out["detail"]["build_error"] = build_error
    return built


def _build(repo: Any, config: Any, jobs: str) -> tuple[bool, str, str]:
    """Upstream `ContainerRepository.build` with the whole console output kept.

    Same command (`_build_argv`), cwd, environment and timeout; upstream returns only the last
    800 bytes of stderr, which for a cmake/ninja or numpy.distutils build is often empty while
    the failing compile line is on stdout. Returns `(built, error_tail, output)`.
    """
    from swesweep_eval.eval.repository import (
        _build_argv,  # pyrefly: ignore[missing-import]
    )

    command_env = {
        name: jobs
        for name in (
            config.build_jobs_env or ((config.jobs_env,) if config.jobs_env else ())
        )
    }
    command_env["SWESWEEP_BUILD_JOBS"] = jobs
    try:
        result = repo.env.execute(
            _build_argv(config.build_cmd, config.build_jobs_flag, jobs),
            cwd=repo.path,
            env=command_env,
            timeout=config.build_timeout,
            merge_stderr=True,
        )
    except subprocess.TimeoutExpired:
        message = f"build timed out after {config.build_timeout}s"
        return False, message, message
    output = result.stdout or ""
    return result.returncode == 0, output[-1500:], output[-200000:]


def _new_subtask_result() -> dict[str, Any]:
    return {
        "resolved": False,
        "test_applied": False,
        "targeted": [],
        "n_passed": 0,
        "n_failed": 0,
        "passed": [],
        "failed": [],
        "detail": {},
    }


def _run_hidden_tests(
    env: Any,
    repo: Any,
    suite: Any,
    config: Any,
    tests_dir: Path,
    sid: str,
    capture: Any,
    jobs: str,
    f2p: frozenset[str] = frozenset(),
) -> tuple[dict[str, Any], Any]:
    """Apply one subtask's hidden tests on the agent's tree, run its targets, revert the tests.

    Upstream `evaluate_in_container`'s per-subtask block; returns the subtask entry and the
    targeted run's captured output.
    """
    from swesweep_eval.eval.suites.utils.evaluation import (  # pyrefly: ignore[missing-import]
        touched_files,
    )

    started = time.monotonic()
    result = _new_subtask_result()
    output = None
    test_patch = tests_dir / SUBTASKS_DIRNAME / sid / "test.patch"
    test_diff = test_patch.read_text(errors="surrogateescape")
    files, names = suite.targets(test_diff, env=env)
    result["targeted"] = names
    applied, apply_error = repo.apply_patch(str(test_patch))
    result["test_applied"] = applied
    if not applied:
        result["detail"]["error"] = (
            "hidden test patch did not apply: " + apply_error.strip()[:200]
        )
    elif not files:
        result["detail"]["error"] = suite.no_targets
    else:
        drop_bytecode_caches(env, config.repo)
        if config.needs_build:
            prepare_incremental_build(repo, suite, [test_diff])
        output = _run_targets(
            env, suite, config, files, names, capture, jobs, result, f2p=f2p
        )
    repo.restore_files(touched_files(test_diff))
    if config.needs_build:
        refresh_build_graph(repo, suite)
    result["duration_s"] = round(time.monotonic() - started, 3)
    return result, output


def _run_targets(
    env: Any,
    suite: Any,
    config: Any,
    files: Any,
    names: list[str],
    capture: Any,
    jobs: str,
    result: dict[str, Any],
    f2p: frozenset[str] = frozenset(),
) -> Any:
    """Run a subtask's targeted tests once and fold the outcomes into `result`; returns the output."""
    from swesweep_eval.eval.suites.utils.evaluation import (  # pyrefly: ignore[missing-import]
        passed_set,
    )

    test_timeout = int(os.environ.get("SWESWEEP_TEST_TIMEOUT", str(config.test_timeout)))
    outcomes, timed_out, output = suite.run_selected(
        env, config.repo, files, names, test_timeout, capture, jobs
    )
    if timed_out or outcomes is None:
        failure = "timed out" if timed_out else "produced no report"
        result["detail"]["error"] = f"targeted tests {failure}"
        return output
    # A targeted run that covers a whole package (go's `-count=1 .`) also reports the tests
    # the task declares unreliable; they cannot fail a subtask any more than the visible run.
    # A subtask's own F2P tests are exempt: quarkus's upstream ignore list names two of them.
    f2p_canonical = {canonical_test_id(x) for x in f2p}
    outcomes = {
        normalize_test_id(k): v
        for k, v in outcomes.items()
        if canonical_test_id(k) in f2p_canonical or not _is_ignored(k)
    }
    failed = {k for k, v in outcomes.items() if v in ("failed", "error")}
    passed = passed_set(outcomes)
    result.update(
        n_passed=len(passed),
        n_failed=len(failed),
        passed=sorted(passed),
        failed=sorted(failed),
        resolved=not failed and bool(passed),
    )
    return output


def _grade_on_gold(
    env: Any,
    repo: Any,
    suite: Any,
    config: Any,
    tests_dir: Path,
    sid: str,
    capture: Any,
    jobs: str,
    snapshot: str | None = None,
    f2p: frozenset[str] = frozenset(),
) -> tuple[dict[str, Any], Any]:
    """Grade one subtask on its own gold, in the order upstream accepted it.

    Upstream `reproduce_in_container`'s post-gold half on the evaluation config: reset (and
    restore `snapshot`), apply the hidden tests, apply the gold, build, run the targets. The
    tests go in before the build because some builds compile them (z3's `test-z3` target), and
    a gold that changes an API those tests use only builds together with its updated tests.
    `reset` keeps ignored build outputs, so successive per-gold builds are incremental.
    """
    started = time.monotonic()
    result = _new_subtask_result()
    output = None
    repo.reset()
    refresh_build_graph(repo, suite)
    if snapshot is not None:
        restored = env.execute(
            ["tar", "-C", config.repo, "-xf", snapshot], merge_stderr=True
        )
        if restored.returncode != 0:
            raise RuntimeError(f"cannot restore {snapshot}: {restored.stdout[-300:]}")
    test_patch = tests_dir / SUBTASKS_DIRNAME / sid / "test.patch"
    files, names = suite.targets(
        test_patch.read_text(errors="surrogateescape"), env=env
    )
    result["targeted"] = names
    gold = tests_dir / ORACLE_DIRNAME / f"{sid}.patch"
    error = ""
    applied, apply_error = repo.apply_patch(str(test_patch))
    result["test_applied"] = applied
    if not applied:
        error = "hidden test patch did not apply: " + apply_error.strip()[:200]
    elif not gold.is_file():
        error = f"no gold patch at {gold}"
    else:
        applied, apply_error = repo.apply_patch(str(gold))
        if not applied:
            error = (
                "gold patch did not apply onto the tested tree: "
                + apply_error.strip()[:200]
            )
    if not error:
        drop_bytecode_caches(env, config.repo)
    if not error and config.needs_build:
        prepare_incremental_build(
            repo,
            suite,
            [
                test_patch.read_text(errors="surrogateescape"),
                gold.read_text(errors="surrogateescape"),
            ],
        )
        built, build_error, build_output = _build(repo, config, jobs)
        result["detail"]["build_output"] = build_output[-20000:]
        if not built:
            error = "build failed after gold patch: " + build_error[-1500:]
    if not error and not files:
        error = suite.no_targets
    if error:
        result["detail"]["error"] = error
    else:
        output = _run_targets(
            env, suite, config, files, names, capture, jobs, result, f2p=f2p
        )
    result["duration_s"] = round(time.monotonic() - started, 3)
    return result, output


# --- upstream `eval/runner.py` verdict folding, on plain dicts ---------------------------------


def edited_files(diff_text: str) -> list[str]:
    """Upstream `utils/patching.edited_files`: the repo-relative paths a unified diff touches."""
    files: set[str] = set()
    for line in (diff_text or "").splitlines():
        m = _DIFF_GIT_RE.match(line)
        if m:
            files.add(m.group(2))
            continue
        m = _PLUSFILE_RE.match(line)
        if m and m.group(1) != "/dev/null":
            files.add(m.group(1))
            continue
        m = _MINUSFILE_RE.match(line)
        if m and m.group(1) != "/dev/null":
            files.add(m.group(1))
    return sorted(files)


def count_changed_lines(diff_text: str) -> tuple[int, int]:
    """Upstream `utils/patching.count_changed_lines`: `(added, removed)` content lines."""
    added = removed = 0
    for line in (diff_text or "").splitlines():
        if line.startswith("+++ ") or line.startswith("--- "):
            continue
        if line.startswith("+"):
            added += 1
        elif line.startswith("-"):
            removed += 1
    return added, removed


def patch_stats(diff_text: str, target_files: list[str]) -> dict[str, Any]:
    """Upstream `PatchStats` for an agent patch, judged against the subtasks' gold source files."""
    edited = edited_files(diff_text)
    added, removed = count_changed_lines(diff_text)
    target = sorted(set(target_files))
    tset, eset = set(target), set(edited)
    on = sorted(eset & tset)
    return {
        "files_edited": edited,
        "lines_added": added,
        "lines_removed": removed,
        "target_files": target,
        "on_target_files": on,
        "off_target_files": sorted(eset - tset),
        "target_coverage_pct": round(len(on) / len(target) * 100.0, 1)
        if target
        else 0.0,
    }


def _format_error(verdict: dict[str, Any]) -> str | None:
    error = verdict.get("error")
    if not error:
        return None
    rc, tail = verdict.get("rc"), (verdict.get("stderr_tail") or "").strip()
    extra = [f"rc={rc}"] if rc is not None else []
    if tail:
        extra.append(f"stderr: {tail}")
    return f"{error} ({'; '.join(extra)})" if extra else error


def _split_targeted(v: dict[str, Any], f2p: set[str]) -> dict[str, Any]:
    raw_pass, raw_fail = v.get("passed"), v.get("failed")
    passed, failed = sorted(raw_pass or []), sorted(raw_fail or [])
    if PROCESS_LEVEL_FAILURE_NODE in f2p:
        # Reproduction could identify only the failing target invocation; every concrete
        # outcome from that same selected scope counts as F2P during evaluation.
        f2p = set(passed) | set(failed)
    return {
        "has_split": raw_pass is not None or raw_fail is not None,
        "f2p_passed": [n for n in passed if n in f2p],
        "p2p_passed": [n for n in passed if n not in f2p],
        "f2p_failed": [n for n in failed if n in f2p],
        "p2p_failed": [n for n in failed if n not in f2p],
    }


def _subtask_result(subtask: dict[str, Any], v: dict[str, Any]) -> dict[str, Any]:
    resolved = bool(v.get("resolved", False))
    split = _split_targeted(v, set(subtask.get("f2p", [])))
    return {
        "subtask_id": subtask["id"],
        "resolved": resolved,
        "partial": not resolved
        and not split["p2p_failed"]
        and bool(split["f2p_passed"]),
        "test_applied": bool(v.get("test_applied", False)),
        "targeted": list(v.get("targeted", []) or []),
        "n_passed": int(v.get("n_passed", 0) or 0),
        "n_failed": int(v.get("n_failed", 0) or 0),
        "duration_s": float(v.get("duration_s", 0.0) or 0.0),
        "detail": dict(v.get("detail", {}) or {}),
        **split,
    }


def _verdict_output(verdict: dict[str, Any]) -> dict[str, Any] | None:
    """Upstream `EvalOutput`: the captured console output of every test invocation."""
    raw = verdict.get("output") or {}
    if not isinstance(raw, dict) or not raw:
        return None
    out: dict[str, Any] = {"baseline_suite": None, "post_suite": None, "subtasks": {}}
    for key, value in raw.items():
        if not isinstance(value, dict):
            continue
        entry = {
            "command": str(value.get("command", "")),
            "returncode": value.get("returncode"),
            "text": str(value.get("text", "")),
            "truncated": bool(value.get("truncated", False)),
        }
        if key in ("baseline_suite", "post_suite"):
            out[key] = entry
        else:
            out["subtasks"][key] = entry
    if (
        out["baseline_suite"] is None
        and out["post_suite"] is None
        and not out["subtasks"]
    ):
        return None
    return out


def verdict_to_result(
    verdict: dict[str, Any],
    subtasks: list[dict[str, Any]],
    version: str,
    agent_patch: str,
) -> dict[str, Any]:
    """Fold the evaluator's verdict into upstream's `EvalResult` shape and compute the score.

    Mirrors upstream `eval/runner.py::_verdict_to_result`; `subtasks` are the fixture records
    (`id`, `f2p`, `target_files`). The `output` key holds the `eval_output.json` sidecar.
    """
    error = _format_error(verdict)
    detail = verdict.get("detail", {}) or {}
    agent_build_ok = bool(detail.get("agent_build_ok", True))
    per = verdict.get("subtasks", {}) or {}
    sub_results: list[dict[str, Any]] = []
    target_files: set[str] = set()
    for subtask in subtasks:
        target_files.update(subtask.get("target_files", []))
    if (not error or verdict.get("sentinel")) and agent_build_ok:
        for subtask in subtasks:
            if subtask["id"] not in per:
                raise RuntimeError(
                    f"eval verdict is missing subtask {subtask['id']!r}; the evaluator must "
                    "report every staged subtask"
                )
            sub_results.append(_subtask_result(subtask, per[subtask["id"]]))
    n_subtasks = len(sub_results)
    n_resolved = sum(1 for s in sub_results if s["resolved"])
    visible_ok = False if error else bool(verdict.get("visible_ok", True))
    score = 0.0 if (not visible_ok or n_subtasks == 0) else n_resolved / n_subtasks
    return {
        "evaluated_at": datetime.now().strftime("%Y%m%dT%H%M%S"),
        "version": version,
        "score": round(score, 4),
        "visible_ok": visible_ok,
        "agent_patch_applied": bool(detail.get("agent_patch_applied", True)),
        "agent_build_ok": agent_build_ok,
        "agent_patch_error": detail.get("agent_patch_error") or None,
        "build_error": detail.get("build_error") or None,
        "regressions": list(verdict.get("regressions", []) or []),
        "visible_tests": dict(verdict.get("visible_tests", {}) or {}),
        "n_subtasks": n_subtasks,
        "n_resolved": n_resolved,
        "n_partial": sum(1 for s in sub_results if s["partial"]),
        "subtasks": sub_results,
        "patch_stats": patch_stats(agent_patch, sorted(target_files)),
        "timings": dict(verdict.get("timings", {}) or {}),
        "error": error,
        "output": _verdict_output(verdict),
    }


def rewards_from_result(result: dict[str, Any]) -> dict[str, float]:
    """Project the result onto the numeric reward dict (`reward` is the headline)."""
    return {
        "reward": float(result["score"]),
        "n_subtasks": float(result["n_subtasks"]),
        "n_resolved": float(result["n_resolved"]),
        "n_partial": float(result["n_partial"]),
        "visible_ok": 1.0 if result["visible_ok"] else 0.0,
        "n_regressions": float(len(result["regressions"])),
        "agent_patch_applied": 1.0 if result["agent_patch_applied"] else 0.0,
        "agent_build_ok": 1.0 if result["agent_build_ok"] else 0.0,
    }


def write_result(verifier_dir: Path, result: dict[str, Any]) -> None:
    """Write `eval.json` (verdict), `eval_output.json` (console output) and `reward.json`."""
    verifier_dir.mkdir(parents=True, exist_ok=True)
    output = result.get("output")
    verdict = {k: v for k, v in result.items() if k != "output"}
    (verifier_dir / "eval.json").write_text(json.dumps(verdict, indent=2) + "\n")
    if output is not None:
        (verifier_dir / "eval_output.json").write_text(
            json.dumps(output, indent=2) + "\n"
        )
    payload: dict[str, Any] = rewards_from_result(result)
    payload["grader_failed"] = 1.0 if result.get("error") else 0.0
    if result.get("error"):
        (verifier_dir / "grader_error.txt").write_text(str(result["error"]) + "\n")
    (verifier_dir / "reward.json").write_text(json.dumps(payload, indent=2) + "\n")


def write_failure(verifier_dir: Path, message: str) -> None:
    """Fail closed: reward 0 with the grader-infrastructure marker (numeric, for Harbor)."""
    verifier_dir.mkdir(parents=True, exist_ok=True)
    (verifier_dir / "grader_error.txt").write_text(message + "\n")
    (verifier_dir / "reward.json").write_text(
        json.dumps({"reward": 0.0, "grader_failed": 1.0}, indent=2) + "\n"
    )


def grade(tests_dir: Path, model_patch: Path, verifier_dir: Path) -> dict[str, Any]:
    """Grade one attempt end to end and write the outputs; returns the result."""
    if not model_patch.is_file() and os.environ.get(VERIFIER_IMAGE_ENV):
        raise RuntimeError(
            f"{model_patch} is missing in the verifier image: the harness did not hand over the "
            "agent's patch (the task's `artifacts` + `[[verifier.collect]]` hook need a harness "
            "that supports them); nothing to grade"
        )
    bundle = load_bundle(tests_dir)
    subtasks: list[dict[str, Any]] = bundle["subtasks"]
    if model_patch.is_file():
        agent_patch = model_patch.read_bytes()
        logger.info("agent patch: %s (%d bytes)", model_patch, len(agent_patch))
    else:
        agent_patch = extract_agent_patch(bundle["container_repo"])
        logger.info(
            "agent patch: extracted from %s (%d bytes)",
            bundle["container_repo"],
            len(agent_patch),
        )
    oracle = oracle_requested(decode_patch(agent_patch), bundle)
    logger.info(
        "SWE-sweep eval: task=%s version=%s subtasks=%d%s",
        bundle["task"],
        bundle["version"],
        len(subtasks),
        " (oracle: each subtask on its own gold patch)" if oracle else "",
    )
    verdict = run_evaluation(bundle, tests_dir, None if oracle else agent_patch)
    result = verdict_to_result(
        verdict, subtasks, bundle["version"], decode_patch(agent_patch)
    )
    result["oracle"] = oracle
    write_result(verifier_dir, result)
    logger.info(
        "SWE-sweep eval: score=%.4f resolved=%d/%d partial=%d visible_ok=%s patch_applied=%s "
        "build_ok=%s%s",
        result["score"],
        result["n_resolved"],
        result["n_subtasks"],
        result["n_partial"],
        result["visible_ok"],
        result["agent_patch_applied"],
        result["agent_build_ok"],
        f" ERROR: {result['error']}" if result["error"] else "",
    )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--tests-dir", default=os.environ.get("SWESWEEP_TESTS_DIR", DEFAULT_TESTS_DIR)
    )
    parser.add_argument(
        "--model-patch",
        default=os.environ.get("SWESWEEP_MODEL_PATCH", DEFAULT_MODEL_PATCH),
    )
    parser.add_argument(
        "--verifier-dir",
        default=os.environ.get("SWESWEEP_VERIFIER_DIR", DEFAULT_VERIFIER_DIR),
    )
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stderr,
    )
    verifier_dir = Path(args.verifier_dir)
    try:
        result = grade(Path(args.tests_dir), Path(args.model_patch), verifier_dir)
    except Exception as exc:  # noqa: BLE001 - anything here is a grading-infrastructure failure
        logger.exception("SWE-sweep grader failed")
        write_failure(verifier_dir, f"{type(exc).__name__}: {exc}")
        return 1
    return 1 if result.get("error") else 0


if __name__ == "__main__":
    sys.exit(main())
