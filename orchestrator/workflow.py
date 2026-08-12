"""The orchestration graph — LangGraph edition.

This is the "conductor". It does not know or care what kind of agent sits
behind each step; it only knows the Agent interface. The graph:

    START -> planner -> coder -> tester --(pass?)--> reviewer -> END
                          ^            |
                          +--(fail & attempts < max)--+
                                       |
                          (fail & attempts == max) -> END   (give up)

The loop back to `coder` is bounded by `max_iterations`, so a failing agent
can never retry forever.
"""

from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from orchestrator.agents.base import Agent
from orchestrator.models import Task, TaskStatus


class WorkflowState(TypedDict, total=False):
    """The shared state every node reads from and writes to.

    ``total=False`` means keys may be absent early on (e.g. ``plan`` does
    not exist until the planner runs), so nodes use ``state.get(...)``.
    """

    goal: str            # the high-level user request (input)
    plan: str            # produced by the planner node
    code: str            # produced/updated by the coder node
    attempts: int        # how many times the coder has run
    tests_passed: bool   # set by the tester node
    review: str          # produced by the reviewer node


def build_coding_graph(
    planner: Agent,
    coder: Agent,
    tester: Agent,
    reviewer: Agent,
    *,
    max_iterations: int = 3,
):
    """Build and compile the coding workflow with a bounded retry loop."""

    async def planner_node(state: WorkflowState) -> dict:
        task = Task(type="planning", prompt=f"Make a plan for: {state['goal']}")
        result = await planner.execute(task)
        return {"plan": result.output}

    async def coder_node(state: WorkflowState) -> dict:
        attempts = state.get("attempts", 0) + 1
        task = Task(type="coding", prompt=f"Implement this plan:\n{state.get('plan', '')}")
        result = await coder.execute(task)
        return {"code": result.output, "attempts": attempts}

    async def tester_node(state: WorkflowState) -> dict:
        task = Task(type="testing", prompt=f"Run tests for:\n{state.get('code', '')}")
        result = await tester.execute(task)
        return {"tests_passed": result.status is TaskStatus.SUCCESS}

    async def reviewer_node(state: WorkflowState) -> dict:
        task = Task(type="review", prompt=f"Review this code:\n{state.get('code', '')}")
        result = await reviewer.execute(task)
        return {"review": result.output}

    def route_after_tester(state: WorkflowState) -> str:
        """Decide the next node based on the current state.

        This function is the conditional edge: LangGraph calls it and jumps
        to whatever node name it returns.
        """
        if state.get("tests_passed"):
            return "reviewer"
        if state.get("attempts", 0) >= max_iterations:
            return END          # out of retries — give up
        return "coder"          # try to fix and test again

    builder = StateGraph(WorkflowState)
    builder.add_node("planner", planner_node)
    builder.add_node("coder", coder_node)
    builder.add_node("tester", tester_node)
    builder.add_node("reviewer", reviewer_node)

    builder.add_edge(START, "planner")
    builder.add_edge("planner", "coder")
    builder.add_edge("coder", "tester")
    builder.add_conditional_edges(
        "tester",
        route_after_tester,
        {
            "reviewer": "reviewer", 
            "coder": "coder", 
            END: END
        },
    )
    builder.add_edge("reviewer", END)

    return builder.compile()
