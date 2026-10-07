"""Upper bound: reads the true game state and searches flap/wait sequences a few decisions ahead.

Each sequence is simulated with the game's own physics and collision test (pipes shifted by the elapsed steps).
The oracle picks the first action of the sequence that survives longest, breaking ties by staying close to a
target slightly below the next gap's centre.
"""
from __future__ import annotations

from ..game import BIRD_R, BIRD_X, PLAY_H, collide
from .base import FLAP, WAIT, Agent, Decision, Observation


class OracleAgent(Agent):
    name = "oracle"
    needs_frame = False
    privileged = True

    def __init__(self, depth: int = 7, block: int = 5):
        self.depth = depth    # decisions searched ahead
        self.block = block    # physics steps per searched decision after the first one

    def decide(self, obs: Observation) -> Decision:
        s = obs.state
        self._d = obs.difficulty
        self._pipes = [p for p in s.pipes if p.right >= BIRD_X - BIRD_R][:3]
        wait = self._search(s.bird_y, s.bird_vy, 0, False, obs.decide_every, self.depth, 0, 0.0)
        flap = self._search(s.bird_y, s.bird_vy, 0, True, obs.decide_every, self.depth, 0, 0.0)
        choose_flap = flap > wait   # (survived steps, -cost): higher is better
        return Decision(FLAP if choose_flap else WAIT, p_flap=float(choose_flap), p_wait=float(not choose_flap),
                        unknown=0.0, info={"survive_flap": flap[0], "survive_wait": wait[0]})

    def _search(self, y, vy, t, flap, steps, depth, survived, cost):
        """Best (survived, -cost) over every continuation starting with `flap`, held for `steps` physics steps."""
        d, pipes = self._d, self._pipes
        for i in range(steps):
            vy = d.flap_velocity if (flap and i == 0) else min(vy + d.gravity, d.max_fall)
            y += vy
            t += 1
            dx = d.pipe_speed * t
            if collide(y, pipes, dx):
                return (survived, -cost)
            survived += 1
            ahead = next((p for p in pipes if p.right - dx >= BIRD_X - BIRD_R), None)
            target = ahead.gap_center + 0.15 * (ahead.gap_bottom - ahead.gap_top) if ahead else PLAY_H * 0.55
            cost += (y - target) ** 2
        if depth <= 1:
            return (survived, -cost)
        return max(self._search(y, vy, t, nxt, self.block, depth - 1, survived, cost) for nxt in (False, True))
