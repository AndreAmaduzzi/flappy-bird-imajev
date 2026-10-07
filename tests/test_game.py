import json

import pytest

from flappy.agents.base import FLAP, Agent, Decision
from flappy.agents.oracle import OracleAgent
from flappy.agents.random_agent import RandomAgent
from flappy.game import DIFFICULTIES, STEP_HZ, Game
from flappy.loop import DecisionLog, LoopConfig, run_game
from flappy.render import GameRenderer, resize_for_model


def trajectory(seed, difficulty, flaps):
    game = Game(seed, difficulty)
    out = []
    for i in range(600):
        game.step(i in flaps)
        out.append((round(game.bird_y, 6), [(round(p.x, 3), round(p.gap_top, 3)) for p in game.pipes], game.alive))
    return out


def test_same_seed_same_run():
    flaps = set(range(0, 600, 17))
    assert trajectory(3, "medium", flaps) == trajectory(3, "medium", flaps)
    assert trajectory(3, "medium", flaps) != trajectory(4, "medium", flaps)


def test_reset_replays():
    game = Game(5, "easy")
    gaps = []
    for _ in range(2):
        game.reset(5)
        for _ in range(400):
            game.step(game.step_count % 20 == 0)
        gaps.append([p.gap_top for p in game.pipes])
    assert gaps[0] == gaps[1]


def test_no_flap_hits_ground():
    game = Game(0, "easy")
    while game.step(False):
        pass
    assert game.death_cause == "ground"


@pytest.mark.parametrize("difficulty", sorted(DIFFICULTIES))
def test_oracle_survives(difficulty):
    for seed in range(3):
        result = run_game(Game(seed, difficulty), OracleAgent(), LoopConfig(max_steps=STEP_HZ * 60))
        assert result.death_cause == "timeout", (difficulty, seed, result)
        assert result.pipes > 20


def test_random_baseline_dies():
    result = run_game(Game(0, "easy"), RandomAgent(0.12), LoopConfig(max_steps=STEP_HZ * 60))
    assert result.death_cause != "timeout"
    assert 0 < result.oracle_agreement_pct < 100


class SlowAgent(Agent):
    """Pretends to be a 50 ms model that always flaps when the bird is below the middle of the screen."""
    name = "slow"
    needs_frame = True

    def decide(self, obs):
        import time
        time.sleep(0.05)
        assert obs.frame is not None and obs.frame.size == (288, 512)
        return Decision(FLAP if obs.state.bird_y > 260 else "wait", p_flap=0.5, p_wait=0.5, unknown=0.0)


def test_realtime_decisions_are_stale(tmp_path):
    log = DecisionLog(tmp_path / "d.jsonl", agent="slow", seed=0)
    result = run_game(Game(0, "easy"), SlowAgent(), LoopConfig(realtime=True, max_steps=90), log=log)
    log.close()
    rows = [json.loads(line) for line in open(tmp_path / "d.jsonl")]
    assert result.decisions == len(rows) > 0
    assert all(r["stale_steps"] >= 2 for r in rows)     # 50 ms = 3 steps at 60 Hz
    assert result.mean_stale_steps >= 2


def test_lockstep_log_fields(tmp_path):
    log = DecisionLog(tmp_path / "d.jsonl", agent="slow", seed=1)
    result = run_game(Game(1, "easy"), SlowAgent(), LoopConfig(max_steps=40, decide_every=4), log=log)
    log.close()
    rows = [json.loads(line) for line in open(tmp_path / "d.jsonl")]
    assert len(rows) == result.decisions == 10
    assert [r["step"] for r in rows] == list(range(0, 40, 4))
    assert all(r["stale_steps"] == 0 and r["agent"] == "slow" for r in rows)
    assert {"p_flap", "unknown", "latency_ms", "oracle_action"} <= set(rows[0])


def test_render_and_resize():
    image = GameRenderer().image(Game(0, "easy"))
    assert image.size == (288, 512)
    assert resize_for_model(image).size == (288, 512)              # already under 400k pixels
    big = image.resize((1152, 2048))
    small = resize_for_model(big)
    assert small.width * small.height <= 400_000 and abs(small.width / small.height - 288 / 512) < 0.01
