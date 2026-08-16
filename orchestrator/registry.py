"""Agent Registry — a lookup from capability to a concrete agent.

Without it, the graph must name every agent explicitly. With it, the graph
asks "give me something that can plan / code / test" and the registry decides
which concrete agent answers. In-memory (plain dicts) for now — no database
until we genuinely need persistence across restarts.

Selection is round-robin, with a per-agent **circuit breaker**: an agent that
fails repeatedly is marked unhealthy and skipped until a cooldown passes, so we
stop wasting calls (and time) on a replica that is down.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Callable

from orchestrator import metrics
from orchestrator.agents.base import Agent

logger = logging.getLogger(__name__)


class NoAgentForCapability(Exception):
    """Raised when nothing registered can handle a requested capability."""


@dataclass
class _Health:
    """Circuit-breaker state for one agent.

    ``opened_at is None`` means the breaker is CLOSED (healthy). Once
    ``consecutive_failures`` reaches the threshold, ``opened_at`` is stamped
    and the breaker is OPEN. After the cooldown elapses the agent is offered
    one trial call (HALF-OPEN); its success or failure closes or re-opens it.
    """

    consecutive_failures: int = 0
    opened_at: float | None = None


class AgentRegistry:
    """Holds agents, selects by capability (round-robin + circuit breaker)."""

    def __init__(
        self,
        *,
        failure_threshold: int = 3,
        cooldown: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._by_name: dict[str, Agent] = {}
        self._by_capability: dict[str, list[Agent]] = {}
        self._next_index: dict[str, int] = {}      # per-capability round-robin cursor
        self._health: dict[str, _Health] = {}      # per-agent breaker state (by name)
        self._failure_threshold = failure_threshold
        self._cooldown = cooldown
        self._clock = clock                         # injectable for testing

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

    def select(self, capability: str) -> Agent:
        """Pick an agent for ``capability``: round-robin, skipping open breakers.

        Starting at the round-robin cursor, return the first *available* agent
        (breaker closed, or cooldown elapsed for a half-open trial). If every
        agent's breaker is open, fall back to the next one anyway — trying is
        better than hard-failing.
        """
        agents = self._by_capability.get(capability, [])
        if not agents:
            raise NoAgentForCapability(
                f"No agent registered for capability {capability!r}"
            )

        n = len(agents)
        start = self._next_index.get(capability, 0)
        for offset in range(n):
            index = (start + offset) % n
            agent = agents[index]
            if self._is_available(agent):
                self._next_index[capability] = (index + 1) % n
                return agent

        # All breakers open — advance the cursor and hand one out regardless.
        index = start % n
        self._next_index[capability] = (index + 1) % n
        return agents[index]

    def record_success(self, agent: Agent) -> None:
        """Report a successful call — closes the breaker (resets its state)."""
        self._health[agent.name] = _Health()

    def record_failure(self, agent: Agent) -> None:
        """Report an infrastructure failure — may open the breaker."""
        health = self._health.setdefault(agent.name, _Health())
        health.consecutive_failures += 1
        if health.consecutive_failures >= self._failure_threshold:
            was_open = health.opened_at is not None
            health.opened_at = self._clock()   # (re)open — resets the cooldown clock
            if not was_open:                   # log/count only on the closed -> open transition
                logger.warning(
                    "circuit breaker opened",
                    extra={"agent": agent.name, "failures": health.consecutive_failures},
                )
                metrics.circuit_breaker_opens_total.labels(agent=agent.name).inc()

    def _is_available(self, agent: Agent) -> bool:
        """True if the agent's breaker allows a call right now."""
        health = self._health.get(agent.name)
        if health is None or health.opened_at is None:
            return True  # never registered a problem, or breaker is closed
        # Breaker is open: only available once the cooldown has elapsed (half-open).
        return (self._clock() - health.opened_at) >= self._cooldown

    def capabilities(self) -> dict[str, list[str]]:
        """Map capability -> agent names (for introspection / GET /agents)."""
        return {
            cap: [agent.name for agent in agents]
            for cap, agents in self._by_capability.items()
        }
