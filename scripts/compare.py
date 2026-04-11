#!/usr/bin/env python3
"""
SDD-TEE v5.0 Cross-Run Comparison Report Generator

Generates an HTML comparison report from multiple benchmark runs,
with support for all v5.0 fields and 5-dimension metrics.

Usage:
  python3 scripts/11_compare_runs.py \
    --runs results/runs/v5.0/*_full.json \
    --output results/reports/v5.0/compare_report.html
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
from schema import STAGES

STAGE_NAMES = {
    "ST-0": "AR 输入",
    "ST-1": "需求澄清",
    "ST-2": "Spec 增量设计",
    "ST-3": "Design 增量设计",
    "ST-4": "任务拆解",
    "ST-5": "开发实现",
    "ST-6": "一致性验证",
    "ST-7": "合并归档",
}


def load_runs(paths):
    runs = []
    for p in paths:
        try:
            with open(p) as f:
                d = json.load(f)
            if "grand_totals" in d and "ar_results" in d:
                d["_source"] = os.path.basename(p)
                runs.append(d)
        except Exception:
            continue
    return runs


def is_run_failed(r):
    gt = r.get("grand_totals", {})
    return (
        r.get("meta", {}).get("status") == "FAILED"
        or (gt.get("total_tokens", 0) == 0 and gt.get("total_loc", 0) == 0)
    )


def run_label(d):
    m = d.get("meta", {})
    label = f"{m.get('tool', '?')} / {m.get('model', '?')}"
    if is_run_failed(d):
        return f"{label} [FAILED]"
    return label


def fmt_val(val, unit_type="num"):
    if val is None or val == 0:
        if unit_type == "pct": return "0.0%"
        if unit_type == "time": return "-"
        if unit_type == "cost": return "$0.00"
        return "0"
    if unit_type == "pct":
        if 0 < val < 0.001: return "<0.1%"
        return f"{val:.1%}" if val <= 1 else f"{val:.1f}%"
    if unit_type == "cost":
        if 0 < val < 0.01: return "<$0.01"
        return f"${val:,.2f}"
    if unit_type == "time":
        if val < 1: return "<1s"
        m, s = divmod(int(val), 60)
        h, m = divmod(m, 60)
        if h > 0: return f"{h}h {m}m"
        if m > 0: return f"{m}m {s}s"
        return f"{s}s"
    if isinstance(val, float): return f"{val:,.1f}"
    return f"{val:,}"


def render_report(runs):
    # Separate valid and failed runs — failed runs are excluded from output
    failed_runs = [r for r in runs if is_run_failed(r)]
    runs = [r for r in runs if not is_run_failed(r)]

    if failed_runs:
        failed_labels = [f"{r['meta'].get('tool','?')} / {r['meta'].get('model','?')}" for r in failed_runs]
        print(f"[11] Excluded {len(failed_runs)} invalid run(s): {', '.join(failed_labels)}")

    runs.sort(key=lambda r: (r["meta"].get("tool", ""), r["meta"].get("model", "")))
    n = len(runs)
    labels = [run_label(r) for r in runs]
    headers = "".join(f"<th>{l}</th>" for l in labels)

    # ─── 1. Grand Totals Table ────────────────────────────────────────────
    def td_row(name, extractor, unit="num", highlight="min"):
        vals = [extractor(r) for r in runs]
        valid_vals = [v for v in vals if v != 0 or name == "Cache Write"]
        best = (min(valid_vals) if highlight == "min" else max(valid_vals)) if valid_vals else None
        row = f"<tr><td>{name}</td>"
        for v in vals:
            cls = ""
            if best is not None and v == best and len(valid_vals) > 1 and highlight != "neutral":
                cls = ' class="best"'
            row += f"<td{cls}>{fmt_val(v, unit)}</td>"
        return row + "</tr>\n"

    gt_rows = ""
    for name, ext, unit, hl in [
        ("总 Token", lambda r: r["grand_totals"].get("total_tokens", 0), "num", "min"),
        ("Input Token", lambda r: r["grand_totals"].get("input_tokens", 0), "num", "min"),
        ("Output Token", lambda r: r["grand_totals"].get("output_tokens", 0), "num", "min"),
        ("Cache Read", lambda r: r["grand_totals"].get("cache_read_tokens", 0), "num", "max"),
        ("Cache Write", lambda r: r["grand_totals"].get("cache_write_tokens", 0), "num", "neutral"),
        ("总成本 (USD)", lambda r: r["grand_totals"].get("total_cost_usd", 0), "cost", "min"),
        ("代码行数 (LOC)", lambda r: r["grand_totals"].get("total_loc", 0), "num", "max"),
        ("文件数", lambda r: r["grand_totals"].get("total_files", 0), "num", "max"),
        ("AR 数", lambda r: r["grand_totals"].get("ar_count", 0), "num", "neutral"),
        ("总耗时", lambda r: r["grand_totals"].get("total_duration_seconds", 0), "time", "min"),
        ("API 调用", lambda r: r["grand_totals"].get("total_api_calls", 0), "num", "min"),
        ("迭代次数", lambda r: r["grand_totals"].get("total_iterations", 0), "num", "min"),
    ]:
        gt_rows += td_row(name, ext, unit, hl)

    # ─── 2. Stage Distribution Table ──────────────────────────────────────
    stage_rows = ""
    for sid in STAGES:
        name = STAGE_NAMES.get(sid, sid)
        valid_vals = [r.get("stage_aggregates", {}).get(sid, {}).get("total_tokens", 0) for r in runs]
        best = min(valid_vals) if valid_vals else None
        stage_rows += f"<tr><td><strong>{sid}</strong><br><small>{name}</small></td>"
        for r in runs:
            v = r.get("stage_aggregates", {}).get(sid, {}).get("total_tokens", 0)
            dur = r.get("stage_aggregates", {}).get(sid, {}).get("duration_seconds", 0)
            cls = ' class="best"' if best is not None and v == best and len(valid_vals) > 1 else ""
            stage_rows += f"<td{cls}>{fmt_val(v)}<br><small>{fmt_val(dur, 'time')}</small></td>"
        stage_rows += "</tr>\n"

    # ─── 3. Efficiency & Quality Table ────────────────────────────────────
    def _avg_metric(run, key):
        vals = [ar.get("metrics", {}).get(key, 0) for ar in run.get("ar_results", [])]
        vals = [v for v in vals if v and v > 0]
        return sum(vals) / len(vals) if vals else 0

    def _cache_rate(run):
        gt = run["grand_totals"]
        cache_read = gt.get("cache_read_tokens", 0)
        gross_input = gt.get("input_tokens", 0) + cache_read
        return cache_read / max(gross_input, 1)

    eff_rows = ""
    for name, ext, unit, hl in [
        ("ET-LOC (Token/行)", lambda r: _avg_metric(r, "ET_LOC"), "num", "min"),
        ("ET-TASK (Token/任务)", lambda r: _avg_metric(r, "ET_TASK"), "num", "min"),
        ("ET-TIME (Token/小时)", lambda r: _avg_metric(r, "ET_TIME"), "num", "min"),
        ("Cache 命中率", lambda r: _cache_rate(r), "pct", "max"),
        ("PT-DESIGN (设计占比)", lambda r: _avg_metric(r, "PT_DESIGN"), "pct", "neutral"),
        ("PT-DEV (开发占比)", lambda r: _avg_metric(r, "PT_DEV"), "pct", "neutral"),
        ("PT-VERIFY (验证占比)", lambda r: _avg_metric(r, "PT_VERIFY"), "pct", "neutral"),
    ]:
        eff_rows += td_row(name, ext, unit, hl)

    # ─── 4. AR Detail Table (per-AR comparison) ──────────────────────────
    ar_rows = ""
    ar_ids = set()
    for r in runs:
        for ar in r.get("ar_results", []):
            ar_ids.add(ar["ar_id"])
    ar_ids = sorted(ar_ids)

    for ar_id in ar_ids:
        ar_rows += f"<tr><td>{ar_id}</td>"
        for r in runs:
            ar_data = None
            for ar in r.get("ar_results", []):
                if ar["ar_id"] == ar_id:
                    ar_data = ar
                    break
            if ar_data:
                tok = ar_data["totals"]["total_tokens"]
                loc = ar_data["output"]["actual_loc"]
                ar_rows += f"<td>{fmt_val(tok)}<br><small>{fmt_val(loc)} LOC</small></td>"
            else:
                ar_rows += "<td>-</td>"
        ar_rows += "</tr>\n"

    # ─── 5. Executive Summary ─────────────────────────────────────────────
    run_list_html = ""
    for r in runs:
        gt = r["grand_totals"]
        lbl = run_label(r)
        run_list_html += (
            f"<li><b>{lbl}</b>: "
            f"{gt.get('total_tokens', 0):,} Tokens, "
            f"{gt.get('total_loc', 0):,} LOC, "
            f"{gt.get('total_files', 0)} files, "
            f"耗时 {fmt_val(gt.get('total_duration_seconds', 0), 'time')}, "
            f"成本 {fmt_val(gt.get('total_cost_usd', 0), 'cost')}</li>\n"
        )

    if runs:
        max_loc_run = max(runs, key=lambda r: r["grand_totals"].get("total_loc", 0))
        min_cost_run = min(runs, key=lambda r: r["grand_totals"].get("total_cost_usd", 1e6))
        best_eff_run = min(runs, key=lambda r: _avg_metric(r, "ET_LOC"))
        best_speed_run = min(runs, key=lambda r: r["grand_totals"].get("total_duration_seconds", 1e9))
        best_cache_run = max(runs, key=lambda r: _cache_rate(r))
    else:
        max_loc_run = min_cost_run = best_eff_run = best_speed_run = best_cache_run = runs[0]

    now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>SDD-TEE v5.0 跨轮次对比报告</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 1400px; margin: 0 auto; padding: 20px; background: #f8f9fa; color: #333; }}
  .section {{ background: #fff; padding: 25px; margin: 20px 0; border-radius: 12px; box-shadow: 0 2px 10px rgba(0,0,0,0.05); }}
  h1 {{ color: #1a73e8; border-bottom: 3px solid #1a73e8; padding-bottom: 10px; font-size: 2.2em; }}
  h2 {{ color: #1a73e8; border-left: 5px solid #1a73e8; padding-left: 15px; margin-top: 40px; }}
  h3 {{ color: #444; margin-top: 25px; border-bottom: 1px solid #eee; padding-bottom: 5px; }}
  table {{ border-collapse: collapse; width: 100%; margin: 15px 0; font-size: 0.92em; table-layout: fixed; }}
  th, td {{ border: 1px solid #eee; padding: 12px; text-align: right; word-wrap: break-word; }}
  th {{ background: #f1f3f4; color: #5f6368; text-align: center; font-weight: 600; position: sticky; top: 0; z-index: 10; }}
  td:first-child {{ text-align: left; font-weight: 600; background: #f8f9fa; width: 200px; color: #202124; }}
  tr:nth-child(even) {{ background: #fafafa; }}
  tr:hover {{ background: #f1f3f4; }}
  .best {{ background: #e6f4ea !important; font-weight: bold; color: #137333; }}
  .summary-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin: 20px 0; }}
  .summary-card {{ background: #fff; padding: 20px; border-radius: 10px; border: 1px solid #e0e0e0; border-top: 4px solid #1a73e8; }}
  .card-label {{ font-size: 0.9em; color: #70757a; text-transform: uppercase; letter-spacing: 1px; }}
  .card-val {{ font-size: 1.8em; font-weight: bold; color: #1a73e8; margin: 10px 0; }}
  .card-meta {{ font-size: 0.85em; color: #5f6368; line-height: 1.4; }}
  .failed-text {{ color: #d93025; font-style: italic; }}
  ul {{ line-height: 1.8; }}
  .footer {{ text-align: center; color: #999; font-size: 0.8em; margin-top: 40px; padding: 20px; }}
</style>
</head>
<body>
<h1>SDD-TEE v5.0 跨轮次对比报告 <small style="font-size:0.5em; font-weight:normal; color:#666;">{now}</small></h1>

<div class="section">
  <h2 style="margin-top:0; border:none; padding:0;">执行摘要 (Executive Summary)</h2>
  <h3>评测轮次 ({n})</h3>
  <ul>{run_list_html}</ul>

  <h3>关键极值</h3>
  <div class="summary-grid">
    <div class="summary-card">
      <div class="card-label">产出规模最优</div>
      <div class="card-val">{fmt_val(max_loc_run["grand_totals"].get("total_loc", 0))} LOC</div>
      <div class="card-meta"><strong>{run_label(max_loc_run)}</strong></div>
    </div>
    <div class="summary-card">
      <div class="card-label">经济性最优</div>
      <div class="card-val">{fmt_val(min_cost_run["grand_totals"].get("total_cost_usd", 0), "cost")}</div>
      <div class="card-meta"><strong>{run_label(min_cost_run)}</strong></div>
    </div>
    <div class="summary-card">
      <div class="card-label">执行速度最快</div>
      <div class="card-val">{fmt_val(best_speed_run["grand_totals"].get("total_duration_seconds", 0), 'time')}</div>
      <div class="card-meta"><strong>{run_label(best_speed_run)}</strong></div>
    </div>
    <div class="summary-card">
      <div class="card-label">Token 效率最高</div>
      <div class="card-val">{fmt_val(_avg_metric(best_eff_run, 'ET_LOC'), 'num')} Token/行</div>
      <div class="card-meta"><strong>{run_label(best_eff_run)}</strong></div>
    </div>
    <div class="summary-card">
      <div class="card-label">Cache 命中率最高</div>
      <div class="card-val">{fmt_val(_cache_rate(best_cache_run), 'pct')}</div>
      <div class="card-meta"><strong>{run_label(best_cache_run)}</strong></div>
    </div>
  </div>
</div>

<div class="section">
  <h2>1. 核心总量对比 (Grand Totals)</h2>
  <table><tr><th>指标</th>{headers}</tr>{gt_rows}</table>
</div>

<div class="section">
  <h2>2. 8 阶段 Token 分布 (ST-0 ~ ST-7)</h2>
  <p style="color:#666; font-size:0.85em;">上行为 Token 消耗，下行为耗时。绿色为最优值。</p>
  <table><tr><th>阶段</th>{headers}</tr>{stage_rows}</table>
</div>

<div class="section">
  <h2>3. 效率与质量指标</h2>
  <table><tr><th>指标</th>{headers}</tr>{eff_rows}</table>
</div>

<div class="section">
  <h2>4. AR 需求级对比</h2>
  <p style="color:#666; font-size:0.85em;">每个 AR 的 Token 消耗与代码行数。</p>
  <table><tr><th>AR</th>{headers}</tr>{ar_rows}</table>
</div>

<div class="section">
  <h2>5. 说明</h2>
  <ul>
    <li><b>ET-LOC</b>: 每生成 1 行代码平均消耗的 Token 数，越低越好</li>
    <li><b>Cache 命中率</b>: Cache Read / Input Tokens，反映上下文复用效率</li>
    <li><b>PT-DESIGN / PT-DEV / PT-VERIFY</b>: 设计/开发/验证阶段占比</li>
    <li>绿色高亮 = 该指标在成功运行中最优</li>
  </ul>
</div>

<div class="footer">
  SDD-TEE v5.0 Report | Generated {now} | SDD-TEE Benchmark Framework
</div>
</body></html>
"""


def main():
    parser = argparse.ArgumentParser(description="SDD-TEE v5.0 Cross-Run Comparison Report")
    parser.add_argument("--runs", nargs="*", help="Paths to *_full.json files")
    parser.add_argument("--output", default="results/reports/v5.0/compare_report.html")
    args = parser.parse_args()

    paths = args.runs if args.runs else glob.glob("results/runs/v5.0/*_full.json")
    print(f"[11] Processing {len(paths)} runs for comparison report...")

    runs = load_runs(paths)
    if not runs:
        print("[11] No valid runs found. Exiting.")
        return

    html = render_report(runs)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[11] Comparison report generated: {args.output}")


if __name__ == "__main__":
    main()
