"""Tests for the RunStore."""

from orchestrator.models import TaskStatus
from orchestrator.runs import RunStore


async def test_create_then_get_is_running():
    store = RunStore(":memory:")
    await store.create("run-1", "build a login form")

    run = await store.get("run-1")
    assert run is not None
    assert run.goal == "build a login form"
    assert run.status is TaskStatus.RUNNING
    assert run.completed_at is None          # not finished yet
    await store.close()


async def test_complete_fills_in_the_outcome():
    store = RunStore(":memory:")
    await store.create("run-1", "x")
    await store.complete(
        "run-1", status=TaskStatus.SUCCESS, code="def f(): ...",
        review="LGTM", tests_passed=True, attempts=2,
    )

    run = await store.get("run-1")
    assert run.status is TaskStatus.SUCCESS
    assert run.code == "def f(): ..."
    assert run.review == "LGTM"
    assert run.tests_passed is True
    assert run.attempts == 2
    assert run.completed_at is not None
    await store.close()


async def test_get_unknown_returns_none():
    store = RunStore(":memory:")
    assert await store.get("nope") is None
    await store.close()


async def test_runs_survive_reconnect(tmp_path):
    db_file = str(tmp_path / "orch.db")

    store1 = RunStore(db_file)
    await store1.create("run-1", "persist me")
    await store1.close()                     # simulate shutdown

    store2 = RunStore(db_file)                # simulate restart
    run = await store2.get("run-1")
    assert run is not None
    assert run.goal == "persist me"
    await store2.close()
