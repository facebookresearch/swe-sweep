<h1 align="center"><img src="docs/assets/swe-sweep-hero.png" alt="SWE-sweep logo" width="300"><br/>SWE-sweep</h1>

<p align="center"><em>How many bugs can LMs find & fix in large codebases?</em></p>

<p align="center">
Given a real repository, an agent must discover & repair as many bugs as they can.<br/>
Agents are not given any hint about the type of bug or its location.
</p>

## Links

<!-- TODO: fill in the public links once available (kept as placeholders to avoid publishing unverified URLs). -->

- Website: https://swesweep.com
- Paper: https://swesweep.com/paper

## Quickstart

> [!note]
> The code in this repo is only a thin wrapper around [Harbor](https://www.harborframework.com/), however see the warning below regarding harbor version

> [!warning]
> * **Harbor version**: Harbor 0.23 does not yet support the separate verifier environments and collect hooks
>   used by these tasks. The project therefore pins a compatible revision from Harbor's source
>   repository until Harbor 0.24 is released.
> * **Final score**: We build a micro-average of the bugs resolved (equivalent to a weighted average of the
>   individual task scores). See evaluation notes.

We recommend [uv](https://docs.astral.sh/uv/getting-started/installation/) for managing
Python environments.

```bash
git clone https://github.com/facebookresearch/swe-sweep.git
cd swe-sweep
uv sync   # or pip install .
```

Verify your setup:

```bash
sweep infra doctor
```

<details>
  <summary>Development setup</summary>

  Clone the repository and install the editable package with its dev dependencies:

  ```bash
  git clone https://github.com/facebookresearch/swe-sweep.git
  cd swe-sweep
  uv sync --extra test
  ```

  Run the test suite (matches CI, which tests on Python 3.12 and 3.13):

  ```bash
  uv run pytest
  ```

  Run the linting/formatting hooks:

  ```bash
  uvx pre-commit run --all-files
  ```

</details>

## Evaluate a single task

Pass a task name and a unified diff against that task's base commit:

```bash
sweep eval <task> <path/to/submission.diff>  # see raw harbor command below
```

<details>
  <summary>Raw harbor command</summary>

  ```bash
  uv run harbor run \
  --path tasks/pandora-bench__dateutil \
  --agent swesweep.patch_agent:PatchAgent \
  --agent-kwarg "patch_path=$(realpath /path/to/model.patch)" \
  --jobs-dir jobs \
  --n-concurrent 1 \
  --yes

  ```
</details>



The command runs the corresponding Harbor task with a small patch-applying agent. Harbor
then evaluates the resulting checkout in the task's separate verifier environment. Results
are written under `jobs/` by default.

<details>
<summary>How evaluation works</summary>

Evaluation follows the following pseudo-code:

```python
reset_to_base_commit()
apply(agent_patch)
reset(test_files)
build_if_needed()
base_commit_results = run_visible_suite()  # test -> pass/fail

subtask_results = {}   # subtask -> {test -> pass/fail}
for subtask in subtasks:
  apply(subtask.test_patch)
  subtask_results[subtask.id] = run(subtask.hidden_tests)
  revert(subtask.test_patch)

if any_new_failures(base_commit_results):
  task_score = 0
else:
  task_score = sum(passed_subtasks) / len(subtasks)
```

</details>

## Calculate the final score

The benchmark score is calculated as

```
total number of bugs solved across tasks / total number of bugs =
    = mean(number of bugs in task * task score)
```

Summarize one or more directories containing graded Harbor trials:

```bash
sweep info path/to/graded-solutions --per-task
sweep info path/to/graded-solutions --json
```

## Citation

<!-- TODO: add the citation once the paper is public. Kept as a placeholder to preserve
the anonymous-submission status; do not fill in author names before release. -->

```bibtex
@misc{swesweep,
  title  = {SWE-sweep},
  author = {TODO},
  year   = {TODO},
  url    = {TODO}
}
```

## License

SWE-sweep is licensed under the terms of the license found in [LICENSE](LICENSE).
