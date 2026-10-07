"""Drawing with pygame: the game view (exactly what the model sees) and, for videos, the info panel.

Original flat-colour graphics only. pygame surfaces need no display, so this works headless; without a display the
module selects SDL's dummy video driver before importing pygame.
"""
from __future__ import annotations

import math
import os
import sys
from dataclasses import dataclass

# Headless (no display, e.g. a GPU server): render off-screen with SDL's dummy driver. With a display, leave SDL alone
# so app.py can open a window.
if sys.platform.startswith("linux") and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame  # noqa: E402
from PIL import Image  # noqa: E402

from .game import BIRD_R, BIRD_X, GROUND_H, HEIGHT, PIPE_W, PLAY_H, WIDTH, Game  # noqa: E402

SKY = (112, 197, 206)
CLOUD = (232, 246, 248)
PIPE = (88, 178, 70)
PIPE_DARK = (44, 110, 38)
PIPE_LIGHT = (140, 214, 110)
GROUND = (222, 206, 150)
GROUND_TOP = (110, 190, 60)
GROUND_STRIPE = (204, 186, 128)
BIRD = (250, 204, 40)
BIRD_DARK = (150, 100, 10)
WING = (255, 236, 150)
BEAK = (240, 110, 40)
WHITE = (255, 255, 255)
BLACK = (20, 20, 20)
CAP_H, CAP_OVER = 18, 4      # pipe lip height and how far it overhangs the pipe body


def _bird_sprite():
    """The bird drawn once, facing right, on a transparent surface; rotated per frame by its speed."""
    size = BIRD_R * 2 + 14
    s = pygame.Surface((size, size), pygame.SRCALPHA)
    c = size // 2
    pygame.draw.ellipse(s, BIRD_DARK, (c - BIRD_R - 3, c - BIRD_R + 1, 2 * BIRD_R + 6, 2 * BIRD_R - 2))
    pygame.draw.ellipse(s, BIRD, (c - BIRD_R - 1, c - BIRD_R + 3, 2 * BIRD_R + 2, 2 * BIRD_R - 6))
    pygame.draw.ellipse(s, WING, (c - BIRD_R + 1, c - 1, 13, 8))                        # wing
    pygame.draw.circle(s, WHITE, (c + 6, c - 4), 5)                                     # eye
    pygame.draw.circle(s, BLACK, (c + 8, c - 4), 2)
    pygame.draw.polygon(s, BEAK, [(c + BIRD_R - 2, c - 1), (c + BIRD_R + 7, c + 2), (c + BIRD_R - 2, c + 5)])
    return s


class GameRenderer:
    """Renders a Game to a WIDTH x HEIGHT surface; `image()` gives the PIL frame sent to the model."""

    def __init__(self, show_score: bool = False):
        self.surface = pygame.Surface((WIDTH, HEIGHT))
        self.bird = _bird_sprite()
        self.show_score = show_score
        self._font = None

    def draw(self, game: Game) -> pygame.Surface:
        s = self.surface
        s.fill(SKY)
        # Two static clouds give the sky some texture without moving background clutter.
        for cx, cy in ((60, 90), (210, 140)):
            for dx, dy, r in ((0, 0, 16), (18, -6, 20), (38, 0, 15)):
                pygame.draw.circle(s, CLOUD, (cx + dx, cy + dy), r)
        for pipe in game.pipes:
            self._pipe(s, pipe)
        self._ground(s, game.ground_offset)
        tilt = max(-30.0, min(70.0, game.bird_vy * 6.0))
        sprite = pygame.transform.rotate(self.bird, -tilt)
        s.blit(sprite, sprite.get_rect(center=(BIRD_X, round(game.bird_y))))
        if self.show_score:
            self._score(s, game.score)
        return s

    def image(self, game: Game) -> Image.Image:
        surface = self.draw(game)
        return Image.frombytes("RGB", surface.get_size(), pygame.image.tobytes(surface, "RGB"))

    # ------------------------------------------------------------------ pieces
    @staticmethod
    def _pipe(s, pipe):
        x = round(pipe.x)
        for top, bottom, cap_y in ((0, pipe.gap_top, pipe.gap_top - CAP_H), (pipe.gap_bottom, PLAY_H, pipe.gap_bottom)):
            top, bottom, cap_y = round(top), round(bottom), round(cap_y)
            pygame.draw.rect(s, PIPE, (x, top, PIPE_W, bottom - top))
            pygame.draw.rect(s, PIPE_LIGHT, (x + 6, top, 8, bottom - top))
            pygame.draw.rect(s, PIPE_DARK, (x, top, PIPE_W, bottom - top), 3)
            cap = (x - CAP_OVER, cap_y, PIPE_W + 2 * CAP_OVER, CAP_H)
            pygame.draw.rect(s, PIPE, cap)
            pygame.draw.rect(s, PIPE_DARK, cap, 3)

    @staticmethod
    def _ground(s, offset):
        pygame.draw.rect(s, GROUND, (0, PLAY_H, WIDTH, GROUND_H))
        for i in range(-1, WIDTH // 24 + 2):
            x = round(i * 24 - offset)
            pygame.draw.polygon(s, GROUND_STRIPE, [(x, PLAY_H + 14), (x + 12, PLAY_H + 14),
                                                   (x + 24, PLAY_H + 26), (x + 12, PLAY_H + 26)])
        pygame.draw.rect(s, GROUND_TOP, (0, PLAY_H, WIDTH, 8))
        pygame.draw.line(s, PIPE_DARK, (0, PLAY_H), (WIDTH, PLAY_H), 2)

    def _score(self, s, score):
        if self._font is None:
            pygame.font.init()
            self._font = pygame.font.Font(None, 56)
        text = str(score)
        for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2)):
            shadow = self._font.render(text, True, BLACK)
            s.blit(shadow, shadow.get_rect(midtop=(WIDTH // 2 + dx, 24 + dy)))
        label = self._font.render(text, True, WHITE)
        s.blit(label, label.get_rect(midtop=(WIDTH // 2, 24)))


# ================================================================================================ video panel

BG = (16, 20, 26)
CARD = (30, 36, 46)
TEXT = (236, 240, 244)
MUTED = (140, 150, 162)
FLAP_C = (255, 150, 50)
WAIT_C = (70, 150, 255)
UNKNOWN_C = (170, 120, 230)
DEAD_C = (235, 64, 64)

TITLE = "imajev-4b plays Flappy Bird from raw pixels"
SUBTITLE = "each decision: one screenshot + a typed question -> calibrated probabilities"


@dataclass
class PanelState:
    agent_label: str                  # e.g. "imajev-4b · direct"
    agent_detail: str                 # e.g. "1 question: flap / wait"
    footer: str                       # e.g. "easy · seed 0 · lockstep (game waits for the model)"
    pipes: int = 0
    game_time_s: float = 0.0
    p_flap: float | None = None
    p_wait: float | None = None
    unknown: float | None = None
    action: str | None = None
    abstained: bool = False
    latency_ms: float | None = None
    lines: tuple[str, ...] = ()       # agent readout (perception answers, rule)
    flash: float = 0.0                # 1 right after a flap decision, fades to 0
    dead: bool = False
    death_cause: str | None = None
    death_t: float = 0.0              # 0..1 through the death hold


class Fonts:
    def __init__(self, scale: float = 1.0):
        pygame.font.init()
        f = lambda px: pygame.font.Font(None, max(8, round(px * scale)))  # noqa: E731  freesansbold, bundled
        self.title, self.big, self.mid, self.small, self.tiny = f(52), f(64), f(40), f(32), f(27)


def _text(surface, font, text, color, pos, anchor="topleft"):
    image = font.render(text, True, color)
    rect = image.get_rect(**{anchor: pos})
    surface.blit(image, rect)
    return rect


def _fmt_pct(p):
    """Whole percents, with one decimal near 50% (so a 49.9% call that lost reads as such) and below 1%."""
    if p is None:
        return "-"
    return f"{100 * p:.1f}%" if 0.45 < p < 0.55 or 0 < p < 0.01 else f"{100 * p:.0f}%"


def draw_panel(surface, rect, st: PanelState, fonts: Fonts):
    """The info panel: agent, P(flap) vs P(wait) bar, unknown, latency, pipes, readout, footer."""
    x, y, w = rect.x, rect.y, rect.width
    pad = round(w * 0.03)
    _text(surface, fonts.mid, st.agent_label, TEXT, (x, y))
    y += fonts.mid.get_height() + 2
    _text(surface, fonts.tiny, st.agent_detail, MUTED, (x, y))
    y += fonts.tiny.get_height() + pad

    # P(flap) vs P(wait): one split bar over the known options, labels above it
    if st.p_flap is not None:
        _text(surface, fonts.mid, f"FLAP {_fmt_pct(st.p_flap)}", FLAP_C, (x, y))
        _text(surface, fonts.mid, f"WAIT {_fmt_pct(st.p_wait)}", WAIT_C, (x + w, y), "topright")
    y += fonts.mid.get_height() + 4
    bar_h = round(fonts.big.get_height() * 0.8)
    pygame.draw.rect(surface, CARD, (x, y, w, bar_h), border_radius=12)
    if st.p_flap is not None:
        fw = round(w * st.p_flap)
        flap_col = tuple(min(255, round(c + (255 - c) * 0.5 * st.flash)) for c in FLAP_C)
        pygame.draw.rect(surface, flap_col, (x, y, fw, bar_h), border_top_left_radius=12, border_bottom_left_radius=12)
        pygame.draw.rect(surface, WAIT_C, (x + fw, y, w - fw, bar_h), border_top_right_radius=12, border_bottom_right_radius=12)
        pygame.draw.line(surface, BG, (x + w // 2, y - 4), (x + w // 2, y + bar_h + 4), 2)   # the 50% mark
        chosen = (x, y, fw, bar_h) if st.action == "flap" else (x + fw, y, w - fw, bar_h)
        pygame.draw.rect(surface, TEXT, chosen, 4, border_radius=12)
    else:
        _text(surface, fonts.small, "waiting for the first decision...", MUTED, (x + pad, y + bar_h // 2), "midleft")
    y += bar_h + pad // 2

    # unknown probability: thin bar on a 0-100% scale
    uh = round(fonts.small.get_height() * 0.6)
    label = _text(surface, fonts.small, f"unknown {_fmt_pct(st.unknown)}", UNKNOWN_C, (x, y))
    bx = label.right + pad
    pygame.draw.rect(surface, CARD, (bx, y + (label.height - uh) // 2, x + w - bx, uh), border_radius=6)
    if st.unknown:
        pygame.draw.rect(surface, UNKNOWN_C, (bx, y + (label.height - uh) // 2, max(3, round((x + w - bx) * st.unknown)), uh),
                         border_radius=6)
    y += label.height + pad

    # tiles: pipes / latency / decision
    tiles = [("PIPES", str(st.pipes), TEXT),
             ("LATENCY", "-" if st.latency_ms is None else "<1 ms" if st.latency_ms < 1 else f"{st.latency_ms:.0f} ms", TEXT),
             ("DECISION", ("WAIT (unknown)" if st.abstained else (st.action or "-").upper()),
              UNKNOWN_C if st.abstained else FLAP_C if st.action == "flap" else WAIT_C)]
    gap = pad
    tw = (w - 2 * gap) // 3
    th = fonts.tiny.get_height() + fonts.big.get_height() + pad
    for i, (name, value, color) in enumerate(tiles):
        tx = x + i * (tw + gap)
        pygame.draw.rect(surface, CARD, (tx, y, tw, th), border_radius=12)
        _text(surface, fonts.tiny, name, MUTED, (tx + tw // 2, y + pad // 2), "midtop")
        vf = fonts.big if len(value) <= 6 else fonts.mid if len(value) <= 9 else fonts.small
        _text(surface, vf, value, color, (tx + tw // 2, y + th - pad // 2), "midbottom")
    y += th + pad

    for line in st.lines:
        _text(surface, fonts.small, line, TEXT, (x, y))
        y += fonts.small.get_height() + 4

    first, _, second = st.footer.rpartition(" · ")
    _text(surface, fonts.tiny, second, MUTED, (x, rect.bottom), "bottomleft")
    _text(surface, fonts.tiny, f"{first} · t = {st.game_time_s:.1f} s", MUTED,
          (x, rect.bottom - fonts.tiny.get_height() - 2), "bottomleft")


def _game_view(surface, game_surface, rect, st: PanelState, fonts: Fonts):
    scaled = pygame.transform.scale(game_surface, rect.size)    # nearest: crisp, exactly the model's pixels
    surface.blit(scaled, rect)
    if st.dead:
        k = min(1.0, st.death_t * 4)
        shade = pygame.Surface(rect.size, pygame.SRCALPHA)
        shade.fill((0, 0, 0, round(90 * k)))
        surface.blit(shade, rect)
        pygame.draw.rect(surface, DEAD_C, rect.inflate(12, 12), 8)
        # the model's last call, on a card in the upper part of the game view
        lines = [(fonts.big, f"CRASH: {st.death_cause.replace('_', ' ')}", DEAD_C)]
        if st.p_flap is not None:
            lines += [(fonts.small, "model's last call", MUTED),
                      (fonts.mid, f"P(flap) {_fmt_pct(st.p_flap)}  ·  P(wait) {_fmt_pct(st.p_wait)}", TEXT),
                      (fonts.small, f"unknown {_fmt_pct(st.unknown)}  ·  chose {(st.action or '-').upper()}", TEXT)]
        height = sum(f.get_height() + 6 for f, _, _ in lines) + 24
        card = pygame.Rect(0, 0, rect.width - 40, height)
        card.midtop = (rect.centerx, rect.y + round(rect.height * 0.06))
        back = pygame.Surface(card.size, pygame.SRCALPHA)
        back.fill((*BG, round(225 * k)))
        surface.blit(back, card)
        ty = card.y + 12
        for font, text, color in lines:
            ty = _text(surface, font, text, color, (card.centerx, ty), "midtop").bottom + 6
    else:
        pygame.draw.rect(surface, CARD, rect.inflate(8, 8), 4)


class Layout:
    """A video format: canvas size, where the game goes, where the panel goes."""

    def __init__(self, name: str, theme: str = "flat"):
        self.name = name
        self.renderer = make_renderer(theme)
        if name == "9x16":      # game on top, panel underneath
            self.size = (1080, 1920)
            self.title_at = (60, 40)
            self.game = pygame.Rect(230, 175, 620, 1102)
            self.panel = pygame.Rect(60, 1310, 960, 575)
            self.fonts = Fonts(1.2)
        elif name == "1x1":     # game left, panel right
            self.size = (1080, 1080)
            self.title_at = None
            self.game = pygame.Rect(32, 32, 576, 1024)
            self.panel = pygame.Rect(640, 150, 412, 890)
            self.fonts = Fonts(0.85)
        else:
            raise ValueError(f"unknown layout {name!r} (9x16 or 1x1)")
        self.canvas = pygame.Surface(self.size)

    def capture(self, game) -> bytes:
        """Render the game view (called on the game loop's thread)."""
        return pygame.image.tobytes(self.renderer.draw(game), "RGB")

    def compose(self, payload: bytes, st: PanelState) -> bytes:
        """Build the full frame from a captured game view (called on the encoder thread)."""
        game_surface = pygame.image.frombytes(payload, (WIDTH, HEIGHT), "RGB")
        c = self.canvas
        c.fill(BG)
        if self.title_at:
            _text(c, self.fonts.title, TITLE, TEXT, self.title_at)
            _text(c, self.fonts.tiny, SUBTITLE, MUTED, (self.title_at[0], self.title_at[1] + self.fonts.title.get_height() + 4))
        else:   # 1:1: the title sits above the panel
            _text(c, self.fonts.mid, "imajev-4b plays", TEXT, (self.panel.x, 36))
            _text(c, self.fonts.mid, "Flappy Bird from pixels", TEXT, (self.panel.x, 36 + self.fonts.mid.get_height()))
        _game_view(c, game_surface, self.game, st, self.fonts)
        draw_panel(c, self.panel, st, self.fonts)
        return pygame.image.tobytes(c, "RGB")


THEMES = ("flat", "day", "sunset", "night")


def make_renderer(theme: str = "flat", scale: float = 1.0, show_score: bool = False):
    """The flat renderer (used for the benchmark) or a detailed themed one (flappy/art.py)."""
    if theme == "flat":
        return GameRenderer(show_score=show_score)
    from .art import ThemedRenderer
    return ThemedRenderer(theme, scale=scale, show_score=show_score)


def resize_for_model(image: Image.Image, max_pixels: int = 400_000) -> Image.Image:
    """Downscale (never upscale) to at most `max_pixels`, as the model was trained (LANCZOS, aspect kept)."""
    scale = min(1.0, math.sqrt(max_pixels / (image.width * image.height)))
    if scale >= 1.0:
        return image
    size = (max(1, int(image.width * scale)), max(1, int(image.height * scale)))
    return image.resize(size, Image.Resampling.LANCZOS)
