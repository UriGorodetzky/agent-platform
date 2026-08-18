"""Agent Registry — a lookup from capability to a concrete agent.

Selection is round-robin with a per-agent circuit breaker. The stateful part
(cursor + breaker health) lives in a pluggable backend (in-memory by default,
Redis when shared across instances), so ``select`` and the feedback methods are
async. The registry itself just maps capabilities to agents.
"""

from __future__ import annotations

import logging
import time
from typing import Callable, Optional

from orchestrator import metrics
from orchestrator.agents.base import Agent
from orchestrator.selection import InMemoryBackend

logger = logging.getLogger(__name__)


class NoAgentForCapability(Exception):
    """Raised when nothing registered can handle a requested capability."""


class AgentRegistry:
    """Holds agents, selects by capability (round-robin + circuit breaker)."""

    def __init__(
        self,
        *,
        backend=None,
        failure_threshold: int = 3,
        cooldown: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._by_name: dict[str, Agent] = {}
        self._by_capability: dict[str, list[Agent]] = {}
        # Default to the in-memory backend; callers pass a RedisBackend to share state.
        self._backend = backend or InMemoryBackend(
            failure_threshold=failure_threshold, cooldown=cooldown, clock=clock
        )

    def register(self, agent: Agent, capabilities: list[str]) -> None:
        """Add an agent and record which capabilities it can serve."""
        self._by_name[agent.name] = agent
        for cap in capabilities:
            self._by_capability.setdefault(cap, []).append(agent)

    def get(self, name: str) -> Agent:
        """Fetch a specific agent by its name."""
        if name not in self._by_name:
            raise KeyError(f"No agent named {name!r}")
        return self._by_name[name]

    async def select(self, capability: str) -> Agent:
        """Pick an agent for ``capability``: round-robin, skipping open breakers."""
        agents = self._by_capability.get(capability, [])
        if not agents:
            raise NoAgentForCapability(
                f"No agent registered for capability {capability!r}"
            )

        n = len(agents)
        start = await self._backend.next_index(capability, n)
        for offset in range(n):
            index = (start + offset) % n
            agent = agents[index]
            if await self._backend.is_available(agent.name):
                return agent

        # Every breaker is open — hand one out anyway (trying beats hard-failing).
        return agents[start]

    async def record_success(self, agent: Agent) -> None:
        """Report a successful call — closes the breaker."""
        await self._backend.record_success(agent.name)

    async def record_failure(self, agent: Agent) -> None:
        """Report an infrastructure failure — may open the breaker."""
        just_opened = await self._backend.record_failure(agent.name)
        if just_opened:
            logger.warning("circuit breaker opened", extra={"agent": agent.name})
            metrics.circuit_breaker_opens_total.labels(agent=agent.name).inc()

    def capabilities(self) -> dict[str, list[str]]:
        """Map capability -> agent names (for introspection / GET /agents)."""
        return {
            cap: [agent.name for agent in agents]
            for cap, agents in self._by_capability.items()
        }

    async def aclose(self) -> None:
        """Release backend resources (e.g. the Redis connection)."""
        await self._backend.close()
