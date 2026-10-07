"""Play one game and optionally record it.

    uv run python play.py --agent direct --seed 0 --difficulty easy --record out.mp4
    uv run python play.py --agent perceive_rule --realtime --record runs/rt.mp4
    uv run python play.py --agent oracle --difficulty hard

--record out.mp4 writes out_9x16.mp4 and out_1x1.mp4 (see --formats). Every decision goes to a JSONL log
(--log, default runs/play/<agent>_<difficulty>_s<seed>[_rt][_2f].jsonl).
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from flappy.agents import AGENTS, MODEL_AGENTS, describe, make_agent
from flappy.game import DIFFICULTIES, STEP_HZ, Game, make_difficulty
from flappy.imajev_client import DEFAULT_URL, ImajevClient
from flappy.loop import DecisionLog, LoopConfig, run_game
from flappy.render import THEMES, PanelState, make_renderer


def build_parser():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--agent", choices=AGENTS, default="direct")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--difficulty", choices=sorted(DIFFICULTIES), default="easy")
    add_difficulty_overrides(ap)
    ap.add_argument("--decide-every", type=int, default=4, help="physics steps between decisions (60 steps = 1 s)")
    ap.add_argument("--realtime", action="store_true", help="do not pause the game while the model thinks")
    ap.add_argument("--speed", type=float, default=1.0,
                    help="real time: game speed (0.25 = physics at a quarter of 60 steps per wall-clock second)")
    ap.add_argument("--two-frames", action="store_true", help="send the previous and the current frame")
    ap.add_argument("--max-seconds", type=float, default=120, help="game-time cap")
    ap.add_argument("--url", default=DEFAULT_URL, help="imajev server")
    ap.add_argument("--max-pixels", type=int, default=400_000)
    ap.add_argument("--variant", help="direct: question variant from flappy/prompts.py (plain, described)")
    ap.add_argument("--threshold", type=float, help="direct: flap when P(flap) >= threshold (default 0.5)")
    ap.add_argument("--flap-rate", type=float, help="random: per-decision flap probability (default: tuned)")
    ap.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                    help="agent option, e.g. --set cooldown=12 --set lower_threshold=0.5 (repeatable)")
    ap.add_argument("--record", help="MP4 path; writes <stem>_9x16.mp4 / <stem>_1x1.mp4")
    ap.add_argument("--formats", default="9x16,1x1", help="comma-separated: 9x16, 1x1, reel")
    ap.add_argument("--theme", choices=THEMES, default="flat",
                    help="game graphics; the model sees these frames (the benchmark used flat)")
    ap.add_argument("--reel-style", choices=("dark", "light", "immersive"), default="dark")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--log", help="decision JSONL path")
    return ap


def add_difficulty_overrides(ap):
    g = ap.add_argument_group("difficulty overrides (change one preset parameter)")
    for name, help_ in (("gap", "vertical opening, px"), ("pipe-speed", "px per step"), ("gravity", "px per step^2"),
                        ("flap-velocity", "vy after a flap (negative = up)"), ("max-gap-shift", "px between gaps"),
                        ("pipe-spacing", "px between pipes")):
        g.add_argument(f"--{name}", type=float, help=help_)


def difficulty_from(a, name=None):
    return make_difficulty(name or a.difficulty, gap=a.gap, pipe_speed=a.pipe_speed, gravity=a.gravity,
                           flap_velocity=a.flap_velocity, max_gap_shift=a.max_gap_shift, pipe_spacing=a.pipe_spacing)


def parse_sets(items) -> dict:
    out = {}
    for item in items:
        key, _, value = item.partition("=")
        for cast in (int, float):
            try:
                value = cast(value)
                break
            except ValueError:
                pass
        out[key] = value
    return out


def default_log(a) -> Path:
    tags = (f"_rt{a.speed:g}" if a.realtime else "") + ("_2f" if a.two_frames else "")
    return Path("runs/play") / f"{a.agent}_{a.difficulty}_s{a.seed}{tags}.jsonl"


def main(argv=None):
    a = build_parser().parse_args(argv)
    client = None
    if a.agent in MODEL_AGENTS:
        client = ImajevClient(a.url, max_pixels=a.max_pixels)
        try:
            print(f"server: {client.info()}", file=sys.stderr)
        except Exception as exc:  # noqa: BLE001
            sys.exit(f"cannot reach the imajev server at {a.url}: {exc}\nstart it with scripts/serve_imajev.sh")
    agent = make_agent(a.agent, client, two_frames=a.two_frames, flap_rate=a.flap_rate, variant=a.variant,
                       threshold=a.threshold, **parse_sets(a.set))
    game = Game(a.seed, difficulty_from(a))
    if client is not None:   # compile kernels before the clock starts
        from flappy.prompts import DIRECT
        client.warmup(make_renderer(a.theme).image(game), {"q": DIRECT["plain"]})
    config = LoopConfig(decide_every=a.decide_every, realtime=a.realtime, max_steps=round(a.max_seconds * STEP_HZ),
                        two_frames=a.two_frames, speed=a.speed, theme=a.theme)
    log_path = Path(a.log) if a.log else default_log(a)
    if log_path.exists():
        log_path.unlink()
    log = DecisionLog(log_path, agent=a.agent, difficulty=a.difficulty, seed=a.seed, realtime=a.realtime,
                      two_frames=a.two_frames, decide_every=a.decide_every)
    recorder = None
    if a.record:
        from flappy.record import Recorder
        label, detail = describe(agent)
        pace = "" if a.speed == 1 else f" at {a.speed:g}x speed"
        mode = f"real time{pace}: the bird keeps falling while the model thinks" if a.realtime else \
            "lockstep: the game waits for each decision"
        recorder = Recorder(a.record, PanelState(label, detail, f"{a.difficulty} · seed {a.seed} · {mode}"),
                            formats=a.formats.split(","), fps=a.fps, theme=a.theme, reel_style=a.reel_style)
    try:
        result = run_game(game, agent, config, log=log, on_step=recorder.on_step if recorder else None)
    finally:
        log.close()
        agent.close()
        paths = recorder.close() if recorder else {}
    print(json.dumps(asdict(result), indent=2, default=lambda v: round(v, 2)))
    print(f"decisions: {log_path}", file=sys.stderr)
    for fmt, path in paths.items():
        print(f"video {fmt}: {path}", file=sys.stderr)
    return result


if __name__ == "__main__":
    main()
