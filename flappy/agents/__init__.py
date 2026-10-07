"""Agents behind one interface (base.Agent). `make_agent` builds one by name for the CLIs."""
from __future__ import annotations

from .base import FLAP, WAIT, Agent, Decision, Observation
from .oracle import OracleAgent
from .random_agent import RandomAgent

AGENTS = ("direct", "perceive_rule", "random", "oracle")
MODEL_AGENTS = ("direct", "perceive_rule")


def make_agent(name: str, client=None, *, two_frames: bool = False, flap_rate: float | None = None,
               variant: str | None = None, threshold: float | None = None, **options) -> Agent:
    """`options` (e.g. from --set key=value) go to the model agents' constructors."""
    if name == "oracle":
        return OracleAgent()
    if name == "random":
        return RandomAgent(flap_rate)
    if client is None:
        raise ValueError(f"agent {name!r} needs an imajev client")
    if name == "direct":
        from .direct import DirectAgent
        kwargs = {k: v for k, v in (("variant", variant), ("threshold", threshold)) if v is not None}
        return DirectAgent(client, two_frames=two_frames, **kwargs, **options)
    if name == "perceive_rule":
        from .perceive_rule import PerceiveRuleAgent
        return PerceiveRuleAgent(client, two_frames=two_frames, **options)
    raise ValueError(f"unknown agent {name!r}; choose from {', '.join(AGENTS)}")


def describe(agent: Agent) -> tuple[str, str]:
    """(label, detail) for the video panel."""
    if agent.name == "oracle":
        return "oracle (reads game state)", "upper bound: no pixels, searches flap/wait sequences"
    if agent.name == "random":
        rate = "tuned rate" if agent.flap_rate is None else f"p = {agent.flap_rate:.2f}"
        return "random baseline", f"flaps at random ({rate})"
    frames = " · 2 frames (previous + current)" if getattr(agent, "two_frames", False) else ""
    if agent.name == "direct":
        return "imajev-4b · direct", "1 question: should the bird flap now? -> flap / wait" + frames
    return "imajev-4b · perceive + rule", f"{len(agent.questions)} perception questions -> hand-written rule" + frames


__all__ = ["AGENTS", "MODEL_AGENTS", "FLAP", "WAIT", "Agent", "Decision", "Observation", "describe", "make_agent"]
