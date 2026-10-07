import time

from flappy.imajev_client import Answer, SystemOneResult
from flappy.live import HUMAN, LiveGame, Settings


def choice(probs, unknown=0.0):
    return Answer("choice", probs, unknown, False, max(probs, key=probs.get))


class SlowClient:
    """A fake imajev server that answers after `delay` seconds: always 'higher than the middle' (wait)."""

    def __init__(self, delay=0.02):
        self.delay, self.calls = delay, 0

    def ask(self, questions, images, state=None):
        time.sleep(self.delay)
        self.calls += 1
        answers = {"vs_center": choice({"higher": 0.9, "lower": 0.1}),
                   "near_ground": choice({"yes": 0.05, "no": 0.95}), "hit_lower": choice({"yes": 0.05, "no": 0.95})}
        return SystemOneResult({k: answers[k] for k in questions}, latency_ms=self.delay * 1000, server_ms=1.0,
                               input_tokens=300)

    def warmup(self, image, questions, n=2):
        time.sleep(self.delay)


def run(live, frames):
    for _ in range(frames):
        live.tick()
    return live


def test_oracle_lockstep_plays():
    live = run(LiveGame(Settings(player="oracle", seed=1)), 900)
    assert live.game.alive and live.game.step_count == 900 and live.game.score > 0
    assert live.decisions == 900 // 4


def test_human_flaps():
    live = LiveGame(Settings(player=HUMAN))
    live.flap()
    live.tick()
    assert live.game.last_flap_step == 0 and live.game.bird_vy < 0


def test_realtime_speed_and_overrides():
    live = run(LiveGame(Settings(player="random", realtime=True, speed=0.5, gap=230, seed=2)), 40)
    assert live.game.step_count == 20                   # half speed: one physics step every two frames
    assert live.game.difficulty.gap == 230 and live.game.difficulty.name == "easy*"


def test_model_lockstep_waits_without_blocking():
    client = SlowClient(delay=0.05)
    live = LiveGame(Settings(player="perceive_rule", seed=0), client)
    start = time.perf_counter()
    for _ in range(200):
        live.tick()
        if live.decisions >= 3:
            break
        time.sleep(0.005)
    assert time.perf_counter() - start < 5
    assert live.decisions >= 3 and client.calls >= 3
    assert live.game.step_count in range(8, 13)         # waited for each decision before moving on
    assert live.latencies and live.last.action == "wait"
    live.close()


def test_server_error_stops_the_game():
    class Broken(SlowClient):
        def ask(self, *args, **kwargs):
            raise ConnectionError("refused")

    live = LiveGame(Settings(player="direct"), Broken(delay=0))
    for _ in range(50):
        live.tick()
        time.sleep(0.002)
        if live.over:
            break
    assert live.over and "refused" in live.error
    live.close()
