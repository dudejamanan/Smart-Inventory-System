"""Real measurement summaries: external edges, actual board FB, or slow-motion frames.

Never use simulator FB values as physical measurements. FB describes firmware code
latency only; external traces/video are needed for light and acoustic latency.
"""

import argparse
import csv
import json
import math
import statistics
from pathlib import Path
from common import connect, wait_for, encode

METRICS = ["scan_to_led", "third_failure_to_buzzer", "removal_to_buzzer"]


def summary(values):
    if not values or any(not math.isfinite(v) or v < 0 for v in values):
        raise ValueError("Need finite, nonnegative actual measurements")
    return statistics.median(values), sorted(values)[math.ceil(0.95 * len(values)) - 1]


def print_summary(name, values):
    median, p95 = summary(values)
    print(f"{name}: n={len(values)} median={median:.3f} ms p95={p95:.3f} ms")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--measurements", help="CSV metric,start_us,end_us from real instrument"
    )
    mode.add_argument("--feedback-log", help="JSONL captured from the real board")
    mode.add_argument(
        "--port", help="Read real FB while operator taps cards; app must be stopped"
    )
    mode.add_argument(
        "--slow-motion-frames", help="CSV metric,frames from actual video observations"
    )
    p.add_argument("--fps", type=float, default=240)
    p.add_argument("--trials", type=int, default=20)
    p.add_argument("--output", default="data/feedback.jsonl")
    args = p.parse_args()
    if args.measurements:
        values = {key: [] for key in METRICS}
        with open(args.measurements, newline="") as f:
            for r in csv.DictReader(f):
                if r["metric"] not in values:
                    raise ValueError("Unknown metric")
                values[r["metric"]].append(
                    (float(r["end_us"]) - float(r["start_us"])) / 1000
                )
        missing = False
        for key, results in values.items():
            if not results:
                print(key + ": NOT MEASURED")
                missing = True
            else:
                print_summary(key, results)
        if missing:
            raise SystemExit(1)
    elif args.slow_motion_frames:
        if args.fps <= 0:
            raise ValueError("FPS must be positive")
        values = {}
        with open(args.slow_motion_frames, newline="") as f:
            for r in csv.DictReader(f):
                values.setdefault(r["metric"], []).append(
                    float(r["frames"]) * 1000 / args.fps
                )
        if not values:
            raise ValueError("No video observations")
        for name, results in values.items():
            print_summary(name + " (video; frame quantization applies)", results)
    else:
        events = []
        if args.port:
            if args.trials < 1:
                raise ValueError("Trials must be positive")
            board = connect(args.port)
            try:
                for _ in range(args.trials):
                    print(
                        "Tap/remove a card. This benchmark returns PRM (red + two beeps), without adding a failure."
                    )
                    event = wait_for(board, lambda e: e["t"] == "SCAN", 30)
                    board.write(
                        encode({"t": "AUTH", "seq": event["seq"], "r": "PRM", "n": 0})
                    )
                    fb = wait_for(
                        board, lambda e: e["t"] == "FB" and e["seq"] == event["seq"]
                    )
                    events.append(fb)
                    print(fb)
            finally:
                board.write(encode({"t": "ACK"}))
                board.close()
            Path(args.output).parent.mkdir(parents=True, exist_ok=True)
            Path(args.output).write_text(
                "".join(json.dumps(e) + "\n" for e in events), encoding="utf-8"
            )
        else:
            events = [
                json.loads(line)
                for line in Path(args.feedback_log).read_text().splitlines()
                if line.strip()
            ]
        values = [float(e["ms"]) for e in events if e.get("t") == "FB"]
        print_summary(
            "SCAN to firmware feedback drive code (not optical/acoustic latency)",
            values,
        )


if __name__ == "__main__":
    main()
