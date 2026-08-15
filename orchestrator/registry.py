"""Agent Registry — a lookup from capability to a concrete agent.

Without it, the graph must name every agent explicitly. With it, the graph
asks "give me something that can plan / code / test" and the registry decides
which concrete agent answers. In-memory (plain dicts) for now — no database
until we genuinely need persistence across restarts.
"""

from __future__ import annotations

from orchestrator.agents.base import Agent


class NoAgentForCapability(Exception):
    """Raised when nothing registered can handle a requested capability."""


class AgentRegistry:
    """Holds agents and indexes them by name and by capability."""

    def __init__(self) -> None:
        self._by_name: dict[str, Agent] = {}
        self._by_capability: dict[str, list[Agent]] = {}
        self._next_index: dict[str, int] = {}  # per-capability round-robin cursor

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
        """Pick an agent that can serve ``capability``, round-robin.

        Successive calls cycle through the registered agents, spreading load
        evenly. This is the single seam where smarter strategies (health-aware,
        least-loaded) will later plug in. Safe without a lock because we never
        ``await`` between reading and updating the cursor (single-threaded loop).
        """
        agents = self._by_capability.get(capability, [])
        if not agents:
            raise NoAgentForCapability(
                f"No agent registered for capability {capability!r}"
            )
        index = self._next_index.get(capability, 0)
        self._next_index[capability] = (index + 1) % len(agents)
        return agents[index % len(agents)]

    def capabilities(self) -> dict[str, list[str]]:
        """Map capability -> agent names (for introspection / GET /agents)."""
        return {
            cap: [agent.name for agent in agents]
            for cap, agents in self._by_capability.items()
        }
