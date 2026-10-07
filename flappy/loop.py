"""The game loop: lockstep (default) or real time, plus the per-decision JSONL log.

Lockstep: every `decide_every` physics steps the loop renders a frame and waits for the agent; the decision applies
to that same step. Game time never advances while the model thinks, so a recorded video plays at normal speed.

Real time (--realtime): physics runs on the wall clock at STEP_HZ x `speed` (speed < 1 slows the game down, to find
how fast the model would need to be). A worker thread asks the agent about the newest
frame; when the answer arrives it applies at the current step (possibly several steps after the frame it was made
from: `stale_steps` in the log). A new request starts when the previous one finished, at most once per
`decide_every` steps.
"""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

from .agents.base import FLAP, Agent, Decision, Observation
from .agents.oracle import OracleAgent
from .game import STEP_HZ, Game
from .metrics import GameResult, summarize
from .render import make_renderer

# on_step(game, last_decision, new_decision) after every physics step; new_decision is set on the step it applied.
StepHook = Callable[[Game, Decision | None, Decision | None], None]


@dataclass
class LoopConfig:
    decide_every: int = 4
    realtime: bool = False
    max_steps: int = STEP_HZ * 120     # game-time cap: 2 minutes
    two_frames: bool = False           # also send the previous decision's frame
    speed: float = 1.0                 # real time only: game speed relative to STEP_HZ on the wall clock
    theme: str = "flat"                # how frames are drawn (render.THEMES); the model sees these frames


@dataclass
class DecisionRecord:
    step: int                 # step the decision applied to
    request_step: int         # step whose frame the agent saw (== step in lockstep)
    action: str
    p_flap: float | None
    p_wait: float | None
    unknown: float | None
    abstained: bool
    latency_ms: float
    server_ms: float | None
    oracle_action: str | None
    bird_y: float
    bird_vy: float
    gap_top: float | None
    gap_bottom: float | None
    pipe_x: float | None
    score: int
    info: dict = field(default_factory=dict)

    @property
    def stale_steps(self):
        return self.step - self.request_step


class DecisionLog:
    """Appends one JSON object per decision; `context` (agent, seed, ...) is repeated on every line for easy plotting."""

    def __init__(self, path: str | Path | None, **context):
        self.context = context
        self.handle = None
        if path is not None:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            self.handle = open(path, "a")

    def write(self, record: DecisionRecord):
        if self.handle is not None:
            row = {**self.context, **asdict(record), "stale_steps": record.stale_steps}
            self.handle.write(json.dumps(row, default=_round) + "\n")

    def close(self):
        if self.handle is not None:
            self.handle.close()


def _round(value):
    return round(value, 5) if isinstance(value, float) else str(value)


def run_game(game: Game, agent: Agent, config: LoopConfig = LoopConfig(), log: DecisionLog | None = None,
             on_step: StepHook | None = None, reference: Agent | None = None) -> GameResult:
    """Play one game to death or `max_steps`. `reference` (default: the oracle) labels every decision with the
    action the oracle would take in the same state, for the agreement metric."""
    agent.reset(game.seed)
    if reference is None and agent.name != "oracle":
        reference = OracleAgent()
    records: list[DecisionRecord] = []
    renderer = make_renderer(config.theme)
    play = _run_realtime if config.realtime else _run_lockstep
    started = time.perf_counter()
    lag_steps = play(game, agent, config, renderer, records, log, on_step, reference)
    return summarize(game, agent.name, records, config, wall_s=time.perf_counter() - started, lag_steps=lag_steps)


def _observe(game, agent, config, renderer, prev_frame):
    frame = renderer.image(game) if agent.needs_frame else None
    obs = Observation(game.step_count, frame, prev_frame if config.two_frames else None, game.state(),
                      game.difficulty, config.decide_every)
    return obs, frame


def _timed_decide(agent, obs):
    start = time.perf_counter()
    decision = agent.decide(obs)
    decision.latency_ms = (time.perf_counter() - start) * 1000
    return decision


def _record(obs, decision, step, reference):
    s = obs.state
    pipe = s.next_pipe
    oracle = decision.action if reference is None else reference.decide(obs).action
    return DecisionRecord(step, obs.step, decision.action, decision.p_flap, decision.p_wait, decision.unknown,
                          decision.abstained, decision.latency_ms, decision.server_ms, oracle, s.bird_y, s.bird_vy,
                          pipe and pipe.gap_top, pipe and pipe.gap_bottom, pipe and pipe.x, s.score, decision.info)


def _run_lockstep(game, agent, config, renderer, records, log, on_step, reference):
    prev_frame, last = None, None
    while game.alive and game.step_count < config.max_steps:
        new = None
        if game.step_count % config.decide_every == 0:
            obs, frame = _observe(game, agent, config, renderer, prev_frame)
            new = last = _timed_decide(agent, obs)
            records.append(_record(obs, new, game.step_count, reference))
            if log:
                log.write(records[-1])
            prev_frame = frame
        game.step(new is not None and new.action == FLAP)
        if on_step:
            on_step(game, last, new)
    return 0


def _run_realtime(game, agent, config, renderer, records, log, on_step, reference):
    period = 1.0 / (STEP_HZ * config.speed)
    pending, pending_obs, prev_frame, last = None, None, None, None
    next_request, lag_steps = 0, 0
    with ThreadPoolExecutor(max_workers=1) as pool:
        t0 = time.perf_counter()
        while game.alive and game.step_count < config.max_steps:
            # Pace physics to the wall clock; count steps that started late (the loop itself fell behind).
            wait = t0 + game.step_count * period - time.perf_counter()
            if wait > 0:
                time.sleep(wait)
            elif wait < -period:
                lag_steps += 1
            new = None
            if pending is not None and pending.done():
                new = last = pending.result()
                records.append(_record(pending_obs, new, game.step_count, reference))
                if log:
                    log.write(records[-1])
                pending = None
            if pending is None and game.step_count >= next_request:
                pending_obs, frame = _observe(game, agent, config, renderer, prev_frame)
                pending = pool.submit(_timed_decide, agent, pending_obs)
                next_request = game.step_count + config.decide_every
                prev_frame = frame
            game.step(new is not None and new.action == FLAP)
            if on_step:
                on_step(game, last, new)
        if pending is not None:
            pending.result()   # let the in-flight request finish before the agent is reused
    return lag_steps
