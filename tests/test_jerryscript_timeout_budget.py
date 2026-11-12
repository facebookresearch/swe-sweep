"""JerryScript cases share one timeout instead of each receiving the whole budget."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]


def _suite():
    shared = str(ROOT / "tasks" / "swe-sweep__jerryscript" / "tests" / "shared")
    for key in list(sys.modules):
        if key == "swesweep_eval" or key.startswith("swesweep_eval."):
            del sys.modules[key]
    sys.path.insert(0, shared)
    try:
        from swesweep_eval.eval.suites.concrete import jerry
    finally:
        sys.path.remove(shared)
    return jerry


def test_finished_cases_consume_the_shared_budget(monkeypatch):
    jerry = _suite()
    clock = {"now": 0.0}
    monkeypatch.setattr(jerry.time, "monotonic", lambda: clock["now"])

    class Env:
        def __init__(self):
            self.timeouts = []

        def execute(self, _argv, timeout=None, **_kwargs):
            self.timeouts.append(timeout)
            clock["now"] += 6
            return SimpleNamespace(returncode=0, stdout="")

    env = Env()
    cases = ["tests/jerry/a.js", "tests/jerry/b.js", "tests/jerry/c.js"]
    outcomes, timed_out, _text = jerry.JerrySuite()._run_cases(env, "/repo", cases, 10)

    assert list(outcomes) == cases[:2]
    assert timed_out is True
    assert env.timeouts == [10, 4]


def test_instant_cases_still_each_see_the_full_budget(monkeypatch):
    jerry = _suite()
    monkeypatch.setattr(jerry.time, "monotonic", lambda: 0.0)

    class Env:
        def __init__(self):
            self.timeouts = []

        def execute(self, _argv, timeout=None, **_kwargs):
            self.timeouts.append(timeout)
            return SimpleNamespace(returncode=0, stdout="")

    env = Env()
    cases = ["tests/jerry/a.js", "tests/jerry/b.js"]
    outcomes, timed_out, _text = jerry.JerrySuite()._run_cases(env, "/repo", cases, 10)

    assert list(outcomes) == cases
    assert timed_out is False
    assert env.timeouts == [10, 10]
