"""The orchestration graph — LangGraph edition.

This is the "conductor". It does not know or care what kind of agent sits
behind each step; it only knows the Agent interface. The graph:

    START -> planner -> coder -> tester --(pass?)--> reviewer -> END
                          ^            |
                          +--(fail & attempts < max)--+
                                       |
                          (fail & attempts == max) -> END   (give up)

The loop back to `coder` is bounded by `max_iterations`, so a failing agent
can never retry forever.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional, TypedDict

from langgraph.graph import END, START, StateGraph
from opentelemetry import trace

from orchestrator import metrics
from orchestrator.events import EventStore, EventType
from orchestrator.logging_config import run_id_var
from orchestrator.models import AgentResult, Task, TaskStatus
from orchestrator.registry import AgentRegistry

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)   # a no-op until tracing is configured


BUILD_CAPABILITIES = {"coding", "docs"}   # capabilities a subtask may route to


def parse_subtasks(plan: str) -> list[tuple[str, str]]:
    """Parse the planner's output into (capability, description) subtasks.

    Lines shaped ``coding: implement X`` route to that capability; anything else
    defaults to coding. So a plain mock plan becomes a single coding subtask.
    """
    subtasks: list[tuple[str, str]] = []
    for raw in plan.splitlines():
        line = raw.strip().lstrip("-*0123456789. ").strip()
        if not line:
            continue
        cap, sep, desc = line.partition(":")
        cap = cap.strip().lower()
        if sep and cap in BUILD_CAPABILITIES and desc.strip():
            subtasks.append((cap, desc.strip()))
        else:
            subtasks.append(("coding", line))
    return subtasks


def _is_retryable(result: AgentResult) -> bool:
    """Retry only *infrastructure* failures, not task-level ones.

    An infra failure means the call itself did not go through (network error,
    timeout, non-zero exit) — our agents mark those with an ``error`` key in
    metadata. A plain FAILURE without ``error`` means the agent ran and judged
    the task failed (e.g. a tester reporting tests did not pass); that is not
    ours to retry here — the workflow's own loop handles it.
    """
    return result.status is TaskStatus.FAILURE and "error" in result.metadata


class WorkflowState(TypedDict, total=False):
    """The shared state every node reads from and writes to.

    ``total=False`` means keys may be absent early on (e.g. ``plan`` does
    not exist until the planner runs), so nodes use ``state.get(...)``.
    """

    goal: str            # the high-level user request (input)
    run_id: str          # identifies this run, for event tracking
    workspace: str       # a real directory the coder writes to and the tester runs in
    plan: str            # produced by the planner node
    code: str            # produced/updated by the coder node
    attempts: int        # how many times the coder has run
    tests_passed: bool   # set by the tester node
    test_output: str     # the tester's output, fed back to the coder on retry
    review: str          # produced by the reviewer node


def build_coding_graph(
    registry: AgentRegistry,
    *,
    max_iterations: int = 3,
    retry_attempts: int = 3,
    retry_base_delay: float = 0.1,
    events: Optional[EventStore] = None,
):
    """Build and compile the coding workflow with a bounded retry loop.

    The graph holds no concrete agents — each node asks the ``registry`` for
    one *at run time*, by capability. That is what makes load balancing real:
    two concurrent runs get different replicas via the registry's round-robin.

    Each agent call is retried up to ``retry_attempts`` times on infrastructure
    failures, with exponential backoff starting at ``retry_base_delay``. Because
    we re-select before every attempt, a retry usually lands on a *different*
    replica — so a single bad replica does not doom the step.

    If an ``events`` store is given, each attempt emits AGENT_STARTED and
    AGENT_COMPLETED/AGENT_FAILED events, tied to ``state['run_id']``.
    """

    async def run_agent(node: str, capability: str, task: Task, state: WorkflowState) -> AgentResult:
        """Select an agent, run it, and retry on infrastructure failures."""
        run_id = state.get("run_id")
        if run_id is not None:
            run_id_var.set(run_id)            # so every log line here carries the run_id
        result: Optional[AgentResult] = None

        with tracer.start_as_current_span(f"node:{node}") as span:
            span.set_attribute("capability", capability)
            for attempt in range(1, retry_attempts + 1):
                agent = await registry.select(capability)   # re-select each try: round-robin steers away from a bad replica
                span.set_attribute("agent", agent.name)
                if events is not None and run_id is not None:
                    await events.emit(run_id, EventType.AGENT_STARTED, agent=agent.name, node=node, attempt=attempt)

                result = await agent.execute(task)

                if result.status is TaskStatus.SUCCESS:
                    metrics.agent_attempts_total.labels(node=node, outcome="success").inc()
                    await registry.record_success(agent)   # feedback: closes the breaker
                    span.set_attribute("attempts", attempt)
                    if events is not None and run_id is not None:
                        await events.emit(run_id, EventType.AGENT_COMPLETED, agent=agent.name, node=node, attempt=attempt)
                    return result

                metrics.agent_attempts_total.labels(node=node, outcome="failure").inc()
                if _is_retryable(result):
                    await registry.record_failure(agent)   # feedback: may open the breaker

                if events is not None and run_id is not None:
                    await events.emit(
                        run_id, EventType.AGENT_FAILED,
                        agent=agent.name, node=node, attempt=attempt, error=result.metadata.get("error"),
                    )

                if not _is_retryable(result) or attempt == retry_attempts:
                    break

                delay = retry_base_delay * (2 ** (attempt - 1))   # exponential backoff
                logger.warning(
                    "agent failed, retrying",
                    extra={"agent": agent.name, "node": node, "attempt": attempt,
                           "error": result.metadata.get("error"), "next_delay_s": round(delay, 3)},
                )
                await asyncio.sleep(delay)

        return result

    async def planner_node(state: WorkflowState) -> dict:
        prompt = (
            "Break this software goal into a short list of subtasks. Output one per "
            "line as `capability: description`, where capability is `coding` (implement "
            "code + pytest tests) or `docs` (write a README with run instructions). "
            "No prose.\n\n"
            f"Goal: {state['goal']}"
        )
        task = Task(type="planning", prompt=prompt)
        result = await run_agent("planner", "planning", task, state)
        return {"plan": result.output}

    async def dispatch_node(state: WorkflowState) -> dict:
        """Route each subtask to the specialized agent for its capability."""
        attempts = state.get("attempts", 0) + 1
        subtasks = parse_subtasks(state.get("plan", "")) or [("coding", state["goal"])]
        prior = state.get("test_output", "")
        code = ""

        for capability, desc in subtasks:
            if capability == "docs":
                prompt = (
                    f"Write a short README.md in the current directory explaining how to run/use "
                    f"the project. Focus: {desc}. Goal: {state['goal']}. Do not ask questions."
                )
            else:  # coding
                prompt = (
                    "You are a coding agent. Implement this subtask in Python in the current "
                    "directory, creating the files it needs plus pytest tests in test_*.py, and "
                    "make the tests pass. Do not ask questions.\n\n"
                    f"Subtask: {desc}\nOverall goal: {state['goal']}"
                )
                if prior:
                    prompt += f"\n\nThe previous attempt's tests FAILED:\n{prior}\n\nFix the code so they pass."

            task = Task(type=capability, prompt=prompt, context={"workspace": state.get("workspace")})
            result = await run_agent(capability, capability, task, state)   # routed by capability
            if capability == "coding" and result.output:
                code = result.output   # the coder returns the assembled .py files

        return {"code": code, "attempts": attempts}

    async def tester_node(state: WorkflowState) -> dict:
        task = Task(type="testing", prompt="run the tests", context={"workspace": state.get("workspace")})
        result = await run_agent("tester", "testing", task, state)
        return {"tests_passed": result.status is TaskStatus.SUCCESS, "test_output": result.output}

    async def reviewer_node(state: WorkflowState) -> dict:
        task = Task(type="review", prompt=f"Review this code:\n{state.get('code', '')}")
        result = await run_agent("reviewer", "review", task, state)
        return {"review": result.output}

    def route_after_tester(state: WorkflowState) -> str:
        """Decide the next node based on the current state.

        This function is the conditional edge: LangGraph calls it and jumps
        to whatever node name it returns.
        """
        if state.get("tests_passed"):
            return "reviewer"
        if state.get("attempts", 0) >= max_iterations:
            return END          # out of retries — give up
        return "coder"          # try to fix and test again

    builder = StateGraph(WorkflowState)
    builder.add_node("planner", planner_node)
    builder.add_node("coder", dispatch_node)   # dispatches subtasks to specialized agents
    builder.add_node("tester", tester_node)
    builder.add_node("reviewer", reviewer_node)

    builder.add_edge(START, "planner")
    builder.add_edge("planner", "coder")
    builder.add_edge("coder", "tester")
    builder.add_conditional_edges(
        "tester",
        route_after_tester,
        {
            "reviewer": "reviewer", 
            "coder": "coder", 
            END: END
        },
    )
    builder.add_edge("reviewer", END)

    return builder.compile()
