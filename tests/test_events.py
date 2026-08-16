"""Tests for the EventStore. Uses an in-memory SQLite DB (":memory:")."""

from orchestrator.events import EventStore, EventType


async def test_events_are_stored_and_returned_in_order():
    store = EventStore(":memory:")
    await store.emit("run-1", EventType.TASK_STARTED, goal="x")
    await store.emit("run-1", EventType.AGENT_STARTED, agent="planner")
    await store.emit("run-1", EventType.TASK_COMPLETED)

    events = await store.get("run-1")
    assert [e.type for e in events] == [
        EventType.TASK_STARTED,
        EventType.AGENT_STARTED,
        EventType.TASK_COMPLETED,
    ]
    assert events[0].metadata == {"goal": "x"}
    assert events[0].run_id == "run-1"
    await store.close()          # release the aiosqlite connection + its thread


async def test_runs_are_isolated():
    store = EventStore(":memory:")
    await store.emit("run-1", EventType.TASK_STARTED)
    assert await store.get("run-2") == []          # unknown run -> empty timeline
    await store.close()


async def test_events_survive_reconnect(tmp_path):
    """The whole point of persistence: a new store on the same file sees the data."""
    db_file = str(tmp_path / "events.db")

    store1 = EventStore(db_file)
    await store1.emit("run-1", EventType.TASK_STARTED, goal="persist me")
    await store1.close()                            # simulate shutdown

    store2 = EventStore(db_file)                     # simulate restart
    events = await store2.get("run-1")
    assert len(events) == 1
    assert events[0].metadata == {"goal": "persist me"}
    await store2.close()
