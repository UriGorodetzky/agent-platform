"""The Agent interface — the contract every agent must fulfill.

This is the single most important abstraction in the system. The
orchestrator depends only on this interface, never on a concrete
provider (Claude, OpenAI, a mock...). That is what makes the platform
"model-agnostic": swapping or adding a provider means adding a subclass,
not touching the orchestration logic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from orchestrator.models import AgentResult, Task


class Agent(ABC):
    """Abstract base class for all agents.

    A concrete agent must implement :meth:`execute`. Because ``execute``
    is declared ``async``, agents are free to await I/O (a network call,
    a subprocess) without blocking the whole process.
    """

    #: Human-readable identifier, used in logs and result metadata.
    name: str = "agent"

    @abstractmethod
    async def execute(self, task: Task) -> AgentResult:
        """Run ``task`` and return its result.

        Implementations should not raise for *expected* task failures;
        instead they return an ``AgentResult`` with ``status=FAILURE``.
        Raising is reserved for unexpected, programmer-level errors.
        """
        ...
