"""Record a game to MP4 (H.264 via the ffmpeg binary) in one or more layouts (9:16, 1:1, reel).

The loop calls `Recorder.on_step` after every physics step. The recorder renders the game view on the calling thread
(cheap) and hands composition + encoding to a worker thread, so --realtime pacing is not disturbed. Video plays at
game speed: `fps` frames per second of game time (lockstep pauses never show up in the video). When the bird dies
the last frame is held for `death_hold_s`, highlighted, with the model's last probabilities.
"""
from __future__ import annotations

import queue
import shutil
import subprocess
import threading
from pathlib import Path


from .agents.base import FLAP, Decision
from .game import STEP_HZ, Game
from .render import Layout, PanelState


def output_paths(path: str | Path, formats) -> dict[str, Path]:
    """out.mp4 + ["9x16", "1x1"] -> {"9x16": out_9x16.mp4, "1x1": out_1x1.mp4}."""
    path = Path(path)
    return {f: path.with_name(f"{path.stem}_{f}{path.suffix or '.mp4'}") for f in formats}


class Recorder:
    def __init__(self, path: str | Path, panel: PanelState, formats=("9x16", "1x1"), fps: int = 30,
                 death_hold_s: float = 2.0, crf: int = 18, theme: str = "flat", reel_style: str = "dark"):
        if STEP_HZ % fps:
            raise ValueError(f"fps must divide {STEP_HZ}")
        if shutil.which("ffmpeg") is None:
            raise RuntimeError("ffmpeg not found on PATH")
        self.every = STEP_HZ // fps
        self.fps, self.death_hold_s = fps, death_hold_s
        self.panel = panel
        self.paths = output_paths(path, formats)
        self.queue: queue.Queue = queue.Queue(maxsize=240)
        self.layouts, self.procs = [], []
        for fmt, out in self.paths.items():
            out.parent.mkdir(parents=True, exist_ok=True)
            if fmt == "reel":
                from .reel import ReelLayout
                layout = ReelLayout(reel_style, "day" if theme == "flat" else theme)
            else:
                layout = Layout(fmt, theme)
            w, h = layout.size
            cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}",
                   "-r", str(fps), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", str(crf),
                   "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)]
            self.layouts.append(layout)
            self.procs.append(subprocess.Popen(cmd, stdin=subprocess.PIPE))
        self.flash_until = -1
        self.worker = threading.Thread(target=self._work, daemon=True)
        self.worker.start()

    # ------------------------------------------------------------------ loop hook
    def on_step(self, game: Game, last: Decision | None, new: Decision | None):
        if new is not None and new.action == FLAP:
            self.flash_until = game.step_count + 8
        if game.step_count % self.every and game.alive:
            return
        st = self._state(game, last)
        payloads = [layout.capture(game) for layout in self.layouts]
        if not game.alive:
            hold = round(self.death_hold_s * self.fps)
            for i in range(hold):
                self.queue.put((payloads, PanelState(**{**st.__dict__, "dead": True, "death_cause": game.death_cause,
                                                        "death_t": i / max(1, hold - 1)})))
        else:
            self.queue.put((payloads, st))

    def _state(self, game, last):
        st = PanelState(**self.panel.__dict__)
        st.pipes, st.game_time_s = game.score, game.step_count / STEP_HZ
        st.flash = max(0.0, (self.flash_until - game.step_count) / 8)
        if last is not None:
            st.p_flap, st.p_wait, st.unknown = last.p_flap, last.p_wait, last.unknown
            st.action, st.abstained, st.latency_ms = last.action, last.abstained, last.latency_ms
            st.lines = tuple(last.info.get("panel_lines", ()))
        return st

    # ------------------------------------------------------------------ encoding
    def _work(self):
        while True:
            item = self.queue.get()
            if item is None:
                break
            payloads, st = item
            for layout, proc, payload in zip(self.layouts, self.procs, payloads):
                proc.stdin.write(layout.compose(payload, st))

    def close(self) -> dict[str, Path]:
        self.queue.put(None)
        self.worker.join()
        for proc in self.procs:
            proc.stdin.close()
            if proc.wait() != 0:
                raise RuntimeError(f"ffmpeg exited with {proc.returncode}")
        return self.paths
