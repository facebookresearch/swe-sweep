"""swc's fixture targets are rebuilt before each run, so each bug's new fixtures are compiled."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tasks" / "swe-sweep__goawk" / "tests" / "shared"))


def _load_suite_module(task: str, name: str):
    path = ROOT / "tasks" / task / "tests" / "shared" / "swesweep_eval" / "eval" / "suites" / "concrete" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"swesweep_eval.eval.suites.concrete.{name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cargo_rebuilds_a_fixture_target_before_running_it(monkeypatch):
    """A fixture target's driver is touched before each run (cargo does not track the globbed corpus); others are not."""
    cargo = _load_suite_module("swe-sweep__swc", "cargo")
    calls = []

    class Result:
        returncode = 0
        stdout = ""

    def fake_run(env, cmd, timeout, cwd):
        calls.append((cmd, cwd))
        return Result()

    monkeypatch.setattr(cargo, "_run", fake_run)
    suite = cargo.CargoSuite(
        fixture_targets=[{"crate": "crates/p", "pattern": "^crates/p/tests/fixture/", "target": "fixture"}]
    )
    suite.run_tests({}, "/repo", [("crates/p", "fixture"), ("crates/p", "other")], [], 60, 1)
    touched = [(cmd, cwd) for cmd, cwd in calls if cmd[0] == "touch"]
    assert touched == [(["touch", "-c", "tests/fixture.rs", "tests/fixture/main.rs"], "/repo/crates/p")]
    bundle = json.loads((ROOT / "tasks" / "swe-sweep__swc" / "tests" / "swesweep_eval.json").read_text())
    assert bundle["reproduction"]["suite"]["fixture_targets"]  # swc declares fixture targets
