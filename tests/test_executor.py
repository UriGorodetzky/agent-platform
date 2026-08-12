"""Tests for run_subprocess, using this Python interpreter as a controllable
'external program'. No Claude, no cost — just real OS processes.
"""

import sys
import time

from orchestrator.executor import run_subprocess

PY = sys.executable  # path to the venv's python.exe


async def test_stdin_flows_to_stdout():
    # A tiny program that upper-cases whatever it reads on stdin.
    result = await run_subprocess(
        [PY, "-c", "import sys; sys.stdout.write(sys.stdin.read().upper())"],
        stdin="hello",
    )
    assert result.exit_code == 0
    assert result.stdout == "HELLO"
    assert result.timed_out is False


async def test_nonzero_exit_and_stderr_are_captured():
    result = await run_subprocess(
        [PY, "-c", "import sys; sys.stderr.write('boom'); sys.exit(3)"],
    )
    assert result.exit_code == 3
    assert "boom" in result.stderr
    assert result.stdout == ""


async def test_timeout_kills_a_hanging_process_quickly():
    start = time.perf_counter()
    result = await run_subprocess(
        [PY, "-c", "import time; time.sleep(5)"],
        timeout=0.3,
    )
    elapsed = time.perf_counter() - start

    assert result.timed_out is True
    assert elapsed < 2.0          # we did NOT wait the full 5 seconds
