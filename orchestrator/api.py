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


def build_default_graph():
    """Wire up the workflow with mock agents (Phase 1 stand-ins)."""
    return build_coding_graph(
        planner=MockAgent("planner", output="1. implement it  2. test it"),
        coder=MockAgent("coder", output="def solution(): ..."),
        tester=MockAgent("tester", output="all tests passed"),
        reviewer=MockAgent("reviewer", output="LGTM"),
    )


def create_app(graph=None) -> FastAPI:
    """Create the FastAPI app. The graph is injectable for testing."""
    app = FastAPI(title="Agent Orchestration Platform")
    graph = graph or build_default_graph()

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

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
