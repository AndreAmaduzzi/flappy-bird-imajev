"""Detailed, themed game art (original drawings, no assets from the original game).

`ThemedRenderer(theme, scale)` draws the same game as render.GameRenderer, with gradient skies, parallax layers,
shaded pipes, a textured ground and an animated, anti-aliased bird. `scale` multiplies the 288x512 game size: 1 for
the frames the model sees, larger for videos. Everything is a function of the game state (step count, positions), so
a seed still renders identically. Pipes stay green and the bird yellow in every theme: the model's questions name
those colours.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, replace
from pathlib import Path

from . import render  # noqa: F401  (sets SDL's dummy driver before pygame is imported)
import pygame  # noqa: E402

from .game import BIRD_X, HEIGHT, PIPE_W, PLAY_H, WIDTH, Game  # noqa: E402

FONTS = Path(__file__).resolve().parents[1] / "assets" / "fonts"
CAP_H, CAP_OVER = 22, 4


@dataclass(frozen=True)
class Theme:
    name: str
    sky: tuple                      # gradient stops: ((position 0..1, (r, g, b)), ...)
    clouds: tuple | None            # (r, g, b, alpha) or None
    far: str                        # "city", "mountains" or "none"
    far_color: tuple
    far_color2: tuple               # second, nearer far layer (mountains) or windows (city at night)
    near_color: tuple | None        # bushes (None: no bushes)
    near_light: tuple
    ground: tuple                   # dirt
    ground_stripe: tuple
    grass: tuple
    grass_dark: tuple
    pipe: tuple = (98, 186, 62)
    pipe_light: tuple = (176, 232, 120)
    pipe_dark: tuple = (52, 122, 40)
    pipe_line: tuple = (38, 78, 30)
    sun: tuple | None = None        # (x, y, radius, (r, g, b))
    moon: tuple | None = None       # (x, y, radius)
    stars: int = 0
    windows: bool = False


THEMES = {
    "day": Theme("day", sky=((0, (86, 190, 232)), (0.75, (178, 230, 244)), (1, (214, 242, 246))),
                 clouds=(255, 255, 255, 235), far="city", far_color=(176, 222, 226), far_color2=(0, 0, 0),
                 near_color=(104, 196, 96), near_light=(146, 220, 120),
                 ground=(226, 212, 152), ground_stripe=(212, 194, 128), grass=(116, 202, 72), grass_dark=(78, 160, 52)),
    "sunset": Theme("sunset", sky=((0, (58, 44, 110)), (0.45, (214, 104, 118)), (0.8, (252, 170, 112)), (1, (255, 206, 140))),
                    clouds=(255, 196, 186, 190), far="mountains", far_color=(150, 86, 130), far_color2=(108, 62, 112),
                    near_color=(70, 120, 76), near_light=(96, 150, 90),
                    ground=(214, 170, 120), ground_stripe=(196, 150, 104), grass=(112, 170, 72), grass_dark=(80, 128, 54),
                    sun=(196, 300, 46, (255, 226, 150))),
    "night": Theme("night", sky=((0, (10, 14, 40)), (0.6, (30, 44, 92)), (1, (58, 78, 132))),
                   clouds=(150, 160, 210, 70), far="city", far_color=(28, 34, 70), far_color2=(255, 214, 120),
                   near_color=(28, 84, 60), near_light=(44, 110, 76),
                   ground=(120, 104, 86), ground_stripe=(104, 90, 74), grass=(64, 150, 70), grass_dark=(44, 108, 52),
                   pipe=(92, 196, 86), pipe_light=(170, 236, 140), pipe_dark=(50, 124, 50),
                   moon=(222, 84, 20), stars=90, windows=True),
}

THEMES["day_clean"] = replace(THEMES["day"], name="day_clean", far="none", near_color=None)          # no skyline, no bushes
THEMES["day_plain"] = replace(THEMES["day_clean"], name="day_plain", clouds=None)                   # plain sky too

BIRD = (252, 206, 44)
BIRD_SHADE = (236, 168, 32)
BIRD_LIGHT = (255, 232, 120)
BELLY = (255, 240, 176)
LINE = (86, 54, 18)
WING = (255, 246, 214)
BEAK_UP = (252, 146, 44)
BEAK_LOW = (226, 96, 30)


def lerp(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def gradient_color(stops, t):
    for (p0, c0), (p1, c1) in zip(stops, stops[1:]):
        if t <= p1:
            return lerp(c0, c1, (t - p0) / (p1 - p0) if p1 > p0 else 0)
    return stops[-1][1]


class ThemedRenderer:
    STRIP = 2 * WIDTH   # logical width of every scrolling layer (tileable)

    def __init__(self, theme: str | Theme = "day", scale: float = 1.0, show_score: bool = False):
        pygame.font.init()
        self.theme = THEMES[theme] if isinstance(theme, str) else theme
        self.s = scale
        self.size = (round(WIDTH * scale), round(HEIGHT * scale))
        self.surface = pygame.Surface(self.size)
        self.show_score = show_score
        self.background = self._background()
        self.clouds = self._clouds()
        self.far = self._far() if self.theme.far != "none" else None
        self.near = self._bushes() if self.theme.near_color else None
        self.pipe_body = self._pipe_row(PIPE_W)
        self.pipe_cap = self._pipe_row(PIPE_W + 2 * CAP_OVER)
        self.birds = {state: self._bird(state) for state in ("up", "mid", "down", "dead")}
        self.font = pygame.font.Font(str(FONTS / "LilitaOne-Regular.ttf"), self.S(46))

    def S(self, v):
        return round(v * self.s)

    # ------------------------------------------------------------------ public
    def draw(self, game: Game) -> pygame.Surface:
        s = self.surface
        dist = game.step_count * game.difficulty.pipe_speed
        s.blit(self.background, (0, 0))
        if self.clouds:
            self._scroll(s, self.clouds, dist * 0.08)
        if self.far:
            self._scroll(s, self.far, dist * 0.2)
        if self.near:
            self._scroll(s, self.near, dist * 0.45)
        for pipe in game.pipes:
            self._pipe(s, pipe)
        self._ground(s, dist)
        self._draw_bird(s, game)
        if self.show_score:
            self._score(s, game.score)
        return s

    def image(self, game: Game):
        from PIL import Image
        surface = self.draw(game)
        return Image.frombytes("RGB", surface.get_size(), pygame.image.tobytes(surface, "RGB"))

    # ------------------------------------------------------------------ static layers (supersampled)
    def _ss(self, logical_w, logical_h, fn, k=2, alpha=True):
        """Draw with plain filled shapes at k x the target scale, then smooth-downscale: clean anti-aliasing.
        fn(surface, P) where P(v) maps logical units to pixels of the big surface."""
        big_scale = self.s * k
        size = (round(logical_w * big_scale), round(logical_h * big_scale))
        big = pygame.Surface(size, pygame.SRCALPHA if alpha else 0)
        fn(big, lambda v: round(v * big_scale))
        return pygame.transform.smoothscale(big, (round(logical_w * self.s), round(logical_h * self.s)))

    def _background(self):
        t = self.theme

        def paint(surf, P):
            w, h = surf.get_size()
            for y in range(h):
                pygame.draw.line(surf, gradient_color(t.sky, y / (h - 1)), (0, y), (w, y))
            rng = random.Random(3)
            for _ in range(t.stars):
                x, y = rng.uniform(0, WIDTH), rng.uniform(0, PLAY_H * 0.72)
                b = rng.randint(150, 255)
                pygame.draw.circle(surf, (b, b, min(255, b + 15)), (P(x), P(y)), max(1, P(0.7 if rng.random() < 0.85 else 1.3)))
            if t.sun:
                x, y, r, color = t.sun
                glow = pygame.Surface((w, h), pygame.SRCALPHA)
                for i in range(60, 0, -1):          # many faint rings: a smooth radial glow
                    pygame.draw.circle(glow, (*color, 3), (P(x), P(y)), P(r + i * 1.4))
                surf.blit(glow, (0, 0))
                pygame.draw.circle(surf, color, (P(x), P(y)), P(r))
            if t.moon:
                x, y, r = t.moon
                glow = pygame.Surface((w, h), pygame.SRCALPHA)
                for i in range(40, 0, -1):
                    pygame.draw.circle(glow, (200, 210, 255, 3), (P(x), P(y)), P(r + i * 0.9))
                surf.blit(glow, (0, 0))
                pygame.draw.circle(surf, (246, 242, 222), (P(x), P(y)), P(r))
                for cx, cy, cr in ((-6, -4, 4), (6, 5, 3), (4, -8, 2.2), (-3, 9, 2)):
                    pygame.draw.circle(surf, (226, 220, 198), (P(x + cx), P(y + cy)), P(cr))
        return self._ss(WIDTH, HEIGHT, paint, k=2, alpha=False)

    def _clouds(self):
        if not self.theme.clouds:
            return None
        color = self.theme.clouds
        rng = random.Random(7)
        clouds = []
        for _ in range(6):
            cx, cy = rng.uniform(0, self.STRIP), rng.uniform(50, 230)
            size = rng.uniform(0.8, 1.3)
            puffs = [(-20, 4, 11), (-8, -4, 15), (8, -7, 17), (22, 0, 12), (2, 4, 13)]
            clouds.append((cx, cy, [(px * size, py * size, pr * size) for px, py, pr in puffs], size))

        def paint(surf, P):
            for cx, cy, puffs, size in clouds:
                for dx in (-self.STRIP, 0, self.STRIP):          # wrap so the strip tiles
                    for px, py, pr in puffs:
                        pygame.draw.circle(surf, color[:3], (P(cx + px + dx), P(cy + py)), P(pr))
                    pygame.draw.rect(surf, color[:3], (P(cx - 20 * size + dx), P(cy + 2 * size), P(42 * size), P(13 * size)),
                                     border_radius=P(6 * size))
        surf = self._ss(self.STRIP, HEIGHT, paint)
        surf.set_alpha(color[3])
        return surf

    def _far(self):
        t, rng = self.theme, random.Random(11)
        base = PLAY_H - 18
        if t.far == "city":
            buildings, x = [], 0.0
            while x < self.STRIP - 20:
                bw, bh = rng.uniform(16, 34), rng.uniform(36, 110)
                buildings.append((x, bw, bh, rng.random() < 0.3, [(wx, wy) for wy in range(int(base - bh + 6), int(base), 9)
                                                                   for wx in range(int(x + 4), int(x + bw - 4), 7)
                                                                   if rng.random() < 0.35]))
                x += bw + rng.uniform(0, 4)
            last_x = buildings[-1][0]
            buildings[-1] = (last_x, self.STRIP - last_x, *buildings[-1][2:])     # fill the strip exactly (tiles)

            def paint(surf, P):
                for x, bw, bh, antenna, windows in buildings:
                    pygame.draw.rect(surf, t.far_color, (P(x), P(base - bh), P(bw) + 1, P(bh + 18)))
                    if antenna:
                        pygame.draw.rect(surf, t.far_color, (P(x + bw / 2 - 1), P(base - bh - 10), max(1, P(2)), P(10)))
                    if t.windows:
                        for wx, wy in windows:
                            pygame.draw.rect(surf, t.far_color2, (P(wx), P(wy), max(1, P(3)), max(1, P(4))))
            return self._ss(self.STRIP, HEIGHT, paint)

        ridges = []   # two ranges of mountains, midpoint-displacement ridges that tile
        for color, height, seed in ((t.far_color, 160, 1), (t.far_color2, 100, 2)):
            r = random.Random(seed)
            n = 64
            ys = [0.0] * (n + 1)
            ys[0] = ys[n] = r.uniform(0.4, 0.7)
            step, amp = n, 0.5
            while step > 1:
                half = step // 2
                for i in range(half, n, step):
                    ys[i] = (ys[i - half] + ys[i + half]) / 2 + r.uniform(-amp, amp)
                step, amp = half, amp * 0.55
            ridges.append((color, [(i * self.STRIP / n, base - max(0.15, min(1.0, y)) * height) for i, y in enumerate(ys)]))

        def paint(surf, P):
            for color, pts in ridges:
                poly = [(0, P(PLAY_H))] + [(P(x), P(y)) for x, y in pts] + [(P(self.STRIP), P(PLAY_H))]
                pygame.draw.polygon(surf, color, poly)
        return self._ss(self.STRIP, HEIGHT, paint)

    def _bushes(self):
        t, rng = self.theme, random.Random(5)
        circles, x = [], 0.0
        while x < self.STRIP:
            r = rng.uniform(10, 18)
            circles.append((x, PLAY_H - r * 0.55, r))
            x += r * rng.uniform(0.9, 1.3)

        def paint(surf, P):
            for dx in (-self.STRIP, 0, self.STRIP):
                for cx, cy, r in circles:
                    pygame.draw.circle(surf, t.near_color, (P(cx + dx), P(cy)), P(r))
            for dx in (-self.STRIP, 0, self.STRIP):
                for cx, cy, r in circles:
                    pygame.draw.circle(surf, t.near_light, (P(cx + dx - r * 0.25), P(cy - r * 0.4)), P(r * 0.42))
            pygame.draw.rect(surf, t.near_color, (0, P(PLAY_H - 6), surf.get_width(), P(6)))
        return self._ss(self.STRIP, HEIGHT, paint)

    def _pipe_row(self, width):
        """One pixel row of a pipe's horizontal shading, stretched vertically when drawn."""
        t = self.theme
        w = self.S(width)
        row = pygame.Surface((w, 1))
        for i in range(w):
            u = i / max(1, w - 1)
            if u < 0.08:
                c = lerp(t.pipe_dark, t.pipe, u / 0.08)
            elif u < 0.3:
                c = lerp(t.pipe, t.pipe_light, (u - 0.08) / 0.22)
            elif u < 0.45:
                c = lerp(t.pipe_light, t.pipe, (u - 0.3) / 0.15)
            elif u < 0.85:
                c = t.pipe
            else:
                c = lerp(t.pipe, t.pipe_dark, (u - 0.85) / 0.15)
            row.set_at((i, 0), c)
        return row

    # ------------------------------------------------------------------ bird sprites (supersampled 4x)
    def _bird(self, state):
        W, H = 56, 46
        cx, cy = 26, 23

        def paint(surf, P):
            def ell(x, y, rx, ry, col):
                pygame.draw.ellipse(surf, col, (P(cx + x - rx), P(cy + y - ry), P(2 * rx), P(2 * ry)))

            def poly(pts, col):
                pygame.draw.polygon(surf, col, [(P(cx + x), P(cy + y)) for x, y in pts])
            # tail feathers
            poly([(-12, -3), (-22, -8), (-20, -1), (-23, 4), (-12, 5)], LINE)
            poly([(-12, -1.6), (-20, -5.6), (-18.6, -0.6), (-20.6, 2.6), (-12, 3.6)], BIRD_SHADE)
            # body: outline, base, lower shade, belly, top highlight
            ell(0, 0, 17.6, 14.4, LINE)
            ell(0, 0, 16, 12.8, BIRD_SHADE)
            ell(0, -1.4, 15.2, 11.2, BIRD)
            ell(5, 5, 9.5, 6, BELLY)
            ell(-3, -7, 7, 3, BIRD_LIGHT)
            # wing (flaps)
            wy, tilt = {"up": (-4, -1), "mid": (1, 0), "down": (5, 1), "dead": (1, 0)}[state]
            ell(-5, wy, 8.4, 5.6 + tilt * 0.6, LINE)
            ell(-5, wy - 0.3, 7, 4.4 + tilt * 0.6, WING)
            ell(-6.5, wy + 1.2, 4.5, 2, (246, 222, 160))
            # eye
            ell(7.5, -5, 6.6, 6.8, LINE)
            ell(7.5, -5, 5.4, 5.6, (255, 255, 255))
            if state == "dead":
                for d in (-1, 1):
                    pygame.draw.line(surf, LINE, (P(cx + 5.2), P(cy - 5 - 2.4 * d)), (P(cx + 10), P(cy - 5 + 2.4 * d)), P(1.6))
            else:
                ell(9.4, -4.8, 2.6, 3.1, (26, 24, 32))
                ell(10.3, -6.2, 0.95, 0.95, (255, 255, 255))
            # beak: upper and lower
            poly([(10.5, -1.8), (22.5, 1.2), (10.5, 3.6)], LINE)
            poly([(11.5, -0.6), (20.5, 1.3), (11.5, 2.6)], BEAK_UP)
            poly([(10.5, 2.6), (20.5, 3.4), (10.5, 7.6)], LINE)
            poly([(11.5, 3.4), (18.5, 3.8), (11.5, 6.4)], BEAK_LOW)
            # cheek
            ell(3, 1.5, 2.6, 1.6, (255, 170, 120))
        return self._ss(W, H, paint, k=4)

    def _draw_bird(self, s, game):
        if not game.alive:
            state = "dead"
        else:
            since = game.step_count - game.last_flap_step
            cycle = 2 if since < 12 else 5        # flaps its wings faster right after a flap
            state = ("up", "mid", "down", "mid")[(game.step_count // cycle) % 4]
        angle = max(-25.0, min(80.0, game.bird_vy * 7.0))
        sprite = pygame.transform.rotozoom(self.birds[state], -angle, 1.0)
        s.blit(sprite, sprite.get_rect(center=(self.S(BIRD_X), self.S(game.bird_y))))

    # ------------------------------------------------------------------ dynamic pieces
    def _scroll(self, s, strip, offset):
        w = strip.get_width()
        x = -round(self.S(offset)) % w
        s.blit(strip, (x - w, 0))
        s.blit(strip, (x, 0))

    def _pipe(self, s, pipe):
        t = self.theme
        x = self.S(pipe.x)
        w, cw = self.pipe_body.get_width(), self.pipe_cap.get_width()
        for top, bottom, cap_y in ((0, pipe.gap_top - CAP_H, pipe.gap_top - CAP_H), (pipe.gap_bottom + CAP_H, PLAY_H, pipe.gap_bottom)):
            y0, y1 = self.S(top), self.S(bottom)
            if y1 > y0:
                s.blit(pygame.transform.scale(self.pipe_body, (w, y1 - y0)), (x, y0))
                pygame.draw.line(s, t.pipe_line, (x, y0), (x, y1), max(1, self.S(1.5)))
                pygame.draw.line(s, t.pipe_line, (x + w - 1, y0), (x + w - 1, y1), max(1, self.S(1.5)))
            # shadow of the cap on the body
            shadow = pygame.Surface((w, self.S(5)), pygame.SRCALPHA)
            shadow.fill((0, 0, 0, 50))
            s.blit(shadow, (x, self.S(cap_y + CAP_H) if cap_y == pipe.gap_bottom else self.S(cap_y) - self.S(5)))
            cx, cy, ch = self.S(pipe.x - CAP_OVER), self.S(cap_y), self.S(CAP_H)
            s.blit(pygame.transform.scale(self.pipe_cap, (cw, ch)), (cx, cy))
            pygame.draw.rect(s, t.pipe_line, (cx, cy, cw, ch), max(1, self.S(1.6)), border_radius=self.S(3))
            pygame.draw.line(s, t.pipe_light, (cx + self.S(3), cy + self.S(3)), (cx + cw - self.S(4), cy + self.S(3)), max(1, self.S(1.2)))

    def _ground(self, s, dist):
        t = self.theme
        y0, w = self.S(PLAY_H), self.size[0]
        pygame.draw.rect(s, t.ground, (0, y0, w, self.size[1] - y0))
        off = dist % 24
        for i in range(-1, WIDTH // 24 + 2):
            x = i * 24 - off
            poly = [(x, PLAY_H + 20), (x + 12, PLAY_H + 20), (x + 24, PLAY_H + 34), (x + 12, PLAY_H + 34)]
            pygame.draw.polygon(s, t.ground_stripe, [(self.S(px), self.S(py)) for px, py in poly])
        for i in range(3):   # speckles
            for j in range(WIDTH // 16 + 2):
                px = (j * 16 + i * 5 + 7 - dist) % (WIDTH + 16) - 8
                pygame.draw.rect(s, t.ground_stripe, (self.S(px), self.S(PLAY_H + 42 + i * 6), max(1, self.S(2)), max(1, self.S(2))))
        # grass band with blades
        pygame.draw.rect(s, t.grass, (0, y0, w, self.S(11)))
        pygame.draw.rect(s, t.grass_dark, (0, y0 + self.S(11), w, self.S(3)))
        boff = dist % 8
        for i in range(-1, WIDTH // 8 + 2):
            bx = i * 8 - boff
            blade = [(bx, PLAY_H + 11), (bx + 4, PLAY_H + 4), (bx + 8, PLAY_H + 11)]
            pygame.draw.polygon(s, t.grass_dark, [(self.S(px), self.S(py)) for px, py in blade])
        pygame.draw.line(s, lerp(t.grass, (255, 255, 255), 0.35), (0, y0 + self.S(1)), (w, y0 + self.S(1)), max(1, self.S(1.5)))
        pygame.draw.line(s, t.grass_dark, (0, y0), (w, y0), max(1, self.S(1)))

    def _score(self, s, score):
        text = str(score)
        outline = self.font.render(text, True, LINE)
        fill = self.font.render(text, True, (255, 255, 255))
        cx, top = self.size[0] // 2, self.S(30)
        r = max(1, self.S(2.5))
        for a in range(0, 360, 30):
            dx, dy = round(r * math.cos(math.radians(a))), round(r * math.sin(math.radians(a)))
            s.blit(outline, outline.get_rect(midtop=(cx + dx, top + dy + max(1, self.S(1.5)))))
        s.blit(fill, fill.get_rect(midtop=(cx, top)))
