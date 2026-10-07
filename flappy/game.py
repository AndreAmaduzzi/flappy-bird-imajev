"""Minimal, deterministic Flappy Bird physics. No pygame here: rendering lives in render.py.

Units are pixels and physics steps; the game runs at a fixed STEP_HZ (one `step()` = one physics tick).
Everything random comes from a `random.Random(seed)` owned by the game, so a seed plus the sequence of
flap decisions fully determines a run.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field, replace

STEP_HZ = 60
WIDTH, HEIGHT = 288, 512
GROUND_H = 60
PLAY_H = HEIGHT - GROUND_H          # y of the ground's top edge
BIRD_X = 70                         # bird centre x (fixed)
BIRD_R = 12                         # collision radius (the drawn bird is slightly larger)
PIPE_W = 52


@dataclass(frozen=True)
class Difficulty:
    name: str
    gap: float            # vertical opening between the two pipes
    pipe_speed: float     # px per step
    gravity: float        # px per step^2
    flap_velocity: float  # vy right after a flap (negative = up)
    max_fall: float       # terminal falling speed, px per step
    pipe_spacing: float   # horizontal distance between consecutive pipes
    max_gap_shift: float  # largest change of gap centre between consecutive pipes
    gap_margin: float = 60.0  # min distance of the gap from the top and from the ground


DIFFICULTIES = {
    "easy": Difficulty("easy", gap=190, pipe_speed=2.0, gravity=0.25, flap_velocity=-4.4, max_fall=7.0,
                       pipe_spacing=190, max_gap_shift=50),
    "medium": Difficulty("medium", gap=165, pipe_speed=2.5, gravity=0.30, flap_velocity=-4.8, max_fall=8.0,
                         pipe_spacing=180, max_gap_shift=80),
    "hard": Difficulty("hard", gap=140, pipe_speed=3.0, gravity=0.35, flap_velocity=-5.0, max_fall=8.5,
                       pipe_spacing=170, max_gap_shift=100),
}
# A flap rises flap_velocity^2 / (2 gravity) px (39 / 38 / 36), about a third of the gap or less, so a controller
# that flaps whenever the bird is below the gap's middle cannot overshoot into the upper pipe; difficulty comes from
# the gap, the speed and how far consecutive gaps move. The oracle survives every preset (tests/test_game.py).


def make_difficulty(name: str, **overrides) -> Difficulty:
    """A preset, optionally with some parameters changed (None = keep). The name gets a '*' when changed."""
    changes = {k: v for k, v in overrides.items() if v is not None}
    base = DIFFICULTIES[name]
    return replace(base, name=f"{name}*", **changes) if changes else base


@dataclass
class Pipe:
    x: float          # left edge
    gap_top: float    # y of the upper pipe's bottom edge
    gap_bottom: float # y of the lower pipe's top edge
    passed: bool = False

    @property
    def right(self):
        return self.x + PIPE_W

    @property
    def gap_center(self):
        return (self.gap_top + self.gap_bottom) / 2


@dataclass
class GameState:
    """Read-only snapshot for the oracle, the logs and the tests."""
    step: int
    bird_y: float
    bird_vy: float
    score: int
    alive: bool
    death_cause: str | None
    next_pipe: Pipe | None   # first pipe whose right edge is still ahead of the bird's left edge
    pipes: tuple[Pipe, ...] = ()  # every pipe on screen (copies), for the oracle's look-ahead


def collide(y: float, pipes, dx: float = 0.0) -> str | None:
    """The death cause for a bird centred at (BIRD_X, y) among `pipes` shifted left by `dx`, or None."""
    if y + BIRD_R >= PLAY_H:
        return "ground"
    if y - BIRD_R <= 0:
        return "ceiling"
    for pipe in pipes:
        # circle vs. the two pipe rectangles: closest point on each rectangle
        cx = min(max(BIRD_X, pipe.x - dx), pipe.right - dx)
        if (BIRD_X - cx) ** 2 >= BIRD_R ** 2:
            continue
        for top, bottom, cause in ((0, pipe.gap_top, "pipe_top"), (pipe.gap_bottom, PLAY_H, "pipe_bottom")):
            cy = min(max(y, top), bottom)
            if (BIRD_X - cx) ** 2 + (y - cy) ** 2 < BIRD_R ** 2:
                return cause
    return None


@dataclass
class Game:
    seed: int = 0
    difficulty: Difficulty = field(default_factory=lambda: DIFFICULTIES["easy"])

    def __post_init__(self):
        if isinstance(self.difficulty, str):
            self.difficulty = DIFFICULTIES[self.difficulty]
        self.reset(self.seed)

    def reset(self, seed=None):
        if seed is not None:
            self.seed = seed
        self.rng = random.Random(self.seed)
        self.step_count = 0
        self.bird_y = PLAY_H / 2
        self.bird_vy = 0.0
        self.score = 0
        self.alive = True
        self.death_cause = None
        self.flapped = False       # did the last step start with a flap (for rendering)
        self.last_flap_step = -1000  # step of the most recent flap (wing animation)
        self.pipes: list[Pipe] = []
        self.ground_offset = 0.0
        self._spawn(WIDTH + 60)

    # ---------------------------------------------------------------- pipes
    def _spawn(self, x):
        d = self.difficulty
        half = d.gap / 2
        low, high = d.gap_margin + half, PLAY_H - d.gap_margin - half
        if self.pipes:
            prev = self.pipes[-1].gap_center
            low, high = max(low, prev - d.max_gap_shift), min(high, prev + d.max_gap_shift)
        center = self.rng.uniform(low, high)
        self.pipes.append(Pipe(x, center - half, center + half))

    def next_pipe(self):
        for pipe in self.pipes:
            if pipe.right >= BIRD_X - BIRD_R:
                return pipe
        return None

    # ---------------------------------------------------------------- physics
    def step(self, flap: bool) -> bool:
        """Advance one physics step. Returns True while the bird is alive."""
        if not self.alive:
            return False
        d = self.difficulty
        self.flapped = bool(flap)
        if flap:
            self.last_flap_step = self.step_count
        if flap:
            self.bird_vy = d.flap_velocity
        else:
            self.bird_vy = min(self.bird_vy + d.gravity, d.max_fall)
        self.bird_y += self.bird_vy

        for pipe in self.pipes:
            pipe.x -= d.pipe_speed
        self.ground_offset = (self.ground_offset + d.pipe_speed) % 24
        if self.pipes and self.pipes[0].right < 0:
            self.pipes.pop(0)
        if self.pipes[-1].x < WIDTH - d.pipe_spacing:
            self._spawn(self.pipes[-1].x + d.pipe_spacing)
        for pipe in self.pipes:
            if not pipe.passed and pipe.right < BIRD_X - BIRD_R:
                pipe.passed = True
                self.score += 1

        self.step_count += 1
        self.death_cause = collide(self.bird_y, self.pipes)
        self.alive = self.death_cause is None
        return self.alive

    def state(self) -> GameState:
        copy = lambda p: Pipe(p.x, p.gap_top, p.gap_bottom, p.passed)  # noqa: E731
        pipe = self.next_pipe()
        return GameState(self.step_count, self.bird_y, self.bird_vy, self.score, self.alive, self.death_cause,
                         None if pipe is None else copy(pipe), tuple(copy(p) for p in self.pipes))
