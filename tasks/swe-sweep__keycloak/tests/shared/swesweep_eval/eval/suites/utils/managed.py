#!/usr/bin/env python3

# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""Shared target-discovery helpers for build-tool-managed adapters."""
import json
import os
import re
import subprocess

from swesweep_eval.eval.suites.utils.compiled import _parse_junit, _patched_files, _run
from swesweep_eval.eval.suites.utils.logging import log

# --- cargo --------------------------------------------------------------------

# An added test function. libtest's attribute is `#[test]`; the async runtimes wrap it
# (`#[tokio::test]`, `#[test_log::test]`), so the attribute is matched loosely and the
# name is taken from the next added `fn` line.
_TEST_ATTR_RE = re.compile(r"^\+\s*#\[[\w:]*test[\w:]*(\(.*\))?\]")
_FN_RE = re.compile(r"^\+\s*(?:pub\s+)?(?:async\s+)?(?:unsafe\s+)?fn\s+([A-Za-z0-9_]+)")
# `test tokio::sync::mutex::try_lock ... ok` — libtest's line per case.
_CARGO_RESULT_RE = re.compile(r"^test\s+(\S+)\s+\.\.\.\s+(ok|FAILED|ignored)")
_CARGO_STATUS = {"ok": "passed", "FAILED": "failed", "ignored": "skipped"}


def cargo_target_of(path):
    """``(crate dir, cargo test target)`` for an integration-test path, or ``None``.

    ``tokio/tests/sync_mutex.rs`` is target ``sync_mutex`` of the crate in ``tokio/``. A
    target may also be a *directory* with a ``main.rs`` — ``core/tests/sql/x.rs`` is part
    of target ``sql`` — so the first component after ``tests/`` names the target whenever
    there is more than one left."""
    if not path.endswith(".rs") or "/tests/" not in ("/" + path):
        return None
    head, _, tail = path.partition("tests/")
    crate = head.rstrip("/")
    parts = [p for p in tail.split("/") if p]
    if not parts:
        return None
    target = parts[0][: -len(".rs")] if len(parts) == 1 else parts[0]
    return crate or ".", target




# --- maven --------------------------------------------------------------------

_TEST_SRC = "/src/test/java/"
# An added JUnit annotation: `@Test`, `@Test(timeout = 5000)`, `@ParameterizedTest`.
# The method name comes from the next added signature line, so javadoc and other
# annotations stacked between them are stepped over.
_ANNOT_RE = re.compile(r"^\+\s*@(Test|ParameterizedTest|RepeatedTest|TestFactory|TestTemplate)\b")
_OTHER_ANNOT_RE = re.compile(r"^\+\s*@[A-Za-z]")
_METHOD_RE = re.compile(
    r"^\+\s*(?:public\s+|protected\s+|private\s+)?(?:static\s+)?(?:final\s+)?[\w<>\[\],.\s]+?\s+([A-Za-z_]\w*)\s*\("
)


def maven_class_of(path):
    """``(module, fully-qualified test class)`` for a Java test path, or ``None``.

    A **single-module** project keeps its tests at ``src/test/java/`` with no module
    directory in front (checkstyle's layout), and maven addresses that module as ``.``.
    The multi-module form is the same path with a prefix.
    """
    if not path.endswith(".java"):
        return None
    if path.startswith(_TEST_SRC.lstrip("/")):
        return ".", path[len(_TEST_SRC) - 1 : -len(".java")].replace("/", ".")
    if _TEST_SRC not in path:
        return None
    module, _, rest = path.partition(_TEST_SRC)
    return module, rest[: -len(".java")].replace("/", ".")




# --- gradle -------------------------------------------------------------------

# `<module>/src/<source set>/<kotlin|java|groovy>/<package path>/<Class>.<ext>`. Unlike
# maven, both the source set and language directory vary. Kotlin modules use `kotlin/`,
# Spock suites use `groovy/`, and builds may expose several source sets.
# The source set is captured because a Gradle build may have more than one, each run by a
# `Test` task of its own (ghidra's `src/test.slow` -> `integrationTest`).
_GRADLE_TEST_SRC_RE = re.compile(
    r"^(?:(?P<module>.+?)/)?src/(?P<srcset>[\w.]+)/(?:kotlin|java|groovy)/(?P<cls>.+)\.(?:kt|java|groovy)$"
)
# A JUnit annotation the patch adds -- the same set maven looks for, plus the JUnit 5
# Kotlin idiom of a `@ParameterizedTest` with the source annotation stacked under it.
_JVM_ANNOT_RE = re.compile(r"^\+\s*@(Test|ParameterizedTest|RepeatedTest|TestFactory|TestTemplate)\b")
_JVM_OTHER_ANNOT_RE = re.compile(r"^\+\s*@[A-Za-z]")
# The signature the annotation arms. Kotlin's `fun` form comes first because its
# backquoted name is the ktlint house style and would otherwise be unparseable; the Java
# form is the same one maven uses.
_KOTLIN_FUN_RE = re.compile(r"^\+\s*(?:(?:public|internal|private|protected|open|override|suspend)\s+)*fun\s+(?:`(?P<quoted>[^`]+)`|(?P<plain>\w+))\s*\(")
_JAVA_METHOD_RE = re.compile(
    r"^\+\s*(?:public\s+|protected\s+|private\s+)?(?:static\s+)?(?:final\s+)?[\w<>\[\],.\s]+?\s+([A-Za-z_]\w*)\s*\("
)
# Gradle says this, and exits non-zero, when a `--tests` pattern selects nothing at all.
# That is not a test failure -- it means the narrowing was wrong, not the tree -- so the
# suite retries at class granularity instead of reporting the whole class as erroring.
_NO_TESTS_MATCHED = "No tests found for given includes"


def gradle_class_of(path, source_sets=("test",)):
    """``(gradle project, source set, fully-qualified test class)`` for a JVM test path
    under one of ``source_sets``, or ``None``.

    The project path is the module directory with ``/`` turned into Gradle's ``:``, so a
    nested module (``a/b/src/test/kotlin/...``) addresses as ``:a:b``. A single-project
    build keeps its tests at ``src/test/kotlin/`` with no module directory, and Gradle
    addresses that as the bare ``:``.

    ``source_sets`` is what the caller can actually run. A build may have several test
    source sets, each with its own ``Test`` task, and a path in one the runner does not
    know about is *not* a target — reporting it would run the wrong task.
    """
    m = _GRADLE_TEST_SRC_RE.match(path)
    if m is None:
        return None
    srcset = m.group("srcset")
    if srcset not in source_sets:
        return None
    module = m.group("module")
    project = ":" + module.replace("/", ":") if module else ":"
    return project, srcset, m.group("cls").replace("/", ".")




# clippy's UI corpus: `tests/ui/<name>.rs` plus the expectation files beside it. Changing only
# an expectation is a complete test patch — the case is unchanged and the recorded diagnostics
# are what move — which is the same rule the CTest suite applies to its `.out` files.
_UI_DIR_RE = re.compile(r"^tests/ui(?:-[\w-]+|-toml/[^/]+)?/(?P<stem>.+?)\.(rs|stderr|stdout|fixed|toml)$")




# --- go -----------------------------------------------------------------------

# An added test function. `go test` runs `TestXxx`; `FuzzXxx` and `ExampleXxx` are run by
# the same command and reported the same way, so all three count.
_GO_TEST_FN_RE = re.compile(r"^\+\s*func\s+((?:Test|Fuzz|Example)[A-Za-z0-9_]*)\s*\(")

# An added **gocheck** test method. `gopkg.in/check.v1` hangs a whole suite off one
# `func Test(t *testing.T) { check.TestingT(t) }`, so its cases are methods on a suite
# struct and `go test -run` cannot address them — a patch that adds one leaves `-run` with
# nothing to match, and the runner falls back to the whole package. For a package whose
# suite also reaches the network or the filesystem that is fatal: unrelated cases fail and
# the subtask never passes post-gold even though its own case does.
#
# gocheck registers its own `-check.f` flag on the test binary, which selects by method
# name, so the fix is to recognise the method and pass it. The `*C` receiver argument is
# what identifies the method as gocheck's rather than testify's — a testify suite method
# takes no argument — so matching on it keeps every non-gocheck Go repo's behaviour
# exactly as it was.
_GOCHECK_TEST_METHOD_RE = re.compile(
    r"^\+\s*func\s+\([^)]*\)\s+(Test[A-Za-z0-9_]*)\s*\(\s*\w+\s+\*(?:\w+\.)?C\s*\)"
)


def go_package_of(path):
    """The directory of a Go test file, relative to the repo root, or ``None``.

    Go has no separate test tree: ``clause/where_test.go`` tests the package in
    ``clause/``, and a file at the repo root tests the root package. The directory *is*
    the unit of invocation."""
    if not path.endswith("_test.go"):
        return None
    return os.path.dirname(path) or "."




# --- dotnet -------------------------------------------------------------------

# An xUnit test attribute the patch adds. Roslyn wraps both of xUnit's own attributes in
# its own (`[ConditionalFact(typeof(WindowsOnly))]`, `[WpfTheory]`, `[ClrOnlyFact]`), so
# the suffix is what is matched rather than the bare name -- and the C# and VB spellings
# differ only in their brackets.
_CS_ATTR_RE = re.compile(r"^\+\s*\[[^\]]*(?:Fact|Theory)\b")
_VB_ATTR_RE = re.compile(r"^\+\s*<[^>]*(?:Fact|Theory)\b")
_CS_OTHER_ATTR_RE = re.compile(r"^\+\s*\[")
_VB_OTHER_ATTR_RE = re.compile(r"^\+\s*<")
# The signature the attribute arms. Unanchored, because the attribute and the signature
# are as often on one line (`[Fact] public void Foo()`) as on two; the caller only ever
# offers it an added line.
_CS_METHOD_RE = re.compile(
    r"\b(?:public|private|protected|internal)\s+"
    r"(?:(?:static|async|unsafe|override|virtual|sealed|extern|partial|new)\s+)*"
    r"[\w<>\[\],.?]+\s+([A-Za-z_]\w*)\s*(?:<[^<>()]*>)?\s*\("
)
_VB_METHOD_RE = re.compile(
    r"\b(?:Public|Private|Protected|Friend)\s+"
    r"(?:(?:Shared|Async|Overrides|Overloads|Iterator|MustOverride|NotOverridable)\s+)*"
    r"(?:Sub|Function)\s+([A-Za-z_]\w*)"
)
# A case the patch only EDITS: git names the enclosing method in the hunk header, which
# is the only place an unchanged signature shows up in a diff.
_CS_HUNK_RE = re.compile(r"^@@ .*@@.*\b(?:void|Task|Task<[^>]*>|ValueTask)\s+([A-Za-z_]\w*)\s*\(", re.M)
_VB_HUNK_RE = re.compile(r"^@@ .*@@.*\b(?:Sub|Function)\s+([A-Za-z_]\w*)\s*\(", re.M)
# The declaring class, read out of the file rather than the diff -- the fallback selector
# when a patch adds cases no signature reader can name (an `[InlineData]` row).
_CS_CLASS_RE = re.compile(r"^\s*(?:(?:public|internal|abstract|sealed|static|partial)\s+)*class\s+([A-Za-z_]\w*)", re.M)
_VB_CLASS_RE = re.compile(
    r"^\s*(?:(?:Public|Friend|Partial|MustInherit|NotInheritable)\s+)*Class\s+([A-Za-z_]\w*)", re.M
)
