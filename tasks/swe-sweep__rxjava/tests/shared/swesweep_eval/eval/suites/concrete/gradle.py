# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""GradleSuite suite adapter."""

import os

from ..base import ReproductionSuite
from ..utils.compiled import _parse_junit, _patched_files, _run
from ..utils.logging import log
from ..utils.managed import (
    _JAVA_METHOD_RE, _JVM_ANNOT_RE, _JVM_OTHER_ANNOT_RE, _KOTLIN_FUN_RE,
    _NO_TESTS_MATCHED, gradle_class_of,
)

class GradleSuite(ReproductionSuite):
    """``gradlew <project>:test --tests …``, one invocation per touched module.

    Three things differ from :class:`MavenSuite`, which is otherwise the same design:

    - **The selector is a glob, not a class#method pair.** Gradle's ``--tests`` takes a
      pattern over the fully-qualified name, and the patterns are OR-ed. The class part is
      written with a trailing ``*`` so that a JUnit 5 ``@Nested inner class`` — whose real
      name is ``Outer$Inner`` and which the file path cannot tell us about — is still
      selected.
    - **A selector that matches nothing is a hard error**, where surefire's
      ``failIfNoTests=false`` just moves on. So a run that comes back with Gradle's
      "no tests found" message is retried once at class granularity: the narrowing was
      wrong, and running the whole class is the same fallback every other suite takes when
      it cannot recover a test name.
    - **``--offline`` is not optional.** The census container has no network, and Gradle
      would otherwise spend its timeout trying to re-resolve the dependency graph the
      image already populated.

    ``gradle_args`` are the repo's own build flags (which quality plugins to skip), and
    ``gradlew`` is the wrapper's path in case the repo hides it.

    ``flat_projects`` picks the other of Gradle's two naming conventions. By default a
    project is addressed by its directory (``Ghidra/Features/Base`` -> ``:Ghidra:Features:Base``),
    which is what ``include`` gives you. A build whose ``settings.gradle`` instead calls
    ``include <name>`` and then reassigns ``projectDir`` gives every project a **flat**
    name — its directory's last segment only (``:Base``) — no matter how deep the
    directory is. The reports still land under the real directory, so only the name the
    command line uses changes.

    ``build_dir`` is the project's build output directory, where the JUnit XML lands. It is
    ``build`` for a stock gradle build, but a repo may move it: hibernate-orm's
    ``gradle/module.gradle`` sets ``buildDir = "target"`` for every module "to minimize
    changes" from its maven past, and with the default the reports are simply never found —
    the run looks like a suite that produced no tests rather than one that failed.

    ``extra_test_sets`` maps a **second** test source-set directory to the ``Test`` task
    that runs it — ghidra's ``{"test.slow": "integrationTest"}``. A Gradle build may have
    several, and they are not interchangeable: they have different base classes and
    different task dependencies, so a class under one has to be run by that one's task.
    Where a repo has only ``src/test``, leave it empty and nothing changes. A path under a
    source set that is not ``test_task``'s or in this map is deliberately **not** a target:
    running it with the wrong task would compile the wrong source set.
    """

    no_targets = "test patch touched no JVM test class"

    def __init__(self, gradle_args=(), gradlew="./gradlew", test_task="test", flat_projects=False,
                 extra_test_sets=None, build_dir="build"):
        self.gradle_args = list(gradle_args)
        self.build_dir = build_dir
        self.gradlew = gradlew
        self.test_task = test_task
        self.flat_projects = flat_projects
        # source-set directory -> the task that runs it; `test_task` runs `src/test`.
        self.tasks_by_source_set = {"test": test_task}
        self.tasks_by_source_set.update(extra_test_sets or {})

    def _project(self, module):
        """The name Gradle answers to for the project whose directory is ``module``."""
        if not module:
            return ":"
        if self.flat_projects:
            return ":" + module.rsplit("/", 1)[-1]
        return ":" + module.replace("/", ":")

    def targets(self, diff, env=None):
        del env
        """``([(project, source set, class), ...], [test method names])``.

        A Kotlin test name is usually a backquoted sentence, so the two signature forms
        are tried in turn; everything else is the arming pass :class:`MavenSuite` uses.
        """
        found = []
        for path in _patched_files(diff):
            t = gradle_class_of(path, tuple(self.tasks_by_source_set))
            if t is not None and t not in found:
                found.append(t)
        names = []
        armed = False
        for line in diff.splitlines():
            if _JVM_ANNOT_RE.match(line):
                armed = True
                continue
            if not armed:
                continue
            if _JVM_OTHER_ANNOT_RE.match(line) or not line.startswith("+") or not line[1:].strip():
                continue  # another annotation, or a blank line — keep looking
            kt = _KOTLIN_FUN_RE.match(line)
            if kt:
                names.append(kt.group("quoted") or kt.group("plain"))
                armed = False
                continue
            java = _JAVA_METHOD_RE.match(line)
            if java:
                names.append(java.group(1))
            armed = False
        return sorted(set(found)), sorted(set(names))

    @staticmethod
    def selectors(classes, names):
        """The ``--tests`` patterns for one module. The trailing ``*`` on the class part
        is what keeps a ``@Nested`` inner class reachable."""
        if not names:
            return [cls + "*" for cls in classes]
        return [cls + "*." + name for cls in classes for name in names]

    def _report_dir(self, repo, module, task):
        return os.path.join(repo, module, self.build_dir, "test-results", task)

    def _reports(self, env, repo, module, task):
        root = self._report_dir(repo, module, task)
        return [
            path
            for path in env.find_files(root)
            if os.path.dirname(path) == root and os.path.basename(path).startswith("TEST-") and path.endswith(".xml")
        ]

    def _invoke(self, env, repo, module, task, patterns, timeout, jobs):
        """One ``gradlew`` run. Stale reports are deleted first: Gradle leaves the last
        run's XML in place when compilation fails, which would otherwise be scored as this
        run's outcome."""
        for path in self._reports(env, repo, module, task):
            env.remove(path)
        project = self._project(module)
        cmd = [self.gradlew, project + ":" + task, "--offline", "--console=plain", "--parallel",
               "--max-workers=" + str(jobs)]
        for pattern in patterns:
            cmd += ["--tests", pattern]
        cmd += self.gradle_args
        return _run(env, cmd, timeout=timeout, cwd=repo)

    def run_tests(self, env, repo, files, names, timeout, jobs):
        if files is None:
            reports = [
                path
                for path in env.find_files(repo)
                if "/%s/test-results/" % self.build_dir in path
                and os.path.basename(path).startswith("TEST-")
                and path.endswith(".xml")
            ]
            for path in reports:
                env.remove(path)
            cmd = [self.gradlew, self.test_task, "--offline", "--console=plain", "--parallel",
                   "--max-workers=" + str(jobs)] + self.gradle_args
            r = _run(env, cmd, timeout=timeout, cwd=repo)
            if r is None:
                log("gradle test TIMEOUT after %ds (whole build)" % timeout)
                return {}, 0, False, True
            log("gradle test whole build rc=%d" % r.returncode)
            log(r.stdout[-2500:])
            outcomes = {}
            n = 0
            for path in env.find_files(repo):
                if "/%s/test-results/" % self.build_dir not in path or not os.path.basename(path).startswith("TEST-") or not path.endswith(".xml"):
                    continue
                got, ran = _parse_junit(env, path, qualified=True)
                outcomes.update(got)
                n += ran
            return outcomes, n, r.returncode != 0 and not outcomes, False
        outcomes = {}
        n = 0
        error = False
        # One invocation per (project, source set): two source sets of the same project are
        # two different Test tasks and cannot be selected in one run.
        for project, srcset in sorted(set((p, s) for p, s, _cls in files)):
            module = project.lstrip(":").replace(":", "/")
            task = self.tasks_by_source_set[srcset]
            label = project + ":" + task
            classes = sorted(set(cls for p, s, cls in files if (p, s) == (project, srcset)))
            r = self._invoke(env, repo, module, task, self.selectors(classes, names), timeout, jobs)
            if r is None:
                log("gradle test TIMEOUT after %ds (%s)" % (timeout, label))
                return {}, 0, False, True
            if r.returncode != 0 and _NO_TESTS_MATCHED in r.stdout and names:
                log("gradle: the method-level filter matched nothing; retrying %s at class level" % label)
                r = self._invoke(env, repo, module, task, self.selectors(classes, []), timeout, jobs)
                if r is None:
                    log("gradle test TIMEOUT after %ds (%s, class level)" % (timeout, label))
                    return {}, 0, False, True
            log("gradle test %s rc=%d" % (label, r.returncode))
            log(r.stdout[-2500:])
            got_any = False
            for path in self._reports(env, repo, module, task):
                got, ran = _parse_junit(env, path, qualified=True)
                outcomes.update(got)
                n += ran
                got_any = got_any or bool(got)
            # A compile failure is the `error` flag, not a failed test: Gradle exits
            # non-zero with no report written, and "the module does not build" and "the
            # test fails" mean different things post-gold.
            if r.returncode != 0 and not got_any:
                error = True
        return outcomes, n, error, False
