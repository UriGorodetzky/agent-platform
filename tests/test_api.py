"""Tests for the HTTP API using FastAPI's in-process TestClient.

Each app gets its own in-memory EventStore so tests never touch a real file
and never share state. We use `with TestClient(...)` so all requests in a test
run on one event loop (aiosqlite's connection is bound to the loop it opened on).
"""

from fastapi.testclient import TestClient

from orchestrator.agents import ClaudeAgent, ClaudeCoderAgent, MockAgent, PytestTesterAgent
from orchestrator.api import build_default_registry, create_app
from orchestrator.events import EventStore
from orchestrator.runs import RunStore


def make_app():
    return create_app(events=EventStore(":memory:"), runs=RunStore(":memory:"))


def test_health():
    with TestClient(make_app()) as client:
        resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_coder_is_mock_by_default_but_claude_with_env(monkeypatch):
    # Default: a mock coder (no external calls, works out of the box).
    assert isinstance(build_default_registry().get("coder"), MockAgent)

    # Opt in: CLAUDE_ROLES swaps in the real Claude agent (constructed, not called).
    monkeypatch.setenv("CLAUDE_ROLES", "coding")
    assert isinstance(build_default_registry().get("coder"), ClaudeAgent)


def test_real_flag_selects_the_closed_loop_agents():
    # real=True gives the workspace coder + pytest tester (constructed, not called).
    registry = build_default_registry(real=True)
    assert isinstance(registry.get("coder"), ClaudeCoderAgent)
    assert isinstance(registry.get("tester"), PytestTesterAgent)


def test_version_reports_git_sha():
    with TestClient(make_app()) as client:
        body = client.get("/version").json()
    assert body["service"] == "orchestrator"
    assert "git_sha" in body                 # "dev" from source; a real SHA in an image


def test_post_task_runs_workflow():
    with TestClient(make_app()) as client:
        resp = client.post("/tasks", json={"goal": "implement add()"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["goal"] == "implement add()"
    assert body["tests_passed"] is True   # default mock tester passes
    assert body["attempts"] == 1
    assert body["review"] == "LGTM"
    assert body["run_id"]                 # a run id was assigned


def test_post_task_rejects_missing_goal():
    with TestClient(make_app()) as client:
        resp = client.post("/tasks", json={})   # no 'goal'
    assert resp.status_code == 422               # FastAPI validation error


def test_list_agents_reflects_the_registry():
    with TestClient(make_app()) as client:
        resp = client.get("/agents")
    assert resp.status_code == 200
    body = resp.json()
    assert body["planning"] == ["planner"]
    assert body["coding"] == ["coder"]


def test_get_task_returns_the_stored_run():
    with TestClient(make_app()) as client:
        run_id = client.post("/tasks", json={"goal": "implement add()"}).json()["run_id"]
        run = client.get(f"/tasks/{run_id}").json()

    assert run["run_id"] == run_id
    assert run["goal"] == "implement add()"
    assert run["status"] == "success"
    assert run["tests_passed"] is True
    assert run["review"] == "LGTM"
    assert run["completed_at"] is not None


def test_get_unknown_task_returns_404():
    with TestClient(make_app()) as client:
        resp = client.get("/tasks/does-not-exist")
    assert resp.status_code == 404


def test_run_produces_a_queryable_event_timeline():
    with TestClient(make_app()) as client:
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
