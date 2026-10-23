"""Harbor agent that applies a submitted patch without running an inference model."""

from __future__ import annotations

from pathlib import Path

from harbor.agents.base import BaseAgent
from harbor.agents.options import AgentOptions
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext

from swesweep.validate import APPLY_ONE


class PatchAgentOptions(AgentOptions):
    patch_path: str


class PatchAgent(BaseAgent):
    """Upload and apply one host-side patch to the task checkout."""

    options_model = PatchAgentOptions

    @staticmethod
    def name() -> str:
        return "swe-sweep-patch"

    def version(self) -> str:
        return "1.0.0"

    @classmethod
    def preflight(cls, kwargs=None, env=None) -> None:
        options = cls.parse_options(kwargs, env)
        if options is None:
            raise ValueError("patch_path is required")
        patch = Path(options.patch_path).expanduser()
        if not patch.is_file():
            raise ValueError(f"submission patch does not exist: {patch}")

    async def setup(self, environment: BaseEnvironment) -> None:
        return None

    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        if not isinstance(self.options, PatchAgentOptions):
            raise TypeError("patch agent options were not initialized")

        patch = Path(self.options.patch_path).expanduser().resolve()
        target = "/tmp/swe-sweep-submission.patch"
        await environment.upload_file(patch, target)
        result = await environment.exec(
            command=f"git apply --binary --whitespace=nowarn {target}",
            cwd=environment.task_env_config.workdir,
        )
        if result.return_code != 0:
            detail = (result.stderr or result.stdout or "git apply failed").strip()
            raise RuntimeError(f"could not apply submission patch: {detail}")
        context.metadata = {"submission_patch": patch.name}


class OfficialFixAgentOptions(AgentOptions):
    oracle_dir: str
    fixes: str = ""


class OfficialFixAgent(BaseAgent):
    """Apply a set of the task's official fixes to the checkout, as a submission would edit it.

    ``fixes`` is a comma-separated list of bug ids, ``all`` for every official fix (applied in
    sorted order), or empty for no edit at all (the empty submission). A fix that does not apply
    is tried with ``git apply --3way`` and otherwise skipped; skipped fixes are recorded in the
    trial metadata, since they are part of what the validation measured.
    """

    options_model = OfficialFixAgentOptions

    @staticmethod
    def name() -> str:
        return "swe-sweep-official-fix"

    def version(self) -> str:
        return "1.0.0"

    @classmethod
    def preflight(cls, kwargs=None, env=None) -> None:
        options = cls.parse_options(kwargs, env)
        if options is None or not Path(options.oracle_dir).expanduser().is_dir():
            raise ValueError("oracle_dir (the task's tests/oracle directory) is required")

    async def setup(self, environment: BaseEnvironment) -> None:
        return None

    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        if not isinstance(self.options, OfficialFixAgentOptions):
            raise TypeError("official-fix agent options were not initialized")
        oracle = Path(self.options.oracle_dir).expanduser().resolve()
        selection = self.options.fixes.strip()
        if selection == "all":
            patches = sorted(oracle.glob("*.patch"))
        else:
            patches = [oracle / f"{bug}.patch" for bug in selection.split(",") if bug]
        applied, skipped = [], []
        for patch in patches:
            target = f"/tmp/swe-sweep-official-{patch.name}"
            await environment.upload_file(patch, target)
            result = await environment.exec(
                command=APPLY_ONE.format(patch=target), cwd=environment.task_env_config.workdir
            )
            (applied if result.return_code == 0 else skipped).append(patch.stem)
        context.metadata = {"official_fixes_applied": applied, "official_fixes_skipped": skipped}
