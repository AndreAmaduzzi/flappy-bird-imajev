"""A game played live, one physics step per display frame: the engine behind app.py (no UI code here).

The agent is asked on a worker thread, so the window stays responsive while the model thinks.
  lockstep  : the game waits for each decision (what the benchmark measures)
  real time : the game keeps running; a decision applies when it arrives (`speed` slows the game down)
  human     : the player flaps with `flap()` (SPACE in the app)
"""
from __future__ import annotations

import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass

from .agents import MODEL_AGENTS, make_agent
from .agents.base import FLAP, Decision, Observation
from .game import Game, make_difficulty
from .imajev_client import ImajevClient
from .prompts import DIRECT
from .render import make_renderer

HUMAN = "human"


@dataclass
class Settings:
    player: str = "perceive_rule"     # perceive_rule, direct, oracle, random, human
    difficulty: str = "easy"
    gap: float | None = None          # None: the preset's value
    pipe_speed: float | None = None
    gravity: float | None = None
    theme: str = "flat"
    realtime: bool = False
    speed: float = 1.0                # real time only
    decide_every: int = 4
    seed: int = 0

    @property
    def uses_model(self):
        return self.player in MODEL_AGENTS


class LiveGame:
    def __init__(self, settings: Settings, client: ImajevClient | None = None):
        self.cfg = settings
        difficulty = make_difficulty(settings.difficulty, gap=settings.gap, pipe_speed=settings.pipe_speed,
                                     gravity=settings.gravity)
        self.game = Game(settings.seed, difficulty)
        self.agent = None if settings.player == HUMAN else make_agent(settings.player, client)
        if self.agent:
            self.agent.reset(settings.seed)
        self.frames = make_renderer(settings.theme)          # what the agent sees (the game window only)
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.pending: Future | None = None
        self.pending_obs: Observation | None = None
        self.decided_for = -1
        self.next_request = 0
        self.acc = 0.0
        self.last: Decision | None = None
        self.last_flap_step = -100
        self.human_flap = False
        self.decisions = 0
        self.abstained = 0
        self.latencies: list[float] = []
        self.error: str | None = None
        self.paused = False
        self.warmup: Future | None = None
        if settings.uses_model and client is not None:   # the first requests compile kernels: keep them out of play
            self.warmup = self.pool.submit(client.warmup, self.frames.image(self.game), {"q": DIRECT["plain"]}, 1)

    # ------------------------------------------------------------------ status
    @property
    def warming_up(self):
        return self.warmup is not None and not self.warmup.done()

    @property
    def thinking(self):
        return self.pending is not None and not self.pending.done()

    @property
    def over(self):
        return not self.game.alive or self.error is not None

    def flap(self):
        self.human_flap = True

    def close(self):
        self.pool.shutdown(wait=False, cancel_futures=True)

    # ------------------------------------------------------------------ one display frame
    def tick(self):
        if self.over or self.paused or self.warming_up:
            return
        if self.warmup is not None and self.warmup.exception():
            self.error = f"imajev server: {self.warmup.exception()}"
            return
        if self.agent is None:
            self.game.step(self.human_flap)
            self.human_flap = False
        elif self.cfg.realtime:
            self.acc += self.cfg.speed
            while self.acc >= 1 and not self.over:
                self.acc -= 1
                self._realtime_step()
        else:
            self._lockstep_step()

    def _lockstep_step(self):
        g = self.game
        if g.step_count % self.cfg.decide_every == 0 and self.decided_for != g.step_count:
            if not self.cfg.uses_model:              # oracle / random: instant, no thread
                self._apply(self._decide(self._observe()), g.step_count)
                return
            if self.pending is None:
                self._submit()
            if self.pending.done():
                self._apply(self._collect(), g.step_count)
            return                                   # the game waits while the model thinks
        g.step(False)

    def _realtime_step(self):
        g = self.game
        flap = False
        if not self.cfg.uses_model:
            if g.step_count % self.cfg.decide_every == 0:
                d = self._decide(self._observe())
                self._record(d)
                flap = d.action == FLAP
        else:
            if self.pending is not None and self.pending.done():
                d = self._collect()
                flap = d is not None and d.action == FLAP
            if self.pending is None and g.step_count >= self.next_request and not self.over:
                self._submit()
                self.next_request = g.step_count + self.cfg.decide_every
        if not self.over:
            if flap:
                self.last_flap_step = g.step_count
            g.step(flap)

    # ------------------------------------------------------------------ decisions
    def _observe(self):
        frame = self.frames.image(self.game) if self.agent.needs_frame else None
        return Observation(self.game.step_count, frame, None, self.game.state(), self.game.difficulty,
                           self.cfg.decide_every)

    def _decide(self, obs):
        start = time.perf_counter()
        decision = self.agent.decide(obs)
        decision.latency_ms = (time.perf_counter() - start) * 1000
        return decision

    def _submit(self):
        self.pending_obs = self._observe()
        self.pending = self.pool.submit(self._decide, self.pending_obs)

    def _collect(self):
        future, self.pending = self.pending, None
        try:
            d = future.result()
        except Exception as exc:  # noqa: BLE001  (server down, timeout, ...)
            self.error = f"imajev server: {exc}"
            return None
        self._record(d)
        return d

    def _record(self, d):
        self.last = d
        self.decisions += 1
        self.abstained += d.abstained
        if self.cfg.uses_model:
            self.latencies.append(d.latency_ms)

    def _apply(self, d, step):
        if d is None:
            return
        if not self.cfg.uses_model:
            self._record(d)
        self.decided_for = step
        flap = d.action == FLAP
        if flap:
            self.last_flap_step = step
        self.game.step(flap)
