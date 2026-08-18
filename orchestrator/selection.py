"""Selection state for the AgentRegistry — round-robin cursor + circuit breaker.

Two backends with the same async API:
- InMemoryBackend: per-process (default; fine for one instance, local, tests).
- RedisBackend:    SHARED across instances, so the cursor and breaker are
  coordinated cluster-wide (a replica marked dead by one instance is skipped by
  all). Uses an atomic INCR for the cursor and a TTL key for the breaker: the
  cooldown is simply the key's time-to-live, so "half-open" = the key expired.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable


@dataclass
class _Health:
    consecutive_failures: int = 0
    opened_at: float | None = None


class InMemoryBackend:
    """Per-process selection state (dicts). The default."""

    def __init__(
        self,
        *,
        failure_threshold: int = 3,
        cooldown: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._cursor: dict[str, int] = {}
        self._health: dict[str, _Health] = {}
        self._failure_threshold = failure_threshold
        self._cooldown = cooldown
        self._clock = clock

    async def next_index(self, capability: str, n: int) -> int:
        i = self._cursor.get(capability, 0)
        self._cursor[capability] = (i + 1) % n
        return i % n

    async def is_available(self, agent_name: str) -> bool:
        health = self._health.get(agent_name)
        if health is None or health.opened_at is None:
            return True
        return (self._clock() - health.opened_at) >= self._cooldown

    async def record_success(self, agent_name: str) -> None:
        self._health[agent_name] = _Health()

    async def record_failure(self, agent_name: str) -> bool:
        """Return True only on the closed -> open transition (for logging/metrics)."""
        health = self._health.setdefault(agent_name, _Health())
        health.consecutive_failures += 1
        if health.consecutive_failures >= self._failure_threshold:
            was_open = health.opened_at is not None
            health.opened_at = self._clock()
            return not was_open
        return False

    async def close(self) -> None:
        pass


class RedisBackend:
    """Selection state shared across instances via Redis."""

    def __init__(
        self,
        url: str,
        *,
        failure_threshold: int = 3,
        cooldown: float = 30.0,
        prefix: str = "agentsel",
    ) -> None:
        import redis.asyncio as redis  # imported lazily so redis is optional

        self._redis = redis.from_url(url, decode_responses=True)
        self._failure_threshold = failure_threshold
        self._cooldown = int(cooldown)
        self._prefix = prefix

    async def next_index(self, capability: str, n: int) -> int:
        # INCR is atomic — safe as a shared cursor. First call returns 1 -> index 0.
        value = await self._redis.incr(f"{self._prefix}:cursor:{capability}")
        return (value - 1) % n

    async def is_available(self, agent_name: str) -> bool:
        # OPEN while the cooldown key exists; when its TTL expires -> half-open.
        return not await self._redis.exists(f"{self._prefix}:open:{agent_name}")

    async def record_success(self, agent_name: str) -> None:
        await self._redis.delete(
            f"{self._prefix}:fails:{agent_name}",
            f"{self._prefix}:open:{agent_name}",
        )

    async def record_failure(self, agent_name: str) -> bool:
        fails_key = f"{self._prefix}:fails:{agent_name}"
        fails = await self._redis.incr(fails_key)
        await self._redis.expire(fails_key, self._cooldown)  # failures decay over the window
        if fails >= self._failure_threshold:
            # Open for `cooldown` seconds. NX makes SET return True only on the
            # closed -> open transition.
            just_opened = await self._redis.set(
                f"{self._prefix}:open:{agent_name}", "1", ex=self._cooldown, nx=True
            )
            return bool(just_opened)
        return False

    async def close(self) -> None:
        await self._redis.aclose()
