"""The orchestration graph — LangGraph edition.

This is the "conductor". It does not know or care what kind of agent sits
behind each step; it only knows the Agent interface. For now the graph is
a straight line:

    START -> planner -> coder -> END

Later we will add a `tester` node and a conditional edge that loops back to
`coder` when tests fail (bounded by max_iterations).
"""

from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from orchestrator.agents.base import Agent
from orchestrator.models import Task


class WorkflowState(TypedDict):
    """The shared state every node reads from and writes to.

    LangGraph passes this dict from node to node. Each node returns a
    *partial* dict; LangGraph merges it in (the default reducer replaces
    the value of each returned key).
    """

    goal: str   # the high-level user request (input)
    plan: str   # produced by the planner node
    code: str   # produced by the coder node


def build_coding_graph(planner: Agent, coder: Agent):
    """Build and compile the linear coding workflow.

    Agents are injected so the same graph works with mocks in tests and
    real agents in production — the graph depends only on the interface.
    """

    async def planner_node(state: WorkflowState) -> dict:
        task = Task(type="planning", prompt=f"Make a plan for: {state['goal']}")
        result = await planner.execute(task)
        return {"plan": result.output}

    async def coder_node(state: WorkflowState) -> dict:
        task = Task(type="coding", prompt=f"Implement this plan:\n{state['plan']}")
        result = await coder.execute(task)
        return {"code": result.output}

    builder = StateGraph(WorkflowState)
    builder.add_node("planner", planner_node)
    builder.add_node("coder", coder_node)

    builder.add_edge(START, "planner")     # where execution begins
    builder.add_edge("planner", "coder")   # planner's output feeds coder
    builder.add_edge("coder", END)         # then we're done

    return builder.compile()
