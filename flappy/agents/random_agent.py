"""Baseline: flap with a fixed probability at every decision. `scripts/tune_random.py` picks the rate."""
from __future__ import annotations

import random

from .base import FLAP, WAIT, Agent, Decision, Observation

# Per-decision flap probability by difficulty, tuned with scripts/tune_random.py (decide_every=4, 300 held-out
# seeds, best mean pipes passed). Random play almost never passes a pipe; the rate mainly sets frames survived.
DEFAULT_FLAP_RATES = {"easy": 0.14, "medium": 0.20, "hard": 0.20}


class RandomAgent(Agent):
    name = "random"
    needs_frame = False

    def __init__(self, flap_rate: float | None = None):
        self.flap_rate = flap_rate    # None: the tuned rate for the game's difficulty
        self.rng = random.Random(0)

    def reset(self, seed: int) -> None:
        self.rng = random.Random(f"random-agent-{seed}")

    def decide(self, obs: Observation) -> Decision:
        rate = self.flap_rate if self.flap_rate is not None else DEFAULT_FLAP_RATES.get(obs.difficulty.name.rstrip("*"), 0.15)
        flap = self.rng.random() < rate
        return Decision(FLAP if flap else WAIT, p_flap=rate, p_wait=1 - rate, unknown=0.0)
