"""Tests for the echo service and the HTTPAgent client.

The HTTPAgent tests route requests to the echo app *in-process* via httpx's
ASGITransport — real HTTP semantics, no real socket, no running server.
"""

import httpx
from fastapi.testclient import TestClient

from orchestrator.agents import HTTPAgent
from orchestrator.models import Task, TaskStatus
from services.echo_agent.main import app as echo_app


def task(prompt: str = "hello", **context) -> Task:
    return Task(type="demo", prompt=prompt, context=context)


# --- The service on its own ---

def test_echo_service_health():
    client = TestClient(echo_app)
    assert client.get("/health").json() == {"status": "ok"}


def test_echo_service_execute():
    client = TestClient(echo_app)
    resp = client.post("/execute", json={"task_id": "t1", "prompt": "hi", "context": {}})
    body = resp.json()
    assert body["status"] == "success"
    assert body["output"] == "echo: hi"


# --- The HTTPAgent talking to the service ---

async def test_http_agent_success():
    transport = httpx.ASGITransport(app=echo_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://echo") as client:
        agent = HTTPAgent("echo", base_url="http://echo", client=client)
        result = await agent.execute(task("build a form"))

    assert result.status is TaskStatus.SUCCESS
    assert result.output == "echo: build a form"
    assert result.metadata["agent"] == "echo"          # our client name wins


async def test_http_agent_maps_service_failure():
    transport = httpx.ASGITransport(app=echo_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://echo") as client:
        agent = HTTPAgent("echo", base_url="http://echo", client=client)
        result = await agent.execute(task("x", fail=True))   # context forces failure

    assert result.status is TaskStatus.FAILURE
    assert result.metadata["reason"] == "forced failure"


async def test_http_agent_handles_unreachable_service():
    # Nothing is listening here -> connection refused -> FAILURE, not a crash.
    agent = HTTPAgent("dead", base_url="http://127.0.0.1:59999", timeout=2)
    result = await agent.execute(task())

    assert result.status is TaskStatus.FAILURE
    assert result.metadata["error"] == "unreachable"
