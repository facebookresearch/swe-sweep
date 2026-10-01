"""MavenSuite suite adapter."""

import os

from ..base import ReproductionSuite
from ..utils.compiled import _parse_junit, _patched_files, _run
from ..utils.logging import log
from ..utils.managed import _ANNOT_RE, _METHOD_RE, _OTHER_ANNOT_RE, maven_class_of

class MavenSuite(ReproductionSuite):
    """One reactor invocation for every touched module.

    ``-am`` builds everything those modules depend on, so a gold patch in an upstream
    module is compiled in by the same command that runs the test; the upstream modules
    also run surefire and match no selected test, which is what ``failIfNoTests=false``
    is for. ``mvn_args`` are the repo's own build flags (which quality plugins to skip).

    ``goal`` is the lifecycle phase to run, and ``test`` is not always enough. A module that
    consumes a *packaged* sibling — keycloak's testsuite unpacks the javascript adapter jar
    of another reactor module — fails under ``test`` with maven's MDEP-98 ("Artifact has not
    been packaged yet"), because ``-am`` stops its upstreams at ``test`` too. The artifact
    being in ``~/.m2`` from the image build does not help: a module inside the reactor is
    resolved from the reactor, not from the repository. Those repos pass ``goal="install"``,
    which packages each upstream on the way past; it is slower, so it is not the default.

    ``reactor`` is where the root pom sits when the repository is not a maven project at
    its own top level — a polyglot repo that keeps its java half in a subdirectory (che4z
    holds the COBOL language server under ``server/``, beside its TypeScript clients).
    Only maven is redirected: the working directory stays the repository root, because
    that is what a patch path is relative to, and the module ids handed to ``-pl`` are
    made relative to the reactor. A test class outside the reactor belongs to the other
    language's half of the repo and selects nothing."""

    no_targets = "test patch touched no JUnit test class"

    def __init__(self, mvn_args=(), goal="test", reactor="."):
        self.mvn_args = list(mvn_args)
        self.goal = goal
        self.reactor = reactor.strip("/")

    def _module(self, module):
        """``module`` (repo-relative, as ``maven_class_of`` reports it) the way maven
        addresses it from the reactor, or ``None`` if it lies outside the reactor."""
        if self.reactor in ("", "."):
            return module
        if module == self.reactor:
            return "."
        prefix = self.reactor + "/"
        return module[len(prefix) :] if module.startswith(prefix) else None

    def _cwd(self, repo):
        return repo if self.reactor in ("", ".") else os.path.join(repo, self.reactor)

    def targets(self, diff, env=None):
        del env
        """``([(module, class), ...], [test method names])``."""
        found = []
        for path in _patched_files(diff):
            t = maven_class_of(path)
            if t is None:
                continue
            module = self._module(t[0])
            if module is None:
                continue
            t = (module, t[1])
            if t not in found:
                found.append(t)
        names = []
        armed = False
        for line in diff.splitlines():
            if _ANNOT_RE.match(line):
                armed = True
                continue
            if not armed:
                continue
            if _OTHER_ANNOT_RE.match(line) or not line.startswith("+") or not line[1:].strip():
                continue  # another annotation, or a blank line — keep looking
            m = _METHOD_RE.match(line)
            if m:
                names.append(m.group(1))
            armed = False
        return sorted(set(found)), sorted(set(names))

    @staticmethod
    def selector(files, names):
        """Surefire's ``-Dtest`` value: the added methods of each touched class, or the
        whole class where the patch only *changed* an existing test and there is no added
        name to key on."""
        classes = sorted(set(cls.rsplit(".", 1)[-1] for _module, cls in files))
        if not names:
            return ",".join(classes)
        return ",".join(c + "#" + "+".join(sorted(set(names))) for c in classes)

    def _reports(self, env, repo, modules):
        base = self._cwd(repo)
        roots = [base] if modules is None else [os.path.join(base, module) for module in modules]
        for root in roots:
            for path in env.find_files(root):
                if "/target/surefire-reports/TEST-" in path and path.endswith(".xml"):
                    yield path

    def run_tests(self, env, repo, files, names, timeout, jobs):
        """Run the selected tests and read surefire's JUnit XML back.

        The previous run's reports are deleted first: surefire leaves them in place when
        it never gets as far as running, so a build failure would otherwise be scored
        with the last run's outcomes."""
        modules = None if files is None else sorted(set(m for m, _cls in files))
        for path in self._reports(env, repo, modules):
            env.remove(path)
        cmd = ["mvn", "-B", "-o", "-T", str(jobs)]
        if modules is not None:
            cmd += [
                "-pl", ",".join(modules), "-am",
                "-Dtest=" + self.selector(files, names),
                "-DfailIfNoTests=false", "-Dsurefire.failIfNoSpecifiedTests=false",
            ]
        cmd += self.mvn_args + [self.goal]
        r = _run(env, cmd, timeout=timeout, cwd=self._cwd(repo))
        if r is None:
            log("mvn test TIMEOUT after %ds" % timeout)
            return {}, 0, False, True
        log("mvn test rc=%d" % r.returncode)
        log(r.stdout[-2500:])
        outcomes = {}
        n = 0
        for path in self._reports(env, repo, modules):
            got, ran = _parse_junit(env, path, qualified=True)
            outcomes.update(got)
            n += ran
        # A compile failure is the `error` flag, not a failed test: maven exits non-zero
        # with no report written, and "the tree does not build" and "the test fails" mean
        # different things post-gold.
        return outcomes, n, r.returncode != 0 and not outcomes, False
