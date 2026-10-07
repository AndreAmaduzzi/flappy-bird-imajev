from PIL import Image

from flappy.agents.base import FLAP, WAIT, Observation
from flappy.agents.direct import DirectAgent
from flappy.agents.perceive_rule import PerceiveRuleAgent
from flappy.game import DIFFICULTIES, Game
from flappy.imajev_client import Answer, SystemOneResult


class FakeClient:
    """Returns canned answers and remembers what it was asked."""

    def __init__(self, answers):
        self.answers = answers
        self.calls = []

    def ask(self, questions, images, state=None):
        self.calls.append((dict(questions), list(images), state))
        return SystemOneResult({k: self.answers[k] for k in questions}, latency_ms=5.0, server_ms=4.0, input_tokens=300)


def choice(probs, unknown=0.0):
    full = {**{k: v * (1 - unknown) for k, v in probs.items()}, "unknown": unknown}
    top = max(full, key=full.get)
    return Answer("choice", probs, unknown, top == "unknown", max(probs, key=probs.get))


def noul(p_yes, unknown=0.0):
    return choice({"yes": p_yes, "no": 1 - p_yes}, unknown)


def obs(two_frames=False):
    game = Game(0, "easy")
    frame = Image.new("RGB", (288, 512))
    return Observation(0, frame, frame.copy() if two_frames else None, game.state(), DIFFICULTIES["easy"], 4)


def test_direct_threshold_and_unknown():
    agent = DirectAgent(FakeClient({"action": choice({"flap": 0.7, "wait": 0.3})}))
    assert agent.decide(obs()).action == FLAP
    agent = DirectAgent(FakeClient({"action": choice({"flap": 0.7, "wait": 0.3})}), threshold=0.8)
    assert agent.decide(obs()).action == WAIT
    d = DirectAgent(FakeClient({"action": choice({"flap": 0.9, "wait": 0.1}, unknown=0.6)})).decide(obs())
    assert d.action == WAIT and d.abstained and d.unknown == 0.6


def test_direct_two_frames_sends_both():
    client = FakeClient({"action": choice({"flap": 0.2, "wait": 0.8})})
    DirectAgent(client, two_frames=True).decide(obs(two_frames=True))
    questions, images, _ = client.calls[-1]
    assert len(images) == 2 and "previous game frame" in questions["action"]["instructions"]


def answers(lower=0.2, near=0.1, hit=0.1, center_unknown=0.0):
    return {"vs_center": choice({"higher": 1 - lower, "lower": lower}, center_unknown),
            "near_ground": noul(near), "hit_lower": noul(hit)}


def test_perceive_rule_triggers():
    assert PerceiveRuleAgent(FakeClient(answers())).decide(obs()).action == WAIT
    assert PerceiveRuleAgent(FakeClient(answers(lower=0.8))).decide(obs()).action == FLAP
    assert PerceiveRuleAgent(FakeClient(answers(near=0.9))).decide(obs()).info["why"] == "near the ground"
    assert PerceiveRuleAgent(FakeClient(answers(hit=0.9))).decide(obs()).info["why"] == "about to hit the lower pipe"


def test_perceive_rule_unknown_policy():
    unsure = answers(lower=0.9, center_unknown=0.7)
    d = PerceiveRuleAgent(FakeClient(unsure)).decide(obs())
    assert d.action == WAIT and d.abstained
    d = PerceiveRuleAgent(FakeClient(unsure), on_unknown="known").decide(obs())
    assert d.action == FLAP and d.abstained
    # a danger trigger still flaps even when vs_center is unknown
    d = PerceiveRuleAgent(FakeClient(answers(lower=0.9, hit=0.95, center_unknown=0.7))).decide(obs())
    assert d.action == FLAP


def test_perceive_rule_cooldown():
    agent = PerceiveRuleAgent(FakeClient(answers(lower=0.9)), cooldown=12)
    first = agent.decide(obs())
    o = obs()
    o.step = 4
    second = agent.decide(o)
    assert first.action == FLAP and second.action == WAIT
