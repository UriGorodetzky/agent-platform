"""A per-run workspace directory — a real filesystem the agents share.

The coder writes code files here; the tester runs them here. This is what turns
the agents from text-in/text-out functions into real workers that produce and
verify an artifact.
"""

from __future__ import annotations

import os
import pathlib
import tempfile


def create_workspace(run_id: str) -> str:
    """Create (and return) an isolated directory for one run."""
    base = pathlib.Path(os.environ.get("WORKSPACE_ROOT", pathlib.Path(tempfile.gettempdir()) / "agent-workspaces"))
    workspace = base / run_id
    workspace.mkdir(parents=True, exist_ok=True)
    return str(workspace)
