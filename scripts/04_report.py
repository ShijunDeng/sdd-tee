#!/usr/bin/env python3
"""
Stage 4: Aggregate benchmark results and generate comparison reports.
Usage: python3 scripts/04_report.py [results_dir]
"""

import json
import os
import sys
import csv
from datetime import datetime
from pathlib import Path

RESULTS_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("./results")
RUNS_DIR = RESULTS_DIR / "runs"
REPORTS_DIR = RESULTS_DIR / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def load_run_results():
    """Load all run result JSON files (excluding stage-specific files)."""
    runs = []
    for f in sorted(RUNS_DIR.glob("*.json")):
        if any(s in f.name for s in ["_planning", "_implementation", "_refinement", "_validation", "_raw", "_aider"]):
            continue
        try:
            with open(f) as fh:
                data = json.load(fh)
                if "run_id" in data and "tool" in data:
                    runs.append(data)
        except (json.JSONDecodeError, KeyError):
            pass
    return runs


def load_validation_results():
    """Load all validation result JSON files."""
    validations = {}
    for f in sorted(RUNS_DIR.glob("*_validation.json")):
        try:
            with open(f) as fh:
                data = json.load(fh)
                run_id = data.get("run_id", f.stem.replace("_validation", ""))
                validations[run_id] = data
        except (json.JSONDecodeError, KeyError):
            pass
    return validations


def generate_summary_csv(runs, validations):
    """Generate a CSV summary of all runs for easy comparison."""
    output = REPORTS_DIR / "summary.csv"
    fields = [
        "run_id", "tool", "model", "timestamp",
        "total_duration_s", "total_input_tokens", "total_output_tokens", "total_cost_usd",
        "planning_tokens", "planning_cost", "planning_duration",
        "impl_tokens", "impl_cost", "impl_duration",
        "files_generated", "loc_generated",
        "file_count_ratio", "loc_ratio", "dir_similarity",
        "go_compiles", "python_syntax_rate"
    ]

    with open(output, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()

        for run in runs:
            totals = run.get("totals", {})
            stages = run.get("stages", {})
            quality = run.get("quality", {})
            planning = stages.get("planning", {})
            impl = stages.get("implementation", {})

            val = validations.get(run["run_id"], {})
            comparison = val.get("comparison", {})
            checks = val.get("checks", {})

            writer.writerow({
                "run_id": run["run_id"],
                "tool": run["tool"],
                "model": run["model"],
                "timestamp": run.get("timestamp", ""),
                "total_duration_s": totals.get("duration_seconds", 0),
                "total_input_tokens": totals.get("input_tokens", 0),
                "total_output_tokens": totals.get("output_tokens", 0),
                "total_cost_usd": totals.get("cost_usd", 0),
                "planning_tokens": planning.get("input_tokens", 0) + planning.get("output_tokens", 0),
                "planning_cost": planning.get("cost_usd", 0),
                "planning_duration": planning.get("duration_seconds", 0),
                "impl_tokens": impl.get("input_tokens", 0) + impl.get("output_tokens", 0),
                "impl_cost": impl.get("cost_usd", 0),
                "impl_duration": impl.get("duration_seconds", 0),
                "files_generated": quality.get("files_generated", 0),
                "loc_generated": quality.get("loc_generated", 0),
                "file_count_ratio": comparison.get("file_count_ratio", ""),
                "loc_ratio": comparison.get("loc_ratio", ""),
                "dir_similarity": comparison.get("directory_similarity", ""),
                "go_compiles": checks.get("go_compiles", ""),
                "python_syntax_rate": checks.get("python_syntax_rate", ""),
            })

    print(f"CSV summary: {output}")
    return output


def generate_comparison_report(runs, validations):
    """Generate a Markdown comparison report."""
    output = REPORTS_DIR / "comparison_report.md"
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

    with open(output, "w") as f:
        f.write(f"# SDD Benchmark Comparison Report\n\n")
        f.write(f"Generated: {timestamp}\n\n")
        f.write(f"Project: agentcube\n\n")

        if not runs:
            f.write("No benchmark runs found.\n")
            return output

        # Summary table
        f.write("## Summary\n\n")
        f.write("| Tool | Model | Duration | Input Tokens | Output Tokens | Cost (USD) | Files | LOC |\n")
        f.write("|------|-------|----------|-------------|--------------|-----------|-------|-----|\n")
        for run in runs:
            t = run.get("totals", {})
            q = run.get("quality", {})
            f.write(f"| {run['tool']} | {run['model']} "
                    f"| {t.get('duration_seconds', 0)}s "
                    f"| {t.get('input_tokens', 0):,} "
                    f"| {t.get('output_tokens', 0):,} "
                    f"| ${t.get('cost_usd', 0):.4f} "
                    f"| {q.get('files_generated', 0)} "
                    f"| {q.get('loc_generated', 0):,} |\n")

        # Per-stage breakdown
        f.write("\n## Per-Stage Token Consumption\n\n")
        for run in runs:
            f.write(f"\n### {run['tool']} + {run['model']}\n\n")
            f.write("| Stage | Duration | Input Tokens | Output Tokens | Cost (USD) |\n")
            f.write("|-------|----------|-------------|--------------|------------|\n")
            for stage_name, stage in run.get("stages", {}).items():
                f.write(f"| {stage_name} "
                        f"| {stage.get('duration_seconds', 0)}s "
                        f"| {stage.get('input_tokens', 0):,} "
                        f"| {stage.get('output_tokens', 0):,} "
                        f"| ${stage.get('cost_usd', 0):.4f} |\n")

        # Quality comparison
        if validations:
            f.write("\n## Quality Comparison\n\n")
            f.write("| Run | Files Ratio | LOC Ratio | Dir Similarity | Go Compiles | Py Syntax Rate |\n")
            f.write("|-----|------------|-----------|----------------|------------|----------------|\n")
            for run_id, val in validations.items():
                comp = val.get("comparison", {})
                chk = val.get("checks", {})
                f.write(f"| {run_id} "
                        f"| {comp.get('file_count_ratio', 'N/A')} "
                        f"| {comp.get('loc_ratio', 'N/A')} "
                        f"| {comp.get('directory_similarity', 'N/A')} "
                        f"| {chk.get('go_compiles', 'N/A')} "
                        f"| {chk.get('python_syntax_rate', 'N/A')} |\n")

        # Cost efficiency analysis
        f.write("\n## Cost Efficiency Analysis\n\n")
        for run in runs:
            t = run.get("totals", {})
            q = run.get("quality", {})
            loc = q.get("loc_generated", 0)
            cost = t.get("cost_usd", 0)
            tokens = t.get("input_tokens", 0) + t.get("output_tokens", 0)

            f.write(f"**{run['tool']} + {run['model']}**\n")
            if loc > 0 and cost > 0:
                f.write(f"- Cost per LOC: ${cost / loc:.6f}\n")
                f.write(f"- Tokens per LOC: {tokens / loc:.1f}\n")
            if loc > 0 and t.get("duration_seconds", 0) > 0:
                f.write(f"- LOC per second: {loc / t['duration_seconds']:.1f}\n")
            f.write("\n")

    print(f"Comparison report: {output}")
    return output


def generate_chart_data(runs):
    """Generate JSON data files suitable for chart rendering."""
    chart_data = {
        "tools": [],
        "token_comparison": [],
        "cost_comparison": [],
        "time_comparison": [],
        "stage_breakdown": []
    }

    for run in runs:
        label = f"{run['tool']}+{run['model']}"
        t = run.get("totals", {})

        chart_data["tools"].append(label)
        chart_data["token_comparison"].append({
            "label": label,
            "input_tokens": t.get("input_tokens", 0),
            "output_tokens": t.get("output_tokens", 0)
        })
        chart_data["cost_comparison"].append({
            "label": label,
            "cost_usd": t.get("cost_usd", 0)
        })
        chart_data["time_comparison"].append({
            "label": label,
            "duration_seconds": t.get("duration_seconds", 0)
        })

        stages = []
        for stage_name, stage in run.get("stages", {}).items():
            stages.append({
                "stage": stage_name,
                "input_tokens": stage.get("input_tokens", 0),
                "output_tokens": stage.get("output_tokens", 0),
                "cost_usd": stage.get("cost_usd", 0),
                "duration_seconds": stage.get("duration_seconds", 0)
            })
        chart_data["stage_breakdown"].append({"label": label, "stages": stages})

    output = REPORTS_DIR / "chart_data.json"
    with open(output, "w") as f:
        json.dump(chart_data, f, indent=2)
    print(f"Chart data: {output}")
    return output


def try_generate_charts(runs):
    """Attempt to generate charts with matplotlib if available."""
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        print("matplotlib not available, skipping chart generation.")
        print("Install with: pip install matplotlib")
        return

    if not runs:
        return

    labels = [f"{r['tool']}\n{r['model']}" for r in runs]

    # Token comparison bar chart
    fig, axes = plt.subplots(1, 3, figsize=(18, 6))

    input_tokens = [r.get("totals", {}).get("input_tokens", 0) for r in runs]
    output_tokens = [r.get("totals", {}).get("output_tokens", 0) for r in runs]
    x = np.arange(len(labels))
    width = 0.35
    axes[0].bar(x - width/2, input_tokens, width, label='Input Tokens', color='#4C78A8')
    axes[0].bar(x + width/2, output_tokens, width, label='Output Tokens', color='#F58518')
    axes[0].set_title('Token Usage Comparison')
    axes[0].set_xticks(x)
    axes[0].set_xticklabels(labels, fontsize=8)
    axes[0].legend()
    axes[0].ticklabel_format(style='scientific', axis='y', scilimits=(0, 0))

    # Cost comparison
    costs = [r.get("totals", {}).get("cost_usd", 0) for r in runs]
    axes[1].bar(labels, costs, color='#E45756')
    axes[1].set_title('Cost Comparison (USD)')
    axes[1].tick_params(axis='x', labelsize=8)

    # Duration comparison
    durations = [r.get("totals", {}).get("duration_seconds", 0) for r in runs]
    axes[2].bar(labels, durations, color='#72B7B2')
    axes[2].set_title('Duration Comparison (seconds)')
    axes[2].tick_params(axis='x', labelsize=8)

    plt.tight_layout()
    chart_path = REPORTS_DIR / "comparison_charts.png"
    plt.savefig(chart_path, dpi=150)
    plt.close()
    print(f"Charts: {chart_path}")

    # Per-stage stacked bar chart
    if any(r.get("stages") for r in runs):
        fig, ax = plt.subplots(figsize=(12, 6))
        all_stages = set()
        for r in runs:
            all_stages.update(r.get("stages", {}).keys())
        all_stages = sorted(all_stages)

        x = np.arange(len(labels))
        width = 0.6
        bottom = np.zeros(len(labels))
        colors = plt.cm.Set3(np.linspace(0, 1, len(all_stages)))

        for i, stage in enumerate(all_stages):
            vals = []
            for r in runs:
                s = r.get("stages", {}).get(stage, {})
                vals.append(s.get("input_tokens", 0) + s.get("output_tokens", 0))
            ax.bar(x, vals, width, bottom=bottom, label=stage, color=colors[i])
            bottom += np.array(vals)

        ax.set_title('Token Usage by Stage')
        ax.set_xticks(x)
        ax.set_xticklabels(labels, fontsize=8)
        ax.legend(loc='upper right')
        ax.ticklabel_format(style='scientific', axis='y', scilimits=(0, 0))

        plt.tight_layout()
        chart_path = REPORTS_DIR / "stage_breakdown_chart.png"
        plt.savefig(chart_path, dpi=150)
        plt.close()
        print(f"Stage chart: {chart_path}")


def main():
    print("=== Stage 4: Report Generation ===")
    print(f"Results directory: {RESULTS_DIR}")

    runs = load_run_results()
    validations = load_validation_results()

    print(f"Found {len(runs)} run(s) and {len(validations)} validation(s)")

    generate_summary_csv(runs, validations)
    generate_comparison_report(runs, validations)
    generate_chart_data(runs)
    try_generate_charts(runs)

    print("\n=== Stage 4 Complete ===")


if __name__ == "__main__":
    main()
