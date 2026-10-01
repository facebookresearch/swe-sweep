"""Harbor agent that applies a submitted patch without running an inference model."""

from __future__ import annotations

from pathlib import Path

from harbor.agents.base import BaseAgent
from harbor.agents.options import AgentOptions
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext


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
