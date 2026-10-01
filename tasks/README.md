# SWE-sweep, Harbor task format

One task per repository at its buggiest ("maxbug") commit: the agent gets the repository and no
hint and is asked to find and fix every bug it can within 12 hours. Every accepted bug has a
hidden test patch; the reward is `resolved bugs / accepted bugs`, gated to 0 by any regression
of the repository's visible test suite. Generated from the upstream PandoraBench commit
`9f7399e15e6172900e0591deb5a57a45769d8205` by Drydock's `pandora_bench.py`; each task's grader drives the upstream
evaluator modules its test suites need, adapted for the Harbor runtime.

## Layout

    swe-sweep__<repo>/
      task.toml                  Harbor task config (resources, timeouts, network, artifacts)
      instruction.md             the no-hint prompt, for harnesses other than mini-swe-agent
      agent/mini_swe_agent.yaml  upstream's mini-swe-agent config for this repo (the paper's
                                 harness; pass it as the agent's config file to reproduce it)
      environment/Dockerfile     agent image: upstream's maxbug Dockerfile, source cloned at the ref
      tests/Dockerfile           verifier image: the agent image + a standalone Python + /tests
      tests/test.sh              grading entry point, writes /logs/verifier/reward.json
      tests/shared/              the grader and the upstream evaluator modules this task uses;
                                 a file has the same bytes in every task that ships it
      tests/swesweep_eval.json    accepted subtasks: ids, fail-to-pass tests, runner declarations
      tests/base_tests.json.gz   visible tests that passed in every recorded pristine base run
      tests/subtasks/<id>/test.patch   hidden tests, one per accepted bug
      tests/oracle/<id>.patch    gold fixes, one per accepted bug
      solution/solve.sh          oracle: asks the grader to score every bug on its own gold fix
    check_shared.py              CI check: every file under tests/shared/ has the same bytes in
                                 every task that ships it (`python3 check_shared.py`)
    score.py                     benchmark score from a directory of graded trials
                                 (`python3 score.py <harbor job dir>`)

## Running with Harbor

Needs Docker and a Harbor with separate verifier sandboxes and `[[verifier.collect]]` hooks:
the hook captures the agent's patch after the agent phase and the verifier receives it as
`/logs/artifacts/model.patch`. The agent phase is offline, as upstream's `--network=none`
container; a hosted model's endpoint is opened with the run-level allowlist:

    harbor run -p swe-sweep__dayjs -a oracle
    harbor run -p swe-sweep__dayjs -a mini-swe-agent -m anthropic/claude-opus-5 \
        --extra-allowed-hosts api.anthropic.com

Tasks declare the paper's 16 vCPU / 64 GiB / 100 GiB per sandbox; `--override-cpus` and
`--override-memory-mb` fit smaller machines. Building an agent image from its Dockerfile takes
minutes to hours per repository (clone, toolchain, repository build).

### Sharing built images

Each task has two images. The agent image is `environment/Dockerfile`, and the verifier image
is `tests/Dockerfile`: the same build plus a standalone Python and `COPY . /tests`, with the
`COPY` last so a change under `tests/` rebuilds only that layer. Harbor builds both per task,
and the local Docker layer cache reuses them across runs on one machine. To share images across
machines or with other people, build each repository's maxbug image once, push it to a registry,
and regenerate the dataset with `--image-registry <prefix>`. `task.toml` then names the image in
`docker_image` (Harbor pulls it instead of building), and `tests/Dockerfile` becomes
`FROM <that image>` plus the Python and `/tests`, which builds in seconds.

`tests/test.sh` also grades in a shared container (Harbor's default mode): it extracts the patch
itself and uses a `python3 >= 3.11` from the image, but the tree is then whatever the agent left
behind rather than a pristine checkout plus the patch.

## How a submission is graded

One verifier session per task: the task's setup command once; reset to the base commit; apply
the patch and revert any test files it touched; build if the repository needs it; run the
visible suite once. Every test in `base_tests.json.gz` that does not pass now is a regression
(there is no pre-patch visible run: upstream's recorded base runs are the reference). Then, for
each accepted bug, apply its hidden `test.patch`, run the tests it targets once, revert it.

One run decides each check, as in the paper: the base list already excludes every visible test
that failed any of upstream's recorded pristine runs, and the reviewed environment-dependent
tests below are out as well, so a flaky failure is a benchmark defect to report, not something
the grader should absorb; the grader has no re-run.

## Scoring

Per task, `reward = n_resolved / n_subtasks`, or 0 if the visible suite regressed. The
benchmark score is resolved bugs over all accepted bugs, i.e. the average of the task rewards
weighted by their `n_subtasks`: `sum(reward * n_subtasks) / sum(n_subtasks)` (4,068 bugs over
the 100 tasks). The unweighted mean of the rewards is a different number. A task whose visible
suite regressed contributes 0 to that sum even if some bugs were resolved; its raw count stays
available as `n_resolved`.

Harbor's own summary averages each `reward.json` key over the trials, so the `reward` it prints
is the unweighted mean. `python3 score.py <job dir>` computes the benchmark score from the
`reward.json` files of a Harbor job (or any directory tree that holds them), excludes
evaluation failures (`grader_failed = 1`) from both sides of the fraction, and prints the
per-task rows with `--per-task` or everything as `--json`.

## Known limitations

17 tasks have an empty `base_tests.json.gz`: their visible suite reports one aggregate unit that already fails at the base commit, so no test is stably passing and there is no regression gate (upstream's live baseline gave them none either). A patch that breaks their visible suite is not zeroed: `swe-sweep__clippy`, `swe-sweep__cvc5`, `swe-sweep__dart-sdk`, `swe-sweep__datafusion`, `swe-sweep__dmd`, `swe-sweep__jest`, `swe-sweep__netty`, `swe-sweep__nim`, `swe-sweep__oxc`, `swe-sweep__phpspreadsheet`, `swe-sweep__rails`, `swe-sweep__sunpy`, `swe-sweep__swc`, `swe-sweep__symfony`, `swe-sweep__syn`, `swe-sweep__tokio`, `swe-sweep__v`.

The regression reference is upstream's recorded base list; the per-bug oracle's own pristine visible run is the sentinel, and a base test it fails (after one confirmation run) is an evaluation error rather than a 0. `base_tests.json.gz` `environment_failed` lists, for review, the base tests the recorded environment runs (`environment_runs`) did not pass; tests confirmed environment-dependent are moved to `ignored`. Recorded so far in 1 tasks: `swe-sweep__go` 532.

Reviewed environment-dependent tests, out of the base list and never a regression or a subtask failure (`swesweep_ignored_tests.json`):

- `aws-cdk` (1): custom-resources provider test that symlinks the SDK under a fixed `/tmp/node_modules/aws-sdk` path and times the install; failed on 2 of 5 pristine runs of the 20 min suite (2026-09-29 v2 and v5), passed in upstream's ten.
- `dayjs` (1): badMutable `week()` on today's date mutates the instance only for some dates; passed in upstream's September runs, failed 2026-09-29 on the pristine tree.
- `duckdb` (2): Read the machine's CPU count.
- `fasthttp` (7): Deadline / pipelining timing tests; a different one fails on each pristine run at any concurrency.
- `fsharp` (1): `#r nuget` restore of a nonexistent package: the offline failure shape differs between upstream's `--network=none` (no interface) and Daytona's egress block (resolver present, timeouts), and the diagnostic assertion trips.
- `opencv` (2): FFMPEG-decoded .avi whose frame count follows the decoder build.
- `pulsar` (80): Never run here: Pulsar's fail-fast TestNG listener skips every test after the first failure in the `pulsar-client-original` fork, and the class order (surefire `runOrder=filesystem`) makes the offline `ConnectionTimeoutTest.testLowTimeout` trip first in our sandboxes where upstream tripped later; all 80 pass whenever they run (upstream 10/10). Two independent runs, identical set.
- `quarkus` (170): Never run here: the whole-reactor `mvn -o -T 4 test` is fail-fast and three unrelated module failures (offline `surefire-junit4` provider, Kotlin under `-T`, `AnalyticsServiceTest`) race with these modules; upstream's own ten runs report 465-947 of 984 ids. All 170 pass whenever they run.
- `qutip` (1): Unseeded `rand_ket(4)` plus random GRAPE initial pulses with no retry; failed 1 of 2 pristine runs here.
- `scipy` (2): `@pytest.mark.xfail(reason='Fails with ATLAS')` tests that XPASS on upstream's host and XFAIL here (BLAS/CPU-dependent sparse interior-point numerics).
- `webpack` (2): `asset-modules/http-url` fetches over HTTP when its lockfile entries are stale; the verifier has no network. Failed on 3 of 3 pristine runs of `drydock-pandora-oracle-perbug-full100-v5` (2026-09-29, confirmed by the second visible run) after passing in v3 and v4, so the flip is time-based, not code.


## Reading results

`reward.json` is numeric: `reward` (the score), `n_subtasks`, `n_resolved`, `n_partial`,
`visible_ok`, `n_regressions`, `agent_patch_applied`, `agent_build_ok`; `grader_failed = 1`
marks an evaluator failure (nothing measurable, not a 0). `eval.json` is upstream's per-subtask
verdict plus `visible_tests`, the post-patch outcome of every visible test, and
`eval_output.json` the console output, so a run can be re-scored offline after a test or a
subtask is excluded.

The gold fixes were validated one at a time upstream and a few overlap, so they cannot be stacked
into one patch. The oracle therefore does not submit them: `solve.sh` leaves a marker and the
grader scores every bug on its own gold fix (gold, rebuild, hidden tests, reset), which is the
check upstream accepted the bug on. Its visible run is on the pristine tree and must pass every
test in `base_tests.json.gz`; one that fails is environment drift (it would count as a
regression against every agent), reported as an evaluation error (`grader_failed = 1`, per-bug
results kept) rather than a 0. `eval.json` carries `"oracle": true`.

The hidden tests ship inside the task directories (Harbor tasks carry their tests), so this is a
public benchmark: do not train on it.
