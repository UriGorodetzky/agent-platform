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
