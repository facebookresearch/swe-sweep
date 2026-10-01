#!/usr/bin/env python3
"""Shared target discovery and runner implementation for Julia adapters."""
import json
import os
import re
import subprocess

from swesweep_eval.eval.suites.utils.logging import log

# A `.jl` file under a test directory. The gold/test split already decided what is a test
# (the crawler's ``test_globs``), so this only has to spot the test *files* in the patch.
JL_TESTFILE_RE = re.compile(r"^(?:test|tests)/.*\.jl$|^.*/tests?/.*\.jl$")
PLUSFILE_RE = re.compile(r"^\+\+\+ b/(.+)$", re.M)
# `@testset "name"` on an added line, and the same in a hunk header (the enclosing set of
# an edited test). An interpolated name (`@testset "$t"`) is deliberately not matched:
# it has no static value to filter on.
ADD_TESTSET_RE = re.compile(r'^\+\s*@testset\s+(?:[A-Za-z_][\w.]*\s+)?"([^"$]+)"')
HUNK_TESTSET_RE = re.compile(r'^@@ .*@@.*@testset\s+(?:[A-Za-z_][\w.]*\s+)?"([^"$]+)"')

ORIG_RUNTESTS = ".swesweep_orig_runtests.jl"
RESULT_JSON = "/tmp/swesweep_julia_results.json"

# The driver, installed as ``test/runtests.jl``. See the module docstring for why it is
# shaped this way. Kept as a literal so the whole runner stays a single staged file.
DRIVER = r"""
module SWESweepRun
using Test

const REPO    = ENV["SWESWEEP_REPO"]
const RESULT  = ENV["SWESWEEP_RESULT_JSON"]
const TARGETS = Set(abspath(joinpath(REPO, f)) for f in
                    split(get(ENV, "SWESWEEP_TARGET_FILES", ""), ':'; keepempty=false))

# Records every result and never throws, so a failing nested DefaultTestSet reports into
# us instead of aborting the run at the first failure.
mutable struct Recording <: Test.AbstractTestSet
    description::String
    results::Vector{Any}
end
Recording(desc::AbstractString; kw...) = Recording(String(desc), [])
Test.record(ts::Recording, t) = (push!(ts.results, t); t)
Test.finish(ts::Recording) = (Test.get_testset_depth() > 0 && Test.record(Test.get_testset(), ts); ts)

# `include` called from inside this module resolves here, so the repo's runtests.jl routes
# its own includes through us: the preamble still runs, non-targeted test files become
# no-ops. An empty TARGETS means "run everything" (the eval runner's full-suite pass).
const _real_include = Base.include
function include(path::AbstractString)
    p = abspath(isabspath(path) ? path : joinpath(REPO, "test", path))
    (isempty(TARGETS) || p in TARGETS) ? _real_include(SWESweepRun, p) : nothing
end

function walk!(out, node, prefix)
    desc = getfield(node, :description)
    name = isempty(prefix) ? desc : string(prefix, "/", desc)
    worst = "passed"; any_leaf = false
    for r in getfield(node, :results)
        if r isa Test.Pass || r isa Test.Broken
            any_leaf = true
        elseif r isa Test.Fail
            any_leaf = true; worst = (worst == "error" ? worst : "failed")
        elseif r isa Test.Error
            any_leaf = true; worst = "error"
        else
            c = walk!(out, r, name)
            worst = (c == "error" || worst == "error") ? "error" :
                    ((c == "failed" || worst == "failed") ? "failed" : worst)
        end
    end
    any_leaf && (out[name] = worst)
    return worst
end

function main()
    out = Dict{String,String}(); loaderror = false
    root = Recording("swesweep", [])
    Test.push_testset(root)
    try
        _real_include(SWESweepRun, joinpath(REPO, "test", "%ORIG%"))
    catch e
        loaderror = true
        println(stderr, "SWESWEEP LOAD ERROR: ", sprint(showerror, e))
    finally
        Test.pop_testset()
    end
    walk!(out, root, "")
    delete!(out, "swesweep")
    open(RESULT, "w") do io
        print(io, "{\"loaderror\": ", loaderror ? "true" : "false", ", \"testsets\": {")
        first = true
        for (k, v) in out
            first || print(io, ", "); first = false
            # strip the synthetic root so names read as the repo writes them
            key = startswith(k, "swesweep/") ? k[9:end] : k
            print(io, "\"", escape_string(key), "\": \"", v, "\"")
        end
        print(io, "}}")
    end
    println(stderr, "SWESWEEP recorded ", length(out), " testsets, loaderror=", loaderror)
end
end
SWESweepRun.main()
"""


# The second driver, for a suite built out of ``@safetestset``. There the whole point of
# the framework is that every test file runs in a *fresh module*, so ``runtests.jl`` is a
# list of files rather than a program — and the include-interception the driver above
# relies on does not reach into the modules ``@safetestset`` creates, so it cannot select
# anything. This driver skips ``runtests.jl`` entirely and includes each target file into
# a module of its own, which is exactly what the framework promises those files tolerate.
#
# The file's repo-relative path is the recording set's description, so a file whose tests
# are bare ``@test`` calls with no ``@testset`` around them still reports an outcome —
# under the driver above those results attach to the synthetic root and are dropped.
FILE_DRIVER = r"""
module SWESweepRun
using Test

const REPO    = ENV["SWESWEEP_REPO"]
const RESULT  = ENV["SWESWEEP_RESULT_JSON"]
# `String`, not the `SubString` `split` hands back: `gensym` below only takes a `String`.
const TARGETS = String[String(f) for f in
                       split(get(ENV, "SWESWEEP_TARGET_FILES", ""), ':'; keepempty=false)]

mutable struct Recording <: Test.AbstractTestSet
    description::String
    results::Vector{Any}
end
Recording(desc::AbstractString; kw...) = Recording(String(desc), [])
Test.record(ts::Recording, t) = (push!(ts.results, t); t)
Test.finish(ts::Recording) = (Test.get_testset_depth() > 0 && Test.record(Test.get_testset(), ts); ts)

function walk!(out, node, prefix)
    desc = getfield(node, :description)
    name = isempty(prefix) ? desc : string(prefix, "/", desc)
    worst = "passed"; any_leaf = false
    for r in getfield(node, :results)
        if r isa Test.Pass || r isa Test.Broken
            any_leaf = true
        elseif r isa Test.Fail
            any_leaf = true; worst = (worst == "error" ? worst : "failed")
        elseif r isa Test.Error
            any_leaf = true; worst = "error"
        else
            c = walk!(out, r, name)
            worst = (c == "error" || worst == "error") ? "error" :
                    ((c == "failed" || worst == "failed") ? "failed" : worst)
        end
    end
    any_leaf && (out[name] = worst)
    return worst
end

# One target file, in a module of its own -- the `@safetestset` contract. A throw escaping
# the file is a load error for that file only; the remaining targets still run.
function run_file(out, rel)
    path = abspath(joinpath(REPO, rel))
    root = Recording(rel, [])
    Test.push_testset(root)
    ok = true
    try
        Base.include(Module(gensym(rel)), path)
    catch e
        ok = false
        println(stderr, "SWESWEEP LOAD ERROR in ", rel, ": ", sprint(showerror, e))
    finally
        Test.pop_testset()
    end
    walk!(out, root, "")
    # A safetestset file is an independently runnable unit. Keep its load failure in the
    # structured result rather than making the other files' outcomes unusable. This also
    # makes the missing part of a partially executed file explicit to baseline screening.
    ok || (out[string(rel, "/<load>")] = "error")
    return ok
end

function main()
    out = Dict{String,String}(); loaderror = false
    for rel in TARGETS
        run_file(out, rel) || (loaderror = true)
    end
    open(RESULT, "w") do io
        print(io, "{\"loaderror\": ", loaderror ? "true" : "false", ", \"testsets\": {")
        first = true
        for (k, v) in out
            first || print(io, ", "); first = false
            print(io, "\"", escape_string(k), "\": \"", v, "\"")
        end
        print(io, "}}")
    end
    println(stderr, "SWESWEEP recorded ", length(out), " testsets, loaderror=", loaderror)
end
end
SWESweepRun.main()
"""


def target_tests(diff):
    """Find the ``.jl`` test files a patch touches and its ``@testset`` names.

    These are the Julia counterparts of pytest modules and test function names."""
    files = [f for f in PLUSFILE_RE.findall(diff) if f != "/dev/null" and JL_TESTFILE_RE.match(f)]
    names = []
    for line in diff.splitlines():
        m = ADD_TESTSET_RE.match(line)
        if m:
            names.append(m.group(1))
        h = HUNK_TESTSET_RE.match(line)
        if h:
            names.append(h.group(1))
    # runtests.jl is the driver's own slot, not a test file to select: a patch that only
    # registers a new file there still targets that new file, which is matched above.
    files = [f for f in files if os.path.basename(f) != "runtests.jl"]
    return sorted(set(files)), sorted(set(names))


def _install_driver(env, repo, driver=None):
    """Move the repo's ``test/runtests.jl`` aside and install ``driver`` in its place
    (the include-intercepting :data:`DRIVER` by default).
    Returns False (with a log line) if the repo has no runtests.jl to drive."""
    testdir = os.path.join(repo, "test")
    runtests = os.path.join(testdir, "runtests.jl")
    if not env.exists(runtests):
        log("no test/runtests.jl in %s" % repo)
        return False
    orig = os.path.join(testdir, ORIG_RUNTESTS)
    if not env.exists(orig):
        env.rename(runtests, orig)
    text = DRIVER if driver is None else driver
    env.write_text(runtests, text.replace("%ORIG%", ORIG_RUNTESTS))
    return True


def _restore_driver(env, repo):
    """Undo :func:`_install_driver` so the tree is the patched source again — the gold
    patch is applied onto it after state A, and a leftover driver would be part of it."""
    testdir = os.path.join(repo, "test")
    orig = os.path.join(testdir, ORIG_RUNTESTS)
    if env.exists(orig):
        env.rename(orig, os.path.join(testdir, "runtests.jl"))


def run_julia(env, repo, files, names, timeout, driver=None):
    """The one Julia test run both entry points below wrap: install the driver, drive
    ``Pkg.test()``, read the JSON back. Returns
    ``(outcomes|None, timed_out, console_text, loaderror)``; ``outcomes`` is ``None`` when
    no result file was produced at all (a harness failure, not a test outcome).

    An empty ``files`` means "run the whole suite" — that is the eval gate's visible-suite
    pass, and it is what the driver's empty-TARGETS branch does.

    ``names`` is the ``-k`` analogue: a recorded test set counts only if one of the names
    appears somewhere in its ``outer/inner`` path. With no names (nothing statically
    extractable from the diff) every test set in the targeted files counts, which is the
    same widening pytest does."""
    if env.exists(RESULT_JSON):
        env.remove(RESULT_JSON)
    if not _install_driver(env, repo, driver):
        return None, False, "no test/runtests.jl in repo", True
    command_env = {
        "SWESWEEP_REPO": repo,
        "SWESWEEP_RESULT_JSON": RESULT_JSON,
        "SWESWEEP_TARGET_FILES": ":".join(files),
    }
    # `Pkg.test()` on the activated repo builds the test environment; the driver swallows
    # test failures, so a non-zero rc here means the *harness* broke, not a failing test.
    code = 'using Pkg; Pkg.activate("%s"); Pkg.test()' % repo
    try:
        # stderr folded into stdout so the captured text reads like the real console.
        r = env.execute(
            ["julia", "--color=no", "-e", code],
            cwd=repo, env=command_env, timeout=timeout, merge_stderr=True,
        )
    except subprocess.TimeoutExpired as e:
        log("julia Pkg.test TIMEOUT after %ds" % timeout)
        partial = e.output or ""
        if not isinstance(partial, str):
            partial = partial.decode("utf-8", "replace")
        _restore_driver(env, repo)
        return None, True, partial + "\n\n[... julia timed out after %ds ...]\n" % timeout, False
    finally:
        _restore_driver(env, repo)
    log("julia rc=%d" % r.returncode)
    log(r.stdout[-1500:])
    if not env.exists(RESULT_JSON):
        log("no result JSON — treating as a harness failure")
        return None, False, r.stdout, True
    data = json.loads(env.read_text(RESULT_JSON))
    outcomes = data.get("testsets", {})
    if names:
        outcomes = {k: v for k, v in outcomes.items() if any(n in k for n in names)}
    return outcomes, False, r.stdout, bool(data.get("loaderror"))


# `include("some_test.jl")`, the only spelling a `@safetestset` suite uses to name a test
# file. A computed path (`include(joinpath(...))`) has no static value and is skipped.
SUITE_INCLUDE_RE = re.compile(r'include\(\s*"([^"]+\.jl)"\s*\)')


def suite_files(env, repo):
    """The test files the repo's own ``runtests.jl`` names, repo-relative.

    This is the whole-suite target list for :func:`run_julia_files` — the counterpart of
    the other driver's "empty TARGETS means run everything". Reading the list out of
    ``runtests.jl`` rather than globbing ``test/`` keeps the suite to what the repo
    declares, so the shared helpers and per-group fixtures beside it are not run as tests.
    """
    runtests = os.path.join(repo, "test", "runtests.jl")
    if not env.exists(runtests):
        return []
    out = []
    for rel in SUITE_INCLUDE_RE.findall(env.read_text(runtests)):
        path = os.path.normpath(os.path.join("test", rel))
        if env.exists(os.path.join(repo, path)) and path not in out:
            out.append(path)
    return out


def run_julia_files(env, repo, files, names, timeout):
    """Run each target test file in a module of its own — the ``@safetestset`` shape.

    Same contract as :func:`run_julia`, and the same empty-``files`` meaning: with no
    targets this runs the whole visible suite, resolved through :func:`suite_files`.
    Outcome keys are prefixed with the test file's repo-relative path, so both entry
    points name the same test the same way."""
    targets = list(files) if files else suite_files(env, repo)
    if not targets:
        log("no target test files and no includes in test/runtests.jl")
        return None, False, "no test files to run", True
    return run_julia(env, repo, targets, names, timeout, driver=FILE_DRIVER)
