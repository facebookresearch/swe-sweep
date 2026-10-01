"""UnionSuite suite adapter."""

from ..base import FullSuite
from ..utils.logging import log

_SEP = "|"


class UnionSuite(FullSuite):
    """Two or more suites over the same repository, as one.

    Some repos test themselves in more than one way and the ways are not
    interchangeable: PROJ has a gtest suite under ``test/unit/`` **and** a corpus of
    declarative ``.gie`` transformation cases, and a fix lands in either one. Grading
    only the larger convention silently drops every subtask whose whole test is in the
    other — a sixth of PROJ's accepted population, and disproportionately the
    wrong-by-N-metres bugs the task exists for.

    Routing is by name. Each member's names are tagged with its index (``0|Suite.Case``,
    ``1|test/gie/unitconvert.gie``) when :meth:`targets` hands them out, and split back
    apart when the drivers hand them in, so a member only ever sees its own. The tag is
    stripped before the member runs, and outcome keys come back untagged — they are the
    ids the report used, and two different frameworks' ids do not collide.

    A member that claims nothing in the patch is not run at all, so the common case (a
    patch touching one convention) costs exactly what the single suite cost.
    """

    no_targets = "test patch touched no test this repo's suites recognise"

    @classmethod
    def from_config(cls, values, *, repo, create_suite):
        members = [create_suite(spec, repo=repo) for spec in values.pop("suites")]
        return cls(suites=members, **values)

    def __init__(self, suites):
        if len(suites) < 2:
            raise ValueError("a union suite needs at least two members")
        self.suites = list(suites)

    def stage(self, env):
        for suite in self.suites:
            suite.stage(env)

    # --- resolving the diff --------------------------------------------------

    def targets(self, diff, env=None):
        files, names = [], []
        for index, suite in enumerate(self.suites):
            member_files, member_names = suite.targets(diff, env=env)
            if not member_names:
                continue
            files += [self._tag(index, str(f)) for f in member_files]
            names += [self._tag(index, n) for n in member_names]
        return files, names

    @staticmethod
    def _tag(index, value):
        return "%d%s%s" % (index, _SEP, value)

    def _split(self, tagged):
        """``{member index: [untagged, ...]}``, keeping each member's order."""
        out = {}
        for value in tagged or []:
            head, _, rest = str(value).partition(_SEP)
            if not head.isdigit() or int(head) >= len(self.suites):
                log("union suite: cannot route %r" % (value,))
                continue
            out.setdefault(int(head), []).append(rest)
        return out

    def _members_for(self, files, names):
        """``[(suite, files, names), ...]`` for the members the selection names."""
        by_files, by_names = self._split(files), self._split(names)
        return [
            (self.suites[i], by_files.get(i, []), by_names[i])
            for i in sorted(by_names)
        ]

    # --- the repro driver's adapter -------------------------------------------

    def run_tests(self, env, repo, files, names, timeout, jobs):
        outcomes, n_run, error, timed_out = {}, 0, False, False
        for suite, member_files, member_names in self._members_for(files, names):
            got, ran, member_error, member_timeout = suite.run_tests(
                env, repo, member_files, member_names, timeout, jobs
            )
            outcomes.update(got or {})
            n_run += ran
            error = error or member_error
            timed_out = timed_out or member_timeout
        return outcomes, n_run, error, timed_out

    # --- the eval driver's adapters -------------------------------------------

    def run_all(self, env, repo, timeout, cap, jobs):
        outcomes, timed_out, captured = {}, False, []
        for suite in self.suites:
            got, member_timeout, capture = suite.run_all(env, repo, timeout, cap, jobs)
            if got is not None:
                outcomes.update(got)
            timed_out = timed_out or member_timeout
            captured.append(capture)
        return outcomes, timed_out, self._merge(captured)

    def run_selected(self, env, repo, files, names, timeout, cap, jobs):
        outcomes, timed_out, captured = {}, False, []
        for suite, member_files, member_names in self._members_for(files, names):
            got, member_timeout, capture = suite.run_selected(
                env, repo, member_files, member_names, timeout, cap, jobs
            )
            if got is not None:
                outcomes.update(got)
            timed_out = timed_out or member_timeout
            captured.append(capture)
        return outcomes, timed_out, self._merge(captured)

    @staticmethod
    def _merge(captured):
        captured = [c for c in captured if c]
        if not captured:
            return {"command": "(no suite ran)", "returncode": None, "text": "", "truncated": False}
        if len(captured) == 1:
            return captured[0]
        return {
            "command": " && ".join(c.get("command", "") for c in captured),
            "returncode": None,
            "text": "\n\n".join(c.get("text", "") for c in captured),
            "truncated": any(c.get("truncated") for c in captured),
        }
