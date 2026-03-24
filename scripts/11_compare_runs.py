#!/usr/bin/env python3
"""
SDD-TEE 跨轮次对比报告生成器 v3 (全面零值/空值审计版)
"""

import argparse
import glob
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "scripts"))
from schema import STAGES, STAGE_FIELDS, METRIC_IDS, WARNING_RULES

def load_runs(paths):
    runs = []
    for p in paths:
        try:
            with open(p) as f:
                d = json.load(f)
            if "grand_totals" in d and "ar_results" in d:
                d["_source"] = os.path.basename(p)
                runs.append(d)
        except: continue
    return runs

def is_run_failed(r):
    return r.get("meta", {}).get("status") == "FAILED" or (r["grand_totals"].get("total_loc", 0) == 0 and r["grand_totals"].get("total_tokens", 0) == 0)

def run_label(d):
    m = d.get("meta", {})
    label = f"{m.get('tool', '?')} / {m.get('model', '?')}"
    if is_run_failed(d):
        return f"{label} <br><span style='color:#d93025;font-size:0.8em;font-weight:bold'>[FAILED]</span>"
    return label

def format_val(val, unit_type="num", run=None):
    """Robustly format any metric value, handling zeros and failures."""
    if run and is_run_failed(run) and val == 0:
        return "<span style='color:#ccc'>-</span>"
    
    if val is None or val == 0:
        if unit_type == "pct": return "0.0%"
        if unit_type == "time": return "-"
        if unit_type == "cost": return "$0.00"
        return "0"

    if unit_type == "pct":
        if val < 0.001 and val > 0: return "<0.1%"
        return f"{val:.1%}" if val <= 1 else f"{val:.1f}%"
    
    if unit_type == "cost":
        if val < 0.01 and val > 0: return "<$0.01"
        return f"${val:,.2f}"
    
    if unit_type == "time":
        if val < 1: return "<1s"
        m, s = divmod(int(val), 60)
        h, m = divmod(m, 60)
        if h > 0: return f"{h}h {m}m"
        if m > 0: return f"{m}m {s}s"
        return f"{s}s"

    if isinstance(val, float):
        return f"{val:,.1f}"
    return f"{val:,}"

def pct(a, b):
    if b == 0: return "0.0%"
    return f"{a / b * 100:.1f}%"

STAGE_NAMES = {
    "ST-0": "需求探索与环境初始化",
    "ST-1": "架构设计与约束对齐",
    "ST-2": "实施方案与依赖图谱",
    "ST-3": "核心逻辑代码编写",
    "ST-4": "辅助模块与胶水代码",
    "ST-5": "单元测试与本地自测",
    "ST-6": "集成校验与Spec比对",
    "ST-7": "文档同步与最终产出"
}

def render_compare_html(runs):
    # Sort: Successful runs first
    runs.sort(key=lambda r: (is_run_failed(r), r["meta"]["tool"], r["meta"]["model"]))
    valid_runs = [r for r in runs if not is_run_failed(r)]
    n = len(runs)
    labels = [run_label(r) for r in runs]
    headers = "".join([f"<th>{l}</th>" for l in labels])

    def get_best(extractor, highlight="min"):
        if not valid_runs: return None
        vals = [extractor(r) for r in valid_runs]
        if not vals: return None
        return min(vals) if highlight == "min" else max(vals)

    def td_row(name, extractor, unit="num", highlight="min"):
        best = get_best(extractor, highlight)
        row = f"<tr><td>{name}</td>"
        for r in runs:
            val = extractor(r)
            cls = ""
            if not is_run_failed(r) and best is not None and val == best and len(valid_runs) > 1:
                if highlight != "neutral": cls = ' class="best"'
            row += f"<td{cls}>{format_val(val, unit, r)}</td>"
        return row + "</tr>\n"

    # 1. Total Metrics
    gt_table = ""
    metrics = [
        ("总 Token", lambda r: r["grand_totals"].get("total_tokens", 0), "num", "min"),
        ("Input Token", lambda r: r["grand_totals"].get("input_tokens", 0), "num", "min"),
        ("Output Token", lambda r: r["grand_totals"].get("output_tokens", 0), "num", "min"),
        ("Cache Read", lambda r: r["grand_totals"].get("cache_read_tokens", 0), "num", "max"),
        ("总耗时", lambda r: r["grand_totals"].get("total_duration_seconds", 0), "time", "min"),
        ("总成本 (USD)", lambda r: r["grand_totals"].get("total_cost_usd", 0), "cost", "min"),
        ("代码行数 (LOC)", lambda r: r["grand_totals"].get("total_loc", 0), "num", "max"),
        ("文件数", lambda r: r["grand_totals"].get("total_files", 0), "num", "max"),
        ("API 调用", lambda r: r["grand_totals"].get("total_api_calls", 0), "num", "min"),
    ]
    for m in metrics: gt_table += td_row(*m)

    # 2. Stage Breakdown
    stage_table = ""
    for sid in STAGES:
        name = STAGE_NAMES.get(sid, sid)
        stage_table += f"<tr><td><strong>{sid}</strong><br><small>{name}</small></td>"
        vals = [r.get("stage_aggregates", {}).get(sid, {}).get("total_tokens", 0) for r in runs]
        valid_vals = [r.get("stage_aggregates", {}).get(sid, {}).get("total_tokens", 0) for r in valid_runs]
        best = min(valid_vals) if valid_vals else None
        for i, r in enumerate(runs):
            v = vals[i]
            dur = r.get("stage_aggregates", {}).get(sid, {}).get("duration_seconds", 0)
            cls = ' class="best"' if not is_run_failed(r) and best is not None and v == best and len(valid_runs) > 1 else ""
            stage_table += f"<td{cls}>{format_val(v, 'num', r)}<br><small>{format_val(dur, 'time', r)}</small></td>"
        stage_table += "</tr>\n"

    # 3. Efficiency & Quality
    eff_table = ""
    eff_metrics = [
        ("ET-LOC (Token/行)", lambda r: _avg_metric(r, "ET_LOC"), "num", "min"),
        ("Cache 命中率", lambda r: _cache_rate(r), "pct", "max"),
        ("代码可用率", lambda r: _avg_quality(r, "code_usability"), "pct", "max"),
        ("一致性评分", lambda r: _avg_quality(r, "consistency_score"), "pct", "max"),
        ("测试覆盖率", lambda r: _avg_quality(r, "test_coverage"), "pct", "max"),
    ]
    for m in eff_metrics: eff_table += td_row(*m)

    # Summary Extremums
    if valid_runs:
        max_loc_run = max(valid_runs, key=lambda r: r["grand_totals"].get("total_loc", 0))
        min_cost_run = min(valid_runs, key=lambda r: r["grand_totals"].get("total_cost_usd", 1e6))
        best_eff_run = min(valid_runs, key=lambda r: _avg_metric(r, "ET_LOC"))
    else:
        max_loc_run = min_cost_run = best_eff_run = runs[0]

    now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>SDD-TEE 跨轮次对比报告</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 1400px; margin: 0 auto; padding: 20px; background: #f8f9fa; color: #333; }}
  .section {{ background: #fff; padding: 20px; margin: 15px 0; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
  h1 {{ color: #1a73e8; border-bottom: 3px solid #1a73e8; padding-bottom: 10px; }}
  table {{ border-collapse: collapse; width: 100%; margin: 15px 0; font-size: 0.9em; }}
  th, td {{ border: 1px solid #ddd; padding: 10px; text-align: right; }}
  th {{ background: #1a73e8; color: #fff; text-align: center; position: sticky; top: 0; }}
  td:first-child {{ text-align: left; font-weight: 500; background: #f0f4ff; width: 180px; }}
  tr:nth-child(even) {{ background: #f8f9fa; }}
  .best {{ background: #e6f4ea !important; font-weight: bold; color: #137333; }}
  .summary-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 15px; margin-top: 15px; }}
  .summary-card {{ background: #e8f0fe; padding: 15px; border-radius: 8px; border-left: 5px solid #1a73e8; }}
  .card-label {{ font-size: 0.85em; color: #666; }}
  .card-val {{ font-size: 1.4em; font-weight: bold; color: #1a73e8; margin: 5px 0; }}
</style>
</head>
<body>
<h1>SDD-TEE 跨轮次对比报告</h1>
<div class="section">
  <p>生成时间: <strong>{now}</strong> | 参评轮次: <strong>{n}</strong> | 成功率: <strong>{pct(len(valid_runs), n)}</strong></p>
  <div class="summary-grid">
    <div class="summary-card">
      <div class="card-label">产出能力最优</div>
      <div class="card-val">{format_val(max_loc_run["grand_totals"].get("total_loc", 0))} LOC</div>
      <div class="card-label">{run_label(max_loc_run).replace('<br>', ' ')}</div>
    </div>
    <div class="summary-card">
      <div class="card-label">经济性最优</div>
      <div class="card-val">{format_val(min_cost_run["grand_totals"].get("total_cost_usd", 0), "cost")}</div>
      <div class="card-label">{run_label(min_cost_run).replace('<br>', ' ')}</div>
    </div>
    <div class="summary-card">
      <div class="card-label">代码浓度最高</div>
      <div class="card-val">{format_val(_avg_metric(best_eff_run, 'ET_LOC'))} T/LOC</div>
      <div class="card-label">{run_label(best_eff_run).replace('<br>', ' ')}</div>
    </div>
  </div>
</div>

<div class="section">
  <h2>1. 核心指标概览</h2>
  <table><tr><th>指标</th>{headers}</tr>{gt_table}</table>
</div>

<div class="section">
  <h2>2. 7 阶段流量分布 (Token / 耗时)</h2>
  <table><tr><th>阶段</th>{headers}</tr>{stage_table}</table>
</div>

<div class="section">
  <h2>3. 效率与质量分析</h2>
  <table><tr><th>指标</th>{headers}</tr>{eff_table}</table>
</div>

<div class="section">
  <h2>4. 运行审计</h2>
  <p>注：[FAILED] 任务指在执行过程中未产出任何有效代码文件且无 API 交互记录的任务。- 符号代表该指标在当前状态下无意义。</p>
</div>
</body></html>
"""
    return html

def _avg_metric(run, key):
    if is_run_failed(run): return 0
    vals = [ar["metrics"].get(key, 0) for ar in run["ar_results"]]
    return sum(vals) / len(vals) if vals else 0

def _cache_rate(run):
    gt = run["grand_totals"]
    return gt.get("cache_read_tokens", 0) / max(gt.get("input_tokens", 1), 1)

def _avg_quality(run, key):
    if is_run_failed(run): return 0
    vals = [ar["quality"].get(key, 0) for ar in run["ar_results"]]
    return sum(vals) / len(vals) if vals else 0

def _sum_quality(run, key):
    return sum(ar["quality"].get(key, 0) for ar in run["ar_results"])

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", nargs="*", help="Paths to *_full.json files")
    parser.add_argument("--output", default="results/reports/compare_report.html")
    args = parser.parse_args()
    paths = args.runs if args.runs else glob.glob("results/runs/v3.0/*_full.json")
    print(f"[11] Processing {len(paths)} runs...")
    runs = load_runs(paths)
    if not runs: return
    html = render_compare_html(runs)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f: f.write(html)
    print(f"[11] Report generated: {args.output}")

if __name__ == "__main__":
    main()
