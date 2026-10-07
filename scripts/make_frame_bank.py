"""Build a labelled bank of game frames for offline prompt tuning (scripts/eval_perception.py).

    uv run python scripts/make_frame_bank.py --out runs/frame_bank --per-class 40

Frames come from oracle play on seeds 2000+ (never used by benchmark.py): at sampled steps a copy of the game gets
the bird moved to a random height and speed, so every part of the screen is covered (with real pipe layouts).
Labels are computed from the true game state. The bank is balanced over bird-vs-gap classes
per difficulty. Each item also stores the frame from `decide_every` steps earlier (for the two-frame experiment).
"""
import argparse
import copy
import json
import random
from pathlib import Path

from flappy.agents.base import FLAP, Observation
from flappy.agents.oracle import OracleAgent
from flappy.game import BIRD_R, BIRD_X, DIFFICULTIES, PLAY_H, Game
from flappy.render import GameRenderer  # the bank uses the flat graphics (as the benchmark)

NEAR_GROUND_PX = 50     # bird bottom within this many px of the ground
PIPE_CLOSE_PX = 70      # next pipe's left edge within this many px of the bird's front (or bird already inside)


def labels(state, oracle_decision):
    pipe = state.next_pipe
    y = state.bird_y
    vs_gap = "above" if y < pipe.gap_top else "below" if y > pipe.gap_bottom else "inside"
    dist = pipe.x - (BIRD_X + BIRD_R)
    survive_flap, survive_wait = oracle_decision.info["survive_flap"], oracle_decision.info["survive_wait"]
    return {
        "vs_gap": vs_gap,
        "vs_center": "higher" if y < pipe.gap_center else "lower",
        "near_ground": PLAY_H - (y + BIRD_R) < NEAR_GROUND_PX,
        "pipe_close": dist < PIPE_CLOSE_PX,
        "falling": state.bird_vy > 1.0,
        "oracle": oracle_decision.action,
        "critical": survive_flap != survive_wait,   # only one action keeps the bird alive over the horizon
        "bird_y": round(y, 1), "bird_vy": round(state.bird_vy, 2), "gap_top": round(pipe.gap_top, 1),
        "gap_bottom": round(pipe.gap_bottom, 1), "pipe_dist": round(dist, 1),
    }


def collect(difficulty, seeds, decide_every, every, rng):
    oracle, renderer, pool = OracleAgent(), GameRenderer(), []
    d = DIFFICULTIES[difficulty]
    for seed in seeds:
        game = Game(seed, difficulty)
        while game.alive and game.step_count < 3600:
            flap = False
            if game.step_count % decide_every == 0:
                obs = Observation(game.step_count, None, None, game.state(), game.difficulty, decide_every)
                flap = oracle.decide(obs).action == FLAP
                if game.step_count % every == 0 and game.step_count >= every:
                    item = _teleported(game, d, decide_every, oracle, renderer, rng)
                    if item is not None:
                        pool.append({"difficulty": difficulty, "seed": seed, "step": game.step_count, **item})
            game.step(flap)
    return pool


def _teleported(game, d, decide_every, oracle, renderer, rng):
    """A copy of `game` with the bird at a random height and speed, rendered now and `decide_every` steps earlier
    (the earlier frame replays the same bird backwards: physics is deterministic given vy)."""
    sample = copy.deepcopy(game)
    sample.bird_y = rng.uniform(BIRD_R + 4, PLAY_H - BIRD_R - 4)
    sample.bird_vy = rng.uniform(d.flap_velocity, d.max_fall)
    state = sample.state()
    if state.next_pipe is None or sample.state().death_cause or _collides(sample):
        return None
    frame = renderer.image(sample)
    earlier = copy.deepcopy(sample)
    # rewind: move pipes right and the bird back along its (no-flap) trajectory
    vy, y = sample.bird_vy, sample.bird_y
    for _ in range(decide_every):
        y -= vy
        vy = max(vy - d.gravity, d.flap_velocity)
    earlier.bird_y, earlier.bird_vy = y, vy
    for p in earlier.pipes:
        p.x += d.pipe_speed * decide_every
    prev = renderer.image(earlier)
    decision = oracle.decide(Observation(sample.step_count, None, None, state, sample.difficulty, decide_every))
    return {**labels(state, decision), "_frame": frame, "_prev": prev}


def _collides(game):
    from flappy.game import collide
    return collide(game.bird_y, game.pipes) is not None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="runs/frame_bank")
    ap.add_argument("--per-class", type=int, default=40, help="frames per (difficulty, vs_gap class)")
    ap.add_argument("--decide-every", type=int, default=4)
    a = ap.parse_args()
    rng = random.Random(0)
    out = Path(a.out)
    (out / "frames").mkdir(parents=True, exist_ok=True)
    items = []
    for d_index, difficulty in enumerate(DIFFICULTIES):
        pool = collect(difficulty, range(2000 + 100 * d_index, 2000 + 100 * d_index + 6), a.decide_every, 20, rng)
        for cls in ("above", "inside", "below"):
            members = [p for p in pool if p["vs_gap"] == cls]
            items += rng.sample(members, min(a.per_class, len(members)))
            print(f"{difficulty:6s} {cls:6s} pool={len(members):5d} kept={min(a.per_class, len(members))}")
    with open(out / "labels.jsonl", "w") as f:
        for i, item in enumerate(items):
            name = f"{i:04d}_{item['difficulty']}_s{item['seed']}_t{item['step']}"
            item.pop("_frame").save(out / "frames" / f"{name}.png")
            item.pop("_prev").save(out / "frames" / f"{name}_prev.png")
            f.write(json.dumps({"id": name, **item}) + "\n")
    keys = ("near_ground", "pipe_close", "falling", "critical")
    print(f"{len(items)} frames -> {out}; positives: " + ", ".join(f"{k}={sum(i[k] for i in items)}" for k in keys)
          + f", oracle flap={sum(i['oracle'] == 'flap' for i in items)}")


if __name__ == "__main__":
    main()
