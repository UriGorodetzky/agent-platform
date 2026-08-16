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


# --- Circuit breaker ---

class FakeClock:
    """A controllable clock so we can test cooldowns without sleeping."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, dt: float) -> None:
        self.now += dt


def two_coder_registry(clock: FakeClock, threshold: int = 2, cooldown: float = 30.0):
    reg = AgentRegistry(failure_threshold=threshold, cooldown=cooldown, clock=clock)
    a, b = MockAgent("a"), MockAgent("b")
    reg.register(a, ["coding"])
    reg.register(b, ["coding"])
    return reg, a, b


def test_breaker_opens_after_threshold_and_select_skips_it():
    clock = FakeClock()
    reg, a, b = two_coder_registry(clock, threshold=2)

    reg.record_failure(a)
    reg.record_failure(a)                         # a's breaker opens

    assert {reg.select("coding") for _ in range(6)} == {b}   # a is skipped entirely


def test_breaker_half_opens_after_cooldown():
    clock = FakeClock()
    reg, a, b = two_coder_registry(clock, threshold=2, cooldown=30)

    reg.record_failure(a)
    reg.record_failure(a)                         # opens at t=0
    assert {reg.select("coding") for _ in range(4)} == {b}   # skipped while open

    clock.advance(30)                             # cooldown elapsed
    assert a in {reg.select("coding") for _ in range(4)}     # offered again (half-open)


def test_success_closes_the_breaker():
    clock = FakeClock()
    reg, a, b = two_coder_registry(clock, threshold=2)

    reg.record_failure(a)
    reg.record_failure(a)                         # open
    reg.record_success(a)                         # a success closes it immediately

    assert a in {reg.select("coding") for _ in range(4)}


def test_one_failure_below_threshold_keeps_agent_available():
    clock = FakeClock()
    reg, a, b = two_coder_registry(clock, threshold=2)

    reg.record_failure(a)                         # 1 < threshold -> still healthy

    assert a in {reg.select("coding") for _ in range(4)}
