"""Tests for the coding workflow graph, including the retry loop."""

from orchestrator.agents import Agent, MockAgent
from orchestrator.models import AgentResult, Task, TaskStatus
from orchestrator.registry import AgentRegistry
from orchestrator.workflow import build_coding_graph, parse_subtasks


def test_parse_subtasks_routes_tagged_lines_by_capability():
    plan = "coding: implement operations.py\n- docs: write a README\nsomething untagged"
    assert parse_subtasks(plan) == [
        ("coding", "implement operations.py"),
        ("docs", "write a README"),
        ("coding", "something untagged"),
    ]


def test_parse_subtasks_defaults_a_plain_plan_to_one_coding_subtask():
    assert parse_subtasks("1. implement it  2. test it") == [("coding", "implement it  2. test it")]
    assert parse_subtasks("") == []


class FlakyTester(Agent):
    """A tester that fails its first ``fail_times`` runs, then succeeds."""

    def __init__(self, fail_times: int) -> None:
        self.name = "tester"
        self._fail_times = fail_times
        self.calls = 0

    async def execute(self, task: Task) -> AgentResult:
        self.calls += 1
        passed = self.calls > self._fail_times
        return AgentResult(
            task_id=task.id,
            status=TaskStatus.SUCCESS if passed else TaskStatus.FAILURE,
            output="tests ran",
        )


def build(tester: Agent):
    """Helper: a registry with fixed planner/coder/reviewer and a given tester."""
    registry = AgentRegistry()
    registry.register(MockAgent("planner", output="the plan"), ["planning"])
    registry.register(MockAgent("coder", output="the code"), ["coding"])
    registry.register(tester, ["testing"])
    registry.register(MockAgent("reviewer", output="LGTM"), ["review"])
    return build_coding_graph(registry, max_iterations=3)


async def test_happy_path_tests_pass_first_try():
    graph = build(FlakyTester(fail_times=0))
    state = await graph.ainvoke({"goal": "implement add()"})

    assert state["tests_passed"] is True
    assert state["attempts"] == 1        # coder ran once
    assert state["review"] == "LGTM"     # reviewer ran


async def test_retry_then_succeed():
    graph = build(FlakyTester(fail_times=2))   # fail, fail, pass
    state = await graph.ainvoke({"goal": "implement add()"})

    assert state["tests_passed"] is True
    assert state["attempts"] == 3        # coder retried until the 3rd run passed
    assert state["review"] == "LGTM"


async def test_give_up_after_max_iterations():
    graph = build(FlakyTester(fail_times=99))  # never passes
    state = await graph.ainvoke({"goal": "implement add()"})

    assert state["tests_passed"] is False
    assert state["attempts"] == 3        # stopped exactly at max_iterations
    assert "review" not in state         # reviewer never ran — we gave up
