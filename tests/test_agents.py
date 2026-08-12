"""Tests for the Agent interface and MockAgent."""

import asyncio

import pytest

from orchestrator.agents import Agent, MockAgent
from orchestrator.models import Task, TaskStatus


def make_task() -> Task:
    return Task(type="demo", prompt="do something")


def test_cannot_instantiate_abstract_agent():
    """The ABC contract: you cannot create an Agent without execute()."""
    with pytest.raises(TypeError):
        Agent()  # type: ignore[abstract]


async def test_mock_agent_returns_success_by_default():
    result = await MockAgent().execute(make_task())
    assert result.status is TaskStatus.SUCCESS
    assert result.output == "mock result"


async def test_mock_agent_can_be_forced_to_fail():
    agent = MockAgent(name="flaky", status=TaskStatus.FAILURE, output="boom")
    task = make_task()
    result = await agent.execute(task)
    assert result.status is TaskStatus.FAILURE
    assert result.task_id == task.id          # result is tied to its task
    assert result.metadata["agent"] == "flaky"


async def test_two_slow_agents_run_concurrently():
    """Two 0.2s agents awaited together finish in ~0.2s, not ~0.4s.

    This proves async concurrency: while one agent is 'waiting', the event
    loop runs the other. We assert < 0.35s to stay well clear of 0.4s.
    """
    slow = MockAgent(delay=0.2)
    loop = asyncio.get_event_loop()

    start = loop.time()
    await asyncio.gather(slow.execute(make_task()), slow.execute(make_task()))
    elapsed = loop.time() - start

    assert elapsed < 0.35
