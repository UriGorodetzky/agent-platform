"""HTTP entry point — FastAPI application.

Flow of one request:

    HTTP POST /tasks
        -> FastAPI parses & validates the JSON body into RunRequest
        -> we invoke the compiled LangGraph workflow
        -> the final state is shaped into RunResponse
        -> FastAPI serializes it back to JSON
"""

from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel, Field

from orchestrator.agents import MockAgent
from orchestrator.registry import AgentRegistry
from orchestrator.workflow import build_coding_graph


class RunRequest(BaseModel):
    """The JSON body a client POSTs to /tasks."""

    goal: str = Field(description="High-level thing to build")


class RunResponse(BaseModel):
    """What we return once the workflow finishes."""

    goal: str
    code: str
    tests_passed: bool
    attempts: int
    review: str | None = None


def build_default_registry() -> AgentRegistry:
    """Register the Phase 1 mock agents under their capabilities."""
    registry = AgentRegistry()
    registry.register(MockAgent("planner", output="1. implement it  2. test it"), ["planning"])
    registry.register(MockAgent("coder", output="def solution(): ..."), ["coding"])
    registry.register(MockAgent("tester", output="all tests passed"), ["testing"])
    registry.register(MockAgent("reviewer", output="LGTM"), ["review"])
    return registry


def build_graph_from_registry(registry: AgentRegistry):
    """Pick each role from the registry by capability, then build the graph."""
    return build_coding_graph(
        planner=registry.select("planning"),
        coder=registry.select("coding"),
        tester=registry.select("testing"),
        reviewer=registry.select("review"),
    )


def create_app(registry=None, graph=None) -> FastAPI:
    """Create the FastAPI app. Registry and graph are injectable for testing."""
    app = FastAPI(title="Agent Orchestration Platform")
    registry = registry or build_default_registry()
    graph = graph or build_graph_from_registry(registry)

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    @app.get("/agents")
    async def list_agents() -> dict:
        """Which agents can serve which capabilities."""
        return registry.capabilities()

    @app.post("/tasks", response_model=RunResponse)
    async def create_task(req: RunRequest) -> RunResponse:
        state = await graph.ainvoke({"goal": req.goal})
        return RunResponse(
            goal=state["goal"],
            code=state.get("code", ""),
            tests_passed=state.get("tests_passed", False),
            attempts=state.get("attempts", 0),
            review=state.get("review"),
        )

    return app


# Module-level app so `uvicorn orchestrator.api:app` works.
app = create_app()
