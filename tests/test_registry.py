"""Tests for the AgentRegistry."""

import pytest

from orchestrator.agents import MockAgent
from orchestrator.registry import AgentRegistry, NoAgentForCapability


def test_select_returns_a_registered_agent():
    reg = AgentRegistry()
    coder = MockAgent("coder")
    reg.register(coder, ["coding", "debugging"])

    assert reg.select("coding") is coder
    assert reg.select("debugging") is coder


def test_select_unknown_capability_raises():
    reg = AgentRegistry()
    with pytest.raises(NoAgentForCapability):
        reg.select("planning")


def test_get_by_name():
    reg = AgentRegistry()
    a = MockAgent("planner")
    reg.register(a, ["planning"])

    assert reg.get("planner") is a
    with pytest.raises(KeyError):
        reg.get("nobody")


def test_first_registered_wins_for_same_capability():
    reg = AgentRegistry()
    first = MockAgent("coder-1")
    second = MockAgent("coder-2")
    reg.register(first, ["coding"])
    reg.register(second, ["coding"])

    assert reg.select("coding") is first


def test_capabilities_introspection():
    reg = AgentRegistry()
    reg.register(MockAgent("planner"), ["planning"])
    reg.register(MockAgent("coder"), ["coding"])

    assert reg.capabilities() == {"planning": ["planner"], "coding": ["coder"]}
