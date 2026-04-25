#!/usr/bin/env python3
"""Compare current gas benchmarks against the committed baseline.

Exit codes:
  0 - all operations within threshold
  1 - one or more regressions detected
"""

import json
import sys
from pathlib import Path

BASELINE_FILE = Path("gas_baseline.json")
CURRENT_FILE = Path("gas_current.json")

# Maximum allowed percentage increase before flagging a regression
REGRESSION_PCT = 10.0


def load(path: Path) -> dict:
    with path.open() as f:
        return json.load(f)


def main() -> int:
    if not BASELINE_FILE.exists():
        print(f"ERROR: baseline file not found: {BASELINE_FILE}")
        return 1
    if not CURRENT_FILE.exists():
        print(f"ERROR: current results file not found: {CURRENT_FILE}")
        return 1

    baseline = load(BASELINE_FILE)
    current = load(CURRENT_FILE)

    regressions = []
    improvements = []

    for op, base_data in baseline.items():
        if op in ("updated_at",):
            continue
        if op not in current:
            print(f"  SKIP  {op}: not present in current results")
            continue

        base_gas = base_data.get("gas_used", 0)
        cur_gas = current[op].get("gas_used", 0)
        threshold = base_data.get("threshold", 0)

        if base_gas == 0:
            # No baseline measurement yet; just check against hard threshold
            if threshold > 0 and cur_gas > threshold:
                regressions.append(
                    f"  FAIL  {op}: gas={cur_gas} exceeds hard threshold={threshold}"
                )
            else:
                print(f"  OK    {op}: gas={cur_gas} (no baseline, threshold={threshold})")
            continue

        pct_change = (cur_gas - base_gas) / base_gas * 100

        if pct_change > REGRESSION_PCT:
            regressions.append(
                f"  FAIL  {op}: {base_gas} -> {cur_gas} (+{pct_change:.1f}%, threshold +{REGRESSION_PCT}%)"
            )
        elif pct_change < -1.0:
            improvements.append(
                f"  IMPROVED {op}: {base_gas} -> {cur_gas} ({pct_change:.1f}%)"
            )
        else:
            print(f"  OK    {op}: {base_gas} -> {cur_gas} ({pct_change:+.1f}%)")

    for msg in improvements:
        print(msg)

    if regressions:
        print("\nGAS REGRESSIONS DETECTED:")
        for msg in regressions:
            print(msg)
        return 1

    print("\nAll operations within acceptable thresholds.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
