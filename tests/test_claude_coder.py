"""Tests for ClaudeCoderAgent, using a fake 'claude' that writes a file.

No real Claude, no cost — we just verify the agent runs a command in the
workspace and returns the solution file it produced.
"""

import sys

from orchestrator.agents import ClaudeCoderAgent
from orchestrator.models import Task, TaskStatus

PY = sys.executable


def task(workspace) -> Task:
    return Task(type="coding", prompt="do it", context={"workspace": str(workspace)})


async def test_returns_the_written_solution(tmp_path):
    # Fake CLI that writes solution.py into the workspace (its cwd).
    fake = [PY, "-c", "open('solution.py', 'w').write('def reverse(s):\\n    return s[::-1]\\n')"]
    result = await ClaudeCoderAgent("coder", command=fake).execute(task(tmp_path))

    assert result.status is TaskStatus.SUCCESS
    assert "return s[::-1]" in result.output          # the file content is the output
    assert (tmp_path / "solution.py").exists()


async def test_no_solution_file_is_a_failure(tmp_path):
    fake = [PY, "-c", "print('I wrote nothing')"]
    result = await ClaudeCoderAgent("coder", command=fake).execute(task(tmp_path))

    assert result.status is TaskStatus.FAILURE
    assert result.metadata["error"] == "no_solution_file"
