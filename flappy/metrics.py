"""Per-game metrics and the benchmark's aggregate table."""
from __future__ import annotations

import statistics
from dataclasses import dataclass


@dataclass
class GameResult:
    agent: str
    difficulty: str
    seed: int
    realtime: bool
    decide_every: int
    two_frames: bool
    speed: float                   # real time only: game speed (1.0 = 60 steps per wall-clock second)
    pipes: int
    frames: int                    # physics steps survived
    decisions: int
    latency_mean_ms: float
    latency_p95_ms: float
    unknown_top_pct: float         # % of decisions where unknown was the most likely outcome
    oracle_agreement_pct: float    # % of decisions equal to what the oracle does in the same state
    flap_pct: float                # % of decisions that flapped
    death_cause: str               # ground / ceiling / pipe_top / pipe_bottom / timeout (survived max_steps)
    mean_stale_steps: float        # real time only: steps between the frame seen and the decision applied
    lag_steps: int                 # real time only: physics steps that started late
    wall_s: float


def percentile(values, q):
    if not values:
        return 0.0
    ordered = sorted(values)
    k = (len(ordered) - 1) * q / 100
    lo, hi = int(k), min(int(k) + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


def summarize(game, agent_name, records, config, wall_s=0.0, lag_steps=0) -> GameResult:
    n = len(records)
    latencies = [r.latency_ms for r in records]
    pct = lambda count: 100.0 * count / n if n else 0.0  # noqa: E731
    return GameResult(
        agent=agent_name, difficulty=game.difficulty.name, seed=game.seed, realtime=config.realtime,
        decide_every=config.decide_every, two_frames=config.two_frames, speed=config.speed,
        pipes=game.score, frames=game.step_count, decisions=n,
        latency_mean_ms=statistics.fmean(latencies) if latencies else 0.0,
        latency_p95_ms=percentile(latencies, 95),
        unknown_top_pct=pct(sum(r.abstained for r in records)),
        oracle_agreement_pct=pct(sum(r.action == r.oracle_action for r in records)),
        flap_pct=pct(sum(r.action == "flap" for r in records)),
        death_cause=game.death_cause or "timeout",
        mean_stale_steps=statistics.fmean(r.stale_steps for r in records) if records else 0.0,
        lag_steps=lag_steps, wall_s=wall_s,
    )
