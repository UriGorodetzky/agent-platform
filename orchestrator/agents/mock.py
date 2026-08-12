"""A fake agent for testing the orchestration machinery.

MockAgent lets us exercise the entire orchestrator — routing, retries,
failure handling — with zero API calls and zero token cost. It is fully
configurable so a test can force success, force failure, or simulate a
slow agent.
"""

from __future__ import annotations

import asyncio

from orchestrator.agents.base import Agent
from orchestrator.models import AgentResult, Task, TaskStatus


class MockAgent(Agent):
    """An agent whose behavior is fixed up front, for tests and demos."""

    def __init__(
        self,
        name: str = "mock",
        *,
        output: str = "mock result",
        status: TaskStatus = TaskStatus.SUCCESS,
        delay: float = 0.0,
    ) -> None:
        self.name = name
        self._output = output
        self._status = status
        self._delay = delay  # simulated work time, in seconds

    async def execute(self, task: Task) -> AgentResult:
        # `await asyncio.sleep(...)` mimics an agent waiting on I/O. Crucially,
        # it yields control back to the event loop, so other tasks can run
        # during the wait — unlike `time.sleep`, which would block everything.
        if self._delay:
            await asyncio.sleep(self._delay)

        return AgentResult(
            task_id=task.id,
            status=self._status,
            output=self._output,
            metadata={"agent": self.name},
        )
