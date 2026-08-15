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


def test_select_round_robins_across_agents_with_same_capability():
    reg = AgentRegistry()
    a = MockAgent("coder-1")
    b = MockAgent("coder-2")
    c = MockAgent("coder-3")
    reg.register(a, ["coding"])
    reg.register(b, ["coding"])
    reg.register(c, ["coding"])

    picks = [reg.select("coding") for _ in range(7)]
    assert picks == [a, b, c, a, b, c, a]   # cycles fairly, then wraps


def test_capabilities_introspection():
    reg = AgentRegistry()
    reg.register(MockAgent("planner"), ["planning"])
    reg.register(MockAgent("coder"), ["coding"])

    assert reg.capabilities() == {"planning": ["planner"], "coding": ["coder"]}
