"""Summarize actual logic-analyzer edge measurements; never infer LED latency from JSON.

CSV columns: metric,start_us,end_us. Metrics: scan_to_led,third_failure_to_buzzer,
removal_to_buzzer. See docs/TEST_PLAN.md for physical trigger definitions.
"""

import argparse
import csv
import statistics

METRICS = ["scan_to_led", "third_failure_to_buzzer", "removal_to_buzzer"]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--measurements",
        required=True,
        help="CSV exported from actual instrument trials",
    )
    args = p.parse_args()
    values = {key: [] for key in METRICS}
    with open(args.measurements, newline="") as f:
        for row in csv.DictReader(f):
            if row["metric"] not in values:
                raise ValueError("Unknown metric")
            delta = (float(row["end_us"]) - float(row["start_us"])) / 1000
            if delta < 0:
                raise ValueError("End precedes start")
            values[row["metric"]].append(delta)
    missing = False
    for metric, results in values.items():
        if not results:
            print(metric + ": NOT MEASURED")
            missing = True
            continue
        p95 = sorted(results)[max(0, __import__("math").ceil(0.95 * len(results)) - 1)]
        print(
            f"{metric}: n={len(results)} median={statistics.median(results):.3f} ms p95={p95:.3f} ms"
        )
    if missing:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
