"""Application metrics, in Prometheus format.

These are defined once at import (prometheus_client keeps them in a global
registry) and incremented from around the codebase. The /metrics endpoint
exposes their current values as plain text for Prometheus to scrape.

The three metric types, and why each fits:
- Counter:   only ever goes up (total tasks, total attempts). Query rate() for
             "per second".
- Gauge:     goes up and down (tasks running right now).
- Histogram: buckets observations + keeps sum/count (task durations) so you can
             compute averages and percentiles like p95 latency.
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

# How many tasks finished, sliced by final status.
tasks_total = Counter(
    "orchestrator_tasks_total",
    "Tasks that finished, by final status",
    ["status"],
)

# Distribution of how long a task run took.
task_duration_seconds = Histogram(
    "orchestrator_task_duration_seconds",
    "Wall-clock duration of a task run, in seconds",
)

# How many tasks are running at this instant.
tasks_in_progress = Gauge(
    "orchestrator_tasks_in_progress",
    "Tasks currently being processed",
)

# Every agent attempt, sliced by node and outcome — this captures retries.
agent_attempts_total = Counter(
    "orchestrator_agent_attempts_total",
    "Agent execution attempts, by node and outcome",
    ["node", "outcome"],
)

# How often a circuit breaker tripped open, by agent.
circuit_breaker_opens_total = Counter(
    "orchestrator_circuit_breaker_opens_total",
    "Times a circuit breaker opened, by agent",
    ["agent"],
)
