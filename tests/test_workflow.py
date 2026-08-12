"""Tests for the linear coding workflow graph."""

from orchestrator.agents import MockAgent
from orchestrator.workflow import build_coding_graph


async def test_linear_graph_runs_planner_then_coder():
    planner = MockAgent("planner", output="1. write function\n2. write test")
    coder = MockAgent("coder", output="def add(a, b): return a + b")

    graph = build_coding_graph(planner, coder)
    final_state = await graph.ainvoke({"goal": "implement add()"})

    # The input survives, and both nodes wrote their outputs into state.
    assert final_state["goal"] == "implement add()"
    assert final_state["plan"] == "1. write function\n2. write test"
    assert final_state["code"] == "def add(a, b): return a + b"
