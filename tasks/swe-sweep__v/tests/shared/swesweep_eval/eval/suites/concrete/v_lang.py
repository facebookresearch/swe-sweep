"""VSuite suite adapter."""

import os
import posixpath
import subprocess

from ..base import FullSuite
from ..utils.compiled import _patched_files
from ..utils.logging import log


class VSuite(FullSuite):
    """V's two test conventions, run through V's own test runner.

    V grades itself in two ways and a bug fix uses either, so an adapter that knows only
    one leaves half the population unmeasurable.

    **``*_test.v`` — the ordinary convention.** Every ``test_*`` function in the file is
    run by V's built-in runner and the process exits non-zero if any assertion fails. The
    file is the unit: V has no machine-readable per-case report, and parsing the
    ``-stats`` console table would tie the suite to one release's formatting.

    **Golden data directories — the compiler-diagnostic convention.** A case is a ``.vv``
    program beside a file holding the exact expected output of compiling or running it
    (``vlib/v/checker/tests``), or a template beside its expected formatting
    (``vlib/v/fmt/tests``), or a program beside the C it must generate
    (``vlib/v/gen/c/testdata``). None of those is a test file; each directory is driven by
    a *test runner* — an ordinary ``_test.v`` whose single test function walks the whole
    directory.

    Running that runner unfiltered would make every golden subtask depend on all several
    hundred of its sibling cases passing. **V's own answer is ``VTEST_ONLY``**: the
    runners select their corpus through ``v.util.vtest.filter_vtest_only``, which keeps
    only the paths containing one of the comma-separated patterns in that variable. So a
    golden case is run by pointing its runner at it — the selection, the compiler options
    per subdirectory, and the output normalisation all stay upstream's, where they belong,
    instead of being re-implemented here and drifting.

    Which runner drives which directory is a per-repo fact and lives in
    ``tasks/v/task.yaml`` as ``golden_dirs`` — a list of
    ``{dir, runner, filters}`` matched longest-``dir``-first so a nested corpus is not
    claimed by its parent. ``runner`` may name several, because a directory can be shared:
    ``vlib/v/fmt/tests`` holds both the ``_input``/``_expected`` pairs of ``fmt_test.v``
    and the idempotency cases of ``fmt_keep_test.v``.

    ``filters: false`` says this runner does *not* consult ``VTEST_ONLY`` — several of
    them glob their corpus directly — so the variable is left unset and the runner runs
    whole. It is per directory rather than assumed, because getting it wrong is silent:
    the variable would simply be ignored.

    **A vacuous pass is reported as an error, not a pass.** If ``VTEST_ONLY`` matches
    nothing the runner iterates an empty corpus and exits 0, which post-gold would look
    exactly like a fixed bug. Where the runner does filter, the case's own name therefore
    has to appear in its output for the run to count.

    A test file that fails to *compile* is a failing test, not a harness error: for a
    compiler repository that is the commonest pre-gold state there is (the checker rejects
    a program it should accept), and calling it an error would throw those subtasks away.
    """

    no_targets = "test patch touched no V test file or golden case"

    def __init__(self, vexe="./v", golden_dirs=(), vflags=(), eval_roots=("vlib",)):
        self.vexe = vexe
        self.vflags = list(vflags)
        self.eval_roots = list(eval_roots)
        self.golden_dirs = sorted(
            (
                {
                    "dir": entry["dir"].strip("/"),
                    "runners": (
                        [entry["runner"]] if isinstance(entry["runner"], str) else list(entry["runner"])
                    ),
                    "filters": bool(entry.get("filters", True)),
                }
                for entry in golden_dirs
            ),
            key=lambda entry: len(entry["dir"]),
            reverse=True,
        )

    # --- resolving the diff --------------------------------------------------

    def _golden_entry(self, path):
        for entry in self.golden_dirs:
            if path.startswith(entry["dir"] + "/"):
                return entry
        return None

    def targets(self, diff, env=None):
        """``([target, ...], [])`` where a target is ``("test", path, None)`` — a whole
        test file — or ``("golden", runner, case)`` — one corpus case and the runner that
        drives it (``case`` is None for a runner that does not filter).

        A golden case is named by whichever half of the pair the patch touched: adding the
        expectation and adding the program are both complete descriptions of the case, and
        both reduce to the same stem. ``names`` stays empty: neither convention has a
        per-function selector to pass down.
        """
        del env
        found = []
        for path in _patched_files(diff):
            if path.endswith("_test.v"):
                new = [("test", path, None)]
            else:
                entry = self._golden_entry(path)
                if entry is None:
                    continue
                # `VTEST_ONLY` is a substring match against the case path, so the stem
                # (no extension) selects the case whichever half of the pair moved.
                case = posixpath.splitext(path)[0] if entry["filters"] else None
                new = [("golden", runner, case) for runner in entry["runners"]]
            for target in new:
                if target not in found:
                    found.append(target)
        # Sorted on the rendered tuple: a target's third slot is a case name or None, and
        # the two do not order against each other.
        return sorted(found, key=lambda target: tuple(str(part) for part in target)), []

    # --- running -------------------------------------------------------------

    def _env(self, repo, only=None):
        """V finds its own installation through ``VEXE`` — the golden runners read it to
        locate vroot — and the recorded expectations are colourless."""
        environment = {
            "VCOLORS": "never",
            "VEXE": posixpath.join(repo, self.vexe.lstrip("./")),
        }
        if only is not None:
            environment["VTEST_ONLY"] = only
        return environment

    def _run_one(self, env, repo, target, timeout):
        """``(outcome, command, returncode, output)``; ``outcome`` is None on timeout."""
        _kind, path, only = target
        # `v <file_test.v>`, not `v test <file_test.v>`: the `test` *subcommand* builds a
        # file list and runs it through the same `VTEST_ONLY` filter the golden runners
        # use, so naming a runner there while selecting one of its cases filters the
        # runner itself out and the whole thing passes on an empty list. Handing V the
        # file directly runs exactly that file, and leaves VTEST_ONLY for the runner.
        argv = [self.vexe] + self.vflags + ["-stats", path]
        try:
            result = env.execute(
                argv, cwd=repo, env=self._env(repo, only), timeout=timeout, merge_stderr=True
            )
        except subprocess.TimeoutExpired:
            return None, " ".join(argv), 0, ""
        command = ("VTEST_ONLY=%s " % only if only else "") + " ".join(argv)
        log("%s rc=%d" % (command, result.returncode))
        log(result.stdout[-2500:])
        if only is not None and os.path.basename(only) not in result.stdout:
            # The runner selected nothing — see the class docstring.
            log("VTEST_ONLY=%s selected no case in %s" % (only, path))
            return "error", command, result.returncode, result.stdout
        outcome = "passed" if result.returncode == 0 else "failed"
        return outcome, command, result.returncode, result.stdout

    def _run(self, targets, env, repo, timeout):
        outcomes = {}
        commands = []
        output = []
        returncode = 0
        for target in targets:
            key = target[1] if target[2] is None else "%s::%s" % (target[1], target[2])
            outcome, command, code, text = self._run_one(env, repo, target, timeout)
            commands.append(command)
            output.append(text)
            returncode = max(returncode, code)
            if outcome is None:
                log("%s TIMEOUT after %ds" % (command, timeout))
                return outcomes, True, commands, returncode, "\n".join(output)
            outcomes[key] = outcome
        return outcomes, False, commands, returncode, "\n".join(output)

    def run_tests(self, env, repo, files, names, timeout, jobs):
        del names, jobs
        outcomes, timed_out, _commands, _rc, _output = self._run(files or [], env, repo, timeout)
        n = len([value for value in outcomes.values() if value != "skipped"])
        return outcomes, n, False, timed_out

    # --- the visible regression gate -----------------------------------------

    def run_all(self, env, repo, timeout, cap, jobs):
        """``v test <root>`` per configured root — V's own recursive runner, which walks
        the tree for ``_test.v`` files itself, golden runners included. One outcome per
        root: the runner prints a summary, not a machine-readable per-file report."""
        del jobs
        outcomes = {}
        commands = []
        output = []
        returncode = 0
        for root in self.eval_roots:
            argv = [self.vexe] + self.vflags + ["test", root]
            commands.append(" ".join(argv))
            try:
                result = env.execute(
                    argv, cwd=repo, env=self._env(repo), timeout=timeout, merge_stderr=True
                )
            except subprocess.TimeoutExpired:
                log("%s TIMEOUT after %ds" % (" ".join(argv), timeout))
                return None, True, self._capture(commands, returncode, "\n".join(output), cap)
            output.append(result.stdout)
            returncode = max(returncode, result.returncode)
            outcomes[root] = "passed" if result.returncode == 0 else "failed"
        return outcomes, False, self._capture(commands, returncode, "\n".join(output), cap)

    def run_selected(self, env, repo, files, names, timeout, cap, jobs):
        del names, jobs
        outcomes, timed_out, commands, returncode, output = self._run(files or [], env, repo, timeout)
        return outcomes, timed_out, self._capture(commands, returncode, output, cap)

    @staticmethod
    def _capture(commands, returncode, output, cap):
        clipped, truncated = cap.clip(output)
        return {
            "command": "\n".join(commands),
            "returncode": returncode,
            "text": clipped,
            "truncated": truncated,
        }
