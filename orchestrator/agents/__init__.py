"""Agent implementations. Import the ones you need from here."""

from orchestrator.agents.base import Agent
from orchestrator.agents.claude import ClaudeAgent
from orchestrator.agents.claude_coder import ClaudeCoderAgent
from orchestrator.agents.claude_doc import ClaudeDocAgent
from orchestrator.agents.http_agent import HTTPAgent
from orchestrator.agents.mock import MockAgent
from orchestrator.agents.pytest_tester import PytestTesterAgent

__all__ = [
    "Agent",
    "ClaudeAgent",
    "ClaudeCoderAgent",
    "ClaudeDocAgent",
    "HTTPAgent",
    "MockAgent",
    "PytestTesterAgent",
]
