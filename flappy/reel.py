"""The 9:16 reel layout: a title, the game, and the FLAP / WAIT bar. Nothing else.

`ReelLayout(style, theme)` is used by record.Recorder like the other layouts: `capture(game)` renders the game (on
the loop's thread) and `compose(payload, state)` builds the 1080x1920 frame (on the encoder thread).
Styles: "dark", "light", "immersive" (the background is a blurred copy of the game).
"""
from __future__ import annotations

import math
from pathlib import Path

import pygame

from .art import FONTS, ThemedRenderer, lerp
from .game import HEIGHT, WIDTH
from .render import PanelState

SIZE = (1080, 1920)
GAME_SCALE = 2.3                  # 662 x 1178 game card
FLAP = ((255, 170, 64), (255, 122, 26))       # gradient start / end
WAIT = ((92, 172, 255), (46, 120, 246))

STYLES = {
    "dark": dict(bg=((12, 16, 24), (24, 30, 44)), title=(244, 246, 250), accent=(255, 210, 63), track=(34, 41, 56),
                 label=(150, 160, 178), card_line=(44, 52, 70), title_font="Poppins-Bold.ttf", shadow=150),
    "light": dict(bg=((248, 245, 238), (236, 229, 216)), title=(28, 36, 52), accent=(46, 158, 68), track=(224, 217, 203),
                  label=(110, 104, 94), card_line=(214, 206, 190), title_font="Poppins-Bold.ttf", shadow=70),
    "immersive": dict(bg=None, title=(255, 255, 255), accent=(255, 214, 70), track=(255, 255, 255, 46),
                      label=(236, 240, 246), card_line=(255, 255, 255, 60), title_font="LilitaOne-Regular.ttf", shadow=120),
}


def font(name, size):
    return pygame.font.Font(str(Path(FONTS) / name), size)


def vertical_gradient(size, top, bottom):
    surf = pygame.Surface(size)
    w, h = size
    for y in range(h):
        pygame.draw.line(surf, lerp(top, bottom, y / (h - 1)), (0, y), (w, y))
    return surf


def rounded_mask(size, radius):
    mask = pygame.Surface(size, pygame.SRCALPHA)
    pygame.draw.rect(mask, (255, 255, 255, 255), (0, 0, *size), border_radius=radius)
    return mask


class ReelLayout:
    name = "reel"

    def __init__(self, style: str = "dark", theme: str = "day", title=("Can Imajev play", "Flappy Bird?")):
        pygame.font.init()
        self.style, self.st = style, STYLES[style]
        self.size = SIZE
        self.canvas = pygame.Surface(SIZE)
        self.renderer = ThemedRenderer(theme, scale=GAME_SCALE, show_score=True)
        gw, gh = self.renderer.size
        self.card = pygame.Rect((SIZE[0] - gw) // 2, 430, gw, gh)
        self.radius = 34
        self.mask = rounded_mask(self.card.size, self.radius)
        self.bar = pygame.Rect(110, self.card.bottom + 136, SIZE[0] - 220, 74)
        self.title_font = font(self.st["title_font"], 104 if style == "immersive" else 92)
        self.label_font = font("Poppins-SemiBold.ttf", 46)
        self.value_font = font("Poppins-Bold.ttf", 72)
        self.title = title
        self.static = None if style == "immersive" else self._static_background()
        self.shown = None            # bar position shown (eased towards the decision's P(flap))

    # ------------------------------------------------------------------ recorder interface
    def capture(self, game) -> bytes:
        return pygame.image.tobytes(self.renderer.draw(game), "RGB")

    def compose(self, payload: bytes, st: PanelState) -> bytes:
        game = pygame.image.frombytes(payload, self.renderer.size, "RGB")
        c = self.canvas
        if self.static is not None:
            c.blit(self.static, (0, 0))
        else:
            self._immersive_background(c, game)
        self._title(c)
        self._game_card(c, game, st)
        self._bar(c, st)
        return pygame.image.tobytes(c, "RGB")

    # ------------------------------------------------------------------ pieces
    def _static_background(self):
        bg = vertical_gradient(SIZE, *self.st["bg"])
        self._card_shadow(bg, self.card)
        return bg

    def _card_shadow(self, surf, rect):
        shadow = pygame.Surface((rect.width + 120, rect.height + 120), pygame.SRCALPHA)
        for i in range(30, 0, -1):    # soft, layered shadow
            a = round(self.st["shadow"] * (1 - i / 30) ** 2 / 12)
            pygame.draw.rect(shadow, (0, 0, 0, a), (60 - i * 2, 60 - i * 2 + 18, rect.width + i * 4, rect.height + i * 4),
                             border_radius=self.radius + i * 2)
        surf.blit(shadow, (rect.x - 60, rect.y - 60))

    def _immersive_background(self, c, game):
        small = pygame.transform.smoothscale(game, (WIDTH // 8, HEIGHT // 8))
        blurred = pygame.transform.smoothscale(pygame.transform.smoothscale(small, (WIDTH // 4, HEIGHT // 4)), SIZE)
        c.blit(blurred, (0, 0))
        shade = pygame.Surface(SIZE, pygame.SRCALPHA)
        shade.fill((8, 10, 20, 120))
        c.blit(shade, (0, 0))
        self._card_shadow(c, self.card)

    def _title(self, c):
        y = 110
        for i, line in enumerate(self.title):
            color = self.st["accent"] if i == len(self.title) - 1 else self.st["title"]
            image = self.title_font.render(line, True, color)
            rect = image.get_rect(midtop=(SIZE[0] // 2, y))
            if self.style == "immersive":
                shadow = self.title_font.render(line, True, (0, 0, 0))
                shadow.set_alpha(110)
                c.blit(shadow, rect.move(0, 5))
            c.blit(image, rect)
            y += round(self.title_font.get_height() * 0.98)

    def _game_card(self, c, game, st):
        card = game.copy()
        rect = self.card.copy()
        if st.dead:
            k = st.death_t
            flash = max(0.0, 1 - k * 6)                      # white flash right after the crash
            if flash:
                white = pygame.Surface(card.get_size(), pygame.SRCALPHA)
                white.fill((255, 255, 255, round(210 * flash)))
                card.blit(white, (0, 0))
            shake = max(0.0, 1 - k * 4) * 16                 # a short shake
            rect.move_ip(round(shake * math.sin(k * 90)), round(shake * 0.5 * math.cos(k * 110)))
        rounded = pygame.Surface(card.get_size(), pygame.SRCALPHA)
        rounded.blit(card, (0, 0))
        rounded.blit(self.mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
        c.blit(rounded, rect)
        line = self.st["card_line"]
        border = pygame.Surface(rect.inflate(6, 6).size, pygame.SRCALPHA)
        pygame.draw.rect(border, line if len(line) == 4 else (*line, 255), border.get_rect(), 3, border_radius=self.radius + 3)
        c.blit(border, rect.inflate(6, 6))

    def _bar(self, c, st):
        bar = self.bar
        target = st.p_flap if st.p_flap is not None else 0.5
        self.shown = target if self.shown is None else self.shown + (target - self.shown) * 0.45
        p = self.shown
        flap_on = st.action == "flap"
        decided = st.action is not None

        # labels: FLAP 62%  ...  38% WAIT
        y = bar.y - 26
        for side, name, value, colors, on in (("left", "FLAP", st.p_flap, FLAP, flap_on),
                                             ("right", "WAIT", st.p_wait, WAIT, decided and not flap_on)):
            text = "–" if value is None else f"{100 * value:.0f}%"
            label = self.label_font.render(name, True, colors[1] if on else self.st["label"])
            number = self.value_font.render(text, True, colors[1] if on else self.st["label"])
            if side == "left":
                r1 = number.get_rect(bottomleft=(bar.x, y))
                r2 = label.get_rect(bottomleft=(r1.right + 14, y - 8))
            else:
                r1 = number.get_rect(bottomright=(bar.right, y))
                r2 = label.get_rect(bottomright=(r1.x - 14, y - 8))
            c.blit(number, r1)
            c.blit(label, r2)

        split = round(bar.width * p)
        # track
        track = pygame.Surface(bar.size, pygame.SRCALPHA)
        tcol = self.st["track"]
        pygame.draw.rect(track, tcol if len(tcol) == 4 else (*tcol, 255), track.get_rect(), border_radius=bar.height // 2)
        c.blit(track, bar)
        # segments in full colour (the labels above show which side was chosen)
        gap = 6
        for x0, x1, colors, on in ((0, split - gap // 2, FLAP, flap_on), (split + gap // 2, bar.width, WAIT, decided and not flap_on)):
            if x1 - x0 < 2:
                continue
            seg = pygame.Surface((x1 - x0, bar.height), pygame.SRCALPHA)
            for x in range(seg.get_width()):
                pygame.draw.line(seg, (*lerp(colors[0], colors[1], x / max(1, seg.get_width() - 1)), 255), (x, 0), (x, bar.height))
            seg.blit(rounded_mask(seg.get_size(), bar.height // 2), (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
            if on and colors is FLAP and st.flash > 0:      # brighten for a moment right after a flap
                white = pygame.Surface(seg.get_size(), pygame.SRCALPHA)
                white.fill((255, 255, 255, round(110 * st.flash)))
                white.blit(rounded_mask(seg.get_size(), bar.height // 2), (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
                seg.blit(white, (0, 0))
            c.blit(seg, (bar.x + x0, bar.y))
        # the 50% mark: two small ticks above and below the bar
        for y0 in (bar.y - 16, bar.bottom + 6):
            pygame.draw.rect(c, self.st["label"][:3], (bar.centerx - 2, y0, 4, 10), border_radius=2)
