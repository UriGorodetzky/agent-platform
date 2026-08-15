"""Echo Agent — a standalone external agent service.

It is deliberately independent of the orchestrator: it defines its own request
and response models and shares only the JSON *contract*. This is what an
external agent looks like — it could be rewritten in any language and the
orchestrator's HTTPAgent would not care.

Run it locally:
    uvicorn services.echo_agent.main:app --port 9001
"""

from __future__ import annotations

import os
import socket

from fastapi import FastAPI
from pydantic import BaseModel, Field

# Who am I? Set per replica via the AGENT_ID env var (falls back to the
# container's hostname). This lets us SEE which replica handled each request.
INSTANCE_ID = os.environ.get("AGENT_ID", socket.gethostname())


class ExecuteRequest(BaseModel):
    """The contract: what the orchestrator POSTs to /execute."""

    task_id: str
    prompt: str
    context: dict = Field(default_factory=dict)


class ExecuteResponse(BaseModel):
    """The contract: what we return."""

    task_id: str
    status: str          # "success" or "failure"
    output: str = ""
    metadata: dict = Field(default_factory=dict)


app = FastAPI(title="Echo Agent")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/execute", response_model=ExecuteResponse)
async def execute(req: ExecuteRequest) -> ExecuteResponse:
    # A trivial, deterministic "agent" — no LLM, no cost.
    # context={"fail": true} forces a failure, which is handy for testing
    # the orchestrator's failure handling.
    if req.context.get("fail"):
        return ExecuteResponse(
            task_id=req.task_id,
            status="failure",
            output="",
            metadata={"agent": "echo-agent", "instance": INSTANCE_ID, "reason": "forced failure"},
        )

    return ExecuteResponse(
        task_id=req.task_id,
        status="success",
        output=f"echo: {req.prompt}",
        metadata={"agent": "echo-agent", "instance": INSTANCE_ID},
    )
