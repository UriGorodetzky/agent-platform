# Agent Orchestration Platform

A learning-first, production-style platform for orchestrating AI agents.
The core idea: a central orchestrator breaks a high-level goal into steps and
routes each step to an agent — **without knowing or caring** whether that agent
is Claude, OpenAI, a local model, or a mock. This "model-agnostic" boundary is
the design principle everything else hangs off of.

## Architecture (Phase 1)

Everything runs in a single Python process. No database, no network services,
no Docker yet — those get introduced later, each as the answer to a concrete
problem the system runs into.

```text
   HTTP POST /tasks
        │
        ▼
     FastAPI              orchestrator/api.py     ← parse, validate, serialize
        │
        ▼
   LangGraph workflow     orchestrator/workflow.py
        │
   START → planner → coder → tester ──(pass?)──► reviewer → END
                      ▲            │
                      └──(fail & attempts < max)──┘
                                   │
                      (fail & attempts == max) → END   (give up)
        │
        ▼
   Agent interface        orchestrator/agents/base.py
        │
        ▼
   MockAgent (for now)    orchestrator/agents/mock.py
```

## Layout

```text
orchestrator/
├── models.py          # Task, AgentResult, TaskStatus (Pydantic)
├── agents/
│   ├── base.py        # Agent ABC — the interface
│   ├── mock.py        # MockAgent — configurable fake for tests/demos
│   ├── claude.py      # ClaudeAgent — runs the Claude Code CLI
│   └── http_agent.py  # HTTPAgent — calls an external agent service over HTTP
├── executor.py        # run_subprocess — async process engine (timeout, cancel)
├── registry.py        # AgentRegistry — pick an agent by capability
├── events.py          # Event, EventStore — per-run timeline, persisted in SQLite
├── workflow.py        # LangGraph state machine + bounded retry loop
└── api.py             # FastAPI app (see Endpoints below)
services/
└── echo_agent/        # a standalone external agent (its own FastAPI service)
tests/                 # pytest suite
```

## External agents

An external agent runs as its own service and speaks only a JSON contract
(POST /execute, GET /health) — no shared code with the orchestrator. Run one:

```bash
uvicorn services.echo_agent.main:app --port 9001
```

The orchestrator reaches it through `HTTPAgent(base_url="http://127.0.0.1:9001")`,
which implements the same `Agent` interface as every in-process agent.

Or run it as a Docker container (self-contained, its own dependencies):

```bash
docker build -t echo-agent:0.2 services/echo_agent
docker run -d --name echo -p 9001:8000 echo-agent:0.2
```

## Run the whole system (Docker Compose)

One command builds and starts the orchestrator plus three echo replicas:

```bash
docker compose up -d --build
```

- Orchestrator API on <http://localhost:8080> (docs at `/docs`).
- The orchestrator reaches the replicas **by service name** (`http://echo-1:8000`)
  over Docker's internal network — set via the `ECHO_AGENT_URLS` env var, no host
  ports involved. The registry round-robins across them, so concurrent runs
  spread out; retries and the circuit breaker route around a failed replica.
- The SQLite event store lives on a named volume (`DB_PATH=/data/orchestrator.db`),
  so a run's timeline survives `docker compose restart orchestrator`.

```bash
curl -X POST http://localhost:8080/tasks -H "Content-Type: application/json" -d "{\"goal\":\"build X\"}"
```

### Observability stack

The compose stack also runs Prometheus and Grafana:

- **Prometheus** at <http://localhost:9090> scrapes the orchestrator's `/metrics` every 5s.
- **Grafana** at <http://localhost:3000> (anonymous access) auto-loads the
  "Agent Platform" dashboard — tasks in progress, task rate, p95 latency, and
  agent attempts. Datasource and dashboard are provisioned from `observability/`.

## Endpoints

```text
POST /tasks                  run a workflow; returns run_id + result
GET  /tasks/{run_id}         the stored run summary (goal, status, result, timestamps)
GET  /tasks/{run_id}/events  the event timeline of a run
GET  /agents                 which agents serve which capabilities
GET  /health                 liveness check
GET  /version                the git commit this image was built from
GET  /metrics                Prometheus metrics (counters, gauge, histogram)
```

To bake the commit into the image and verify what's running:

```bash
GIT_SHA=$(git rev-parse --short HEAD) docker compose up -d --build orchestrator
curl -s http://localhost:8080/version    # git_sha should match `git rev-parse --short HEAD`
```

## Run it

Create the environment and install (one time):

```bash
py -3.10 -m venv .venv
./.venv/Scripts/python.exe -m pip install -e ".[dev]"
```

Run the tests:

```bash
./.venv/Scripts/python.exe -m pytest -q
```

Start the API:

```bash
./.venv/Scripts/python.exe -m uvicorn orchestrator.api:app --reload
```

Then, in another terminal:

```bash
curl -X POST http://127.0.0.1:8000/tasks -H "Content-Type: application/json" -d "{\"goal\":\"implement a fibonacci function\"}"
```

Interactive API docs are auto-generated by FastAPI at
<http://127.0.0.1:8000/docs>.

### Mock vs real agents

By default every agent is a mock, so the orchestration works out of the box with
no cost. The real path uses **Claude Code in a workspace** to write code + tests
and a **pytest** tester to run them for real. Choose it two ways:

```bash
# server-wide default:
REAL_AGENTS=1 ./.venv/Scripts/python.exe -m uvicorn orchestrator.api:app

# or per request (no restart), overriding the default:
curl -X POST http://localhost:8000/tasks -H "Content-Type: application/json" \
  -d "{\"goal\":\"a function that checks if a number is prime\",\"real\":true}"
```

The real coder runs Claude (costs tokens); the produced file lands in a per-run
workspace under your temp dir.

## Key design decisions

- **Agent is an ABC, not a Protocol.** We write every agent ourselves, so
  runtime enforcement and a place for shared logic win over structural typing.
- **Everything async.** Real agents are I/O-bound (network, subprocess). One
  process can juggle many agents concurrently while they wait.
- **Two layers of loop protection.** `max_iterations` is the business rule;
  LangGraph's `recursion_limit` is the engine's safety net.
- **The endpoint runs synchronously for now.** Returning a task id and polling
  is a Phase 2/3 concern — we add it when tasks get slow enough to need it.
- **Dependency injection at the seams.** The graph takes agents as arguments;
  the app takes a graph. This is what makes everything testable with mocks.
- **Structured (JSON) logging to stdout**, with the `run_id` carried in a
  ContextVar and injected into every line. These developer-facing diagnostics
  (retries, circuit-breaker opens, timings) complement the user-facing events.

## Roadmap

- **Phase 1 (done):** FastAPI + LangGraph + MockAgent, single process.
- **Phase 2:** real agents (Claude CLI, external API), agent registry, events.
- **Phase 3:** PostgreSQL + Redis, persistent workflows, observability.
- **Phase 4:** Dockerize every component.
- **Phase 5:** Kubernetes on AWS (EKS, RDS, ElastiCache, S3, ECR).
- **Phase 6:** CI/CD and scaling.
