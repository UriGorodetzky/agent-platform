"""PostgreSQL-backed stores — the production alternative to the SQLite ones.

Same method API as EventStore/RunStore (emit/get, create/complete/get, close),
so the rest of the app doesn't change; api.py picks the backend from
DATABASE_URL. Differences from aiosqlite: `$1` placeholders, a connection pool
(not one connection), and native Postgres types (timestamptz, boolean, jsonb).
"""

from __future__ import annotations

import json
from asyncio import Lock
from datetime import datetime

import asyncpg

from orchestrator.events import Event, EventType
from orchestrator.models import TaskStatus
from orchestrator.runs import Run


class PostgresEventStore:
    """Events table, backed by Postgres."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._pool: asyncpg.Pool | None = None
        self._lock = Lock()

    async def _ensure(self) -> asyncpg.Pool:
        if self._pool is None:
            async with self._lock:
                if self._pool is None:
                    pool = await asyncpg.create_pool(self._dsn)
                    await pool.execute(
                        """
                        CREATE TABLE IF NOT EXISTS events (
                            id        BIGSERIAL PRIMARY KEY,
                            run_id    TEXT NOT NULL,
                            type      TEXT NOT NULL,
                            timestamp TIMESTAMPTZ NOT NULL,
                            metadata  JSONB NOT NULL
                        )
                        """
                    )
                    self._pool = pool
        return self._pool

    async def emit(self, run_id: str, type: EventType, **metadata) -> Event:
        event = Event(run_id=run_id, type=type, metadata=metadata)
        pool = await self._ensure()
        await pool.execute(
            "INSERT INTO events (run_id, type, timestamp, metadata) VALUES ($1, $2, $3, $4::jsonb)",
            run_id, event.type.value, event.timestamp, json.dumps(metadata),
        )
        return event

    async def get(self, run_id: str) -> list[Event]:
        pool = await self._ensure()
        rows = await pool.fetch(
            "SELECT run_id, type, timestamp, metadata FROM events WHERE run_id = $1 ORDER BY id",
            run_id,
        )
        return [
            Event(
                run_id=row["run_id"],
                type=EventType(row["type"]),
                timestamp=row["timestamp"],
                metadata=json.loads(row["metadata"]),
            )
            for row in rows
        ]

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None


class PostgresRunStore:
    """Runs table, backed by Postgres."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._pool: asyncpg.Pool | None = None
        self._lock = Lock()

    async def _ensure(self) -> asyncpg.Pool:
        if self._pool is None:
            async with self._lock:
                if self._pool is None:
                    pool = await asyncpg.create_pool(self._dsn)
                    await pool.execute(
                        """
                        CREATE TABLE IF NOT EXISTS runs (
                            run_id       TEXT PRIMARY KEY,
                            goal         TEXT NOT NULL,
                            status       TEXT NOT NULL,
                            code         TEXT NOT NULL DEFAULT '',
                            review       TEXT,
                            tests_passed BOOLEAN NOT NULL DEFAULT FALSE,
                            attempts     INTEGER NOT NULL DEFAULT 0,
                            created_at   TIMESTAMPTZ NOT NULL,
                            completed_at TIMESTAMPTZ
                        )
                        """
                    )
                    self._pool = pool
        return self._pool

    async def create(self, run_id: str, goal: str) -> Run:
        run = Run(run_id=run_id, goal=goal, status=TaskStatus.RUNNING, created_at=datetime.now().astimezone())
        pool = await self._ensure()
        await pool.execute(
            "INSERT INTO runs (run_id, goal, status, created_at) VALUES ($1, $2, $3, $4)",
            run.run_id, run.goal, run.status.value, run.created_at,
        )
        return run

    async def complete(
        self,
        run_id: str,
        *,
        status: TaskStatus,
        code: str,
        review: str | None,
        tests_passed: bool,
        attempts: int,
    ) -> None:
        pool = await self._ensure()
        await pool.execute(
            """
            UPDATE runs
               SET status = $1, code = $2, review = $3, tests_passed = $4,
                   attempts = $5, completed_at = $6
             WHERE run_id = $7
            """,
            status.value, code, review, tests_passed, attempts, datetime.now().astimezone(), run_id,
        )

    async def get(self, run_id: str) -> Run | None:
        pool = await self._ensure()
        row = await pool.fetchrow(
            """
            SELECT run_id, goal, status, code, review, tests_passed, attempts,
                   created_at, completed_at
              FROM runs WHERE run_id = $1
            """,
            run_id,
        )
        if row is None:
            return None
        return Run(
            run_id=row["run_id"],
            goal=row["goal"],
            status=TaskStatus(row["status"]),
            code=row["code"],
            review=row["review"],
            tests_passed=row["tests_passed"],
            attempts=row["attempts"],
            created_at=row["created_at"],
            completed_at=row["completed_at"],
        )

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
