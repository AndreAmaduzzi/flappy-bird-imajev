"""direct: one question per decision, "Should the bird flap now to pass through the next gap?", options flap / wait.

The bird flaps when P(flap) >= threshold. If unknown is the most likely outcome the agent waits and the decision
is marked abstained (logged, and counted in the metrics).
"""
from __future__ import annotations

from ..imajev_client import ImajevClient
from ..prompts import DIRECT, DIRECT_TWO_FRAMES, GAME_STATE
from .base import FLAP, WAIT, Agent, Decision, Observation


class DirectAgent(Agent):
    name = "direct"

    def __init__(self, client: ImajevClient, variant: str = "plain", threshold: float = 0.5,
                 two_frames: bool = False, with_state: bool = False):
        self.client = client
        self.question = dict(DIRECT[variant])
        self.two_frames = two_frames
        self.threshold = threshold
        self.state = {"game": GAME_STATE} if with_state else {}

    def decide(self, obs: Observation) -> Decision:
        images, question = [obs.frame], self.question
        if self.two_frames and obs.prev_frame is not None:
            images = [obs.prev_frame, obs.frame]
            question = {**question, "instructions": DIRECT_TWO_FRAMES}
        result = self.client.ask({"action": question}, images, self.state)
        answer = result.answers["action"]
        p_flap = answer.probabilities["flap"]
        if answer.top == "unknown":
            action = WAIT
        else:
            action = FLAP if p_flap >= self.threshold else WAIT
        return Decision(action, p_flap=p_flap, p_wait=answer.probabilities["wait"], unknown=answer.unknown,
                        abstained=answer.top == "unknown", server_ms=result.server_ms,
                        info={"images": len(images), "input_tokens": result.input_tokens})
