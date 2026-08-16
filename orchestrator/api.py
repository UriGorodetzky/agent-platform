"""HTTP entry point — FastAPI application.

Flow of one request:

    HTTP POST /tasks
        -> FastAPI parses & validates the JSON body into RunRequest
        -> we invoke the compiled LangGraph workflow
        -> the final state is shaped into RunResponse
        -> FastAPI serializes it back to JSON
"""

from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel, Field

from orchestrator import metrics
from orchestrator.agents import HTTPAgent, MockAgent
from orchestrator.events import EventStore, EventType
from orchestrator.logging_config import run_id_var, setup_logging
from orchestrator.models import TaskStatus
from orchestrator.registry import AgentRegistry
from orchestrator.runs import Run, RunStore
from orchestrator.workflow import build_coding_graph

setup_logging(os.environ.get("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

# The git commit baked into the image at build time (see Dockerfile). "dev" when
# running from source. Exposed at /version to verify what's actually deployed.
GIT_SHA = os.environ.get("GIT_SHA", "dev")


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
    """Register agents under their capabilities.

    The "coding" agents come from the ECHO_AGENT_URLS env var (comma-separated
    URLs) when set — that's how the dockerized orchestrator reaches the echo
    replicas by service name. With no env var, we fall back to a mock coder so
    the app still runs locally with zero setup.
    """
    registry = AgentRegistry()
    registry.register(MockAgent("planner", output="1. implement it  2. test it"), ["planning"])

    coder_urls = [u.strip() for u in os.environ.get("ECHO_AGENT_URLS", "").split(",") if u.strip()]
    if coder_urls:
        for i, url in enumerate(coder_urls, start=1):
            registry.register(HTTPAgent(f"echo-{i}", base_url=url), ["coding"])
        logger.info("registered HTTP coding agents", extra={"count": len(coder_urls)})
    else:
        registry.register(MockAgent("coder", output="def solution(): ..."), ["coding"])
        logger.info("using mock coding agent (no ECHO_AGENT_URLS)")

    registry.register(MockAgent("tester", output="all tests passed"), ["testing"])
    registry.register(MockAgent("reviewer", output="LGTM"), ["review"])
    return registry


def build_graph_from_registry(registry: AgentRegistry, events: EventStore | None = None):
    """Build the graph over the registry; nodes select agents at run time."""
    return build_coding_graph(registry, events=events)


def create_app(registry=None, graph=None, events=None, runs=None) -> FastAPI:
    """Create the FastAPI app. Registry, graph, events, and runs are injectable."""
    db_path = os.environ.get("DB_PATH", "orchestrator.db")
    registry = registry or build_default_registry()
    events = events or EventStore(db_path)
    runs = runs or RunStore(db_path)
    graph = graph or build_graph_from_registry(registry, events)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Startup: nothing to do (the stores connect lazily on first use).
        yield
        # Shutdown: release both DB connections and their background threads.
        await events.close()
        await runs.close()

    app = FastAPI(title="Agent Orchestration Platform", lifespan=lifespan)

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    @app.get("/version")
    async def version() -> dict:
        """The git commit this running image was built from."""
        return {"service": "orchestrator", "git_sha": GIT_SHA}

    @app.get("/metrics")
    async def metrics_endpoint() -> Response:
        """Current metric values, in Prometheus text format (for scraping)."""
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @app.get("/agents")
    async def list_agents() -> dict:
        """Which agents can serve which capabilities."""
        return registry.capabilities()

    @app.post("/tasks", response_model=RunResponse)
    async def create_task(req: RunRequest) -> RunResponse:
        run_id = uuid4().hex
        run_id_var.set(run_id)                                 # correlate all logs of this run
        started = time.perf_counter()
        logger.info("task received", extra={"goal": req.goal})

        metrics.tasks_in_progress.inc()                        # gauge: one more in flight
        try:
            await runs.create(run_id, req.goal)                # record the run (RUNNING)
            await events.emit(run_id, EventType.TASK_STARTED, goal=req.goal)

            state = await graph.ainvoke({"goal": req.goal, "run_id": run_id})

            tests_passed = state.get("tests_passed", False)
            attempts = state.get("attempts", 0)
            status = "success" if tests_passed else "failure"
            await events.emit(run_id, EventType.TASK_COMPLETED, tests_passed=tests_passed, attempts=attempts)
            await runs.complete(                               # fill in the outcome
                run_id,
                status=TaskStatus.SUCCESS if tests_passed else TaskStatus.FAILURE,
                code=state.get("code", ""),
                review=state.get("review"),
                tests_passed=tests_passed,
                attempts=attempts,
            )

            duration = time.perf_counter() - started
            metrics.tasks_total.labels(status=status).inc()   # counter: +1 by outcome
            metrics.task_duration_seconds.observe(duration)   # histogram: record latency
            logger.info(
                "task completed",
                extra={"status": status, "attempts": attempts, "duration_ms": round(duration * 1000)},
            )
            return RunResponse(
                run_id=run_id,
                goal=state["goal"],
                code=state.get("code", ""),
                tests_passed=tests_passed,
                attempts=attempts,
                review=state.get("review"),
            )
        finally:
            metrics.tasks_in_progress.dec()                   # gauge: back down, even on error

    @app.get("/tasks/{run_id}", response_model=Run)
    async def get_task(run_id: str) -> Run:
        """The stored summary/result of a run."""
        run = await runs.get(run_id)
        if run is None:
            logger.warning("run not found", extra={"requested_run_id": run_id})
            raise HTTPException(status_code=404, detail=f"No run {run_id!r}")
        return run

    @app.get("/tasks/{run_id}/events")
    async def get_events(run_id: str) -> dict:
        """The timeline of a run: what happened, in order."""
        return {
            "run_id": run_id,
            "events": [event.model_dump(mode="json") for event in await events.get(run_id)],
        }

    return app


# Module-level app so `uvicorn orchestrator.api:app` works.
app = create_app()
