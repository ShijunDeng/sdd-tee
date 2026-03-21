#!/usr/bin/env python3
"""
Stage 4: Aggregate benchmark results and generate comparison reports.
Usage: python3 scripts/04_report.py [results_dir]
"""

import json
import os
import sys
import csv
from datetime import datetime, timezone
from pathlib import Path

RESULTS_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("./results")
RUNS_DIR = RESULTS_DIR / "runs"
REPORTS_DIR = RESULTS_DIR / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

SKIP_SUFFIXES = ("_planning", "_implementation", "_refinement", "_validation", "_raw", "_aider")


def load_run_results():
    runs = []
    for f in sorted(RUNS_DIR.glob("*.json")):
        if any(f.stem.endswith(s) for s in SKIP_SUFFIXES):
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
    output = REPORTS_DIR / "summary.csv"
    fields = [
        "run_id", "tool", "model", "timestamp",
        "total_duration_s",
        "stage0_analysis_s", "stage1_spec_gen_s", "stage2_sdd_dev_s", "stage3_validate_s",
        "files_generated", "loc_generated",
        "original_files", "original_loc",
        "file_count_ratio", "loc_ratio",
        "directory_similarity", "file_overlap_ratio",
        "key_files_rate", "python_syntax_rate", "yaml_syntax_rate"
    ]

    with open(output, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()

        for run in runs:
            totals = run.get("totals", {})
            stages = run.get("stages", {})
            quality = run.get("quality", {})

            writer.writerow({
                "run_id": run["run_id"],
                "tool": run["tool"],
                "model": run["model"],
                "timestamp": run.get("timestamp", ""),
                "total_duration_s": totals.get("duration_seconds", 0),
                "stage0_analysis_s": stages.get("project_analysis", {}).get("duration_seconds", 0),
                "stage1_spec_gen_s": stages.get("spec_generation", {}).get("duration_seconds", 0),
                "stage2_sdd_dev_s": stages.get("sdd_development", {}).get("duration_seconds", 0),
                "stage3_validate_s": stages.get("validation", {}).get("duration_seconds", 0),
                "files_generated": quality.get("files_generated", 0),
                "loc_generated": quality.get("loc_generated", 0),
                "original_files": quality.get("original_files", 0),
                "original_loc": quality.get("original_loc", 0),
                "file_count_ratio": quality.get("file_count_ratio", ""),
                "loc_ratio": quality.get("loc_ratio", ""),
                "directory_similarity": quality.get("directory_similarity", ""),
                "file_overlap_ratio": quality.get("file_overlap_ratio", ""),
                "key_files_rate": quality.get("key_files_rate", ""),
                "python_syntax_rate": quality.get("python_syntax_rate", ""),
                "yaml_syntax_rate": quality.get("yaml_syntax_rate", ""),
            })

    print(f"  CSV summary: {output}")
    return output


def generate_comparison_report(runs, validations):
    output = REPORTS_DIR / "comparison_report.md"
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    with open(output, "w") as f:
        f.write("# SDD Benchmark Comparison Report\n\n")
        f.write(f"Generated: {timestamp}\n\n")
        f.write(f"Target Project: [agentcube](https://github.com/ShijunDeng/agentcube)\n\n")

        if not runs:
            f.write("No benchmark runs found.\n")
            return output

        # Overview
        f.write("## Run Overview\n\n")
        f.write("| Tool | Model | Total Duration | Files | LOC | Key Files Rate |\n")
        f.write("|------|-------|---------------|-------|-----|----------------|\n")
        for run in runs:
            t = run.get("totals", {})
            q = run.get("quality", {})
            dur = t.get("duration_seconds", 0)
            f.write(f"| {run['tool']} | {run['model']} "
                    f"| {dur // 60}m {dur % 60}s "
                    f"| {q.get('files_generated', 0)}/{q.get('original_files', 0)} "
                    f"| {q.get('loc_generated', 0):,}/{q.get('original_loc', 0):,} "
                    f"| {q.get('key_files_rate', 0):.0%} |\n")

        # Per-stage timing
        f.write("\n## Per-Stage Duration\n\n")
        f.write("| Tool + Model | Analysis | Spec Gen | SDD Dev | Validation | Total |\n")
        f.write("|-------------|----------|----------|---------|-----------|-------|\n")
        for run in runs:
            stages = run.get("stages", {})
            label = f"{run['tool']} + {run['model']}"
            s0 = stages.get("project_analysis", {}).get("duration_seconds", 0)
            s1 = stages.get("spec_generation", {}).get("duration_seconds", 0)
            s2 = stages.get("sdd_development", {}).get("duration_seconds", 0)
            s3 = stages.get("validation", {}).get("duration_seconds", 0)
            total = run.get("totals", {}).get("duration_seconds", 0)
            f.write(f"| {label} | {s0}s | {s1}s | {s2}s | {s3}s | {total}s |\n")

        # Quality comparison
        f.write("\n## Quality Metrics\n\n")
        f.write("| Tool + Model | File Ratio | LOC Ratio | Dir Similarity | File Overlap | Py Syntax | YAML Syntax |\n")
        f.write("|-------------|-----------|-----------|----------------|-------------|-----------|-------------|\n")
        for run in runs:
            q = run.get("quality", {})
            label = f"{run['tool']} + {run['model']}"
            f.write(f"| {label} "
                    f"| {q.get('file_count_ratio', 'N/A')} "
                    f"| {q.get('loc_ratio', 'N/A')} "
                    f"| {q.get('directory_similarity', 'N/A'):.2%} "
                    f"| {q.get('file_overlap_ratio', 'N/A'):.2%} "
                    f"| {q.get('python_syntax_rate', 'N/A'):.0%} "
                    f"| {q.get('yaml_syntax_rate', 'N/A'):.0%} |\n")

        # Stage descriptions
        f.write("\n## Stage Descriptions\n\n")
        for run in runs:
            f.write(f"### {run['tool']} + {run['model']}\n\n")
            for stage_name, stage in run.get("stages", {}).items():
                desc = stage.get("description", stage_name)
                dur = stage.get("duration_seconds", 0)
                notes = stage.get("notes", "")
                f.write(f"- **{stage_name}** ({dur}s): {desc}")
                if notes:
                    f.write(f" — {notes}")
                f.write("\n")
            f.write("\n")

        # Efficiency
        f.write("## Efficiency Metrics\n\n")
        for run in runs:
            q = run.get("quality", {})
            t = run.get("totals", {})
            loc = q.get("loc_generated", 0)
            dur = t.get("duration_seconds", 0)
            label = f"{run['tool']} + {run['model']}"

            f.write(f"**{label}**\n")
            if loc > 0 and dur > 0:
                f.write(f"- LOC per minute: {loc / dur * 60:.1f}\n")
                f.write(f"- Files per minute: {q.get('files_generated', 0) / dur * 60:.1f}\n")
            f.write("\n")

        # Missing files
        for run in runs:
            q = run.get("quality", {})
            missing = q.get("key_files_missing", [])
            if missing:
                f.write(f"\n### Missing Key Files ({run['tool']})\n\n")
                for mf in missing:
                    f.write(f"- `{mf}`\n")
                f.write("\n")

    print(f"  Comparison report: {output}")
    return output


def generate_chart_data(runs):
    chart_data = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "runs": []
    }

    for run in runs:
        t = run.get("totals", {})
        q = run.get("quality", {})
        stages = run.get("stages", {})

        entry = {
            "label": f"{run['tool']}+{run['model']}",
            "tool": run["tool"],
            "model": run["model"],
            "total_duration_s": t.get("duration_seconds", 0),
            "files_generated": q.get("files_generated", 0),
            "loc_generated": q.get("loc_generated", 0),
            "file_count_ratio": q.get("file_count_ratio", 0),
            "loc_ratio": q.get("loc_ratio", 0),
            "directory_similarity": q.get("directory_similarity", 0),
            "file_overlap_ratio": q.get("file_overlap_ratio", 0),
            "key_files_rate": q.get("key_files_rate", 0),
            "python_syntax_rate": q.get("python_syntax_rate", 0),
            "yaml_syntax_rate": q.get("yaml_syntax_rate", 0),
            "stages": {}
        }

        for stage_name, stage in stages.items():
            entry["stages"][stage_name] = {
                "duration_seconds": stage.get("duration_seconds", 0)
            }

        chart_data["runs"].append(entry)

    output = REPORTS_DIR / "chart_data.json"
    with open(output, "w") as f:
        json.dump(chart_data, f, indent=2)
    print(f"  Chart data: {output}")
    return output


def try_generate_charts(runs):
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        print("  matplotlib not available, skipping chart generation.")
        return

    if not runs:
        return

    labels = [f"{r['tool']}\n{r['model']}" for r in runs]

    # 1. Stage duration stacked bar chart
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    stage_names = ["project_analysis", "spec_generation", "sdd_development", "validation"]
    stage_labels = ["Analysis", "Spec Gen", "SDD Dev", "Validation"]
    colors = ['#4C78A8', '#F58518', '#E45756', '#72B7B2']

    x = np.arange(len(labels))
    width = 0.5
    bottom = np.zeros(len(labels))

    for i, (sn, sl) in enumerate(zip(stage_names, stage_labels)):
        vals = []
        for r in runs:
            vals.append(r.get("stages", {}).get(sn, {}).get("duration_seconds", 0))
        axes[0].bar(x, vals, width, bottom=bottom, label=sl, color=colors[i])
        bottom += np.array(vals, dtype=float)

    axes[0].set_title('Duration by Stage (seconds)')
    axes[0].set_xticks(x)
    axes[0].set_xticklabels(labels, fontsize=9)
    axes[0].legend(loc='upper right', fontsize=8)

    # 2. Quality radar chart data as bar chart
    quality_metrics = ["file_count_ratio", "loc_ratio", "directory_similarity",
                       "file_overlap_ratio", "key_files_rate", "python_syntax_rate"]
    metric_labels = ["File Ratio", "LOC Ratio", "Dir Similarity",
                     "File Overlap", "Key Files", "Py Syntax"]

    for idx, r in enumerate(runs):
        q = r.get("quality", {})
        vals = [q.get(m, 0) for m in quality_metrics]
        bar_x = np.arange(len(metric_labels))
        axes[1].bar(bar_x + idx * 0.3, vals, 0.3,
                     label=f"{r['tool']}+{r['model']}", alpha=0.8)

    axes[1].set_title('Quality Metrics')
    axes[1].set_xticks(np.arange(len(metric_labels)))
    axes[1].set_xticklabels(metric_labels, fontsize=8, rotation=30, ha='right')
    axes[1].legend(fontsize=8)
    axes[1].set_ylim(0, 1.1)

    plt.tight_layout()
    chart_path = REPORTS_DIR / "benchmark_charts.png"
    plt.savefig(chart_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  Charts: {chart_path}")


def main():
    print("=== Stage 4: Report Generation ===")
    print(f"Results directory: {RESULTS_DIR}")

    runs = load_run_results()
    validations = load_validation_results()

    print(f"Found {len(runs)} run(s) and {len(validations)} validation(s)\n")

    generate_summary_csv(runs, validations)
    generate_comparison_report(runs, validations)
    generate_chart_data(runs)
    try_generate_charts(runs)

    print("\n=== Stage 4 Complete ===")


if __name__ == "__main__":
    main()
