#!/usr/bin/env python3
"""Check gas benchmark results against gas_baseline.json thresholds.

Reads gas_baseline.json (committed baseline) and optionally a current
results JSON produced by run_gas_benchmarks.py.  When no current results
file is available the script checks the baseline values against their own
hard thresholds (useful for a first-run sanity check).

Exit codes:
  0 – all operations within threshold
  1 – one or more threshold violations or regressions detected

Usage:
  python3 scripts/check_performance_baseline.py
  python3 scripts/check_performance_baseline.py --current gas_current.json
  python3 scripts/check_performance_baseline.py --regression-pct 15
"""

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BASELINE_FILE = REPO_ROOT / "gas_baseline.json"
REGRESSION_PCT_DEFAULT = 10.0


def load(path: Path) -> dict:
    with path.open() as f:
        return json.load(f)


def check(baseline: dict, current: dict, regression_pct: float) -> list[str]:
    """Return a list of failure messages (empty = all pass)."""
    failures = []
    for op, base in baseline.items():
        if op == "updated_at":
            continue
        threshold = base.get("threshold", 0)
        base_gas = base.get("gas_used", 0)
        cur_gas = current.get(op, {}).get("gas_used", base_gas)

        # Hard threshold check
        if threshold > 0 and cur_gas > threshold:
            failures.append(
                f"THRESHOLD  {op}: gas={cur_gas} exceeds hard limit={threshold}"
            )
            continue

        # Regression check (only meaningful when baseline has a real measurement)
        if base_gas > 0:
            pct = (cur_gas - base_gas) / base_gas * 100
            if pct > regression_pct:
                failures.append(
                    f"REGRESSION {op}: {base_gas} → {cur_gas} "
                    f"(+{pct:.1f}% > allowed +{regression_pct}%)"
                )
            elif pct < -1.0:
                print(f"  IMPROVED  {op}: {base_gas} → {cur_gas} ({pct:.1f}%)")
            else:
                print(f"  OK        {op}: {cur_gas} ({pct:+.1f}% vs baseline)")
        else:
            print(f"  OK        {op}: gas={cur_gas} (no prior baseline)")

    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Check gas performance baseline")
    parser.add_argument(
        "--current",
        type=Path,
        default=None,
        help="Path to current benchmark results JSON (default: use baseline values)",
    )
    parser.add_argument(
        "--regression-pct",
        type=float,
        default=REGRESSION_PCT_DEFAULT,
        help=f"Max allowed %% increase before flagging regression (default: {REGRESSION_PCT_DEFAULT})",
    )
    args = parser.parse_args()

    if not BASELINE_FILE.exists():
        print(f"ERROR: baseline not found: {BASELINE_FILE}")
        return 1

    baseline = load(BASELINE_FILE)
    current = load(args.current) if args.current and args.current.exists() else {}

    failures = check(baseline, current, args.regression_pct)

    if failures:
        print("\nFAILURES:")
        for msg in failures:
            print(f"  {msg}")
        return 1

    print("\nAll operations within thresholds.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
