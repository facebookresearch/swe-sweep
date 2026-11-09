"""Added ``async def test_*`` functions are pytest tests."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _target_tests():
    shared = ROOT / "tasks" / "swe-sweep__agda" / "tests" / "shared"
    sys.path.insert(0, str(shared))
    try:
        from swesweep_eval.eval.suites.utils.pytest import target_tests
    finally:
        sys.path.remove(str(shared))
    return target_tests


def test_added_async_test_is_selected():
    target_tests = _target_tests()
    diff = """\
diff --git a/tests/test_chars.py b/tests/test_chars.py
--- a/tests/test_chars.py
+++ b/tests/test_chars.py
@@ -1,0 +1,2 @@ class C
+    async def test_single_character(self) -> None:
+        assert True
"""
    files, names = target_tests(diff)
    assert files == ["tests/test_chars.py"]
    assert names == ["test_single_character"]


def test_sync_tests_and_hunk_headers_still_count():
    target_tests = _target_tests()
    diff = """\
+++ b/tests/test_sync.py
@@ -4,2 +4,3 @@ async def test_existing(self):
+    def test_added(self):
"""
    files, names = target_tests(diff)
    assert files == ["tests/test_sync.py"]
    assert names == ["test_added", "test_existing"]
