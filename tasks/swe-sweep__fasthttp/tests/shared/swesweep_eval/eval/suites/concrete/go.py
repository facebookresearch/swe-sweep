"""GoSuite suite adapter."""

import json
import os
import re

from ..base import FullSuite
from ..utils.compiled import _patched_files, _run
from ..utils.logging import log
from ..utils.managed import _GO_TEST_FN_RE, _GOCHECK_TEST_METHOD_RE, go_package_of

# A gocheck case line in `-check.v` output, e.g. `PASS: worktree_test.go:64: WorktreeSuite.TestCheckout`.
# These lines are a whole-suite run's only per-case signal; `MISS` (unexpected pass) folds with `SKIP`.
_GOCHECK_CASE_RE = re.compile(
    r"^(PASS|FAIL|SKIP|MISS|PANIC):\s+\S+?:\d+:\s+([A-Za-z_]\w*)\.([A-Za-z_]\w*)"
)
_GOCHECK_CASE_STATUS = {
    "PASS": "passed",
    "FAIL": "failed",
    "PANIC": "failed",
    "SKIP": "skipped",
    "MISS": "skipped",
}
_GOCHECK_IMPORT = "gopkg.in/check.v1"


def _links_gocheck(pkgdir):
    """Whether any test file in the package imports gocheck, i.e. whether its test binary accepts `-check.v`.
    A binary without gocheck exits on the unknown flag and the whole run is lost."""
    try:
        names = os.listdir(pkgdir)
    except OSError:
        return False
    for name in names:
        if not name.endswith("_test.go"):
            continue
        try:
            with open(os.path.join(pkgdir, name), encoding="utf-8", errors="replace") as f:
                if _GOCHECK_IMPORT in f.read():
                    return True
        except OSError:
            continue
    return False


class GoSuite(FullSuite):
    """``go test``, one invocation per package directory the patch touches.

    Three things are Go's own.

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

    **The whole-suite gate reads gocheck's per-case lines**, so one failing case no longer drops its whole package.
    Packages linking gocheck run once with ``-check.v`` (ids like ``pkg::WorktreeSuite.TestCheckout``); others run without.

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

    def _visible_runs(self, env, cwd, cmd, check_pkgs):
        """The whole-suite invocations for one eval root, ``[(argv, cwd), ...]``, gocheck packages run apart.
        Records gocheck import paths in ``check_pkgs``; falls back to one ``./...`` run when there is no gocheck package."""
        listed = _run(
            env,
            ["go", "list", "-f", "{{.ImportPath}}|{{.Dir}}", "./..."],
            timeout=120,
            cwd=cwd,
        )
        if listed is None or listed.returncode != 0:
            return [(cmd + ["./..."], cwd)]
        check, plain = [], []
        for line in listed.stdout.splitlines():
            imp, _, pkgdir = line.partition("|")
            if not imp or not pkgdir:
                continue
            (check if _links_gocheck(pkgdir) else plain).append(imp)
        if not check:
            return [(cmd + ["./..."], cwd)]
        check_pkgs.update(check)
        runs = []
        if plain:
            runs.append((cmd + sorted(plain), cwd))
        # The test-binary flag goes last: `go` stops reading package names at the first flag it does not know.
        # A `-check.v` placed earlier would swallow the packages and silently test the current directory.
        runs.append((cmd + sorted(check) + ["-check.v"], cwd))
        return runs

    def _run(self, env, repo, packages, names, timeout, recursive=False):
        """Run one ``go test -json`` invocation per package/root.

        ``-run`` takes a regex anchored on both ends so ``TestFind`` does not also select
        ``TestFindInBatches``; with no names the whole package runs, the same fallback
        pytest gets. A build failure reports no test events at all, which is the ``error``
        flag rather than a failed test — the driver counts it as failing pre-gold and as
        not passing post-gold, exactly like a pytest collection error.

        ``recursive`` is the eval gate's whole-suite mode: each entry is a module root and
        the command names ``./...`` instead of just that one package — or, for a module
        with gocheck packages, the split runs `_visible_runs` computes."""
        outcomes = {}
        error = False
        output = []
        commands = []
        returncode = 0
        check_pkgs = set()
        for pkg in packages:
            cwd = os.path.join(repo, pkg) if pkg != "." else repo
            cmd = ["go", "test", "-json", "-count=1"] + self.go_args
            if recursive:
                runs = self._visible_runs(env, cwd, cmd, check_pkgs)
            else:
                if names:
                    cmd += ["-run", "^(" + "|".join(names) + ")$"]
                elif self.check_names.get(pkg):
                    # No `func Test…` was added but gocheck methods were: select those instead of the whole package.
                    # `-check.f` is a test-binary flag, so it goes only to the package the methods were added to.
                    cmd += ["-check.f", "^(" + "|".join(self.check_names[pkg]) + ")$"]
                runs = [(cmd + ["."], cwd)]
            for run_cmd, run_cwd in runs:
                commands.append("cd %s && %s" % (run_cwd, " ".join(run_cmd)))
                r = _run(env, run_cmd, timeout=timeout, cwd=run_cwd)
                if r is None:
                    log("go test TIMEOUT after %ds (%s)" % (timeout, " ".join(run_cmd)))
                    return outcomes, 0, False, True, commands, returncode, "\n".join(output)
                log("go test rc=%d (%s)" % (r.returncode, " ".join(run_cmd)))
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
                    if name and action in ("pass", "fail", "skip"):
                        seen += 1
                        prefix = ev.get("Package", pkg) if recursive else pkg
                        outcomes[prefix + "::" + name] = {
                            "pass": "passed", "fail": "failed", "skip": "skipped",
                        }[action]
                        continue
                    if recursive and action == "output" and ev.get("Package") in check_pkgs:
                        m = _GOCHECK_CASE_RE.match(ev.get("Output", ""))
                        if m:
                            # Tested code shares this stream, so a later line never clears a failure already reported.
                            key = "%s::%s.%s" % (ev["Package"], m.group(2), m.group(3))
                            if outcomes.get(key) != "failed":
                                outcomes[key] = _GOCHECK_CASE_STATUS[m.group(1)]
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
