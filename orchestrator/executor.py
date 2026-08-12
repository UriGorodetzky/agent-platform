"""Run external programs as OS processes, the async way.

This is the low-level engine beneath any CLI-based agent (e.g. ClaudeAgent).
It knows nothing about Claude or prompts — it just launches a command, feeds
it input, captures its output, and enforces a timeout, all without blocking
the event loop.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass


@dataclass
class ProcessResult:
    """The outcome of running a subprocess.

    A plain dataclass, not a Pydantic model: this never crosses the HTTP
    boundary, it's an internal value. Not everything needs validation.
    """

    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False


async def run_subprocess(
    cmd: list[str],
    *,
    stdin: str | None = None,
    timeout: float | None = None,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
) -> ProcessResult:
    """Run ``cmd`` as a child process and return its result.

    Args:
        cmd:     program + args, e.g. ["python", "-c", "print('hi')"].
        stdin:   text to send to the process's standard input.
        timeout: seconds before we give up and kill the process.
        cwd:     working directory for the child (None = inherit ours).
        env:     environment for the child (None = inherit ours).
    """
    # Ask the OS to spawn the process. Returns immediately with a handle;
    # the child now runs independently, with three pipes wired up.
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
        env=env,
    )

    input_bytes = stdin.encode() if stdin is not None else None

    try:
        # communicate() writes our input, then reads stdout+stderr to EOF and
        # waits for exit — concurrently, so a full pipe buffer can't deadlock.
        # wait_for() is the watchdog that enforces the timeout.
        stdout_b, stderr_b = await asyncio.wait_for(
            proc.communicate(input=input_bytes),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        proc.kill()          # OS terminates the child
        await proc.wait()    # reap it so it doesn't linger as a zombie
        return ProcessResult(exit_code=-1, stdout="", stderr="", timed_out=True)
    except asyncio.CancelledError:
        # Our caller was cancelled: don't leak an orphan process.
        proc.kill()
        await proc.wait()
        raise

    return ProcessResult(
        exit_code=proc.returncode if proc.returncode is not None else -1,
        stdout=stdout_b.decode(errors="replace"),
        stderr=stderr_b.decode(errors="replace"),
    )
