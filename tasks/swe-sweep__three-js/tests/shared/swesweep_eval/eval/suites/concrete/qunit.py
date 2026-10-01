"""QUnitSuite suite adapter."""

import json
from pathlib import Path

from ..base import ReproductionSuite
from ..utils.javascript import _ADD_QUNIT_TEST_RE, _QUNIT_FILE_RE, _QUNIT_REPORT, _run
from ..utils.pytest import PLUSFILE_RE

class QUnitSuite(ReproductionSuite):
    """Node QUnit files, run directly without a browser or aggregate entry point."""

    no_targets = "test patch touched no QUnit unit-test files"

    def __init__(self, all_files=()):
        self.all_files = list(all_files)

    def stage(self, env):
        helper = Path(__file__).parents[1] / "utils" / "qunit_runner.cjs"
        env.write_text("/scripts/qunit_runner.cjs", helper.read_text())

    def targets(self, diff, env=None):
        del env
        files = [f for f in PLUSFILE_RE.findall(diff) if _QUNIT_FILE_RE.match(f)]
        names = []
        for line in diff.splitlines():
            match = _ADD_QUNIT_TEST_RE.match(line)
            if match:
                names.append(match.group(2))
        return sorted(set(files)), sorted(set(names))

    def run_tests(self, env, repo, files, names, timeout, jobs):
        files = self.all_files if files is None else files
        if env.exists(_QUNIT_REPORT):
            env.remove(_QUNIT_REPORT)
        cmd = ["node", "/scripts/qunit_runner.cjs", repo, _QUNIT_REPORT] + files
        rc, timed_out = _run(env, cmd, repo, timeout)
        if timed_out:
            return {}, 0, False, True
        if not env.exists(_QUNIT_REPORT):
            return {}, 0, True, False
        try:
            report = json.loads(env.read_text(_QUNIT_REPORT))
        except ValueError:
            return {}, 0, True, False
        outcomes = report.get("outcomes", {})
        n = len([o for o in outcomes.values() if o != "skipped"])
        return outcomes, n, bool(report.get("collection_error")) or (not outcomes and bool(rc)), False
