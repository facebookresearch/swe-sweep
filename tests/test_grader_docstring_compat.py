from __future__ import annotations

import ast
from pathlib import Path
from types import ModuleType


GRADER = Path(__file__).resolve().parents[1] / "tasks/swe-sweep__click/tests/shared/swesweep_grade.py"


def test_documented_json_escape_is_literal_valid_unicode():
    function = next(
        node
        for node in ast.parse(GRADER.read_bytes()).body
        if isinstance(node, ast.FunctionDef) and node.name == "normalize_test_id"
    )
    text = ast.get_docstring(function)
    assert r"\ud83d" in text
    text.encode("utf-8")


def test_grader_compiles_and_normalization_behavior_is_unchanged():
    module = ModuleType("synthetic_grader_docstring")
    module.__file__ = str(GRADER)
    exec(compile(GRADER.read_bytes(), str(GRADER), "exec"), module.__dict__)
    assert module.normalize_test_id("ordinary \U0001f600") == "ordinary \U0001f600"
    assert module.normalize_test_id(chr(0xD83D)) == "\ufffd" * 3
