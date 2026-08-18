"""A tester agent that actually RUNS the code with pytest.

This closes the loop: instead of a mock that always says "passed", it executes
the tests in the workspace and reports the real result. A failure sends the
workflow back to the coder with the pytest output to fix.
"""

from __future__ import annotations

import sys

from orchestrator.agents.base import Agent
from orchestrator.executor import run_subprocess
from orchestrator.models import AgentResult, Task, TaskStatus


class PytestTesterAgent(Agent):
    """Runs ``pytest`` in ``task.context['workspace']``."""

    def __init__(self, name: str = "tester", *, timeout: float = 120) -> None:
        self.name = name
        self._timeout = timeout

    async def execute(self, task: Task) -> AgentResult:
        workspace = task.context.get("workspace")

        result = await run_subprocess(
            [sys.executable, "-m", "pytest", "-q"],
            cwd=workspace,
            timeout=self._timeout,
        )

        passed = result.exit_code == 0   # pytest returns 0 only when tests pass
        output = (result.stdout + result.stderr).strip()
        return AgentResult(
            task_id=task.id,
            status=TaskStatus.SUCCESS if passed else TaskStatus.FAILURE,
            output=output,
            metadata={"agent": self.name, "returncode": result.exit_code},
        )
