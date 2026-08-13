"""Tests for the HTTP API using FastAPI's in-process TestClient."""

from fastapi.testclient import TestClient

from orchestrator.api import create_app


def test_health():
    client = TestClient(create_app())
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_post_task_runs_workflow():
    client = TestClient(create_app())
    resp = client.post("/tasks", json={"goal": "implement add()"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["goal"] == "implement add()"
    assert body["tests_passed"] is True   # default mock tester passes
    assert body["attempts"] == 1
    assert body["review"] == "LGTM"


def test_post_task_rejects_missing_goal():
    client = TestClient(create_app())
    resp = client.post("/tasks", json={})   # no 'goal'
    assert resp.status_code == 422          # FastAPI validation error


def test_list_agents_reflects_the_registry():
    client = TestClient(create_app())
    resp = client.get("/agents")
    assert resp.status_code == 200
    body = resp.json()
    assert body["planning"] == ["planner"]
    assert body["coding"] == ["coder"]


def test_run_produces_a_queryable_event_timeline():
    client = TestClient(create_app())
    run_id = client.post("/tasks", json={"goal": "implement add()"}).json()["run_id"]

    events = client.get(f"/tasks/{run_id}/events").json()["events"]
    types = [e["type"] for e in events]

    # The run's story: it starts, agents run, it completes.
    assert types[0] == "TASK_STARTED"
    assert types[-1] == "TASK_COMPLETED"
    assert "AGENT_STARTED" in types
    assert "AGENT_COMPLETED" in types
    # planner + coder + tester + reviewer each start once on the happy path.
    assert types.count("AGENT_STARTED") == 4
