"""Event system — a timeline of what happened during a run.

Each workflow run emits events (task started, an agent started/finished, task
completed). We keep them in memory, keyed by run_id, so a client can later ask
"what happened in run X?". This is the seed of real-time UI and observability;
persistence (a database) comes later, only when in-memory is no longer enough.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class EventType(str, Enum):
    """The kinds of events a run can produce."""

    TASK_STARTED = "TASK_STARTED"
    AGENT_STARTED = "AGENT_STARTED"
    AGENT_COMPLETED = "AGENT_COMPLETED"
    AGENT_FAILED = "AGENT_FAILED"
    TASK_COMPLETED = "TASK_COMPLETED"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Event(BaseModel):
    """A single thing that happened, tied to a run."""

    run_id: str
    type: EventType
    timestamp: datetime = Field(default_factory=_utcnow)
    metadata: dict = Field(default_factory=dict)


class EventBus:
    """In-memory store of events, grouped by run_id."""

    def __init__(self) -> None:
        self._events: dict[str, list[Event]] = {}

    def emit(self, run_id: str, type: EventType, **metadata) -> Event:
        """Record an event and return it."""
        event = Event(run_id=run_id, type=type, metadata=metadata)
        self._events.setdefault(run_id, []).append(event)
        return event

    def get(self, run_id: str) -> list[Event]:
        """All events for a run, in the order they happened."""
        return self._events.get(run_id, [])
