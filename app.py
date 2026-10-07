"""Can Imajev play Flappy Bird? A desktop app: pick the player and the game settings, then watch it play live.

    uv run python app.py                      # imajev server at http://127.0.0.1:8765
    uv run python app.py --url http://gpu-box:8765

Players: Imajev (perceive + rule, or the direct question), the oracle, random, or yourself (SPACE).
Without a running imajev server the oracle, random and human players still work.

Menu: UP/DOWN select · LEFT/RIGHT change · ENTER start (or use the mouse)
Game: SPACE flap (you) · P pause · R restart · N next seed · ESC menu
"""
from __future__ import annotations

import argparse
import random
import threading
import time
from pathlib import Path

from flappy.render import GameRenderer  # noqa: F401  (selects the SDL driver before pygame starts)
import pygame  # noqa: E402

from flappy.art import FONTS, ThemedRenderer, lerp  # noqa: E402
from flappy.game import DIFFICULTIES, HEIGHT, STEP_HZ, WIDTH  # noqa: E402
from flappy.imajev_client import DEFAULT_URL, ImajevClient  # noqa: E402
from flappy.live import HUMAN, LiveGame, Settings  # noqa: E402

WINDOW = (1000, 880)
VIEW_SCALE = 1.6                       # 461 x 819 game view
BG = ((12, 16, 24), (24, 30, 44))
CARD, CARD_HI = (30, 37, 52), (44, 54, 76)
TEXT, MUTED, ACCENT = (240, 243, 248), (140, 150, 168), (255, 210, 63)
GOOD, BAD = (96, 214, 128), (255, 104, 104)
FLAP_C = ((255, 170, 64), (255, 122, 26))
WAIT_C = ((92, 172, 255), (46, 120, 246))

PLAYERS = [("perceive_rule", "Imajev · perceive + rule"), ("direct", "Imajev · direct question"),
           ("oracle", "Oracle (reads the game state)"), ("random", "Random"), (HUMAN, "You (SPACE to flap)")]
THEMES = [("flat", "Flat (plays best)"), ("day", "Day"), ("day_clean", "Day, plain background"),
          ("sunset", "Sunset"), ("night", "Night")]
RT_SPEEDS = [1.0, 0.5, 0.25, 0.125]


def font(name, size):
    return pygame.font.Font(str(Path(FONTS) / name), size)


class Row:
    """One menu setting: a label, how to read/write it on Settings, and its choices."""

    def __init__(self, label, get, step, show, enabled=lambda s: True, hint=""):
        self.label, self.get, self.step, self.show, self.enabled, self.hint = label, get, step, show, enabled, hint


def cycle(options, current, delta):
    i = options.index(current) if current in options else 0
    return options[(i + delta) % len(options)]


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def preset(s, field):
    return getattr(DIFFICULTIES[s.difficulty], field)


def build_rows():
    def set_(field, fn):
        def step(s, d):
            setattr(s, field, fn(s, d))
        return step

    def numeric(field, unit, delta, lo, hi, fmt):
        def step(s, d):
            value = getattr(s, field)
            value = preset(s, field) if value is None else value
            setattr(s, field, round(clamp(value + d * delta, lo, hi), 4))

        def show(s):
            value = getattr(s, field)
            return f"{fmt(preset(s, field) if value is None else value)}{unit}" + ("" if value is not None else "  (preset)")
        return step, show

    def difficulty_step(s, d):
        s.difficulty = cycle(list(DIFFICULTIES), s.difficulty, d)
        s.gap = s.pipe_speed = s.gravity = None          # back to the preset's values

    model = lambda s: s.player not in (HUMAN,)           # noqa: E731
    gap_step, gap_show = numeric("gap", " px", 10, 100, 260, lambda v: f"{v:.0f}")
    speed_step, speed_show = numeric("pipe_speed", " px/step", 0.25, 1.0, 4.0, lambda v: f"{v:.2f}")
    grav_step, grav_show = numeric("gravity", " px/step²", 0.025, 0.15, 0.5, lambda v: f"{v:.3f}")
    return [
        Row("Player", lambda s: s.player, set_("player", lambda s, d: cycle([p for p, _ in PLAYERS], s.player, d)),
            lambda s: dict(PLAYERS)[s.player]),
        Row("Difficulty", lambda s: s.difficulty, difficulty_step, lambda s: s.difficulty.capitalize(),
            hint="resets gap, speed and gravity"),
        Row("Gap", None, gap_step, gap_show, hint="vertical opening between the pipes"),
        Row("Pipe speed", None, speed_step, speed_show),
        Row("Gravity", None, grav_step, grav_show),
        Row("Graphics", lambda s: s.theme, set_("theme", lambda s, d: cycle([t for t, _ in THEMES], s.theme, d)),
            lambda s: dict(THEMES)[s.theme], hint="Imajev sees exactly this game window"),
        Row("Timing", lambda s: s.realtime, set_("realtime", lambda s, d: not s.realtime),
            lambda s: "Real time (the bird keeps falling)" if s.realtime else "Lockstep (the game waits)", model),
        Row("Real-time speed", lambda s: s.speed, set_("speed", lambda s, d: cycle(RT_SPEEDS, s.speed, -d)),
            lambda s: f"{s.speed:g}x", lambda s: model(s) and s.realtime),
        Row("Decide every", lambda s: s.decide_every,
            set_("decide_every", lambda s, d: clamp(s.decide_every + d, 1, 12)),
            lambda s: f"{s.decide_every} steps ({STEP_HZ / s.decide_every:.0f} decisions / game second)", model),
        Row("Seed", lambda s: s.seed, set_("seed", lambda s, d: clamp(s.seed + d, 0, 9999)), lambda s: str(s.seed),
            hint="same seed = same pipes"),
    ]


class ServerStatus:
    """Polls the imajev server in the background so the menu never blocks."""

    def __init__(self, url):
        self.url, self.client = url, ImajevClient(url, timeout=120)
        self.online, self.detail, self.checked = None, "checking...", 0.0
        self.lock = threading.Lock()

    def poll(self, every=5.0):
        if time.time() - self.checked < every:
            return
        self.checked = time.time()
        threading.Thread(target=self._check, daemon=True).start()

    def _check(self):
        try:
            probe = ImajevClient(self.url, timeout=2)
            info = probe.info()
            online, detail = True, f"{info.get('model', 'imajev')} · {info.get('backend', '?')}"
        except Exception:  # noqa: BLE001
            online, detail = False, "offline"
        with self.lock:
            self.online, self.detail = online, detail


class App:
    def __init__(self, url=DEFAULT_URL, settings: Settings | None = None):
        pygame.init()
        pygame.display.set_caption("Can Imajev play Flappy Bird?")
        self.screen = pygame.display.set_mode(WINDOW)
        self.clock = pygame.time.Clock()
        self.f_title = font("Poppins-Bold.ttf", 40)
        self.f_big = font("Poppins-Bold.ttf", 44)
        self.f_mid = font("Poppins-SemiBold.ttf", 24)
        self.f_small = font("Poppins-SemiBold.ttf", 18)
        self.f_label = font("Poppins-SemiBold.ttf", 15)
        self.bg = pygame.Surface(WINDOW)
        for y in range(WINDOW[1]):
            pygame.draw.line(self.bg, lerp(*BG, y / (WINDOW[1] - 1)), (0, y), (WINDOW[0], y))
        self.server = ServerStatus(url)
        self.settings = settings or Settings()
        self.rows = build_rows()
        self.selected = 0
        self.mode = "menu"
        self.live: LiveGame | None = None
        self.view = None
        self.best = {}
        self.message = ""
        self.hit = []          # clickable areas: (rect, action)
        self.running = True

    # ------------------------------------------------------------------ main loop
    def run(self):
        while self.running:
            for event in pygame.event.get():
                self.handle(event)
            self.update()
            self.draw()
            pygame.display.flip()
            self.clock.tick(STEP_HZ)
        if self.live:
            self.live.close()
        pygame.quit()

    def update(self):
        self.server.poll()
        if self.mode == "play" and self.live:
            self.live.tick()
            key = (self.settings.player, self.settings.difficulty)
            self.best[key] = max(self.best.get(key, 0), self.live.game.score)

    # ------------------------------------------------------------------ input
    def handle(self, event):
        if event.type == pygame.QUIT:
            self.running = False
        elif event.type == pygame.KEYDOWN:
            (self._menu_key if self.mode == "menu" else self._play_key)(event.key)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for rect, action in self.hit:
                if rect.collidepoint(event.pos):
                    action()
                    break
            else:
                if self.mode == "play" and self.settings.player == HUMAN and self.live:
                    self.live.flap()

    def _menu_key(self, key):
        if key in (pygame.K_UP, pygame.K_w):
            self.selected = (self.selected - 1) % len(self.rows)
        elif key in (pygame.K_DOWN, pygame.K_s):
            self.selected = (self.selected + 1) % len(self.rows)
        elif key in (pygame.K_LEFT, pygame.K_a):
            self._change(self.selected, -1)
        elif key in (pygame.K_RIGHT, pygame.K_d):
            self._change(self.selected, +1)
        elif key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
            self.start()
        elif key == pygame.K_ESCAPE:
            self.running = False

    def _play_key(self, key):
        live = self.live
        if key == pygame.K_SPACE and self.settings.player == HUMAN:
            live.flap()
        elif key == pygame.K_p:
            live.paused = not live.paused
        elif key == pygame.K_r:
            self.start()
        elif key == pygame.K_n:
            self.settings.seed = (self.settings.seed + 1) % 10000
            self.start()
        elif key in (pygame.K_ESCAPE, pygame.K_m):
            self.to_menu()

    def _change(self, index, delta):
        row = self.rows[index]
        if row.enabled(self.settings):
            row.step(self.settings, delta)

    # ------------------------------------------------------------------ screens
    def start(self):
        s = self.settings
        if s.uses_model and self.server.online is False:
            self.message = f"The imajev server at {self.server.url} is offline: start it (see README), or pick another player."
            return
        if self.live:
            self.live.close()
        self.message = ""
        self.live = LiveGame(s, self.server.client if s.uses_model else None)
        if s.theme == "flat":
            self.view = ("flat", GameRenderer(show_score=True))
        else:
            self.view = ("art", ThemedRenderer(s.theme, scale=VIEW_SCALE, show_score=True))
        self.mode = "play"

    def to_menu(self):
        if self.live:
            self.live.close()
        self.live, self.mode = None, "menu"

    def draw(self):
        self.screen.blit(self.bg, (0, 0))
        self.hit = []
        (self._draw_menu if self.mode == "menu" else self._draw_play)()

    def _text(self, f, text, color, pos, anchor="topleft"):
        image = f.render(text, True, color)
        rect = image.get_rect(**{anchor: pos})
        self.screen.blit(image, rect)
        return rect

    def _title(self, x, y, anchor="midtop"):
        r = self._text(self.f_title, "Can Imajev play", TEXT, (x, y), anchor)
        return self._text(self.f_title, "Flappy Bird?", ACCENT, (x if anchor == "midtop" else r.x, r.bottom - 6),
                          anchor if anchor == "midtop" else "topleft")

    def _button(self, rect, label, action, primary=False):
        pygame.draw.rect(self.screen, ACCENT if primary else CARD_HI, rect, border_radius=rect.height // 2)
        self._text(self.f_mid, label, BG[0] if primary else TEXT, rect.center, "center")
        self.hit.append((rect, action))

    def _draw_menu(self):
        s = self.settings
        bottom = self._title(WINDOW[0] // 2, 26).bottom
        y = bottom + 26
        for i, row in enumerate(self.rows):
            rect = pygame.Rect(120, y, WINDOW[0] - 240, 44)
            enabled = row.enabled(s)
            if i == self.selected:
                pygame.draw.rect(self.screen, CARD_HI, rect, border_radius=14)
            else:
                pygame.draw.rect(self.screen, CARD, rect, border_radius=14)
            color = TEXT if enabled else MUTED
            self._text(self.f_mid, row.label, color, (rect.x + 22, rect.centery), "midleft")
            value = row.show(s) if enabled else "-"
            self._text(self.f_small, value, ACCENT if (enabled and i == self.selected) else color,
                       (rect.right - 64, rect.centery), "midright")
            left, right = pygame.Rect(rect.right - 56, rect.y + 6, 24, 32), pygame.Rect(rect.right - 30, rect.y + 6, 24, 32)
            for arrow, d in ((left, -1), (right, 1)):
                pts = ([(arrow.right - 6, arrow.y + 8), (arrow.x + 6, arrow.centery), (arrow.right - 6, arrow.bottom - 8)] if d < 0
                       else [(arrow.x + 6, arrow.y + 8), (arrow.right - 6, arrow.centery), (arrow.x + 6, arrow.bottom - 8)])
                pygame.draw.polygon(self.screen, color, pts)
                self.hit.append((arrow, lambda i=i, d=d: (setattr(self, "selected", i), self._change(i, d))))
            self.hit.append((rect, lambda i=i: setattr(self, "selected", i)))
            y += 50
        row = self.rows[self.selected]
        self._text(self.f_label, row.hint, MUTED, (WINDOW[0] // 2, y + 2), "midtop")

        online = self.server.online
        dot = GOOD if online else BAD if online is False else MUTED
        status = (f"imajev server {self.server.url}: {self.server.detail}" if online is not None
                  else f"imajev server {self.server.url}: checking...")
        sy = y + 30
        pygame.draw.circle(self.screen, dot, (WINDOW[0] // 2 - self.f_small.size(status)[0] // 2 - 14, sy + 12), 6)
        self._text(self.f_small, status, MUTED, (WINDOW[0] // 2, sy), "midtop")
        if online is False:
            self._text(self.f_label, "Oracle, Random and You work without it.", MUTED, (WINDOW[0] // 2, sy + 26), "midtop")
        self._button(pygame.Rect(WINDOW[0] // 2 - 120, sy + 54, 240, 52), "Start", self.start, primary=True)
        if self.message:
            self._text(self.f_label, self.message, BAD, (WINDOW[0] // 2, sy + 114), "midtop")
        self._text(self.f_label, "UP/DOWN select · LEFT/RIGHT change · ENTER start · ESC quit", MUTED,
                   (WINDOW[0] // 2, WINDOW[1] - 18), "midbottom")

    def _draw_play(self):
        live, s = self.live, self.settings
        kind, renderer = self.view
        surface = renderer.draw(live.game)
        view = pygame.Rect(32, 30, round(WIDTH * VIEW_SCALE), round(HEIGHT * VIEW_SCALE))
        if kind == "flat":
            surface = pygame.transform.scale(surface, view.size)
        card = pygame.Surface(view.size, pygame.SRCALPHA)
        card.blit(surface, (0, 0))
        mask = pygame.Surface(view.size, pygame.SRCALPHA)
        pygame.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(), border_radius=22)
        card.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
        self.screen.blit(card, view)
        pygame.draw.rect(self.screen, CARD_HI, view.inflate(4, 4), 2, border_radius=24)
        if live.over or live.paused:
            self._overlay(view)

        x, w = view.right + 40, WINDOW[0] - view.right - 72
        y = self._title(x, 26, anchor="topleft").bottom + 18
        name = dict(PLAYERS)[s.player]
        self._text(self.f_mid, name, TEXT, (x, y))
        y += 34
        if s.player == HUMAN:
            timing = "press SPACE (or click) to flap"
        elif s.realtime:
            timing = f"real time · {s.speed:g}x speed"
        else:
            timing = "lockstep (the game waits)"
        self._text(self.f_label, f"{s.difficulty} · seed {s.seed} · {timing}", MUTED, (x, y))
        y += 40

        if s.player != HUMAN:
            y = self._bar(pygame.Rect(x, y + 42, w, 30), live.last) + 20
            status = ""
            if live.warming_up:
                status = "warming up Imajev" + "." * (1 + int(time.time() * 3) % 3)
            elif live.thinking and not s.realtime:
                status = "Imajev is thinking" + "." * (1 + int(time.time() * 3) % 3)
            self._text(self.f_small, status, ACCENT, (x, y))
            y += 34
        tiles = [("PIPES", str(live.game.score)), ("BEST", str(self.best.get((s.player, s.difficulty), 0)))]
        if s.uses_model:
            lat = f"{live.latencies[-1]:.0f} ms" if live.latencies else "-"
            unk = f"{100 * live.last.unknown:.0f}%" if live.last and live.last.unknown is not None else "-"
            tiles += [("LATENCY", lat), ("UNKNOWN", unk)]
        tw = (w - 12 * (len(tiles) - 1)) // len(tiles)
        for i, (label, value) in enumerate(tiles):
            r = pygame.Rect(x + i * (tw + 12), y, tw, 84)
            pygame.draw.rect(self.screen, CARD, r, border_radius=14)
            self._text(self.f_label, label, MUTED, (r.centerx, r.y + 10), "midtop")
            f = self.f_big if len(value) <= 4 else self.f_mid
            self._text(f, value, TEXT, (r.centerx, r.bottom - 8), "midbottom")
        y += 104
        if live.last is not None:
            for line in live.last.info.get("panel_lines", ()):
                self._text(self.f_label, line.strip(), MUTED, (x, y))
                y += 22
        if live.error:
            for i, chunk in enumerate([live.error[j:j + 48] for j in range(0, min(len(live.error), 192), 48)]):
                self._text(self.f_label, chunk, BAD, (x, y + 10 + i * 20))
        keys = ("SPACE flap · " if s.player == HUMAN else "") + "P pause · R restart · N next seed · ESC menu"
        self._text(self.f_label, keys, MUTED, (x, WINDOW[1] - 24), "bottomleft")

    def _bar(self, bar, last):
        p_flap = last.p_flap if last and last.p_flap is not None else None
        p_wait = last.p_wait if last and last.p_wait is not None else None
        flap_on = last is not None and last.action == "flap"
        for side, name, value, colors, on in (("left", "FLAP", p_flap, FLAP_C, flap_on),
                                             ("right", "WAIT", p_wait, WAIT_C, last is not None and not flap_on)):
            text = "-" if value is None else f"{100 * value:.0f}%"
            color = colors[1] if on else MUTED
            num = self.f_big.render(text, True, color)
            lab = self.f_small.render(name, True, color)
            if side == "left":
                rn = num.get_rect(bottomleft=(bar.x, bar.y - 6))
                rl = lab.get_rect(bottomleft=(rn.right + 8, rn.bottom - 8))
            else:
                rn = num.get_rect(bottomright=(bar.right, bar.y - 6))
                rl = lab.get_rect(bottomright=(rn.x - 8, rn.bottom - 8))
            self.screen.blit(num, rn)
            self.screen.blit(lab, rl)
        pygame.draw.rect(self.screen, CARD, bar, border_radius=bar.height // 2)
        if p_flap is not None:
            split = round(bar.width * p_flap)
            for x0, x1, colors in ((0, split - 3, FLAP_C), (split + 3, bar.width, WAIT_C)):
                if x1 - x0 >= bar.height // 2:
                    seg = pygame.Rect(bar.x + x0, bar.y, x1 - x0, bar.height)
                    pygame.draw.rect(self.screen, colors[1], seg, border_radius=bar.height // 2)
        pygame.draw.rect(self.screen, MUTED, (bar.centerx - 1, bar.bottom + 5, 3, 8), border_radius=1)
        if last is not None and last.abstained:
            self._text(self.f_label, "unknown was most likely -> wait", MUTED, (bar.x, bar.bottom + 14))
            return bar.bottom + 34
        return bar.bottom + 14

    def _overlay(self, view):
        live = self.live
        shade = pygame.Surface(view.size, pygame.SRCALPHA)
        shade.fill((8, 10, 18, 150))
        self.screen.blit(shade, view)
        cx, cy = view.centerx, view.centery - 60
        if live.paused and not live.over:
            self._text(self.f_big, "Paused", TEXT, (cx, cy), "center")
            self._text(self.f_small, "P to resume", MUTED, (cx, cy + 46), "center")
            return
        title = "Error" if live.error else "Game over"
        self._text(self.f_big, title, BAD if live.error else TEXT, (cx, cy), "center")
        if not live.error:
            cause = (live.game.death_cause or "").replace("_", " ")
            self._text(self.f_mid, f"{live.game.score} pipes · hit the {cause}", TEXT, (cx, cy + 48), "center")
        self._button(pygame.Rect(cx - 150, cy + 92, 140, 46), "Restart", self.start, primary=True)
        self._button(pygame.Rect(cx + 10, cy + 92, 140, 46), "Menu", self.to_menu)
        self._text(self.f_label, "R restart · N next seed · ESC menu", MUTED, (cx, cy + 156), "center")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default=DEFAULT_URL, help="imajev server")
    ap.add_argument("--seed", type=int, help="first seed (default: random)")
    a = ap.parse_args(argv)
    settings = Settings(seed=a.seed if a.seed is not None else random.randrange(1000))
    App(a.url, settings).run()


if __name__ == "__main__":
    main()
