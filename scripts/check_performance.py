#!/usr/bin/env python3
"""
Compare gas benchmark output against gas_baseline.json thresholds.
Reads gas_output.txt and Soroban test_snapshots.
Writes reports/performance_results.json. Exits 1 on regression.
"""
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).parent.parent

def load_json(p):
    return json.loads(p.read_text()) if p.exists() else {}

baseline = load_json(ROOT / "gas_baseline.json")

# Parse gas_output.txt for lines like: op_name: instructions=123456
measured = {}
gas_txt = ROOT / "gas_output.txt"
if gas_txt.exists():
    for line in gas_txt.read_text().splitlines():
        m = re.search(r"(\w+):\s+instructions=(\d+)(?:\s+memory=(\d+))?", line, re.I)
        if m:
            measured[m.group(1)] = {"instructions": int(m.group(2)), "memory": int(m.group(3) or 0)}

# Supplement from Soroban test_snapshots (gas_bench_*.json)
for snap in (ROOT / "contracts/teachlink/test_snapshots").glob("gas_bench_*.json"):
    op = snap.stem.replace("gas_bench_", "")
    if op in measured:
        continue
    try:
        cost = json.loads(snap.read_text())["results"][0]["result"]["Ok"]["cost"]
        cpu = int(cost.get("cpu_insns", 0))
        if cpu:
            measured[op] = {"instructions": cpu, "memory": int(cost.get("mem_bytes", 0))}
    except Exception:
        pass

MAX_PCT = 10  # fail if >10% over baseline
results, regressions, warnings = [], [], []

for op, cur in measured.items():
    base = baseline.get(op, {})
    base_insns = base.get("gas_used", 0)
    threshold  = base.get("threshold", 0)
    cur_insns  = cur["instructions"]

    pct = ((cur_insns - base_insns) / base_insns * 100) if base_insns else None
    status = "OK"

    if threshold and cur_insns > threshold:
        status = "FAIL"
        regressions.append(f"{op}: {cur_insns} > threshold {threshold}")
    elif pct is not None and pct > MAX_PCT:
        status = "FAIL"
        regressions.append(f"{op}: +{pct:.1f}% vs baseline (limit {MAX_PCT}%)")
    elif pct is not None and pct > 5:
        status = "WARN"
        warnings.append(f"{op}: +{pct:.1f}% vs baseline")

    results.append({"operation": op, "instructions": cur_insns, "baseline": base_insns,
                    "pct_change": round(pct, 2) if pct is not None else None,
                    "threshold": threshold or None, "status": status})

Path("reports").mkdir(exist_ok=True)
(Path("reports") / "performance_results.json").write_text(
    json.dumps({"results": results, "regressions": regressions, "warnings": warnings}, indent=2))

print(f"Operations: {len(measured)} | Regressions: {len(regressions)} | Warnings: {len(warnings)}")
for r in regressions:
    print(f"  REGRESSION: {r}")
for w in warnings:
    print(f"  WARNING: {w}")

if regressions:
    sys.exit(1)
