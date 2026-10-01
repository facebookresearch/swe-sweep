"""DotnetTestSuite suite adapter."""

import os
import re
import xml.etree.ElementTree as ET

from ..base import ReproductionSuite
from ..utils.compiled import _patched_files, _run
from ..utils.logging import log
from ..utils.managed import (
    _CS_ATTR_RE,
    _CS_CLASS_RE,
    _CS_HUNK_RE,
    _CS_METHOD_RE,
    _CS_OTHER_ATTR_RE,
    _VB_ATTR_RE,
    _VB_CLASS_RE,
    _VB_HUNK_RE,
    _VB_METHOD_RE,
    _VB_OTHER_ATTR_RE,
)

# A test the patch ADDS. xUnit and NUnit both mark one with an attribute, and the name comes
# from the *next* added declaration, so attributes stacked between them are stepped over —
# the same arming pass the JVM suites use.
_ATTR_RE = re.compile(r"^\+\s*\[<\s*(Fact|Theory|Test|TestCase|Property)\b")
_OTHER_ATTR_RE = re.compile(r"^\+\s*\[<")
# F# spells a test either as a module-level `let` or as a member of a class, and its name is
# very often a backquoted sentence — that is the house style in this cohort.
_LET_RE = re.compile(r"^\+\s*let\s+(?:``(?P<quoted>[^`]+)``|(?P<plain>[\w']+))\s*(?:\(|:)")
_MEMBER_RE = re.compile(r"^\+\s*member\s+(?:\w+\.)?(?:``(?P<quoted>[^`]+)``|(?P<plain>[\w']+))\s*\(")
# C# helper projects in the same tree.
_CSHARP_RE = re.compile(r"^\+\s*(?:public|internal)\s+(?:async\s+)?[\w<>\[\],.]+\s+(\w+)\s*\(")

_CODE_EXTS = (".fs", ".fsx", ".cs", ".vb")
_PROJECT_EXTS = (".fsproj", ".csproj", ".vbproj")
# The characters vstest's filter grammar treats as operators. A backquoted F# test name is a
# whole English sentence, so parentheses and exclamation marks in it are the rule, not the
# exception, and an unescaped one silently changes the expression.
_FILTER_ESCAPE = "\\()&|=!~,"

_TRX_NS = "{http://microsoft.com/schemas/VisualStudio/TeamTest/2010}"

# The declaration a test file opens with, which is also the start of every fully-qualified
# test name in it: either `namespace Foo` plus a column-0 `module ``Bar`` =` inside it, or a
# single column-0 `module Foo.Bar.Baz`. Names are routinely backquoted sentences.
_NAMESPACE_RE = re.compile(r"^namespace\s+(?:rec\s+)?(?P<name>[\w.`]+)\s*$")
_TOP_MODULE_RE = re.compile(
    r"^module\s+(?:rec\s+|public\s+|internal\s+|private\s+)*"
    r"(?:``(?P<quoted>[^`]+)``|(?P<plain>[^\s=]+))\s*=?\s*$"
)
# vstest says this, and exits non-zero, when a `--filter` selects nothing at all.
_NO_TESTS_MATCHED = "No test matches the given testcase filter"


class DotnetTestSuite(ReproductionSuite):
    """``dotnet test <project> --filter …``, one invocation per touched test project.

    A .NET repository is a set of projects, and ``dotnet test`` takes one at a time, so the
    project is the unit of invocation and the test name is the filter inside it. Three
    things about this cohort shape the adapter:

    - **The name is a sentence.** F# lets a binding be named with backquotes, and this
      cohort uses that for nearly every test — ``let \\`\\`CompiledName on tuple binding
      fires FS0755 exactly once\\`\\` ()``. Spaces are fine in a filter (the whole expression
      is one argv element), but the punctuation such a name carries is not: vstest reads
      ``(``, ``!``, ``|`` and friends as operators, so every name is escaped before it goes
      into ``FullyQualifiedName~…``.
    - **The project is found, not guessed.** The layout is not uniform — a test project may
      sit one directory under the test root or three — so the owning project is the nearest
      ancestor of the touched file that holds a ``*proj``. That needs the container, which
      is why ``targets`` uses ``env``; with no ``env`` it falls back to the first directory
      under the test root, which is right for the common case.
    - **The report is TRX.** ``dotnet test`` writes no report at all unless asked, and its
      exit code says only that *something* failed, so the ``trx`` logger is not optional.

    **``dotnet test`` must be allowed to build.** The census applies the test patch and runs
    the targeted tests *before* it builds anything — which is right for a language whose
    tests are compiled per run, and wrong here: with ``--no-build`` the newly added test is
    simply not in the assemblies yet, so it cannot fail pre-gold and the subtask is scored on
    whatever was already there. So the build is part of the test command (with
    ``--no-restore``, because the census container has no network), and the task sets
    ``needs_build: false``.
    """

    no_targets = "test patch touched no .NET test project"

    def __init__(
        self,
        test_roots=(),
        configuration="Release",
        framework=None,
        dotnet="dotnet",
        results_dir="/tmp/swesweep-trx",
        no_build=False,
        solution=None,
        test_args=(),
    ):
        self.test_roots = list(test_roots)
        # What the *visible* suite runs. `dotnet test` takes one project or solution, and a
        # test root is neither, so a task that wants a whole-suite gate has to name its
        # solution file.
        self.solution = solution
        self.configuration = configuration
        self.framework = framework
        self.dotnet = dotnet
        self.results_dir = results_dir
        self.no_build = no_build
        self.test_args = list(test_args)

    def _under_test_root(self, path):
        return not self.test_roots or any(path.startswith(root + "/") for root in self.test_roots)

    def _fallback_project_dir(self, path):
        """The first directory under the test root — right whenever a project sits directly
        there, which is the common layout."""
        for root in self.test_roots:
            if path.startswith(root + "/"):
                rest = path[len(root) + 1 :].split("/")
                if len(rest) > 1:
                    return root + "/" + rest[0]
        return None

    def _project_dir(self, env, repo, path):
        """The nearest ancestor directory of ``path`` that holds a project file."""
        if env is None:
            return self._fallback_project_dir(path)
        directory = os.path.dirname(path)
        while directory and self._under_test_root(directory + "/x"):
            entries = env.find_files(os.path.join(repo, directory))
            here = [
                p
                for p in entries
                if os.path.dirname(p) == os.path.join(repo, directory) and p.endswith(_PROJECT_EXTS)
            ]
            if here:
                return directory
            directory = os.path.dirname(directory)
        return self._fallback_project_dir(path)

    @classmethod
    def from_config(cls, values, *, repo, create_suite):
        """Unlike most adapters this one keeps ``repo``: finding a file's project is a
        lookup in the container, and ``targets`` is handed no path prefix."""
        del create_suite
        suite = cls(**values)
        suite.repo = repo
        return suite

    repo = None

    @staticmethod
    def _names_from_diff(diff):
        """Names of added or edited F#, C#, and Visual Basic test methods."""
        names = []
        armed = None
        for line in diff.splitlines():
            if _ATTR_RE.match(line):
                armed = "fsharp"
                continue
            if _CS_ATTR_RE.match(line):
                same = _CS_METHOD_RE.search(line)
                if same:
                    names.append(same.group(1))
                    armed = None
                else:
                    armed = "cs"
                continue
            if _VB_ATTR_RE.match(line):
                same = _VB_METHOD_RE.search(line)
                if same:
                    names.append(same.group(1))
                    armed = None
                else:
                    armed = "vb"
                continue
            if armed is None:
                continue
            other = {"fsharp": _OTHER_ATTR_RE, "cs": _CS_OTHER_ATTR_RE, "vb": _VB_OTHER_ATTR_RE}[armed]
            if other.match(line) or not line.startswith("+") or not line[1:].strip():
                continue
            if armed == "fsharp":
                for pattern in (_LET_RE, _MEMBER_RE):
                    match = pattern.match(line)
                    if match:
                        names.append(match.group("quoted") or match.group("plain"))
                        break
                else:
                    match = _CSHARP_RE.match(line)
                    if match:
                        names.append(match.group(1))
            else:
                match = (_CS_METHOD_RE if armed == "cs" else _VB_METHOD_RE).search(line)
                if match:
                    names.append(match.group(1))
            armed = None
        for pattern in (_CS_HUNK_RE, _VB_HUNK_RE):
            names += [match.group(1) for match in pattern.finditer(diff)]
        return sorted(set(names))

    @staticmethod
    def _classes_of(env, repo, paths):
        found = []
        for path in paths:
            full = os.path.join(repo, path)
            if not env.is_file(full):
                continue
            text = env.read_text(full)
            for pattern in (_CS_CLASS_RE, _VB_CLASS_RE):
                for match in pattern.finditer(text):
                    if match.group(1) not in found:
                        found.append(match.group(1))
        return sorted(found)

    def targets(self, diff, env=None):
        """``([(project directory, touched file), ...], [test names])``.

        The touched file is kept, not just its project, because it is the only way to narrow
        a run when no test *name* can be recovered: the file's own `namespace`/`module`
        declaration is the prefix of every fully-qualified test name in it, and running the
        whole project instead means running tens of thousands of tests and scoring the
        subtask on whichever of them happens to be red."""
        found = []
        for path in _patched_files(diff):
            if not path.endswith(_CODE_EXTS) or not self._under_test_root(path):
                continue
            project = self._project_dir(env, self.repo, path)
            if project and (project, path) not in found:
                found.append((project, path))
        names = self._names_from_diff(diff)
        paths = [path for _project, path in found]
        if not names and env is not None:
            names = self._classes_of(env, self.repo, paths) or self._prefixes(env, self.repo, paths)
        return sorted(set(found)), sorted(set(names))

    @staticmethod
    def escape(name):
        """One test name, safe inside a vstest filter expression."""
        return "".join("\\" + c if c in _FILTER_ESCAPE else c for c in name)

    def filter_expression(self, names):
        """``FullyQualifiedName~a|FullyQualifiedName~b``, or ``None`` to run the project
        whole — the same fallback every other suite takes when it cannot recover a name."""
        if not names:
            return None
        return "|".join("FullyQualifiedName~" + self.escape(n) for n in names)

    @staticmethod
    def selector(names):
        """Compatibility name for the VSTest filter used by the C#/VB suite tests."""
        if not names:
            return None
        return "|".join("FullyQualifiedName~" + DotnetTestSuite.escape(n) for n in sorted(set(names)))

    @staticmethod
    def file_prefix(text):
        """The fully-qualified prefix every test in a source file shares, or ``None``.

        Two shapes, both common here: a `namespace Foo` with a column-0
        ``module ``Bar`` =`` inside it (prefix ``Foo.Bar``), and a single column-0
        `module Foo.Bar.Baz` with no `=` (prefix ``Foo.Bar.Baz``)."""
        namespace = None
        for line in text.splitlines():
            match = _NAMESPACE_RE.match(line)
            if match:
                namespace = match.group("name").replace("`", "")
                if namespace == "global":
                    namespace = None
                continue
            match = _TOP_MODULE_RE.match(line)
            if match:
                module = match.group("quoted") or match.group("plain")
                return namespace + "." + module if namespace else module
        return namespace

    def _prefixes(self, env, repo, paths):
        """The fully-qualified prefixes of the touched files, read from the container."""
        out = []
        for path in paths:
            full = os.path.join(repo, path)
            if not env.is_file(full):
                continue
            prefix = self.file_prefix(env.read_text(full))
            if prefix and prefix not in out:
                out.append(prefix)
        return out

    def _reports(self, env):
        return sorted(path for path in env.find_files(self.results_dir) if path.endswith(".trx"))

    def _invoke(self, env, repo, project, names, timeout):
        for report in self._reports(env):
            env.remove(report)
        prefix = project.replace("/", "_").replace(".", "_") or "root"
        cmd = [
            self.dotnet,
            "test",
            project,
            "-c",
            self.configuration,
            "--nologo",
            "--no-restore",
            "--results-directory",
            self.results_dir,
            "--logger",
            "trx;LogFilePrefix=" + prefix,
        ]
        if self.no_build:
            cmd.append("--no-build")
        if self.framework:
            cmd += ["--framework", self.framework]
        expression = self.filter_expression(names)
        if expression is not None:
            cmd += ["--filter", expression]
        cmd += self.test_args
        return _run(env, cmd, timeout=timeout, cwd=repo), self._reports(env)

    def run_tests(self, env, repo, files, names, timeout, jobs):
        del jobs
        if files is None:
            if not self.solution:
                raise ValueError("dotnet-test needs a `solution` to run the whole visible suite")
            per_project = {self.solution: []}
        else:
            per_project = {}
            for project, path in files:
                per_project.setdefault(project, []).append(path)
        outcomes = {}
        n = 0
        error = False
        for project, paths in sorted(per_project.items()):
            # Narrow by test name when one was recovered; otherwise by the touched files'
            # own namespace, which is the prefix of every test name in them. Only a
            # whole-suite run is allowed to have no filter at all.
            selectors = list(names) or (self._prefixes(env, repo, paths) if paths else [])
            result, reports = self._invoke(env, repo, project, selectors, timeout)
            if result is None:
                log("dotnet test %s TIMEOUT after %ds" % (project, timeout))
                return {}, 0, False, True
            log("dotnet test %s rc=%d" % (project, result.returncode))
            log(result.stdout[-2500:])
            got = {}
            ran = 0
            for report in reports:
                report_outcomes, report_ran = self._parse_trx(env, report)
                got.update(report_outcomes)
                ran += report_ran
            # A name-level filter that matches nothing is a *narrowing* mistake, not an
            # empty tree: retry at namespace level, the same fallback the gradle suite makes.
            if not got and _NO_TESTS_MATCHED in result.stdout and names and paths:
                wider = self._prefixes(env, repo, paths)
                if wider and wider != selectors:
                    log("dotnet: the name filter matched nothing; retrying %s at namespace level" % project)
                    result, reports = self._invoke(env, repo, project, wider, timeout)
                    if result is None:
                        log("dotnet test %s TIMEOUT after %ds" % (project, timeout))
                        return {}, 0, False, True
                    got = {}
                    ran = 0
                    for report in reports:
                        report_outcomes, report_ran = self._parse_trx(env, report)
                        got.update(report_outcomes)
                        ran += report_ran
            outcomes.update(got)
            n += ran
            # No report at all means the run never reached a test — the project does not
            # build, or the filter is malformed. That is the `error` flag, not a failure.
            if result.returncode != 0 and not got:
                error = True
        return outcomes, n, error, False

    @staticmethod
    def _parse_trx(env, path):
        """``(outcomes, n_run)`` from a TRX report, or empty if it was never written."""
        if hasattr(env, "is_file") and not env.is_file(path):
            return {}, 0
        root = ET.fromstring(env.read_text(path))
        outcomes = {}
        for result in root.iter(_TRX_NS + "UnitTestResult"):
            name = result.get("testName", "")
            outcome = result.get("outcome", "")
            if not name:
                continue
            if outcome == "Passed":
                outcomes[name] = "passed"
            elif outcome in ("NotExecuted", "Inconclusive"):
                outcomes[name] = "skipped"
            else:
                outcomes[name] = "failed"
        return outcomes, len([v for v in outcomes.values() if v != "skipped"])
