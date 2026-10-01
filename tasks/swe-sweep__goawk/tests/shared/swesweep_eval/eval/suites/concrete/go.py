"""GoSuite suite adapter."""

import json
import os

from ..base import FullSuite
from ..utils.compiled import _patched_files, _run
from ..utils.logging import log
from ..utils.managed import _GO_TEST_FN_RE, _GOCHECK_TEST_METHOD_RE, go_package_of

class GoSuite(FullSuite):
    """``go test``, one invocation per package directory the patch touches.

    Two things are Go's own.

    **The test cache has to be off.** ``go test`` caches a package's result keyed on the
    package's own inputs, and replays it verbatim — so a post-gold run whose only change is
    in a *different* package would report the pre-gold outcome from cache. ``-count=1`` is
    the documented way to force a real run, and it is not optional here.

    **A repo can hold more than one module.** gorm keeps its integration suite in a
    ``tests/`` directory with its own ``go.mod``, which the root module's ``./...`` does not
    reach. Running from inside the package's own directory sidesteps that entirely: the go
    tool walks up to the nearest enclosing ``go.mod`` by itself.

    **gocheck suites are addressed by ``-check.f``.** ``gopkg.in/check.v1`` hangs a whole
    suite off a single ``func Test``, so a patch that adds a case adds no ``func Test…`` and
    ``-run`` degenerates to running the entire package. go-git's root package is the case
    that matters: its suite clones from github.com, which a census container cannot reach,
    so eleven unrelated cases fail and every subtask in that package is lost. gocheck
    registers ``-check.f`` on the test binary for exactly this, and the flag is only ever
    passed when the test patch actually added a gocheck method — so a repo that does not use
    gocheck never sees it.

    ``go_args`` are the repo's own test flags (build tags, ``-tags sqlite``)."""

    no_targets = "test patch touched no Go test file"

    def __init__(self, go_args=(), eval_roots=(".",)):
        self.go_args = list(go_args)
        self.eval_roots = list(eval_roots)
        # {package dir: [gocheck method names]}, set by `targets()`; see the class docstring.
        self.check_names = {}

    def targets(self, diff, env=None):
        del env
        """``([package dirs], [test fn names])``."""
        found = []
        for path in _patched_files(diff):
            pkg = go_package_of(path)
            if pkg is not None and pkg not in found:
                found.append(pkg)
        names = [m.group(1) for m in
                 (_GO_TEST_FN_RE.match(line) for line in diff.splitlines()) if m]
        # gocheck methods, kept per package: `-check.f` is only valid for a test binary
        # that links gocheck, so it must not leak onto a sibling package the same patch
        # happens to touch.
        self.check_names = {}
        pkg = None
        for line in diff.splitlines():
            if line.startswith("+++ b/"):
                pkg = go_package_of(line[len("+++ b/"):].strip())
                continue
            m = _GOCHECK_TEST_METHOD_RE.match(line)
            if m and pkg is not None:
                self.check_names.setdefault(pkg, set()).add(m.group(1))
        self.check_names = dict((k, sorted(v)) for k, v in self.check_names.items())
        return sorted(set(found)), sorted(set(names))

    def _run(self, env, repo, packages, names, timeout, recursive=False):
        """Run one ``go test -json`` invocation per package/root.

        ``-run`` takes a regex anchored on both ends so ``TestFind`` does not also select
        ``TestFindInBatches``; with no names the whole package runs, the same fallback
        pytest gets. A build failure reports no test events at all, which is the ``error``
        flag rather than a failed test — the driver counts it as failing pre-gold and as
        not passing post-gold, exactly like a pytest collection error.

        ``recursive`` is the eval gate's whole-suite mode: each entry is a module root and
        the command names ``./...`` instead of just that one package."""
        outcomes = {}
        error = False
        output = []
        commands = []
        returncode = 0
        for pkg in packages:
            cmd = ["go", "test", "-json", "-count=1"] + self.go_args
            if names:
                cmd += ["-run", "^(" + "|".join(names) + ")$"]
            elif not recursive and self.check_names.get(pkg):
                # No `func Test…` was added but gocheck methods were: select those instead
                # of falling back to the whole package. `-check.f` is the test binary's own
                # flag, so it is passed only to the package the methods were added to.
                cmd += ["-check.f", "^(" + "|".join(self.check_names[pkg]) + ")$"]
            cmd += ["./..." if recursive else "."]
            cwd = os.path.join(repo, pkg) if pkg != "." else repo
            commands.append("cd %s && %s" % (cwd, " ".join(cmd)))
            r = _run(env, cmd, timeout=timeout, cwd=cwd)
            if r is None:
                log("go test TIMEOUT after %ds (%s)" % (timeout, pkg))
                return outcomes, 0, False, True, commands, returncode, "\n".join(output)
            log("go test %s rc=%d" % (pkg, r.returncode))
            log(r.stdout[-2000:])
            output.append(r.stdout)
            returncode = max(returncode, r.returncode)
            seen = 0
            for line in r.stdout.splitlines():
                if not line.startswith("{"):
                    continue  # a build error is printed as plain text, not as an event
                try:
                    ev = json.loads(line)
                except ValueError:
                    continue
                name = ev.get("Test")
                action = ev.get("Action")
                if not name or action not in ("pass", "fail", "skip"):
                    continue
                seen += 1
                prefix = ev.get("Package", pkg) if recursive else pkg
                outcomes[prefix + "::" + name] = {
                    "pass": "passed", "fail": "failed", "skip": "skipped",
                }[action]
            if r.returncode != 0 and seen == 0:
                error = True
        n = len([o for o in outcomes.values() if o != "skipped"])
        return outcomes, n, error, False, commands, returncode, "\n".join(output)

    def run_tests(self, env, repo, files, names, timeout, jobs):
        """One ``go test -json`` per package touched by the hidden test patch."""
        packages = self.eval_roots if files is None else files
        outcomes, n, error, timed_out, _commands, _returncode, _output = self._run(
            env, repo, packages, names, timeout, recursive=files is None)
        return outcomes, n, error, timed_out

    def run_all(self, env, repo, timeout, cap, jobs):
        outcomes, _n, error, timed_out, commands, returncode, output = self._run(
            env, repo, self.eval_roots, [], timeout, recursive=True)
        if error and not outcomes:
            outcomes = None
        return outcomes, timed_out, self._capture(commands, returncode, output, cap)

    def run_selected(self, env, repo, files, names, timeout, cap, jobs):
        outcomes, _n, error, timed_out, commands, returncode, output = self._run(
            env, repo, files, names, timeout)
        if error and not outcomes:
            outcomes = dict((pkg + "::<build>", "error") for pkg in files)
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
