"""Event system — a persistent timeline of what happened during a run.

Each workflow run emits events (task started, an agent started/finished, task
completed). They are stored in SQLite, keyed by run_id, so a client can ask
"what happened in run X?" — and, unlike the old in-memory version, the answer
survives a restart.

Why SQLite: a full SQL database in a single file, no server to run. When we
outgrow it (many concurrent writers, multiple machines) we move to PostgreSQL.

Why aiosqlite: the stdlib ``sqlite3`` is blocking; calling it from async code
would freeze the event loop. aiosqlite runs SQLite on a dedicated thread and
hands us an ``await``-able API.
"""

from __future__ import annotations

import json
from asyncio import Lock
from datetime import datetime, timezone
from enum import Enum

import aiosqlite
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


class EventStore:
    """Persists events in SQLite, grouped by run_id."""

    def __init__(self, db_path: str = "orchestrator.db") -> None:
        self._db_path = db_path
        self._conn: aiosqlite.Connection | None = None
        self._lock = Lock()  # guards one-time connection setup

    async def _ensure(self) -> aiosqlite.Connection:
        """Open the connection and create the table on first use (lazily)."""
        if self._conn is None:
            async with self._lock:
                if self._conn is None:  # double-check: another coroutine may have won
                    conn = await aiosqlite.connect(self._db_path)
                    await conn.execute(
                        """
                        CREATE TABLE IF NOT EXISTS events (
                            id        INTEGER PRIMARY KEY AUTOINCREMENT,
                            run_id    TEXT NOT NULL,
                            type      TEXT NOT NULL,
                            timestamp TEXT NOT NULL,
                            metadata  TEXT NOT NULL
                        )
                        """
                    )
                    await conn.commit()
                    self._conn = conn
        return self._conn

    async def emit(self, run_id: str, type: EventType, **metadata) -> Event:
        """Record an event and return it."""
        event = Event(run_id=run_id, type=type, metadata=metadata)
        conn = await self._ensure()
        # `?` placeholders — never f-strings. This is what prevents SQL injection.
        await conn.execute(
            "INSERT INTO events (run_id, type, timestamp, metadata) VALUES (?, ?, ?, ?)",
            (run_id, event.type.value, event.timestamp.isoformat(), json.dumps(metadata)),
        )
        await conn.commit()
        return event

    async def get(self, run_id: str) -> list[Event]:
        """All events for a run, in the order they happened."""
        conn = await self._ensure()
        cursor = await conn.execute(
            "SELECT run_id, type, timestamp, metadata FROM events WHERE run_id = ? ORDER BY id",
            (run_id,),
        )
        rows = await cursor.fetchall()
        return [
            Event(
                run_id=row[0],
                type=EventType(row[1]),
                timestamp=datetime.fromisoformat(row[2]),
                metadata=json.loads(row[3]),
            )
            for row in rows
        ]

    async def close(self) -> None:
        """Close the connection (e.g. on shutdown)."""
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
