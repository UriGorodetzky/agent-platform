"""Run store — the summary/result of each workflow run, persisted in SQLite.

Where the EventStore keeps the fine-grained *timeline* (many rows per run), the
RunStore keeps one *summary* row per run: its goal, final status, outputs, and
timestamps. That's what GET /tasks/{run_id} returns.

It uses the same DB file as the EventStore (its own connection). Two connections
to one SQLite file can contend on writes, so we set ``PRAGMA busy_timeout`` to
make a write wait for the lock instead of failing with "database is locked".
"""

from __future__ import annotations

from asyncio import Lock
from datetime import datetime, timezone

import aiosqlite
from pydantic import BaseModel, Field

from orchestrator.models import TaskStatus


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Run(BaseModel):
    """One workflow run's stored summary."""

    run_id: str
    goal: str
    status: TaskStatus                      # RUNNING while in flight, then SUCCESS/FAILURE
    code: str = ""
    review: str | None = None
    tests_passed: bool = False
    attempts: int = 0
    created_at: datetime
    completed_at: datetime | None = None


class RunStore:
    """Stores one summary row per run."""

    def __init__(self, db_path: str = "orchestrator.db") -> None:
        self._db_path = db_path
        self._conn: aiosqlite.Connection | None = None
        self._lock = Lock()

    async def _ensure(self) -> aiosqlite.Connection:
        if self._conn is None:
            async with self._lock:
                if self._conn is None:
                    conn = await aiosqlite.connect(self._db_path)
                    # Wait (up to 5s) for a lock instead of erroring out.
                    await conn.execute("PRAGMA busy_timeout = 5000")
                    await conn.execute(
                        """
                        CREATE TABLE IF NOT EXISTS runs (
                            run_id       TEXT PRIMARY KEY,
                            goal         TEXT NOT NULL,
                            status       TEXT NOT NULL,
                            code         TEXT NOT NULL DEFAULT '',
                            review       TEXT,
                            tests_passed INTEGER NOT NULL DEFAULT 0,
                            attempts     INTEGER NOT NULL DEFAULT 0,
                            created_at   TEXT NOT NULL,
                            completed_at TEXT
                        )
                        """
                    )
                    await conn.commit()
                    self._conn = conn
        return self._conn

    async def create(self, run_id: str, goal: str) -> Run:
        """Insert a new run in the RUNNING state."""
        run = Run(run_id=run_id, goal=goal, status=TaskStatus.RUNNING, created_at=_utcnow())
        conn = await self._ensure()
        await conn.execute(
            "INSERT INTO runs (run_id, goal, status, created_at) VALUES (?, ?, ?, ?)",
            (run.run_id, run.goal, run.status.value, run.created_at.isoformat()),
        )
        await conn.commit()
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
        """Fill in the outcome and stamp completed_at."""
        conn = await self._ensure()
        await conn.execute(
            """
            UPDATE runs
               SET status = ?, code = ?, review = ?, tests_passed = ?,
                   attempts = ?, completed_at = ?
             WHERE run_id = ?
            """,
            (status.value, code, review, int(tests_passed), attempts, _utcnow().isoformat(), run_id),
        )
        await conn.commit()

    async def get(self, run_id: str) -> Run | None:
        """Fetch a run's summary, or None if there's no such run."""
        conn = await self._ensure()
        cursor = await conn.execute(
            """
            SELECT run_id, goal, status, code, review, tests_passed, attempts,
                   created_at, completed_at
              FROM runs WHERE run_id = ?
            """,
            (run_id,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return Run(
            run_id=row[0],
            goal=row[1],
            status=TaskStatus(row[2]),
            code=row[3],
            review=row[4],
            tests_passed=bool(row[5]),
            attempts=row[6],
            created_at=datetime.fromisoformat(row[7]),
            completed_at=datetime.fromisoformat(row[8]) if row[8] else None,
        )

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
