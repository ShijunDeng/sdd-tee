#!/usr/bin/env python3
"""
SDD-TEE v5.0 Data Exporter

Exports benchmark run data into formats suitable for chart generation
and cross-run comparison: CSV, aggregated JSON, and Markdown tables.

Usage:
  # Export all v5.0 runs to CSV
  python3 scripts/export_data.py --format csv

  # Export specific runs to JSON summary
  python3 scripts/export_data.py --format json --runs results/runs/v5.0/*_full.json

  # Export to Markdown (for quick review)
  python3 scripts/export_data.py --format markdown

  # Export all formats
  python3 scripts/export_data.py --format all
"""

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "scripts"))


def load_run(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def discover_runs(pattern: str = "results/runs/v5.0/*_full.json") -> list[str]:
    import glob
    return sorted(glob.glob(pattern))


def export_csv(runs: list[dict], output_dir: Path):
    """Export runs as CSV files — one for summary, one for per-stage, one for per-AR."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Summary CSV (one row per run)
    summary_path = output_dir / "summary.csv"
    with open(summary_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "run_id", "tool", "model", "total_tokens", "input_tokens",
            "output_tokens", "cache_read_tokens", "cache_write_tokens",
            "cost_usd", "total_loc", "total_files", "ar_count",
            "duration_seconds", "api_calls", "iterations",
        ])
        for r in runs:
            gt = r["grand_totals"]
            m = r["meta"]
            writer.writerow([
                m.get("run_id", ""),
                m.get("tool", ""),
                m.get("model", ""),
                gt.get("total_tokens", 0),
                gt.get("input_tokens", 0),
                gt.get("output_tokens", 0),
                gt.get("cache_read_tokens", 0),
                gt.get("cache_write_tokens", 0),
                round(gt.get("cost_usd", 0), 4),
                gt.get("total_loc", 0),
                gt.get("total_files", 0),
                gt.get("ar_count", 0),
                gt.get("total_duration_seconds", 0),
                gt.get("total_api_calls", 0),
                gt.get("total_iterations", 0),
            ])
    print(f"  CSV summary → {summary_path}")

    # 2. Per-stage CSV
    stage_path = output_dir / "stages.csv"
    with open(stage_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "run_id", "tool", "model", "stage", "stage_name",
            "total_tokens", "input_tokens", "output_tokens",
            "cache_read_tokens", "duration_seconds", "iterations",
        ])
        for r in runs:
            m = r["meta"]
            for sid in ["ST-0", "ST-1", "ST-2", "ST-3", "ST-4", "ST-5", "ST-6", "ST-7"]:
                sa = r.get("stage_aggregates", {}).get(sid, {})
                writer.writerow([
                    m.get("run_id", ""),
                    m.get("tool", ""),
                    m.get("model", ""),
                    sid,
                    sa.get("name", ""),
                    sa.get("total_tokens", 0),
                    sa.get("input_tokens", 0),
                    sa.get("output_tokens", 0),
                    sa.get("cache_read_tokens", 0),
                    sa.get("duration_seconds", 0),
                    sa.get("iterations", 0),
                ])
    print(f"  CSV stages → {stage_path}")

    # 3. Per-AR CSV
    ar_path = output_dir / "ar_results.csv"
    with open(ar_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "run_id", "tool", "model", "ar_id", "ar_name", "module",
            "lang", "size", "total_tokens", "cost_usd",
            "actual_loc", "actual_files", "duration_seconds",
        ])
        for r in runs:
            m = r["meta"]
            for ar in r.get("ar_results", []):
                writer.writerow([
                    m.get("run_id", ""),
                    m.get("tool", ""),
                    m.get("model", ""),
                    ar["ar_id"],
                    ar["ar_name"],
                    ar["module"],
                    ar["lang"],
                    ar["size"],
                    ar["totals"]["total_tokens"],
                    round(ar["totals"]["cost_usd"], 4),
                    ar["output"]["actual_loc"],
                    ar["output"]["actual_files"],
                    ar["totals"]["duration_seconds"],
                ])
    print(f"  CSV per-AR → {ar_path}")


def export_json_summary(runs: list[dict], output_dir: Path):
    """Export a compact JSON summary suitable for chart libraries."""
    output_dir.mkdir(parents=True, exist_ok=True)

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_count": len(runs),
        "runs": [],
        "comparison": {},
    }

    for r in runs:
        gt = r["grand_totals"]
        m = r["meta"]
        run_data = {
            "run_id": m.get("run_id", ""),
            "tool": m.get("tool", ""),
            "model": m.get("model", ""),
            "tokens": {
                "total": gt.get("total_tokens", 0),
                "input": gt.get("input_tokens", 0),
                "output": gt.get("output_tokens", 0),
                "cache_read": gt.get("cache_read_tokens", 0),
                "cache_write": gt.get("cache_write_tokens", 0),
            },
            "cost_usd": round(gt.get("cost_usd", 0), 4),
            "output": {
                "loc": gt.get("total_loc", 0),
                "files": gt.get("total_files", 0),
                "ar_count": gt.get("ar_count", 0),
            },
            "efficiency": {
                "duration_s": gt.get("total_duration_seconds", 0),
                "api_calls": gt.get("total_api_calls", 0),
                "iterations": gt.get("total_iterations", 0),
            },
            "stage_distribution": {},
        }

        # Stage distribution
        total = max(gt.get("total_tokens", 1), 1)
        for sid in ["ST-0", "ST-1", "ST-2", "ST-3", "ST-4", "ST-5", "ST-6", "ST-7"]:
            sa = r.get("stage_aggregates", {}).get(sid, {})
            run_data["stage_distribution"][sid] = {
                "tokens": sa.get("total_tokens", 0),
                "pct": round(sa.get("total_tokens", 0) / total, 4),
            }

        summary["runs"].append(run_data)

    # Compute comparison metrics
    if len(runs) >= 2:
        valid = [r for r in runs if r["grand_totals"].get("total_tokens", 0) > 0]
        if valid:
            summary["comparison"] = {
                "best_total_tokens": min(r["grand_totals"]["total_tokens"] for r in valid),
                "best_cost_usd": min(r["grand_totals"]["cost_usd"] for r in valid),
                "most_loc": max(r["grand_totals"]["total_loc"] for r in valid),
                "fastest": min(r["grand_totals"]["total_duration_seconds"] for r in valid),
                "best_cache_rate": max(
                    r["grand_totals"].get("cache_read_tokens", 0)
                    / max(r["grand_totals"].get("input_tokens", 1), 1)
                    for r in valid
                ),
            }

    out_path = output_dir / "export.json"
    with open(out_path, "w") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"  JSON summary → {out_path}")


def export_markdown(runs: list[dict], output_dir: Path):
    """Export a Markdown comparison table."""
    output_dir.mkdir(parents=True, exist_ok=True)

    lines = [
        "# SDD-TEE v5.0 Benchmark Comparison",
        "",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"Runs: {len(runs)}",
        "",
        "## Summary",
        "",
        "| Run | Tool | Model | Tokens | Cost | LOC | Duration |",
        "|-----|------|-------|--------|------|-----|----------|",
    ]

    for r in runs:
        gt = r["grand_totals"]
        m = r["meta"]
        dur = gt.get("total_duration_seconds", 0)
        if dur >= 60:
            dur_str = f"{dur/60:.1f}m"
        else:
            dur_str = f"{dur:.0f}s"

        lines.append(
            f"| {m.get('run_id', '?')} "
            f"| {m.get('tool', '?')} "
            f"| {m.get('model', '?')} "
            f"| {gt.get('total_tokens', 0):,} "
            f"| ${gt.get('cost_usd', 0):.2f} "
            f"| {gt.get('total_loc', 0):,} "
            f"| {dur_str} |"
        )

    lines.append("")
    lines.append("## Stage Distribution")
    lines.append("")
    lines.append("| Run | ST-0 | ST-1 | ST-2 | ST-3 | ST-4 | ST-5 | ST-6 | ST-7 |")
    lines.append("|-----|------|------|------|------|------|------|------|------|")

    for r in runs:
        total = max(r["grand_totals"].get("total_tokens", 1), 1)
        parts = [f"| {r['meta'].get('run_id', '?')} |"]
        for sid in ["ST-0", "ST-1", "ST-2", "ST-3", "ST-4", "ST-5", "ST-6", "ST-7"]:
            sa = r.get("stage_aggregates", {}).get(sid, {})
            pct = sa.get("total_tokens", 0) / total * 100
            parts.append(f"{pct:.1f}%|")
        lines.append(" ".join(parts))

    lines.append("")
    md_path = output_dir / "comparison.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  Markdown → {md_path}")


def main():
    parser = argparse.ArgumentParser(description="SDD-TEE v5.0 Data Exporter")
    parser.add_argument("--format", choices=["csv", "json", "markdown", "all"],
                        default="all", help="Export format")
    parser.add_argument("--runs", nargs="*",
                        help="Paths to *_full.json files (default: all v5.0 runs)")
    parser.add_argument("--output", default="results/reports/v5.0",
                        help="Output directory")
    args = parser.parse_args()

    run_paths = args.runs if args.runs else discover_runs()
    if not run_paths:
        print("No run files found. Run a benchmark first.")
        return

    print(f"[export] Loading {len(run_paths)} runs...")
    runs = []
    for p in run_paths:
        try:
            runs.append(load_run(p))
        except Exception as e:
            print(f"  [WARN] Skipping {p}: {e}")

    output_dir = Path(args.output)
    fmt = args.format

    if fmt in ("csv", "all"):
        export_csv(runs, output_dir)
    if fmt in ("json", "all"):
        export_json_summary(runs, output_dir)
    if fmt in ("markdown", "all"):
        export_markdown(runs, output_dir)

    print(f"\n[export] Done. All files in {output_dir}/")


if __name__ == "__main__":
    main()
