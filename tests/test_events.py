"""Tests for the EventBus."""

from orchestrator.events import EventBus, EventType


def test_events_are_stored_and_returned_in_order():
    bus = EventBus()
    bus.emit("run-1", EventType.TASK_STARTED, goal="x")
    bus.emit("run-1", EventType.AGENT_STARTED, agent="planner")
    bus.emit("run-1", EventType.TASK_COMPLETED)

    events = bus.get("run-1")
    assert [e.type for e in events] == [
        EventType.TASK_STARTED,
        EventType.AGENT_STARTED,
        EventType.TASK_COMPLETED,
    ]
    assert events[0].metadata == {"goal": "x"}
    assert events[0].run_id == "run-1"


def test_runs_are_isolated():
    bus = EventBus()
    bus.emit("run-1", EventType.TASK_STARTED)
    assert bus.get("run-2") == []          # unknown run -> empty timeline
