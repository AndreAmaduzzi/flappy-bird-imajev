"""Pick the random baseline's per-decision flap rate on held-out seeds (1000+, never used by benchmark.py).

    uv run python scripts/tune_random.py --difficulty easy --seeds 200

Ranks rates by mean pipes passed, then mean frames survived. Copy the winner into
flappy/agents/random_agent.py:DEFAULT_FLAP_RATE.
"""
import argparse
import statistics

from flappy.agents.random_agent import RandomAgent
from flappy.game import Game
from flappy.loop import LoopConfig, run_game


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--difficulty", default="easy")
    ap.add_argument("--decide-every", type=int, default=4)
    ap.add_argument("--seeds", type=int, default=200)
    ap.add_argument("--rates", default="0.04,0.06,0.08,0.10,0.12,0.14,0.16,0.18,0.20,0.25,0.30")
    a = ap.parse_args()
    config = LoopConfig(decide_every=a.decide_every)
    rows = []
    for rate in map(float, a.rates.split(",")):
        games = [run_game(Game(1000 + s, a.difficulty), RandomAgent(rate), config, reference=RandomAgent(rate))
                 for s in range(a.seeds)]
        pipes = statistics.fmean(g.pipes for g in games)
        frames = statistics.fmean(g.frames for g in games)
        rows.append((pipes, frames, rate))
        print(f"rate={rate:.2f}  mean pipes={pipes:.3f}  max pipes={max(g.pipes for g in games)}  mean frames={frames:.1f}")
    best = max(rows)
    print(f"best rate: {best[2]:.2f} (mean pipes {best[0]:.3f}, mean frames {best[1]:.1f})")


if __name__ == "__main__":
    main()
