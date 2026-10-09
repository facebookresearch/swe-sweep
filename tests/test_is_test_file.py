from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHARED = ROOT / "tasks" / "swe-sweep__symfony" / "tests" / "shared"


def _is_test_file():
    sys.path.insert(0, str(SHARED))
    try:
        from swesweep_eval.eval.suites.utils.evaluation import is_test_file
    finally:
        sys.path.remove(str(SHARED))
    return is_test_file


def test_symfony_capital_tests_dir_is_a_test_dir():
    is_test_file = _is_test_file()
    assert is_test_file("src/Symfony/Component/BrowserKit/Tests/HttpBrowserTest.php")
    assert is_test_file("src/Symfony/Bundle/FrameworkBundle/Tests/Fixtures/config.yml")


def test_symfony_singular_test_dir_stays_library_code():
    is_test_file = _is_test_file()
    assert not is_test_file("src/Symfony/Component/BrowserKit/Test/Constraint/BrowserCookieValueSame.php")
    assert not is_test_file("src/Symfony/Component/BrowserKit/HttpBrowser.php")
