"""The interface every agent implements: one Observation in, one Decision out."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from PIL import Image

from ..game import Difficulty, GameState

FLAP, WAIT = "flap", "wait"


@dataclass
class Observation:
    step: int                       # physics step the decision applies to
    frame: Image.Image | None       # the rendered game frame (what the model sees)
    prev_frame: Image.Image | None  # the frame from the previous decision, if any
    state: GameState                # true game state: only privileged agents (oracle) may read it
    difficulty: Difficulty
    decide_every: int               # physics steps between decisions


@dataclass
class Decision:
    action: str                                  # FLAP or WAIT (the action actually applied)
    p_flap: float | None = None                  # P(flap) over the known options (unknown excluded)
    p_wait: float | None = None
    unknown: float | None = None                 # unknown probability of the deciding answer
    abstained: bool = False                      # unknown was the most likely outcome -> defaulted to WAIT
    latency_ms: float = 0.0                      # wall-clock time of decide(), client side
    server_ms: float | None = None               # server-reported total_ms
    info: dict[str, Any] = field(default_factory=dict)  # agent-specific detail (raw answers, rule trace)


class Agent:
    name = "agent"
    needs_frame = True    # False: the loop skips rendering the model frame (oracle, random)
    privileged = False    # True: reads Observation.state

    def reset(self, seed: int) -> None:
        pass

    def decide(self, obs: Observation) -> Decision:
        raise NotImplementedError

    def close(self) -> None:
        pass
