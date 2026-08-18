"""Tests for workspace naming."""

import os

from orchestrator.workspace import _slug, create_workspace


def test_slug_is_readable_and_safe():
    assert _slug("Reverse a String!") == "reverse-a-string"
    assert _slug("Build a REST API (v2)") == "build-a-rest-api-v2"
    assert _slug("") == "task"


def test_create_workspace_uses_a_meaningful_name(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))
    ws = create_workspace("092befdd7f68429991b0", "Reverse a string")

    assert os.path.isdir(ws)
    assert os.path.basename(ws) == "reverse-a-string-092befdd"   # slug + short run id
