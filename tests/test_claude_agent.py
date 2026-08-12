"""Tests for ClaudeAgent, using a fake 'claude' CLI (a small python script).

This proves the whole agent path — prompt in via stdin, result out — without
the real CLI and without spending any tokens.
"""

import sys

from orchestrator.agents import ClaudeAgent
from orchestrator.models import Task, TaskStatus

PY = sys.executable


def task(prompt: str = "hello") -> Task:
    return Task(type="demo", prompt=prompt)


# A fake CLI that reads the prompt from stdin and echoes a canned reply.
FAKE_OK = [PY, "-c", "import sys; print('You said:', sys.stdin.read().strip())"]

# A fake CLI that writes to stderr and exits non-zero.
FAKE_FAIL = [PY, "-c", "import sys; sys.stderr.write('cli error'); sys.exit(2)"]

# A fake CLI that hangs.
FAKE_HANG = [PY, "-c", "import time; time.sleep(5)"]


async def test_success_maps_stdout_to_output():
    agent = ClaudeAgent(command=FAKE_OK)
    result = await agent.execute(task("build a login form"))

    assert result.status is TaskStatus.SUCCESS
    assert result.output == "You said: build a login form"
    assert result.metadata["agent"] == "claude"


async def test_nonzero_exit_becomes_failure():
    agent = ClaudeAgent(command=FAKE_FAIL)
    result = await agent.execute(task())

    assert result.status is TaskStatus.FAILURE
    assert result.metadata["error"] == "nonzero_exit"
    assert result.metadata["exit_code"] == 2
    assert "cli error" in result.metadata["stderr"]


async def test_timeout_becomes_failure():
    agent = ClaudeAgent(command=FAKE_HANG, timeout=0.3)
    result = await agent.execute(task())

    assert result.status is TaskStatus.FAILURE
    assert result.metadata["error"] == "timeout"
