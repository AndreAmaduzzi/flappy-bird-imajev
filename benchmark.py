"""Run N seeds per agent configuration and difficulty; write per-game rows and a comparison table.

    uv run python benchmark.py                                   # defaults below, one server on :8765
    uv run python benchmark.py --seeds 10 --difficulties easy,medium \
        --configs oracle,random,direct,perceive_rule,direct+2f,perceive_rule+rt \
        --urls http://127.0.0.1:8765,http://127.0.0.1:8766 --out runs/bench/main

A config is an agent name plus optional modifiers: +rt (real time), +rt0.25 (real time at a quarter of the game
speed), +2f (two frames). Benchmark seeds are
0..N-1 (prompt tuning uses 2000+, random-rate tuning 1000+). Outputs in --out:
  games.jsonl / games.csv   one row per game (re-running skips games already there: resumable)
  decisions/*.jsonl         every decision of every game
  summary.csv / summary.md  one row per (config, difficulty)
Each server URL gets one worker thread, so a server plays one game at a time (clean real-time latencies).
"""
from __future__ import annotations

import argparse
import csv
import json
import queue
import statistics
import threading
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from flappy.agents import MODEL_AGENTS, make_agent
from flappy.game import STEP_HZ, Game
from flappy.imajev_client import ImajevClient
from flappy.loop import DecisionLog, LoopConfig, run_game
from flappy.metrics import percentile
from flappy.prompts import DIRECT
from flappy.render import make_renderer
from play import add_difficulty_overrides, difficulty_from, parse_sets


def parse_config(spec):
    """'perceive_rule+rt0.5+2f' -> ('perceive_rule', realtime=True, two_frames=True, speed=0.5)."""
    agent, *mods = spec.split("+")
    realtime, two_frames, speed = False, False, 1.0
    for mod in mods:
        if mod == "2f":
            two_frames = True
        elif mod.startswith("rt"):
            realtime, speed = True, float(mod[2:] or 1.0)
        else:
            raise SystemExit(f"unknown modifier {mod!r} in {spec!r} (use +rt, +rt<speed>, +2f)")
    return agent, realtime, two_frames, speed


def job_key(job):
    return f"{job['config']}|{job['difficulty']}|{job['seed']}"


def play(job, client, a):
    agent_name, realtime, two_frames, speed = parse_config(job["config"])
    agent = make_agent(agent_name, client, two_frames=two_frames,
                       **(parse_sets(a.set) if agent_name in MODEL_AGENTS else {}))
    config = LoopConfig(decide_every=a.decide_every, realtime=realtime, two_frames=two_frames, speed=speed, theme=a.theme,
                        max_steps=round(a.max_seconds * STEP_HZ))
    name = f"{job['config'].replace('+', '_')}_{job['difficulty']}_s{job['seed']}.jsonl"
    path = Path(a.out) / "decisions" / name
    path.unlink(missing_ok=True)
    log = DecisionLog(path, config=job["config"], agent=agent_name, difficulty=job["difficulty"], seed=job["seed"],
                      realtime=realtime, two_frames=two_frames, speed=speed)
    try:
        result = run_game(Game(job["seed"], difficulty_from(a, job["difficulty"])), agent, config, log=log)
    finally:
        log.close()
    latencies = [json.loads(line)["latency_ms"] for line in open(path)]
    return {"config": job["config"], **asdict(result), "latencies_ms": latencies}


def worker(jobs, results, lock, client, a):
    while True:
        try:
            job = jobs.get_nowait()
        except queue.Empty:
            return
        row = play(job, client, a)
        with lock:
            results.append(row)
            with open(Path(a.out) / "games.jsonl", "a") as f:
                f.write(json.dumps(row) + "\n")
            print(f"[{len(results)}] {job_key(job):40s} pipes={row['pipes']:4d} frames={row['frames']:5d} "
                  f"death={row['death_cause']:11s} lat={row['latency_mean_ms']:.0f}ms", flush=True)


SUMMARY_COLUMNS = ["config", "difficulty", "games", "pipes_mean", "pipes_sd", "pipes_median", "pipes_max",
                   "frames_mean", "survived_pct", "decisions_mean", "latency_mean_ms", "latency_p95_ms",
                   "unknown_top_pct", "oracle_agreement_pct", "flap_pct", "stale_steps_mean", "deaths"]


def summarize(rows):
    groups = {}
    for r in rows:
        groups.setdefault((r["config"], r["difficulty"]), []).append(r)
    out = []
    for (config, difficulty), games in sorted(groups.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        pipes = [g["pipes"] for g in games]
        latencies = [x for g in games for x in g["latencies_ms"]]
        decisions = sum(g["decisions"] for g in games)
        weighted = lambda key: sum(g[key] * g["decisions"] for g in games) / decisions if decisions else 0.0  # noqa: E731
        deaths = Counter(g["death_cause"] for g in games)
        out.append({
            "config": config, "difficulty": difficulty, "games": len(games),
            "pipes_mean": statistics.fmean(pipes), "pipes_sd": statistics.stdev(pipes) if len(pipes) > 1 else 0.0,
            "pipes_median": statistics.median(pipes), "pipes_max": max(pipes),
            "frames_mean": statistics.fmean(g["frames"] for g in games),
            "survived_pct": 100.0 * deaths.get("timeout", 0) / len(games),
            "decisions_mean": decisions / len(games),
            "latency_mean_ms": statistics.fmean(latencies) if latencies else 0.0,
            "latency_p95_ms": percentile(latencies, 95),
            "unknown_top_pct": weighted("unknown_top_pct"), "oracle_agreement_pct": weighted("oracle_agreement_pct"),
            "flap_pct": weighted("flap_pct"), "stale_steps_mean": weighted("mean_stale_steps"),
            "deaths": " ".join(f"{k}:{v}" for k, v in deaths.most_common()),
        })
    return out


def fmt(value):
    return f"{value:.1f}" if isinstance(value, float) else str(value)


def write_tables(rows, out, a):
    with open(out / "games.csv", "w", newline="") as f:
        fields = [k for k in rows[0] if k != "latencies_ms"]
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: (r["difficulty"], r["config"], r["seed"])))
    summary = summarize(rows)
    with open(out / "summary.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=SUMMARY_COLUMNS)
        w.writeheader()
        w.writerows({k: (round(v, 3) if isinstance(v, float) else v) for k, v in s.items()} for s in summary)
    md_cols = ["config", "difficulty", "games", "pipes_mean", "pipes_sd", "pipes_median", "pipes_max", "frames_mean",
               "decisions_mean", "latency_mean_ms", "latency_p95_ms", "unknown_top_pct", "oracle_agreement_pct",
               "deaths"]
    lines = [f"# Benchmark: {len(rows)} games, decide every {a.decide_every} steps, "
             f"cap {a.max_seconds:.0f} s game time\n",
             "| " + " | ".join(md_cols) + " |", "|" + "---|" * len(md_cols)]
    lines += ["| " + " | ".join(fmt(s[c]) for c in md_cols) + " |" for s in summary]
    lines.append("\nLatency: client-side time per decision (ms). unknown_top_pct: decisions where unknown was the most "
                 "likely outcome (the agent then waits). oracle_agreement_pct: decisions equal to the oracle's action "
                 "in the same state. deaths: cause counts (timeout = survived the cap).")
    (out / "summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--configs", default="oracle,random,direct,perceive_rule")
    ap.add_argument("--difficulties", default="easy,medium,hard")
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--decide-every", type=int, default=4)
    ap.add_argument("--max-seconds", type=float, default=120)
    ap.add_argument("--urls", default="http://127.0.0.1:8765", help="comma-separated imajev servers (one game each at a time)")
    ap.add_argument("--out", default="runs/bench/latest")
    add_difficulty_overrides(ap)
    ap.add_argument("--theme", default="flat", help="game graphics the model sees (flat, day, sunset, night)")
    ap.add_argument("--set", action="append", default=[], metavar="KEY=VALUE", help="option for the model agents")
    ap.add_argument("--report", action="store_true", help="only rebuild the tables from games.jsonl")
    a = ap.parse_args()
    out = Path(a.out)
    (out / "decisions").mkdir(parents=True, exist_ok=True)
    games_path = out / "games.jsonl"
    done = [json.loads(line) for line in open(games_path)] if games_path.exists() else []
    if not a.report:
        configs = a.configs.split(",")
        for spec in configs:
            parse_config(spec)
        jobs = [{"config": c, "difficulty": d, "seed": s} for d in a.difficulties.split(",")
                for c in configs for s in range(a.seeds)]
        finished = {job_key(r) for r in done}
        todo = [j for j in jobs if job_key(j) not in finished]
        print(f"{len(jobs)} games, {len(jobs) - len(todo)} already done, {len(todo)} to play", flush=True)
        results, lock = list(done), threading.Lock()
        local = queue.Queue()
        model = queue.Queue()
        for job in todo:
            (model if parse_config(job["config"])[0] in MODEL_AGENTS else local).put(job)
        # Baselines first, on their own: the oracle's search is CPU-heavy and would inflate model latencies (GIL).
        worker(local, results, lock, None, a)
        threads = []
        if not model.empty():
            for url in a.urls.split(","):
                client = ImajevClient(url)
                client.warmup(make_renderer(a.theme).image(Game(0)), {"q": DIRECT["plain"]})
                threads.append(threading.Thread(target=worker, args=(model, results, lock, client, a)))
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        done = results
    if done:
        write_tables(done, out, a)


if __name__ == "__main__":
    main()
