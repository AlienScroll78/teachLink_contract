#!/usr/bin/env python3
"""Generate structured regression reports (Markdown + JSON) from CI artifacts.

Reads:
  - gas_baseline.json        – committed baseline thresholds
  - gas_current.json         – current benchmark results (optional)
  - test-unit.txt            – unit test output (optional)
  - test-integration.txt     – integration test output (optional)
  - wasm_size.txt            – single line: "<bytes>" (optional)

Writes:
  - regression_report.json   – machine-readable report
  - regression_report.md     – human-readable Markdown summary

Usage:
  python3 scripts/generate_regression_report.py [--output-dir DIR]
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WASM_SIZE_LIMIT = 307_200   # 300 KB
WASM_SIZE_WARN  = 256_000   # 250 KB
REGRESSION_PCT  = 10.0


# ── helpers ──────────────────────────────────────────────────────────────────

def _load_json(path: Path) -> dict:
    return json.loads(path.read_text()) if path.exists() else {}


def _read(path: Path) -> str:
    return path.read_text() if path.exists() else ""


def _parse_test_log(text: str) -> dict:
    """Extract pass/fail counts from `cargo test` output."""
    passed = failed = 0
    for line in text.splitlines():
        m = re.search(r"test result:.*?(\d+) passed.*?(\d+) failed", line)
        if m:
            passed += int(m.group(1))
            failed += int(m.group(2))
    return {"passed": passed, "failed": failed, "ok": failed == 0}


def _check_gas(baseline: dict, current: dict) -> tuple[list, list]:
    """Return (ok_ops, regression_ops)."""
    ok, regressions = [], []
    for op, base in baseline.items():
        if op == "updated_at":
            continue
        threshold  = base.get("threshold", 0)
        base_gas   = base.get("gas_used", 0)
        cur_gas    = current.get(op, {}).get("gas_used", base_gas)
        pct_change = (cur_gas - base_gas) / base_gas * 100 if base_gas > 0 else 0.0

        entry = {"operation": op, "baseline": base_gas, "current": cur_gas,
                 "threshold": threshold, "pct_change": round(pct_change, 2)}

        if (threshold > 0 and cur_gas > threshold) or pct_change > REGRESSION_PCT:
            entry["status"] = "FAIL"
            regressions.append(entry)
        else:
            entry["status"] = "OK"
            ok.append(entry)
    return ok, regressions


def _wasm_status(size: int) -> str:
    if size > WASM_SIZE_LIMIT:
        return "FAIL"
    if size > WASM_SIZE_WARN:
        return "WARN"
    return "OK"


# ── report builders ───────────────────────────────────────────────────────────

def build_json_report(unit: dict, integ: dict, gas_ok: list,
                      gas_fail: list, wasm_size: int) -> dict:
    overall_ok = (
        unit.get("ok", True)
        and integ.get("ok", True)
        and not gas_fail
        and wasm_size <= WASM_SIZE_LIMIT
    )
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "overall": "PASS" if overall_ok else "FAIL",
        "tests": {"unit": unit, "integration": integ},
        "gas": {
            "regressions": gas_fail,
            "passed": gas_ok,
            "regression_count": len(gas_fail),
        },
        "wasm": {
            "size_bytes": wasm_size,
            "limit_bytes": WASM_SIZE_LIMIT,
            "status": _wasm_status(wasm_size),
        },
    }


def build_md_report(report: dict) -> str:
    ts   = report["generated_at"]
    ov   = report["overall"]
    unit = report["tests"]["unit"]
    intg = report["tests"]["integration"]
    gas  = report["gas"]
    wasm = report["wasm"]

    badge = "✅ PASS" if ov == "PASS" else "❌ FAIL"
    lines = [
        f"# Regression Report — {ts}",
        "",
        f"**Overall: {badge}**",
        "",
        "## Tests",
        f"| Suite | Passed | Failed | Status |",
        f"|-------|--------|--------|--------|",
        f"| Unit        | {unit.get('passed',0)} | {unit.get('failed',0)} | {'✅' if unit.get('ok',True) else '❌'} |",
        f"| Integration | {intg.get('passed',0)} | {intg.get('failed',0)} | {'✅' if intg.get('ok',True) else '❌'} |",
        "",
        "## WASM Binary Size",
        f"| Size | Limit | Status |",
        f"|------|-------|--------|",
        f"| {wasm['size_bytes']:,} B | {wasm['limit_bytes']:,} B | "
        f"{'✅' if wasm['status']=='OK' else ('⚠️' if wasm['status']=='WARN' else '❌')} |",
        "",
        "## Gas Performance",
    ]

    if gas["regressions"]:
        lines += [
            f"**{len(gas['regressions'])} regression(s) detected:**",
            "",
            "| Operation | Baseline | Current | Change | Status |",
            "|-----------|----------|---------|--------|--------|",
        ]
        for r in gas["regressions"]:
            lines.append(
                f"| {r['operation']} | {r['baseline']:,} | {r['current']:,} "
                f"| {r['pct_change']:+.1f}% | ❌ |"
            )
        lines.append("")

    if gas["passed"]:
        lines += [
            "<details><summary>Passing operations</summary>",
            "",
            "| Operation | Baseline | Current | Change |",
            "|-----------|----------|---------|--------|",
        ]
        for r in gas["passed"]:
            lines.append(
                f"| {r['operation']} | {r['baseline']:,} | {r['current']:,} "
                f"| {r['pct_change']:+.1f}% |"
            )
        lines += ["", "</details>"]

    if not gas["regressions"] and not gas["passed"]:
        lines.append("_No gas measurements available._")

    return "\n".join(lines) + "\n"


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Generate regression report")
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "testing" / "reports")
    parser.add_argument("--artifacts-dir", type=Path, default=REPO_ROOT / "ci-artifacts")
    args = parser.parse_args()

    art = args.artifacts_dir

    baseline = _load_json(REPO_ROOT / "gas_baseline.json")
    current  = _load_json(art / "gas-results" / "gas_current.json")

    unit_log  = _read(art / "test-logs" / "test-unit.txt")
    integ_log = _read(art / "test-logs" / "test-integration.txt")

    wasm_size_txt = _read(art / "performance-results" / "wasm_size.txt").strip()
    wasm_size = int(wasm_size_txt) if wasm_size_txt.isdigit() else 0

    unit  = _parse_test_log(unit_log)
    integ = _parse_test_log(integ_log)
    gas_ok, gas_fail = _check_gas(baseline, current)

    report = build_json_report(unit, integ, gas_ok, gas_fail, wasm_size)
    md     = build_md_report(report)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "regression_report.json").write_text(
        json.dumps(report, indent=2)
    )
    (args.output_dir / "regression_report.md").write_text(md)

    print(md)
    print(f"Reports written to {args.output_dir}")
    return 0 if report["overall"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
