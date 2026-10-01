# Reducing evaluator duplication in the Harbor port

Status: design options, not yet implemented

## Recommendation

Given that the expected updates are mostly changes to which subtasks count, use this path:

1. **Now:** stop rewriting `swesweep_eval.json` for selection and ignore changes. Pass a runtime policy to the already-built verifier, filter before running subtasks when possible, and optionally recompute the score on the host. This avoids image churn and needs no Harbor change.
2. **Then:** perform the obvious lazy-registry pruning and generate each minimal task bundle from one source. The remaining shared code is small enough that a more elaborate package/injection system can be deferred.
3. **Only if ownership remains painful:** materialize one local runtime or publish a shared wheel. Move to a fully host-side verifier only for broader architectural reasons, not merely to save the remaining bytes.

If individual task directories must remain directly runnable with raw Harbor, use a pinned package or prebuilt verifier image instead of mandatory materialization.

## The current problem

There are 100 Harbor task directories. Every task contains a complete evaluator under `tests/swesweep_eval/eval/`, even though each task uses only one or two suite adapters.

Current duplication includes:

- 11,900 evaluator files: 119 per task;
- about 1,672,400 repeated source lines under `tests/swesweep_eval/eval/`—16,724 lines per task;
- 100 byte-identical copies each of `host.py`, `runner_config.py`, and `repository.py`;
- 100 byte-identical copies of the 450-line `swesweep_grade.py`;
- 100 byte-identical copies of `test.sh`;
- every concrete suite adapter in every task, including irrelevant runners for other languages;
- one `tests/Dockerfile` per task that is almost the corresponding `environment/Dockerfile`, plus a common Python stage and verifier tail.

The legitimate task-specific payload is much smaller conceptually:

- `swesweep_eval.json`;
- `subtasks/<id>/test.patch`;
- runner configuration;
- upstream repository and image metadata.

Git already stores byte-identical files as one blob, so the principal cost is not Git object storage. The real costs are maintenance, review noise, possible drift, large working trees and Docker contexts, repeated task-package payloads, and having no single authoritative evaluator implementation.

## How much is actually shared?

Almost all of the executable test harness is exactly shared, rather than merely similar.

| Content | Physical source lines | Exact sharing |
|---|---:|---|
| `tests/swesweep_eval/` | 17,016 per task; 1,701,600 total | All 100 complete directory trees are byte-identical |
| `tests/swesweep_eval/eval/` | 16,724 per task; 1,672,400 total | Included in the identical runtime trees |
| `tests/swesweep_grade.py` | 450 per task; 45,000 total | All 100 copies are byte-identical |
| `tests/test.sh` | 30 per task; 3,000 total | All 100 copies are byte-identical |
| Shared runtime, grader, and launcher | 17,496 per task; 1,749,600 total | Entire shared source payload before pruning |

By bytes, the shared runtime, grader, and launcher account for 84.2% of everything under `tasks/*/tests`; the remaining large inputs are task-specific JSON and hidden patches rather than code. These current totals demonstrate the over-copying, but they should not be used to estimate the value of deduplicating an already-pruned design.

The answer therefore depends on the objective:

- **For disk space in `.git` alone:** a large redesign is not justified. Git content-addresses identical blobs, so 100 identical copies do not consume 100 times the object storage.
- **For checkout/package size:** yes in the current form. An independently archived task currently carries 17,496 lines of identical runtime and launcher code before its own configuration and patches.
- **For correctness and maintenance:** strongly yes. The evaluator is scoring-critical code; fixing it once is materially safer than regenerating or reviewing changes across 100 directories and a second public repository.
- **For runtime speed:** only modestly from source deduplication. Docker layer caching already helps. Prebuilt OCI images provide the meaningful startup/build-speed improvement.
- **For a major Harbor redesign:** deduplication alone is not enough justification. Design D is worthwhile if we also want clearer trust boundaries, provider portability, host-controlled regrading, and architectural alignment with the original evaluator.

The sensible scope is therefore to move subtask policy to runtime first, then implement B or C if source/package deduplication is desired. Design A offers limited return by itself. Prebuilt OCI images are a deployment choice, while Design D should be chosen only for architectural benefits beyond file deduplication.

### After the obvious per-task pruning

The current 17,496-line per-task runtime is not the correct number for deciding whether the *remaining* common code deserves a shared-library mechanism. Assume the obvious cleanup has already happened:

- the suite registry imports adapters lazily;
- each task carries only its selected reproduction/evaluation adapters and their transitive utilities;
- default pytest adapters are included only for tasks that use the defaults;
- unrelated concrete runners and README files are omitted.

A static import-closure estimate across all 100 current task configurations gives:

| Minimal selective bundle measurement | Physical source lines |
|---|---:|
| Code required by every task, including `swesweep_grade.py` and `test.sh` | about 1,849 lines |
| Runner-specific code above that common core | about 392 lines per task on average |
| Complete minimal task bundle | 1,933–2,838 lines; about 2,241 lines on average |
| Common core copied across 100 tasks | about 184,900 lines |
| All runner-specific copies across 100 tasks | about 39,200 lines |
| One canonical library containing every runner used by any current task | about 9,707 lines |

The universal 1,849 lines consist mainly of:

- `host.py`: 521 lines;
- `swesweep_grade.py`: 450 lines;
- the local execution session: 273 lines;
- common evaluation and pytest parsing utilities: 246 lines;
- runner configuration, repository operations, suite contracts/registry, constants, package initializers, and the shell launcher: the remaining 359 lines.

So even after pruning, the common code is approximately 82% of an average minimal bundle, but it is only about 1,849 physical lines per task. Eliminating 99 repeated copies removes about 183,000 checked-out source lines. Git already deduplicates their content internally, so the real value would be having one scoring-critical implementation and eliminating regeneration/drift across repositories.

Moving only verdict folding and score construction to the host reduces the in-container common code by roughly 188 function lines, plus a small amount of imports/constants. Most shared code is the evaluation state machine, command/session adapter, repository operations, and report parsing, which must remain available wherever test execution is controlled.

These figures are an engineering estimate from the current static import graph after modeling a lazy registry, not a promise of the exact generated artifact size. A production packager and resource tests should establish the final number.

### What is really in the common core?

The 1,849-line estimate is a conservative “obvious pruning” result, not a theoretical minimum. It still includes complete source files containing construction/reproduction paths that the Harbor grader never calls.

The actual grading algorithm can be reduced to approximately this:

```text
selected_subtasks = apply_runtime_policy(all_subtasks)
expected_visible_results = load_precomputed_baseline()

with one_clean_verifier_environment():
    setup_once()
    reset_to_base_commit()
    apply(agent_patch)
    restore_any_test_files_touched_by_agent()
    build_if_needed()

    actual_visible_results = run_visible_suite()
    regressions = compare(expected_visible_results, actual_visible_results)

    raw_subtask_results = {}
    for subtask in selected_subtasks:
        targets = runner.targets(subtask.test_patch)
        apply(subtask.test_patch)
        raw_subtask_results[subtask.id] = runner.run(targets)
        restore(files_touched_by(subtask.test_patch))

emit_raw_results(regressions, raw_subtask_results, failures, timings)
```

The baseline visible-suite run in the current implementation can disappear if the frozen image already carries a trustworthy list of expected passing outcomes. The post-agent visible run still matters: it detects regressions. Missing expected tests must count as non-passing so a patch cannot evade the gate by breaking test collection.

Beyond the skeleton, the genuinely shared behavior is:

| Shared concern | Why it exists |
|---|---|
| Agent-patch integrity | Apply the captured patch, reject apply failures, and restore test files modified by the agent so it cannot rewrite the grader's tests |
| Repository state | Reset to the baseline commit, preserve intended build artifacts, apply/revert one hidden patch at a time, and clean newly added hidden-test files |
| Build lifecycle | Run the task-declared setup once, apply build flags/environment consistently, and distinguish build failures from grader failures |
| Failure and timeout semantics | Distinguish patch failure, build failure, missing reports, test failure, timeout, and grader infrastructure failure |
| Output capture | Bound very large logs, preserve invalid text safely, and associate output with the visible suite or subtask |
| Outcome normalization | Turn framework-specific reports into the common `test_id -> passed/failed/error` representation |
| Result integrity | Require every selected subtask to appear in the verdict and record exact selection, timings, patch status, and errors |

The runner-specific portion is mostly `targets(test_patch)`, `run_visible_suite()`, `run_selected()`, and report parsing for pytest/Jest/Cargo/Maven/etc. Everything else above is common orchestration or policy.

The common-code budget can be tightened further:

| Step | Approximate physical source lines copied into each verifier |
|---|---:|
| Obvious lazy-registry/per-task pruning | about 1,849 lines |
| Also remove unused base-screen, gold-compatibility, and reproduction entry points; use precomputed baseline outcomes | about 1,530 lines |
| Also move verdict folding, score construction, and rich result formatting to one host-side postprocessor | about 1,340 lines in the verifier, plus roughly 190 function lines once on the host |

The last numbers are conservative source subtraction from the current implementation, not the result of a completed rewrite. Splitting mixed-purpose utility modules and replacing the compatibility-oriented `ContainerSession` with a smaller local command helper could reduce the common in-container portion further, probably to roughly 1,000–1,250 physical lines. That is not merely the score formula: it includes orchestration, repository safety, process management, failure semantics, and report normalization.

This makes the decision fairly narrow: after obvious pruning, full deduplication removes roughly 1,300–1,850 copied source lines per task, depending on how much logic moves to the host. Keeping generated copies is reasonable if CI guarantees they come from one source. Moving scoring to the host is useful for flexible ignore policies, not because the scoring code itself is large.

### Which strictly shared code is likely to change?

Most future policy changes should not require editing the shared execution engine at all. Once an ignore/selection input exists, changing the IDs is per-task or per-run data and is therefore excluded from this table.

| Shared area | Current scale | How likely to change | How task-specific | Plausible future changes |
|---|---:|---|---|---|
| Verdict and score folding | About 190 function lines in `swesweep_grade.py` | Unlikely | shared | Change denominator rules, partial credit, F2P/P2P reporting, visible-regression gating, or emitted metrics. |
| Evaluation state machine | About 178 lines for the current `evaluate_in_container()` before removing the baseline phase | Unlikely | shared | Change ordering, batching, rebuild policy, patch isolation, or behavior after failures/timeouts. |
| Repository and patch integrity | 70 lines in `repository.py`, plus roughly 31 function lines for touched/test-file detection | Unlikely | Mostly shared. The build command and test-directory rules are task-specific configuration. | Change reset/clean behavior, agent-test restoration, patch application, or build invocation. |
| Suite configuration and contracts | 220 lines across the current runner config, suite base classes, and registry | Changes when a new runner cannot fit the existing suite interface or a new common setup/build option is required. | The interfaces and loader are shared; suite selection and option values are task-specific. Individual adapter implementations are excluded from this row. | Add a build/setup option or a capability required by multiple runner families. Reproduction-only pieces can be removed from an evaluation-only bundle. |
| Bundle/bootstrap and result I/O | Roughly 260 lines in `swesweep_grade.py` outside score-folding functions | Changes when Harbor artifact paths, the bundle schema, runtime-policy transport, or result files change. | The loader/writer is shared; bundle contents, artifact paths, and selected subtasks are task/run data. | Change bundle-schema validation, artifact locations, runtime-policy loading, output files, or grader-failure reporting. Shared-mode patch extraction and some CLI compatibility code are optional, not irreducible. |
| Generic output helpers | About 63 function lines for test-file detection, touched-file extraction, pass-set construction, and bounded output capture | Expected to remain stable except for logging limits, output corruption, or test-file classification bugs. | Mostly shared. A task may supply extra test directories; framework report parsing is runner-specific and excluded. | Change truncation, test-file detection, or generic outcome handling. Pytest execution/parsing belongs to the pytest runner after utility modules are split. |
| Local process/session adapter | 273 lines today | Changes for runtime/platform bugs involving subprocesses, signals, permissions, or filesystem behavior—not for scoring changes. | Shared by all tasks under the current in-container A–C designs. It is architecture-specific rather than benchmark-specific and disappears from task bundles under host-side Design D. | Fix timeout/process-group behavior, environment propagation, permissions, output decoding, or filesystem operations; it could also be replaced by a smaller local-only helper. |

Not included as strictly shared code:

- ignored/selected subtask IDs and precomputed baseline outcomes, which are task/run data;
- `targets()` and report parsers for pytest, Jest, Cargo, Maven, etc., which are runner-specific;
- base screening, gold compatibility checks, and reproduction/census entry points, which are not needed by the evaluation-only Harbor grader;
- the registry's unused runner imports, which disappear under lazy loading.

For the anticipated “ignore some subtasks” work, only a small shared selection parser/filter—likely tens of lines plus tests—needs implementation. Each task or run then supplies its own IDs. Updating those IDs changes zero shared source lines and zero image layers. Host-side score folding is useful only if the definition of the score changes, not when the same scoring function receives a different per-task exclusion list.

### Can the shared behavior be enforced with shared tests?

Yes. Test source does not need to be copied into every task. Use one repository-level test suite with several scopes:

| Test layer | Runs against | What it proves |
|---|---|---|
| Core state-machine tests | One fake session/repository | Exact reset/apply/build/run/revert ordering; agent test files are restored; every selected subtask produces a result; failure and timeout branches are classified correctly |
| Scoring-policy tests | Plain synthetic verdict dictionaries | Visible-regression gate, denominator/exclusion behavior, resolved/partial status, F2P/P2P splitting, grader failure versus agent score zero, and deterministic result serialization |
| Execution-session contract tests | Each backend implementation once | Shell versus argv execution, cwd/env propagation, output decoding, timeout/process-group cleanup, file operations, and permissions |
| Runner-adapter tests | Each distinct runner type once | `targets()` selection and parsing representative pytest/Jest/Cargo/Maven/etc. output into the common outcome schema |
| Task-data validation | One parameterized test over all task directories | Selected suite exists, options validate, ignored IDs exist, hidden patches are present, precomputed baseline IDs are well formed, and evaluator API versions match |
| Generated-bundle validation | One parameterized test over all task directories | Regenerating the minimal closure from the canonical source produces exactly the checked-in files and bytes; no unrelated runner was copied |
| Environment integration | Individual task images, preferably release/nightly | The real repository builds, hidden patches apply, declared test commands exist, and the precomputed baseline still matches the frozen image |

The first six layers use one shared body of tests. A parameterized test may produce 100 cases, but there are not 100 copies of its source. For example:

```python
@pytest.mark.parametrize("task_dir", task_directories())
def test_generated_verifier_is_current(task_dir):
    expected = generate_minimal_verifier(task_dir)
    assert_tree_equal(expected, task_dir / "tests")
```

With today's unpruned bundles, the generated-bundle check can simply compare every supposedly shared file to a canonical manifest/hash. After pruning, the same test computes the expected transitive runner closure and checks both that required files exist and irrelevant files do not.

Some validation is inherently per task because task images contain different languages, dependencies, build commands, patches, and upstream test suites. That does not require per-task test *implementations*: one common integration driver can parameterize over task metadata. Expensive real-container checks can run at release time or on a rotating matrix, while static bundle/data validation runs on every change.

For ignored subtasks specifically, shared unit tests cover parsing, validation, filtering, denominator changes, and recording the policy. The only per-task cases are data checks that each ignored ID actually exists. No image build is needed for those checks.

## Why the Harbor port currently needs copies

The pinned Harbor revision handles a separate verifier as follows:

```text
task/tests directory
        |
        | used as Docker build context
        v
separate verifier image
        |
        | model.patch transferred after inference
        v
/tests/test.sh runs with no network
```

For a separate verifier, Harbor:

1. builds the verifier from the task's `tests/` directory;
2. starts it as a fresh environment after the agent finishes;
3. transfers declared artifacts such as `model.patch`;
4. assumes `/tests` was baked into the image and does not upload it again.

This is a good security boundary: the agent cannot inspect hidden tests and cannot persist changes into the verifier container. The downside is that each `tests/` directory must currently be a closed Docker build context. It cannot `COPY` a shared directory from the repository root.

Cross-directory symlinks do not fix this. Harbor rejects input links that resolve outside the task, Docker build contexts cannot read their parents, and a published task archive would contain broken links.

### Harbor environments are not fundamentally Docker containers

Harbor operates on a `BaseEnvironment` abstraction. The installed revision supports Docker and Podman as well as Apple Container, Singularity, cloud/sandbox providers such as Daytona, E2B, Modal, Runloop, EC2, and GKE, plus a custom environment import path.

For **this repository's current runs**, however, both phases are Docker-backed:

- no alternative environment type is selected, so Harbor defaults to Docker;
- the task's agent environment is built from `environment/Dockerfile`;
- `environment_mode = "separate"` makes the verifier a second, fresh Docker environment built from `tests/Dockerfile`.

If verifier mode were `shared`, verification would run in the agent's existing environment rather than a second container. A custom verifier class itself runs in the Harbor host process, although any repository commands it issues still run through the selected environment provider.

### What actually causes an image rebuild?

Harbor's Docker backend tags images by a content hash of the Dockerfile and complete build context. The agent and separate verifier have different contexts:

| Change | Agent image | Separate verifier image today |
|---|---:|---:|
| Instruction text, timeout, resource limit, scoring display | Unchanged | Unchanged unless copied into `tests/` |
| `environment/Dockerfile` or its context | New image | Usually also new, because its contents are duplicated in `tests/Dockerfile` |
| Evaluator source or `test.sh` | Unchanged | New content-addressed image |
| Hidden `test.patch` or `swesweep_eval.json` | Unchanged | New content-addressed image |
| Current `--bugs` or `--build-jobs` override | Unchanged | New image, because `configured_task()` rewrites `swesweep_eval.json` |
| Runtime environment variable | Unchanged | Unchanged |
| Host-only postprocessing policy | Unchanged | Unchanged |

“New image” does not mean a cold rebuild from the first instruction. Docker/BuildKit still uses its layer cache. In the current verifier Dockerfiles, task data enters only at the final `COPY . /tests`, so changing a selected subtask normally reruns the Docker build command and creates a new content-addressed tag, but the expensive source clone, dependency installation, and task-build layers should be reused. Usually only the final copy/chmod layers change.

This is still avoidable churn. Selection, ignore lists, build parallelism, or scoring weights are run policy, not image contents. Passing them after container creation avoids even the cheap rebuild and stops accumulating image variants.

## Network and Python constraints

Installing a library during image construction is technically possible.

Every current verifier Dockerfile already downloads a pinned standalone Python 3.12 and copies it to `/opt/swesweep/python`. The verifier does not need another Python installation.

Harbor applies `network_mode = "no-network"` while inference and verification run. Docker image construction happens earlier and already uses network access for Git clones, OS packages, language dependencies, and the standalone Python archive. A package may therefore be fetched during the image build without enabling network access during inference.

That does not make an unpinned `pip install` acceptable. A benchmark release must pin an immutable wheel or image by version and SHA-256/digest, and it should support prefetched artifacts for air-gapped builds.

### Coexisting with a task's Python

The current setup already solves most Python-version conflicts by using two distinct interpreters:

```text
/opt/swesweep/python/bin/python3   evaluator Python 3.12
/usr/bin/python, python, venv     task/project Python, version chosen by the task image
```

All 100 verifier Dockerfiles copy the standalone interpreter to `/opt/swesweep/python`, and all 100 launchers select it explicitly. They do not add it to `PATH` and do not set `PYTHONHOME`. Commands launched by suite adapters, such as `python -m pytest`, still resolve through the task image's normal `PATH` and use the task's own Python and dependencies.

Installing the evaluator wheel with this exact command targets only its private interpreter:

```text
/opt/swesweep/python/bin/python3 -m pip install ...
```

It does not modify the task's system Python or virtual environment. In that form, coexistence is mostly the same issue already present today: the verifier already executes its controller with the standalone Python while project tests use the task runtime.

There are still avoidable hazards:

- Never invoke bare `pip` or install into the task's Python. That could upgrade pytest or another task dependency and change test results.
- Prefer a stdlib-only, pure-Python evaluator wheel installed with `--no-deps`. Installing the complete original package would pull Pydantic/PyYAML; Pydantic's compiled `pydantic-core` also introduces platform/ABI concerns.
- Require a wheel rather than an sdist so pip never creates a build environment or fetches build dependencies.
- Protect the evaluator from task-defined `PYTHONPATH`, user site packages, and similarly named modules. For an installed wheel, launch it with isolated mode, for example `/opt/swesweep/python/bin/python3 -I -m swesweep_eval`.
- If Design B copies source rather than installing it, use a tiny isolated bootstrap that explicitly inserts the trusted runtime directory into `sys.path`; do not rely on a task-controlled `PYTHONPATH`.
- Keep the evaluator namespace distinct from likely project packages and from the two existing `swesweep` distributions.
- The standalone interpreter itself must match the container's architecture and libc. That compatibility requirement already exists in the current verifier images; a wheel does not create it, though binary wheel dependencies would make it harder.

Thus, installing into `/opt/swesweep/python` is safe and isolated. Installing into whatever `python` happens to be present in a task image is not.

## Why the original package is not drop-in today

The original `/Users/klieret/Documents/repos/swe-sweep-iclr-2027/` code has the correct evaluation logic, but installing it unchanged inside the verifier would not work:

- its `ContainerSession` starts and controls a Docker or Podman container from the host;
- the Harbor verifier is already inside the clean task container and needs the port's local-process session;
- the Harbor-specific bundle loader, artifact handling, reward writer, and `grader_failed` behavior live in `swesweep_grade.py`;
- the original package has Pydantic and PyYAML dependencies, while the copied verifier runtime is stdlib-only;
- both repositories currently use the normalized distribution/package name `swe-sweep`/`swesweep`, which makes two independently published packages ambiguous.

The reusable core should first accept an execution backend instead of importing a concrete container implementation:

```text
task data
   |
   v
grader frontend -> evaluator core -> execution-session interface
                                      |       |        |
                                    local   Docker   Harbor
```

Ideally, a small `swesweep-eval-core` package becomes the single owner across both repositories. The original CLI and Harbor adapter should be frontends to that package, not independently editable forks.

## Requirements for every design

Any accepted design should preserve these properties:

1. The agent cannot read hidden tests, gold patches, or verifier-only data during inference.
2. Verification runs without network access.
3. Scoring uses a fresh environment rather than an agent-controlled container.
4. The exact evaluator revision is immutable and recorded in results.
5. A missing or incompatible evaluator is a grader failure, not a score of zero.
6. Captured patches can be regraded without rerunning the agent.
7. Results remain compatible with the original evaluator's scoring semantics.
8. Task-specific behavior stays declarative; Python files do not become subtly task-specific forks.

Every bundle should declare a compatibility version and exact runtime revision:

```json
{
  "evaluator_api": 1,
  "evaluator_revision": "<commit or wheel SHA-256>"
}
```

The runtime must fail closed on a mismatch and record the same identifiers in `eval.json`.

## Comparison

### Executive summary of every strategy

- **A. Pruned generated bundles:** Keep every task fully self-contained, but generate only the common core and suite adapters that task actually uses. This is the safest incremental cleanup, although shared code still appears as generated copies across tasks.
- **B. Local materialization:** Store one runtime in the repository and copy it into a temporary complete Harbor task just before evaluation or export. This gives the best immediate reduction without a registry or Harbor change, at the cost of requiring `sweep eval` or `sweep task export` instead of running the lean source task directly.
- **C. Pinned wheel install:** Extract one package shared by the original and Harbor repositories, then install its exact wheel while building each verifier image. Tasks remain independently buildable and verification remains offline, but image builds depend on a pinned artifact source or a vendored wheelhouse.
- **D. Host-side Harbor verifier:** Keep evaluator control on the host and send only commands and patches into a fresh Harbor-managed task environment. This removes the evaluator and Python runtime from task images and is the cleanest long-term architecture, but completing it requires an async evaluator refactor and a small Harbor enhancement.

## Design A: prune each self-contained task bundle

### Idea

Keep the current task format, but copy only the evaluator modules needed by that task. Treat all copied files as generated outputs from one canonical source.

For example, a pytest task would contain the common state machine, base contracts, pytest reproduction/evaluation adapters, and their utilities—not Cargo, Maven, Jest, Julia, and every other adapter.

### Implementation

1. Move the current transformed evaluator to a canonical `runtime-src/` directory.
2. Make suite registration lazy. Replace eager class imports in `concrete/__init__.py` with import strings resolved through `importlib`.
3. Define suite dependencies in a checked-in manifest rather than guessing them from source text. Include non-Python resources such as `qunit_runner.cjs`.
4. Add `sweep task regenerate` to read each `swesweep_eval.json`, resolve default and nested suites, compute the dependency closure, and write the minimal runtime tree.
5. Mark generated files with the evaluator revision and a “do not edit” header.
6. Add `sweep task check-generated` to regenerate in a temporary directory and compare names, modes, and bytes in CI.

Conceptual dependency declaration:

```toml
[suite.pytest]
modules = ["concrete.pytest", "utils.pytest", "utils.logging"]

[suite.pytest-eval]
modules = ["concrete.pytest_evaluation", "utils.evaluation", "utils.pytest"]

[suite.reproduction]
modules = ["concrete.reproduction_evaluation"]
```

### Validation

- Import and instantiate every suite from a directory containing only its declared dependency closure.
- Test default/null suite selection and nested suites.
- Compare normalized results for empty, invalid, partial, regression-causing, and gold patches.
- Regenerate all task bundles in CI and reject drift.

### Benefits

- Lowest implementation risk.
- Tasks remain independent, source-only Harbor packages.
- No new network or packaging dependency.
- Much smaller task bundles and import surfaces.

### Drawbacks

- Core changes still update up to 100 generated locations.
- The verifier Dockerfiles remain duplicated.
- This is generated duplication rather than true runtime sharing.

Choose this when self-contained task directories are mandatory and the smallest possible change is preferred.

## Additional design decision: move runtime policy out of the image

### Idea

Keep the current copy-to-verifier and local-execution design, preferably after Design A's obvious pruning. Treat the verifier image as a stable evaluator for the full task population. Subtask inclusion, exclusions, build parallelism, and scoring rules become runtime inputs rather than files baked into the image.

This is a weaker version of Design D: a container still runs the complete evaluation state machine and tests. The host performs only configuration and, optionally, pure postprocessing of the emitted outcomes. No async conversion of the suite adapters is required.

### The immediate fix for ignored subtasks

Current `sweep eval --bugs ...` creates a temporary task and rewrites `tests/swesweep_eval.json`. Because that file is in the verifier Docker build context, Harbor sees new content and creates a new verifier image tag.

Instead:

1. Keep one immutable `swesweep_eval.json` containing every available subtask.
2. Pass `selected_subtasks`, `ignored_subtasks`, and `build_jobs` as verifier runtime configuration.
3. Have `swesweep_grade.py` validate that every requested ID exists, filter `bundle["subtasks"]`, and only then call `stage_instance()` and `run_evaluator()`.
4. Record the complete selection and policy revision in `eval.json`.

For short lists, Harbor's existing verifier environment support is enough:

```text
--verifier-env SWESWEEP_SELECTED_SUBTASKS=id1,id2,id3
--verifier-env SWESWEEP_IGNORED_SUBTASKS=id4,id5
--verifier-env SWESWEEP_BUILD_JOBS=4
```

Environment values are applied when the verifier runs and are not part of its Docker build context, so they do not invalidate the image.

For larger or structured policies, use a small custom host verifier wrapper:

1. `SweepPolicyVerifier` receives the policy through verifier kwargs or a host file.
2. Before running `/tests/test.sh`, it uploads `runtime_policy.json` into the already-started separate verifier environment.
3. It delegates execution and log collection to Harbor's normal `Verifier` implementation.
4. The in-container grader reads the runtime policy and emits raw, per-subtask outcomes.
5. The wrapper reads `eval.json`, applies any purely scoring-level exclusions/weights, and returns the final Harbor `VerifierResult`.

The wrapper is small because it does not drive repository commands. The existing in-container state machine remains unchanged.

### Selection versus postprocessing

There are two different meanings of “ignore”:

- **Do not count a subtask:** the container may run everything and the host can remove ignored subtasks from the denominator afterward. This is the smallest implementation, but wastes test time.
- **Do not run a subtask:** pass the exclusion list into the container and filter before staging/running hidden tests. This saves time and still avoids an image rebuild.

Visible base-test exclusions are not necessarily pure score postprocessing because they participate in regression gating. Pass those into the container before evaluation unless the raw baseline/post-patch outcomes are sufficiently complete to reproduce the gate exactly on the host.

Do not let the displayed local score disagree with Harbor's recorded reward. If the host changes the score, use the custom verifier wrapper so its returned `VerifierResult` is the authoritative Harbor reward; merely rewriting a report after the Harbor job ends would leave inconsistent job summaries.

### Source ownership

For the minimal 1,933–2,838-line task bundles, the simplest maintenance arrangement may be:

- one canonical runtime source;
- generated, selectively pruned task copies;
- a CI regeneration check;
- no wheel, registry, or Harbor patch.

Git already deduplicates the common blobs. This keeps task archives independent while ensuring developers edit one source. It does not reduce checkout size as much as Design B, but after pruning the remaining duplication is about 1,849 lines per task, or 184,900 lines across all 100 task trees.

### Rebuild behavior

With runtime policy, these changes require no image rebuild:

- ignoring or restoring a subtask;
- evaluating only a selected subset;
- changing denominator/weighting rules handled by the host policy;
- changing build parallelism;
- changing report presentation.

A verifier image still changes when executable evaluator code, a hidden patch, the fixed task configuration, or the task environment changes. Docker layer caching normally limits a test-data change to the final `COPY . /tests` layer.

### Benefits

- Directly solves the expected frequent update: changing ignored subtasks.
- No Harbor core change and no suite async refactor.
- Keeps the proven separate-container security boundary.
- One stable verifier image per task across many scoring policies.
- Compatible with generated minimal self-contained tasks.

### Drawbacks

- Common code still appears in each exported task, though only about 1,849 physical source lines after pruning.
- A custom wrapper is needed if host postprocessing must change Harbor's authoritative reward.
- Policy and evaluator API versions must be recorded together for reproducible regrading.
- New or corrected hidden test patches still require a verifier-image update.

For the expected workload, this is the recommended first implementation regardless of which design is chosen for code distribution.

## Design B: copy one local runtime while materializing the task

### Idea

Keep one evaluator runtime in the installed `sweep` package. Before invoking Harbor, construct a temporary standard Harbor task and copy the runtime into its `tests/` build context. Generate the verifier Dockerfile from the environment Dockerfile at the same time.

This uses copying where it is appropriate: as an ephemeral build step, not as the repository's source-of-truth structure.

### Source and generated layouts

```text
src/swesweep/
  verifier_runtime/
    grade.py
    eval/...
    infra/local_session.py
    resources/qunit_runner.cjs
  verifier_templates/
    test.sh
    python-stage.Dockerfile
    verifier-tail.Dockerfile

tasks/swe-sweep__astropy/tests/
  swesweep_eval.json
  subtasks/.../test.patch
```

At run time, the materializer creates:

```text
<tmp>/swe-sweep__astropy/tests/
  Dockerfile
  test.sh
  _runtime/swesweep_verifier/...
  swesweep_eval.json
  subtasks/...
```

### Implementation

1. Move `swesweep_grade.py` and the evaluator tree into one importable, stdlib-only runtime package.
2. Make `python -m swesweep_verifier.grade` the common entry point.
3. Change `configured_task()` so it always yields a complete temporary task, not the original directory.
4. Apply `--bugs` and `--build-jobs` overrides in that temporary copy.
5. Copy runtime package resources into `tests/_runtime` and set `PYTHONPATH=/tests/_runtime` in the generated image.
6. Generate `tests/Dockerfile` from `environment/Dockerfile`, inserting the existing pinned Python stage at a required marker and appending the common verifier tail.
7. Write a manifest with the evaluator API, source revision, and SHA-256 of injected files.
8. Validate the materialized task with Harbor before running it.

The generated tail remains simple:

```dockerfile
COPY --from=swesweep-python /opt/swesweep/python /opt/swesweep/python
COPY . /tests
ENV PYTHONPATH=/tests/_runtime
RUN chmod +x /tests/test.sh
```

No pip installation or runtime download occurs.

### Standalone task export

Lean source task directories would no longer work directly with raw Harbor. Preserve that use case explicitly:

```text
uv run sweep task export astropy --output dist/tasks/swe-sweep__astropy
uv run sweep task export --all --output dist/tasks
```

Harbor Hub publication consumes exported task directories. The same deterministic materializer serves local evaluation and release builds.

### Validation

- Materialize the same task twice and require identical bytes and modes.
- Test materialization from both an editable checkout and an installed wheel using `importlib.resources`.
- Compare generated verifier images and normalized evaluation results with the current tasks.
- Verify the agent image contains neither `_runtime` nor hidden test data.
- Export and load all 100 tasks with Harbor in CI.

### Benefits

- One maintained evaluator copy.
- No package registry or network dependency.
- Removes committed duplicate verifier Dockerfiles too.
- Fits the existing `sweep eval` wrapper and its temporary-copy mechanism.

### Drawbacks

- Raw source task directories require `sweep task export` first.
- Publication must never bypass the materializer.
- Dockerfile generation needs strict markers and broad CI coverage.
- If the shared code lives only here, the original repository still has another copy. Prefer consuming a shared package or mechanically syncing from its pinned source.

This is the recommended next step only if eliminating the remaining generated copies is worth changing the raw-task workflow. For subtask-ignore updates alone, runtime policy is sufficient.

## Design C: install a pinned shared wheel during image construction

### Idea

Publish a small evaluator distribution, install it into each verifier image during `docker build`, and keep only task data plus a thin launcher in each task.

The package should contain the evaluator core, suite adapters, local execution backend, fixture loader, result writer, and package resources. It should exclude task data, Docker control, crawling, dashboards, and unrelated authoring tools.

### Installation modes

There are three practical modes:

1. **Vendored wheelhouse:** release tooling copies the wheel and dependencies into the build context. Builds work offline, but each exported task archive contains the wheel unless Harbor supports shared assets.
2. **Immutable release URL:** the Docker build downloads a wheel and verifies its SHA-256. Source tasks stay small; the first build needs network.
3. **Package index:** install from a hash-locked requirements file. Convenient, but less robust than a content-addressed release artifact.

Never use an unconstrained `pip install swe-sweep` in a benchmark image.

Conceptual offline-wheelhouse installation:

```dockerfile
COPY --from=swesweep-python /opt/swesweep/python /opt/swesweep/python
COPY wheelhouse/ /opt/swesweep/wheelhouse/
RUN /opt/swesweep/python/bin/python3 -m pip install \
      --no-index --no-deps \
      /opt/swesweep/wheelhouse/swesweep_eval_runtime-0.2.0-py3-none-any.whl \
 && rm -rf /opt/swesweep/wheelhouse
COPY . /tests
RUN chmod +x /tests/test.sh
```

### Required refactor

The original evaluator must accept an injected session backend. The standalone CLI supplies the Docker/Podman backend; Harbor supplies the local-process backend. The Harbor grading wrapper moves into the package rather than remaining in each task.

Use a dedicated distribution name such as `swesweep-eval-runtime`, or merge ownership of the current two `swe-sweep` distributions. Do not publish two different projects under names that normalize to the same package name.

Keep the runtime pure Python if possible. If it retains Pydantic or PyYAML, pin and hash the full wheel closure.

### Versioning and release

- Give the package a semantic version.
- Record the exact wheel SHA-256 in task metadata and results.
- Reject evaluator API mismatches as infrastructure failures.
- Publish provenance and an SBOM.
- Test a built verifier under `--network=none`.
- Retain immutable artifacts for historical regrading.

### Benefits

- One implementation shared by the original and Harbor repositories.
- Independently distributed task directories remain usable.
- Runtime verification stays offline.
- Normal Python packaging handles versions and resources.

### Drawbacks

- Initial builds depend on an artifact host unless a wheelhouse is included.
- Supply-chain and retention become benchmark infrastructure concerns.
- This does not remove the duplicated verifier Dockerfiles by itself.
- Installing the original package is not possible until its container backend and Harbor frontend are separated.

Choose this when independent source task packages matter more than zero build-time dependencies.

### Note on prebuilt images

Harbor can use prebuilt agent and verifier images instead of building their Dockerfiles on demand. Images can be pinned by digest, pulled or preloaded before evaluation, and share common filesystem layers in the registry and local container store.

This is useful for release reproducibility and startup speed, but it does not change how evaluator code is organized or where scoring runs. It can be applied later to A, B, or C, so it is not treated as a separate design here.

## Design D: run a custom verifier on the Harbor host

### Idea

The evaluator is control-plane code and does not fundamentally need to live inside the task container. Harbor already loads custom verifier classes on the host. A `SWESweepVerifier` can read task metadata and hidden patches from the host while sending only repository commands and staged patches into a fresh verifier environment.

This most closely matches the original architecture: one host controller evaluates many heterogeneous containers.

### Stage 1: works with current Harbor

Add this to the Harbor invocation:

```text
--verifier swesweep.harbor_verifier:SWESweepVerifier
```

`SWESweepVerifier` subclasses Harbor's `BaseVerifier`. Its `verify()`:

1. reads `swesweep_eval.json` and hidden patches through `self.task.paths`;
2. reads the collected model patch from the trial artifacts;
3. uploads the required patch data into `self.environment`;
4. runs repository commands through `self.environment.exec()`;
5. computes the verdict on the host;
6. writes `eval.json` and `eval_output.json` through `self.trial_paths`;
7. returns `VerifierResult(rewards=...)` directly.

Keep `environment_mode = "separate"`. Current Harbor still builds that separate environment from `tests/Dockerfile`, so this stage retains the duplicated task environment definition. It removes the standalone Python, evaluator source, `swesweep_grade.py`, and executable verifier script from the image.

### Async evaluator refactor

Harbor's environment API is asynchronous while the current evaluator is synchronous. Introduce an async session protocol:

```python
class ExecutionSession(Protocol):
    async def execute(...): ...
    async def upload_dir(...): ...
    async def exists(...): ...
```

Provide three implementations:

- `HarborExecutionSession` around `BaseEnvironment`;
- `SubprocessExecutionSession` for local in-container execution;
- `ContainerExecutionSession` for the original Docker/Podman CLI.

Port the state machine and suites to `await` the protocol. The standalone synchronous entry point may call `asyncio.run()` once at its outer boundary. The Harbor verifier must await the core directly because Harbor's event loop is already active.

### Stage 2: a small Harbor enhancement

Add an environment source setting:

```toml
[verifier]
environment_mode = "separate"
environment_source = "task"  # new; default remains "tests"
```

Semantics:

- `tests` retains current behavior and builds from `tests/`.
- `task` starts a fresh environment from the top-level `environment/` definition.
- It may reuse the built image/cache, but it always creates a distinct container/session.
- Artifact collection completes before the fresh verifier starts.
- The default shell verifier uploads `tests/` after startup.
- A custom host verifier can read task data directly and upload only what its commands need.

The narrow implementation point is Harbor's `_verifier_env_build_context()`, which currently always selects `task.paths.tests_dir`. It should select `task.paths.environment_dir` for the new mode and stop forcing `skip_tests_upload=True` when the default verifier needs uploaded tests.

SWE-sweep's custom host verifier needs no Python interpreter or test runner inside the environment, so after this change all `tests/Dockerfile` files can be removed.

### Security validation

Test with a deliberately malicious agent action that:

- leaves background processes running;
- replaces tools through `PATH`;
- modifies global Git configuration;
- writes fake `/tests` and reward files.

None of those changes may appear in the verifier environment, and the agent must not be able to write the host-produced result files.

Also add backend conformance tests for command arguments, shell mode, working directories, environment variables, output decoding, timeouts, process-group cleanup, file operations, uploads, and permissions.

### Benefits

- One host evaluator; tasks contain only declarative data.
- No evaluator or Python runtime in task images.
- No verifier Dockerfile after the Harbor enhancement.
- Strong isolation and regrading remain intact.
- Clear ownership: Harbor manages environments; SWE-sweep manages scoring.

### Drawbacks

- The async evaluator conversion is substantial because all suite adapters execute commands.
- Generic Harbor users must install and select the custom verifier plugin.
- The final form needs a new Harbor setting and provider-level tests.
- Workers must pin the host package as carefully as an in-image package.

This is the recommended long-term architecture.

## Decision guide

### First separate the two decisions

Runtime policy is not a competitor to A, B, C, or D. It answers a different question:

- **The additional runtime-policy decision determines when subtask/scoring policy is supplied:** at runtime, so changing an ignore list does not change an image.
- **A/B/C decide how in-container evaluator code is distributed:** generated files, temporary materialization, or a wheel.
- **D decides where evaluation control runs:** on the host instead of inside the verifier environment.

Runtime policy should be adopted regardless of which in-container distribution strategy is chosen. The main distribution choice is therefore among A, B, and C; D is the larger alternative that moves control to the host.

### Advantages and disadvantages

| Design | Shared code between tasks | Integrity checks for shared evaluation behavior | Description | Advantages | Disadvantages | Pick when |
|---|---|---|---|---|---|---|
| **X. Completely independent** | everything independent, shared behavior is duplicated | just separate tests asserting behavior separately | every task fights for itself | Strictly no issues with python versions/containers not having python, complexity from refactorings etc. | Somewhat harder to argue about the correctness. | We deem most things to be independent anyway and might just as well assert behavior independently for every task |
| **A. Minimal generated bundle** we have a copy of shared files for every task (basically what we have, but we can slightly improve by at least not copying over files that are clearly not needed) | shared behavior duplicated as exact shared files | Check that shared files are identical with CI; shared files are unit teststed in one location | Kinda like now, except we cut down on the duplication a bit by only copying what we need. | Keeps `harbor run --path <task>` working with no preparation, package download, or Harbor change.  Compared to C: Can make exceptions for some tasks and not ship pythone everywhere. Immediately see what tasks have changed. | Every evaluator change regenerates many paths.  Compared to E: Need python in every container by default | There's no issue with building eval around python |
| **B. Local materialization** | Duplicated Tracked in one place, until export function is called | Shared | Like now, but we keep everything in one `shared/` folder; then there is a `sweep export` step to populate everything before people run. | Compared to A: Slightly cleaner because there's never any duplicated things tracked, otherwise same. Not sure how big of an advantage that actually is | Not directly ingestible by harbor | ? |
| **C. Pinned wheel installed in the verifier image** | Tracked in python package | Shared | `pip install swesweep` from within Harbor when we run: distribute SWE-sweep as a PyPI package, then install it inside the verifier containers during Harborization. | ? | More maintenance for pip releases & versioning. Strictly need python installation within container | ? |
| **D. Host-side Harbor verifier** | Backed into library | Shared | Like the internal Pandora repository. | Removes evaluator Python from task images. One host controller can apply selection/scoring policy and drive a fresh Harbor environment through `BaseEnvironment`, matching the original evaluator architecture and supporting non-Docker providers. Regrading logic and authoritative reward construction remain centralized on the host. | Very far from how harbor works today | ? |

Git object size should not drive the choice: it already deduplicates identical generated blobs. The meaningful differences are task portability, number of maintained/generated paths, external package infrastructure, and whether evaluation control stays inside the verifier environment.

copy of table, keep for now for backup

| Design                                                       | Engineering effort                            | Operational burden | Maintained source duplication       | Physical common code after pruning      | Best reason to choose it                                     |
| ------------------------------------------------------------ | --------------------------------------------- | ------------------ | ----------------------------------- | --------------------------------------- | ------------------------------------------------------------ |
| A. Minimal generated bundle (kinda like now, except we cut down on the duplication a bit by only copying what we need) | Low–medium                                    | Low                | None if generated and checked in CI | only minimal shared code is duplicated  | Keep conventional, self-contained task directories, closest to normal |
| B. Local materialization (like now, but we keep everything in one shared/ folder, then there's a `sweep export` step to populate everything before people run) | Medium                                        | Low                | None                                | One source copy; temporary build copies | This repository/CLI is the product boundary                  |
| C. Pinned wheel, i.e., `pip install swesweep` from within harbor when we run  (distribute swe-sweep as pypi thing and then for the harborication, it pip installs things within the containers) | Medium                                        | Medium             | None across both repositories       | One installed copy per image            | Independent task packages plus shared package ownership      |
| D. Host-side verifier (like internal pandora repo)           | High, because harbor isn't really made for it | Medium             | None                                | No evaluator in task images             | Cleaner architecture and provider abstraction                |

### What matters for the expected ignore-list changes

If the main maintenance action is “ignore these subtasks now,” none of B–D is required.

Pass the policy after the verifier starts:

```text
stable task image
    + runtime ignored_subtasks policy
    -> filter before executing hidden tests
    -> record raw outcomes and selected denominator
    -> optional host rescore
```

This has the useful properties directly relevant to that work:

- no change to `swesweep_eval.json`;
- no new content-addressed verifier image;
- no Docker build invocation for the policy update;
- ignored tests can be skipped rather than merely removed from the score;
- the same captured full outcomes can be rescored under a new pure scoring policy;
- the policy revision and ignored IDs can be recorded independently from the evaluator/image revision.

The first implementation change that teaches the grader to accept runtime policy requires one evaluator/image update. Subsequent ignore-list changes do not.

### When A is enough

Choose **A plus runtime policy** and stop there if all of the following are true:

- task directories should remain ordinary self-contained Harbor tasks;
- evaluator code changes are infrequent;
- a deterministic generator and CI check are acceptable;
- roughly 1,849 lines of common generated code per task is not operationally important;
- avoiding a package registry or custom export workflow is valuable.

This is likely the best decision for the stated workload. It removes the absurd “all 119 modules in every task” duplication, prevents ignore lists from rebuilding images, and avoids a larger architecture project.

### When B is worth it

Choose **B plus runtime policy** if one-copy source and small checkouts matter, and users already enter through `sweep eval`. The tradeoff is explicit: lean source task directories are no longer standalone until `sweep task export` materializes them.

Compared with A, B eliminates about 183,000 repeated checked-out source lines after retaining one canonical copy. Because Git already deduplicates identical blobs, its stronger justification is avoiding generated paths and regeneration diffs, not repository object storage.

### When C is worth it

Choose **C plus runtime policy** if both repositories should consume one independently versioned evaluator and third parties should run source task directories directly. It establishes the cleanest cross-repository ownership without changing Harbor.

The costs are package release discipline, immutable artifact retention, and build-time acquisition. The separate `/opt/swesweep/python` interpreter keeps it isolated from task dependencies.

### When D is worth it

Choose **D** only if at least one broader goal matters:

- evaluation control should be outside untrusted task environments;
- the original and Harbor evaluators should use the same host-controlled architecture;
- non-Docker Harbor providers are important;
- scoring and regrading policy should live entirely on the host;
- removing Python and verifier build definitions from task environments is valuable in its own right.

Moving only score construction to the host is not enough justification: it relocates roughly 190 function lines. The small runtime-policy wrapper provides host-side policy without the async suite refactor.

### Recommended choice for this repository

| Priority | Choice |
|---|---|
| Frequent subtask exclusions without image churn | Runtime-policy decision |
| Obvious removal of irrelevant runner copies | A |
| Keep direct raw Harbor compatibility | A plus runtime policy |
| Eliminate even generated shared copies | B plus runtime policy |
| Share one evaluator across both repositories and preserve standalone tasks | C plus runtime policy |
| Redesign evaluator/Harbor ownership | D |

Based on the expected changes, **A plus runtime policy is the proportionate choice**. Reconsider B or C only if the remaining 1,849-line generated common core per task causes real maintenance or distribution pain. D should remain a possible architectural endpoint, not a prerequisite for changing ignored subtasks.

## Final decision summary

For the expected work—mostly ignoring or restoring subtasks—the most practical answer is to keep the existing in-container evaluator and make the selection a runtime policy. It should not alter `swesweep_eval.json`, so it should not alter the verifier image. Filter before running to save test time; use a small host verifier wrapper only if host postprocessing changes Harbor's authoritative reward.

After obvious runner pruning, the shared remainder is about 1,849 physical source lines per task, repeated across 100 generated trees. That is worth centralizing for correctness if evaluator development is frequent, but not worth a major architecture project for storage alone. A canonical source plus deterministic generation and CI may be enough.

If a true single deployed copy is still desired, the most portable answer is a pinned wheel installed during image construction. It is safe with offline inference because installation happens before the container runs, and Python is already present in every verifier image. It requires refactoring the original evaluator around an injected execution backend.

The cleanest final answer is a host-side custom Harbor verifier operating on a fresh Harbor-managed environment. With one small Harbor feature to reuse the task environment definition for a separate verifier, the task package becomes almost entirely data and all evaluator/Dockerfile duplication disappears.
