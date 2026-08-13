"""HTTP entry point — FastAPI application.

Flow of one request:

    HTTP POST /tasks
        -> FastAPI parses & validates the JSON body into RunRequest
        -> we invoke the compiled LangGraph workflow
        -> the final state is shaped into RunResponse
        -> FastAPI serializes it back to JSON
"""

from __future__ import annotations

from uuid import uuid4

from fastapi import FastAPI
from pydantic import BaseModel, Field

from orchestrator.agents import MockAgent
from orchestrator.events import EventBus, EventType
from orchestrator.registry import AgentRegistry
from orchestrator.workflow import build_coding_graph


class RunRequest(BaseModel):
    """The JSON body a client POSTs to /tasks."""

    goal: str = Field(description="High-level thing to build")


class RunResponse(BaseModel):
    """What we return once the workflow finishes."""

    run_id: str
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


def build_graph_from_registry(registry: AgentRegistry, events: EventBus | None = None):
    """Pick each role from the registry by capability, then build the graph."""
    return build_coding_graph(
        planner=registry.select("planning"),
        coder=registry.select("coding"),
        tester=registry.select("testing"),
        reviewer=registry.select("review"),
        events=events,
    )


def create_app(registry=None, graph=None, events=None) -> FastAPI:
    """Create the FastAPI app. Registry, graph, and events are injectable."""
    app = FastAPI(title="Agent Orchestration Platform")
    registry = registry or build_default_registry()
    events = events or EventBus()
    graph = graph or build_graph_from_registry(registry, events)

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    @app.get("/agents")
    async def list_agents() -> dict:
        """Which agents can serve which capabilities."""
        return registry.capabilities()

    @app.post("/tasks", response_model=RunResponse)
    async def create_task(req: RunRequest) -> RunResponse:
        run_id = uuid4().hex
        events.emit(run_id, EventType.TASK_STARTED, goal=req.goal)

        state = await graph.ainvoke({"goal": req.goal, "run_id": run_id})

        events.emit(
            run_id,
            EventType.TASK_COMPLETED,
            tests_passed=state.get("tests_passed", False),
            attempts=state.get("attempts", 0),
        )
        return RunResponse(
            run_id=run_id,
            goal=state["goal"],
            code=state.get("code", ""),
            tests_passed=state.get("tests_passed", False),
            attempts=state.get("attempts", 0),
            review=state.get("review"),
        )

    @app.get("/tasks/{run_id}/events")
    async def get_events(run_id: str) -> dict:
        """The timeline of a run: what happened, in order."""
        return {
            "run_id": run_id,
            "events": [event.model_dump(mode="json") for event in events.get(run_id)],
        }

    return app


# Module-level app so `uvicorn orchestrator.api:app` works.
app = create_app()
