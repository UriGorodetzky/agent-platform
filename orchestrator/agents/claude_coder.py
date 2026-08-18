"""A coder agent that runs Claude Code *agentically* in a workspace.

Unlike ClaudeAgent (text in, text out), this lets Claude actually use its tools
— write files, run them — inside a sandboxed workspace directory. The artifact
is the file Claude produces, which we read back and return.
"""

from __future__ import annotations

import pathlib

from orchestrator.agents.base import Agent
from orchestrator.agents.claude import _default_claude_command
from orchestrator.executor import run_subprocess
from orchestrator.models import AgentResult, Task, TaskStatus


class ClaudeCoderAgent(Agent):
    """Runs Claude Code with tool access in ``task.context['workspace']``."""

    def __init__(
        self,
        name: str = "coder",
        *,
        command: list[str] | None = None,
        timeout: float = 600,
    ) -> None:
        self.name = name
        # Agentic mode: allow tools without interactive prompts. Safe because the
        # workspace is an isolated directory we created for this run.
        self._command = command or _default_claude_command() + ["--dangerously-skip-permissions"]
        self._timeout = timeout

    async def execute(self, task: Task) -> AgentResult:
        workspace = task.context.get("workspace")

        result = await run_subprocess(
            self._command,
            stdin=task.prompt,
            timeout=self._timeout,
            cwd=workspace,
        )

        # The real output is the code files Claude wrote, not its chat summary.
        # Read every non-test .py file so a multi-file project comes through too.
        code = ""
        if workspace:
            root = pathlib.Path(workspace)
            files = sorted(
                p for p in root.rglob("*.py")           # recursive: catch package subdirs
                if not p.name.startswith("test_")
                and "__pycache__" not in p.parts
                and ".pytest_cache" not in p.parts
            )
            code = "\n\n".join(
                f"# {p.relative_to(root)}\n{p.read_text(encoding='utf-8', errors='replace')}" for p in files
            )

        if result.timed_out:
            return AgentResult(task_id=task.id, status=TaskStatus.FAILURE,
                               metadata={"agent": self.name, "error": "timeout"})
        if not code:
            return AgentResult(task_id=task.id, status=TaskStatus.FAILURE, output=result.stdout.strip(),
                               metadata={"agent": self.name, "error": "no_code_files"})

        return AgentResult(
            task_id=task.id,
            status=TaskStatus.SUCCESS,
            output=code,
            metadata={"agent": self.name, "workspace": workspace},
        )
