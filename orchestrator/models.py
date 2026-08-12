"""Core data models for the orchestration platform.

These models are the "vocabulary" every part of the system speaks:
the API, the orchestrator, and every agent all pass around ``Task`` and
``AgentResult`` objects. Because they cross the HTTP boundary later, we
model them with Pydantic so validation and (de)serialization are automatic.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    """Lifecycle states of a task.

    Inherits from ``str`` so it serializes to a plain JSON string
    (e.g. ``"pending"``) instead of an opaque enum object.

    Note: an ``AgentResult`` only ever uses SUCCESS or FAILURE — the
    PENDING/RUNNING states belong to a Task's lifecycle, not to a result.
    We reuse the same enum for now to keep things simple.
    """

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILURE = "failure"


def _utcnow() -> datetime:
    """Timezone-aware 'now' in UTC. Naive datetimes are a classic bug source."""
    return datetime.now(timezone.utc)


class Task(BaseModel):
    """A unit of work handed to an agent.

    The orchestrator creates Tasks and routes them; agents consume them.
    Nothing here is Claude-specific — that is the whole point.
    """

    id: str = Field(default_factory=lambda: uuid4().hex)
    type: str = Field(description="Capability needed, e.g. 'code_review', 'planning'")
    prompt: str = Field(description="The natural-language instruction for the agent")
    context: dict = Field(default_factory=dict, description="Extra structured input")
    status: TaskStatus = TaskStatus.PENDING
    timeout: int = Field(default=300, gt=0, description="Max seconds before we give up")
    created_at: datetime = Field(default_factory=_utcnow)


class AgentResult(BaseModel):
    """The outcome an agent returns after running a Task."""

    task_id: str = Field(description="Which Task this result belongs to")
    status: TaskStatus = Field(description="SUCCESS or FAILURE")
    output: str = Field(default="", description="The agent's main textual output")
    metadata: dict = Field(default_factory=dict, description="Timings, tokens, errors, etc.")
