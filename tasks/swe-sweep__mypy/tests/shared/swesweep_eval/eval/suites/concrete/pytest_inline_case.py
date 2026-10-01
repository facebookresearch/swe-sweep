"""PytestInlineCaseSuite suite adapter."""

import os
import re

from ..utils.pytest import PLUSFILE_RE, target_tests
from .pytest import PytestSuite

class PytestInlineCaseSuite(PytestSuite):
    """pytest for data files that contain named cases consumed by test drivers.

    Some compiler/analyser suites keep many cases in one text file, with a marker such
    as ``[case testName]`` starting each case.  The data file is not itself collectable
    by pytest; the marker name becomes the parametrised pytest id exposed by one or more
    driver modules.  This suite extracts those ids from added, removed, or context lines
    in the patch, or resolves the enclosing case from an applied hunk's line, and runs
    the drivers narrowed by ``-k``.

    A data-file patch whose hunks cannot be resolved to a case is deliberately not
    widened to the entire driver corpus. Such a run would be both expensive and
    ambiguous about which pre-existing failure belongs to the patch.
    """

    no_targets = "test patch touched no .py test file or named inline corpus case"

    @classmethod
    def from_config(cls, values, *, repo, create_suite):
        del create_suite
        values.setdefault("repo", repo)
        return cls(**values)

    def __init__(self, corpus_re, drivers, case_re=r"^[ +\-]\[case\s+([^\]\s]+)\]", repo=None):
        self.corpus_re = re.compile(corpus_re)
        self.drivers = list(drivers)
        self.case_re = re.compile(case_re, re.M)
        self.repo = repo

    def _cases_at_hunks(self, env, diff):
        """Read the applied data files and find the case enclosing each changed hunk.

        ``targets`` runs after the test patch is applied, so the new-side hunk line is a
        stable pointer into the exact state pytest will collect.  This recovers edits deep
        inside an existing case where the marker is too far above the hunk for git to show
        it as context.
        """
        if not self.repo:
            return []
        path = None
        cases = []
        for line in diff.splitlines():
            if line.startswith("+++ b/"):
                path = line[6:]
                continue
            if path is None or not self.corpus_re.match(path) or not line.startswith("@@ "):
                continue
            m = re.search(r"\+(\d+)(?:,\d+)?", line)
            if m is None:
                continue
            try:
                source = env.read_text(os.path.join(self.repo, path)).splitlines()
            except OSError:
                continue
            index = min(max(int(m.group(1)) - 1, 0), len(source) - 1)
            while index >= 0:
                marker = re.match(r"^\[case\s+([^\]\s]+)\]", source[index])
                if marker:
                    cases.append(marker.group(1))
                    break
                index -= 1
        return cases

    def targets(self, diff, env=None):
        files, names = target_tests(diff)
        has_corpus_file = any(
            path != "/dev/null" and self.corpus_re.match(path)
            for path in PLUSFILE_RE.findall(diff)
        )
        cases = (self.case_re.findall(diff) + self._cases_at_hunks(env, diff)) if has_corpus_file else []
        if cases:
            files.extend(self.drivers)
            names.extend(cases)
        return sorted(set(files)), sorted(set(names))
