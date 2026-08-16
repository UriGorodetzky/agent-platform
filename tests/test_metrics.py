"""Tests for the /metrics endpoint."""

from fastapi.testclient import TestClient

from orchestrator.api import create_app
from orchestrator.events import EventStore
from orchestrator.runs import RunStore


def make_app():
    return create_app(events=EventStore(":memory:"), runs=RunStore(":memory:"))


def test_metrics_endpoint_exposes_prometheus_text():
    with TestClient(make_app()) as client:
        resp = client.get("/metrics")

    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]
    body = resp.text
    assert "orchestrator_tasks_in_progress" in body         # gauge
    assert "orchestrator_task_duration_seconds" in body     # histogram


def test_running_a_task_updates_the_counters():
    with TestClient(make_app()) as client:
        client.post("/tasks", json={"goal": "x"})
        body = client.get("/metrics").text

    assert 'orchestrator_tasks_total{status="success"}' in body
    assert 'orchestrator_agent_attempts_total{node="coder",outcome="success"}' in body
