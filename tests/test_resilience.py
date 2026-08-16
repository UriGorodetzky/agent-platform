"""Tests for agent-level retry (F1)."""

from orchestrator.agents import Agent, MockAgent
from orchestrator.models import AgentResult, Task, TaskStatus
from orchestrator.registry import AgentRegistry
from orchestrator.workflow import build_coding_graph


class InfraFlakyCoder(Agent):
    """Fails with an *infrastructure* error N times, then succeeds."""

    def __init__(self, fail_times: int) -> None:
        self.name = "coder"
        self._fail_times = fail_times
        self.calls = 0

    async def execute(self, task: Task) -> AgentResult:
        self.calls += 1
        if self.calls <= self._fail_times:
            return AgentResult(
                task_id=task.id,
                status=TaskStatus.FAILURE,
                metadata={"agent": self.name, "error": "network_error"},  # infra
            )
        return AgentResult(task_id=task.id, status=TaskStatus.SUCCESS, output="fixed code")


class TaskFailingCoder(Agent):
    """Always fails at the *task* level (no 'error' key) — not retryable here."""

    def __init__(self) -> None:
        self.name = "coder"
        self.calls = 0

    async def execute(self, task: Task) -> AgentResult:
        self.calls += 1
        return AgentResult(task_id=task.id, status=TaskStatus.FAILURE, output="nope")


def registry_with(coder: Agent) -> AgentRegistry:
    reg = AgentRegistry()
    reg.register(MockAgent("planner", output="plan"), ["planning"])
    reg.register(coder, ["coding"])
    reg.register(MockAgent("tester", output="ok"), ["testing"])   # SUCCESS
    reg.register(MockAgent("reviewer", output="LGTM"), ["review"])
    return reg


async def test_infra_failure_is_retried_until_success():
    coder = InfraFlakyCoder(fail_times=2)     # fail, fail, succeed
    graph = build_coding_graph(registry_with(coder), retry_base_delay=0.0)

    state = await graph.ainvoke({"goal": "x"})

    assert coder.calls == 3               # retried twice, then succeeded
    assert state["code"] == "fixed code"


async def test_task_level_failure_is_not_retried():
    coder = TaskFailingCoder()
    graph = build_coding_graph(registry_with(coder), retry_base_delay=0.0)

    await graph.ainvoke({"goal": "x"})

    assert coder.calls == 1               # a task-level failure is not our retry


async def test_infra_failure_gives_up_after_max_attempts():
    coder = InfraFlakyCoder(fail_times=99)    # never recovers
    graph = build_coding_graph(registry_with(coder), retry_attempts=3, retry_base_delay=0.0)

    await graph.ainvoke({"goal": "x"})

    assert coder.calls == 3               # exactly retry_attempts, then gives up
