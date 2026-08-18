"""A documentation agent — Claude Code writing docs in the workspace.

A second *specialized* agent (distinct from the coder), so the planner can route
a "docs" subtask to it while "coding" subtasks go to the coder. Same interface,
different job.
"""

from __future__ import annotations

import pathlib

from orchestrator.agents.base import Agent
from orchestrator.agents.claude import _default_claude_command
from orchestrator.executor import run_subprocess
from orchestrator.models import AgentResult, Task, TaskStatus


class ClaudeDocAgent(Agent):
    """Runs Claude Code to write documentation in ``task.context['workspace']``."""

    def __init__(self, name: str = "doc-writer", *, command: list[str] | None = None, timeout: float = 300) -> None:
        self.name = name
        self._command = command or _default_claude_command() + ["--dangerously-skip-permissions"]
        self._timeout = timeout

    async def execute(self, task: Task) -> AgentResult:
        workspace = task.context.get("workspace")
        result = await run_subprocess(self._command, stdin=task.prompt, timeout=self._timeout, cwd=workspace)

        if result.timed_out or result.exit_code != 0:
            return AgentResult(task_id=task.id, status=TaskStatus.FAILURE,
                               metadata={"agent": self.name, "error": "timeout" if result.timed_out else "nonzero_exit"})

        # Return the README if it was written, else the CLI summary.
        output = result.stdout.strip()
        if workspace:
            readme = pathlib.Path(workspace) / "README.md"
            if readme.exists():
                output = readme.read_text(encoding="utf-8", errors="replace")

        return AgentResult(task_id=task.id, status=TaskStatus.SUCCESS, output=output,
                           metadata={"agent": self.name, "workspace": workspace})
