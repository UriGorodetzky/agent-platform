"""A per-run workspace directory — a real filesystem the agents share.

The coder writes code files here; the tester runs them here. This is what turns
the agents from text-in/text-out functions into real workers that produce and
verify an artifact.
"""

from __future__ import annotations

import os
import pathlib
import re
import tempfile


def _slug(text: str) -> str:
    """A short, filesystem-safe name from the goal (e.g. 'reverse-a-string')."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:40].rstrip("-") or "task"


def create_workspace(run_id: str, goal: str = "") -> str:
    """Create (and return) an isolated directory for one run.

    Named from the goal + a short run-id suffix, so it's recognizable on disk
    (e.g. ``reverse-a-string-092befdd``) instead of an opaque hash.
    """
    base = pathlib.Path(os.environ.get("WORKSPACE_ROOT", pathlib.Path(tempfile.gettempdir()) / "agent-workspaces"))
    name = f"{_slug(goal)}-{run_id[:8]}" if goal else run_id
    workspace = base / name
    workspace.mkdir(parents=True, exist_ok=True)
    return str(workspace)
