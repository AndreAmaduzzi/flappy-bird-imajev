"""Score imajev's answers on the labelled frame bank (scripts/make_frame_bank.py) before playing any game.

    uv run python scripts/eval_perception.py --tag rot1            # every question in flappy/prompts.py
    uv run python scripts/eval_perception.py --tag rot1 --report   # re-print the table from saved answers

Saves raw answers to runs/perception/<tag>.jsonl and prints, per question: accuracy (most likely real option),
AUC for binary questions, how often unknown was on top, Brier score and ECE with the server's calibration and
with it undone (calibration is one temperature T, so softmax(z/T)**T renormalised recovers the raw softmax).
For the direct questions accuracy is also reported on `critical` frames (only one action keeps the bird alive).
"""
import argparse
import json
import statistics
from pathlib import Path

from PIL import Image

from flappy.imajev_client import DEFAULT_URL, ImajevClient, uncalibrate
from flappy.prompts import DIRECT, DIRECT_TWO_FRAMES, GAME_STATE, LABELS, PERCEPTION

TEMPERATURE = 1.3051569717552742   # calibration.json and calibration-rot4.json (every bucket); pass --temperature otherwise


def label_value(row, label):
    if label == "vs_gap_below":
        return row["vs_gap"] == "below"
    if label == "vs_gap_above":
        return row["vs_gap"] == "above"
    if label == "near_upper_pipe":   # bird centre within 47 px below the upper pipe's bottom end (or above it), pipe near
        return row["bird_y"] - row["gap_top"] < 47 and row["pipe_dist"] < 120
    if label == "near_lower_pipe":   # bird centre within 47 px above the lower pipe's top end (or below it), pipe near
        return row["gap_bottom"] - row["bird_y"] < 47 and row["pipe_dist"] < 120
    return row[label]


def collect(client, rows, bank, out_path, with_state, only=None):
    questions = {k: v for k, v in {**DIRECT, **PERCEPTION}.items() if not only or k in only}
    two = {"two_frames": {**DIRECT["plain"], "instructions": DIRECT_TWO_FRAMES}} if not only or "two_frames" in only else {}
    state = {"game": GAME_STATE} if with_state else {}
    with open(out_path, "w") as out:
        for i, row in enumerate(rows):
            frame = Image.open(bank / "frames" / f"{row['id']}.png")
            prev = Image.open(bank / "frames" / f"{row['id']}_prev.png")
            answers, latency = {}, {}
            ids = list(questions)
            for chunk in (ids[:5], ids[5:10], ids[10:]):  # at most 8 questions per request
                if chunk:
                    result = client.ask({k: questions[k] for k in chunk}, [frame], state)
                    answers.update(result.raw["answers"])
                    latency[",".join(chunk)] = result.server_ms
            if two:
                result = client.ask(two, [prev, frame], state)
                answers.update(result.raw["answers"])
                latency["two_frames"] = result.server_ms
            out.write(json.dumps({"id": row["id"], "answers": answers, "server_ms": latency}) + "\n")
            if i % 50 == 0:
                print(f"{i}/{len(rows)}", flush=True)


def full_distribution(raw):
    """Options + unknown as the server scored them (calibrated)."""
    u = raw["unknown_probability"]
    if raw["type"] == "noul":
        p_yes = raw["noul"] - 0.5 * u
        return {"yes": p_yes, "no": 1 - p_yes - u, "unknown": u}
    return {**{k: v * (1 - u) for k, v in raw["probabilities"].items()}, "unknown": u}


def auc(scores, positives):
    pos = [s for s, p in zip(scores, positives) if p]
    neg = [s for s, p in zip(scores, positives) if not p]
    if not pos or not neg:
        return float("nan")
    wins = sum((a > b) + 0.5 * (a == b) for a in pos for b in neg)
    return wins / (len(pos) * len(neg))


def ece(confidences, correct, bins=10):
    total, err = len(confidences), 0.0
    for b in range(bins):
        idx = [i for i, c in enumerate(confidences) if b / bins <= c < (b + 1) / bins or (b == bins - 1 and c == 1)]
        if idx:
            err += len(idx) / total * abs(statistics.fmean(confidences[i] for i in idx) - statistics.fmean(correct[i] for i in idx))
    return err


def report(rows, answers):
    by_id = {r["id"]: r for r in rows}
    print(f"{'question':18s} {'n':>4s} {'acc':>6s} {'acc_crit':>8s} {'AUC':>6s} {'unk_top':>7s} "
          f"{'brier':>6s} {'brier_raw':>9s} {'ece':>6s} {'ece_raw':>7s}")
    for qid, (label, mapping) in LABELS.items():
        acc, crit, unk, brier, brier_raw, conf, conf_raw, ok, pos_scores, positives = [], [], [], [], [], [], [], [], [], []
        for a in answers:
            if qid not in a["answers"]:
                continue
            row = by_id[a["id"]]
            truth = label_value(row, label)
            full = full_distribution(a["answers"][qid])
            raw = uncalibrate(full, TEMPERATURE)
            known = {k: v for k, v in full.items() if k != "unknown"}
            pred = max(known, key=known.get)
            hit = mapping[pred] == truth
            acc.append(hit)
            if label == "oracle" and row["critical"]:
                crit.append(hit)
            unk.append(max(full, key=full.get) == "unknown")
            target = {k: float(mapping[k] == truth) for k in known}
            brier.append(sum((full[k] - target[k]) ** 2 for k in known) + full["unknown"] ** 2)
            brier_raw.append(sum((raw[k] - target[k]) ** 2 for k in known) + raw["unknown"] ** 2)
            top = max(full, key=full.get)
            conf.append(full[top]); conf_raw.append(raw[max(raw, key=raw.get)])
            ok.append(top != "unknown" and mapping[top] == truth)
            if len(known) == 2:
                positive_option = next(k for k in known if mapping[k] in (True, "flap", "lower"))
                pos_scores.append(full[positive_option]); positives.append(mapping[positive_option] == truth)
        if not acc:
            continue
        pct = lambda xs: f"{100 * statistics.fmean(xs):5.1f}%" if xs else "    -"  # noqa: E731
        print(f"{qid:18s} {len(acc):4d} {pct(acc):>6s} {pct(crit):>8s} "
              f"{auc(pos_scores, positives) if pos_scores else float('nan'):6.3f} {pct(unk):>7s} "
              f"{statistics.fmean(brier):6.3f} {statistics.fmean(brier_raw):9.3f} "
              f"{ece(conf, ok):6.3f} {ece(conf_raw, ok):7.3f}")
    lat = {}
    for a in answers:
        for k, v in a["server_ms"].items():
            lat.setdefault(k, []).append(v)
    for k, v in lat.items():
        print(f"server_ms[{k[:40]}]: mean {statistics.fmean(v):.0f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bank", default="runs/frame_bank")
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--tag", required=True, help="name of this run (e.g. rot1, rot3)")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--with-state", action="store_true", help="also send the game description as state")
    ap.add_argument("--report", action="store_true", help="only print the table from a saved run")
    ap.add_argument("--questions", help="comma-separated subset of question ids (default: all)")
    a = ap.parse_args()
    bank = Path(a.bank)
    rows = [json.loads(line) for line in open(bank / "labels.jsonl")]
    if a.limit:
        rows = rows[:: max(1, len(rows) // a.limit)][: a.limit]
    out = Path("runs/perception") / f"{a.tag}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    if not a.report:
        client = ImajevClient(a.url)
        first = Image.open(bank / "frames" / f"{rows[0]['id']}.png")
        client.warmup(first, {"q": DIRECT["plain"]})
        collect(client, rows, bank, out, a.with_state, a.questions.split(",") if a.questions else None)
    answers = [json.loads(line) for line in open(out)]
    report(rows, answers)


if __name__ == "__main__":
    main()
