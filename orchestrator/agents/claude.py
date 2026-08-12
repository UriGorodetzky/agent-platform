"""An agent backed by the Claude Code CLI.

ClaudeAgent is a thin translator: it turns a Task into a CLI invocation and
turns the process result back into an AgentResult. All the process mechanics
(pipes, timeout, cancellation) live in run_subprocess — this class stays about
*what to run*, not *how to run a process*.
"""

from __future__ import annotations

from orchestrator.agents.base import Agent
from orchestrator.executor import run_subprocess
from orchestrator.models import AgentResult, Task, TaskStatus


class ClaudeAgent(Agent):
    """Runs the Claude Code CLI as a subprocess.

    The prompt is delivered on stdin (robust for long prompts). The command
    is injectable so tests can substitute a fake CLI.
    """

    def __init__(
        self,
        name: str = "claude",
        *,
        command: list[str] | None = None,
        timeout: float = 300,
        cwd: str | None = None,
    ) -> None:
        self.name = name
        # Default: real Claude Code CLI in non-interactive print mode.
        # NOTE: verify the exact flags against your installed CLI version.
        self._command = command or ["claude", "-p"]
        self._timeout = timeout
        self._cwd = cwd

    async def execute(self, task: Task) -> AgentResult:
        result = await run_subprocess(
            self._command,
            stdin=task.prompt,
            timeout=self._timeout,
            cwd=self._cwd,
        )

        if result.timed_out:
            return AgentResult(
                task_id=task.id,
                status=TaskStatus.FAILURE,
                output="",
                metadata={"agent": self.name, "error": "timeout"},
            )

        if result.exit_code != 0:
            return AgentResult(
                task_id=task.id,
                status=TaskStatus.FAILURE,
                output=result.stdout.strip(),
                metadata={
                    "agent": self.name,
                    "error": "nonzero_exit",
                    "exit_code": result.exit_code,
                    "stderr": result.stderr.strip(),
                },
            )

        return AgentResult(
            task_id=task.id,
            status=TaskStatus.SUCCESS,
            output=result.stdout.strip(),   # .strip() handles trailing CRLF
            metadata={"agent": self.name, "exit_code": 0},
        )
