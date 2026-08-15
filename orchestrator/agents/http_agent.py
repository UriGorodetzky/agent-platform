"""An agent that lives behind an HTTP endpoint (a separate service).

From the orchestrator's point of view this is just another Agent: it has the
same execute(task) -> AgentResult shape. The difference is that the work
happens in another process, reached over the network — which introduces new
ways to fail (service down, timeout) that in-process agents never had.
"""

from __future__ import annotations

import httpx

from orchestrator.agents.base import Agent
from orchestrator.models import AgentResult, Task, TaskStatus


class HTTPAgent(Agent):
    """Calls an external agent service's POST /execute endpoint."""

    def __init__(
        self,
        name: str = "http",
        *,
        base_url: str,
        timeout: float = 30,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.name = name
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        # An injected client lets tests route to an in-process app and lets
        # callers reuse a connection pool. If None, we make one per call.
        self._client = client

    async def execute(self, task: Task) -> AgentResult:
        payload = {"task_id": task.id, "prompt": task.prompt, "context": task.context}
        try:
            data = await self._post(payload)
        except httpx.HTTPStatusError as exc:
            # We reached the service, but it answered with a 4xx/5xx status.
            return self._failure(task, "http_error", status_code=exc.response.status_code)
        except httpx.RequestError as exc:
            # We never got a response: connection refused, timeout, DNS, reset...
            # These vary by OS (e.g. ConnectError vs ConnectTimeout), so we catch
            # the stable parent and keep the specific name only as diagnostic data.
            return self._failure(task, "network_error", detail=type(exc).__name__)

        ok = data.get("status") == "success"
        return AgentResult(
            task_id=task.id,
            status=TaskStatus.SUCCESS if ok else TaskStatus.FAILURE,
            output=data.get("output", ""),
            metadata={**data.get("metadata", {}), "agent": self.name},
        )

    async def _post(self, payload: dict) -> dict:
        url = f"{self._base_url}/execute"
        if self._client is not None:
            resp = await self._client.post(url, json=payload)
            resp.raise_for_status()
            return resp.json()
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            return resp.json()

    def _failure(self, task: Task, error: str, **extra) -> AgentResult:
        return AgentResult(
            task_id=task.id,
            status=TaskStatus.FAILURE,
            metadata={"agent": self.name, "error": error, **extra},
        )
