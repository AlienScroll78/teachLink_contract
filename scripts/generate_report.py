#!/usr/bin/env python3
"""
Generate reports/summary.md and reports/report.json from:
  - test_output.txt          (cargo test output)
  - reports/performance_results.json  (from check_performance.py)
"""
import json, re, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT    = Path(__file__).parent.parent
REPORTS = ROOT / "reports"
REPORTS.mkdir(exist_ok=True)

def read(p):
    return p.read_text() if p.exists() else ""

def load_json(p):
    try: return json.loads(p.read_text())
    except Exception: return {}

now      = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
test_out = read(ROOT / "test_output.txt")
passed   = len(re.findall(r"test .+ \.\.\. ok",     test_out))
failed   = len(re.findall(r"test .+ \.\.\. FAILED", test_out))
ignored  = len(re.findall(r"test .+ \.\.\. ignored",test_out))

perf        = load_json(REPORTS / "performance_results.json")
gas_results = perf.get("results", [])
regressions = perf.get("regressions", [])
warnings    = perf.get("warnings", [])

overall = "❌ FAILED" if (failed or regressions) else ("⚠️ WARNINGS" if warnings else "✅ PASSED")

md = [f"# Regression Report — {now}", "", f"## Overall: {overall}", "",
      "## Tests", "",
      "| Passed | Failed | Ignored |", "|--------|--------|---------|",
      f"| {passed} | {failed} | {ignored} |", ""]

if gas_results:
    md += ["## Gas Performance", "",
           "| Operation | Instructions | Baseline | Δ% | Threshold | Status |",
           "|-----------|-------------|----------|----|-----------|--------|"]
    for r in gas_results:
        pct    = f"{r['pct_change']:+.1f}%" if r.get("pct_change") is not None else "—"
        icon   = {"OK": "✅", "WARN": "⚠️", "FAIL": "❌"}.get(r["status"], r["status"])
        md.append(f"| {r['operation']} | {r['instructions']:,} | {r['baseline'] or '—'} "
                  f"| {pct} | {r['threshold'] or '—'} | {icon} |")
    md.append("")

for label, items in [("Regressions", regressions), ("Warnings", warnings)]:
    if items:
        md += [f"## {label}", ""] + [f"- {i}" for i in items] + [""]

summary = "\n".join(md)
(REPORTS / "summary.md").write_text(summary)
(REPORTS / "report.json").write_text(json.dumps({
    "generated_at": now, "overall": overall,
    "tests": {"passed": passed, "failed": failed, "ignored": ignored},
    "gas": {"results": gas_results, "regressions": regressions, "warnings": warnings},
}, indent=2))

print(summary)
if failed or regressions:
    sys.exit(1)
