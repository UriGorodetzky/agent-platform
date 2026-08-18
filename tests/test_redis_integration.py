"""Integration tests for the RedisBackend against a REAL Redis.

Skipped unless REDIS_URL is set — so local `pytest` stays green, while CI runs
these against a redis service container.
"""

import os
import uuid

import pytest

from orchestrator.selection import RedisBackend

REDIS_URL = os.environ.get("REDIS_URL", "")

pytestmark = pytest.mark.skipif(
    not REDIS_URL.startswith("redis://"),
    reason="set REDIS_URL to a Redis URL to run these integration tests",
)


async def test_round_robin_cursor_is_shared():
    prefix = f"t-{uuid.uuid4().hex}"                 # isolate from other runs
    a = RedisBackend(REDIS_URL, prefix=prefix)
    b = RedisBackend(REDIS_URL, prefix=prefix)       # a second "instance"

    # The cursor is shared (atomic INCR), so the two instances interleave.
    picks = [await a.next_index("coding", 3), await b.next_index("coding", 3),
             await a.next_index("coding", 3), await b.next_index("coding", 3)]
    assert picks == [0, 1, 2, 0]
    await a.close()
    await b.close()


async def test_circuit_breaker_is_shared_across_instances():
    prefix = f"t-{uuid.uuid4().hex}"
    a = RedisBackend(REDIS_URL, failure_threshold=2, cooldown=60, prefix=prefix)
    b = RedisBackend(REDIS_URL, failure_threshold=2, cooldown=60, prefix=prefix)

    assert await a.is_available("echo-1") is True
    await a.record_failure("echo-1")
    assert await a.record_failure("echo-1") is True   # 2nd failure -> just opened
    assert await b.is_available("echo-1") is False     # the OTHER instance sees it

    await a.record_success("echo-1")                   # close it
    assert await b.is_available("echo-1") is True
    await a.close()
    await b.close()
