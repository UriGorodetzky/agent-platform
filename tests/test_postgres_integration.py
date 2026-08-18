"""Integration tests for the Postgres stores against a REAL Postgres.

Skipped unless DATABASE_URL points at a Postgres — so local `pytest` (no DB
server) stays green, while CI runs these against a postgres service container.
"""

import os
import uuid

import pytest

from orchestrator.events import EventType
from orchestrator.models import TaskStatus
from orchestrator.postgres import PostgresEventStore, PostgresRunStore

DATABASE_URL = os.environ.get("DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL.startswith(("postgres://", "postgresql://")),
    reason="set DATABASE_URL to a Postgres URL to run these integration tests",
)


async def test_event_store_round_trip():
    run_id = f"run-{uuid.uuid4().hex}"          # unique so parallel runs don't clash
    store = PostgresEventStore(DATABASE_URL)
    await store.emit(run_id, EventType.TASK_STARTED, goal="x")
    await store.emit(run_id, EventType.AGENT_COMPLETED, agent="echo-1", attempt=1)

    events = await store.get(run_id)
    assert [e.type for e in events] == [EventType.TASK_STARTED, EventType.AGENT_COMPLETED]
    assert events[0].metadata == {"goal": "x"}          # jsonb round-trips
    assert events[1].metadata == {"agent": "echo-1", "attempt": 1}
    await store.close()


async def test_run_store_round_trip():
    run_id = f"run-{uuid.uuid4().hex}"
    store = PostgresRunStore(DATABASE_URL)
    await store.create(run_id, "build X")
    await store.complete(
        run_id, status=TaskStatus.SUCCESS, code="def f(): ...",
        review="LGTM", tests_passed=True, attempts=2,
    )

    run = await store.get(run_id)
    assert run.status is TaskStatus.SUCCESS
    assert run.tests_passed is True                      # native boolean round-trips
    assert run.attempts == 2
    assert run.completed_at is not None
    assert await store.get("does-not-exist") is None
    await store.close()
