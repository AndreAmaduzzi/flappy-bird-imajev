"""perceive+rule: a few perception questions in one request, then a short hand-written rule.

Questions (chosen on the labelled frame bank, see README "Prompt selection"):
  vs_center    is the bird higher or lower than the middle of the next gap?   (choice: higher / lower)
  near_ground  is the bird close to the ground?                              (noul)
  hit_lower    is the bird about to hit the lower pipe in front of it?       (noul)

Rule:
  1. near the ground, or about to hit the lower pipe  -> flap
  2. lower than the gap's middle (P >= threshold)     -> flap
  3. otherwise                                        -> wait
Unknown handling (`on_unknown`): with "wait" (default) the agent waits whenever unknown is the most likely answer
to vs_center and marks the decision abstained; with "known" it marks it abstained but still decides from the
probabilities of the real options.
"""
from __future__ import annotations

from ..imajev_client import Answer, ImajevClient
from ..prompts import PERCEPTION
from .base import FLAP, WAIT, Agent, Decision, Observation

QUESTIONS = ("vs_center", "near_ground", "hit_lower")


def p_yes(answer: Answer | None) -> float:
    """P(yes) over the real options; 0 when the question was not asked or unknown is on top."""
    if answer is None or answer.top == "unknown":
        return 0.0
    return answer.probabilities["yes"]


def pct(p: float) -> str:
    """For the video panel: one decimal close to the 50% decision line."""
    return f"{100 * p:.1f}%" if 0.45 < p < 0.55 else f"{100 * p:.0f}%"


class PerceiveRuleAgent(Agent):
    name = "perceive_rule"

    def __init__(self, client: ImajevClient, two_frames: bool = False, lower_threshold: float = 0.5,
                 danger_threshold: float = 0.5, on_unknown: str = "wait", cooldown: int = 0, questions=QUESTIONS):
        if on_unknown not in ("wait", "known"):
            raise ValueError("on_unknown must be 'wait' or 'known'")
        self.client = client
        self.two_frames = two_frames
        self.lower_threshold = lower_threshold
        self.danger_threshold = danger_threshold
        self.on_unknown = on_unknown
        self.cooldown = cooldown            # min physics steps between flaps (the agent's own action memory)
        self.questions = {q: PERCEPTION[q] for q in questions}
        self.last_flap = -10**9

    def reset(self, seed: int) -> None:
        self.last_flap = -10**9

    def decide(self, obs: Observation) -> Decision:
        images = [obs.prev_frame, obs.frame] if self.two_frames and obs.prev_frame is not None else [obs.frame]
        result = self.client.ask(self.questions, images)
        a = result.answers
        center = a["vs_center"]
        p_lower = center.probabilities["lower"]
        p_near = p_yes(a.get("near_ground"))
        p_hit = p_yes(a.get("hit_lower"))

        abstained = center.top == "unknown"
        if p_near > self.danger_threshold:
            action, why = FLAP, "near the ground"
        elif p_hit > self.danger_threshold:
            action, why = FLAP, "about to hit the lower pipe"
        elif abstained and self.on_unknown == "wait":
            action, why = WAIT, "unknown -> wait"
        elif p_lower >= self.lower_threshold:
            action, why = FLAP, "lower than the gap's middle"
        else:
            action, why = WAIT, "higher than the gap's middle"
        if action == FLAP and obs.step - self.last_flap < self.cooldown:
            action, why = WAIT, "still rising from the last flap"
        if action == FLAP:
            self.last_flap = obs.step

        # The panel bar shows the strongest trigger: with the default 0.5 thresholds the bird flaps exactly when it
        # is >= 50% (unless unknown won on vs_center, shown as "WAIT (unknown)").
        p_flap = max(p_near, p_hit, p_lower)
        lines = (f"sees: lower than gap middle {pct(p_lower)}",
                 f"      about to hit lower pipe {pct(p_hit)} · near ground {pct(p_near)}",
                 f"rule: {why}")
        return Decision(action, p_flap=p_flap, p_wait=1 - p_flap, unknown=center.unknown, abstained=abstained,
                        server_ms=result.server_ms,
                        info={"p_lower": p_lower, "p_hit": p_hit, "p_near": p_near, "why": why,
                              "unknown_by_question": {k: v.unknown for k, v in a.items()},
                              "input_tokens": result.input_tokens, "panel_lines": lines})
