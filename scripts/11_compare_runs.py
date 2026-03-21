#!/usr/bin/env python3
"""
SDD-TEE 跨轮次对比报告生成器

从 results/runs/ 中读取多轮 *_full.json 数据，生成横向对比 HTML 报告。
支持 Tool × Model 多维度比较。

Usage:
  python3 scripts/11_compare_runs.py                          # 自动扫描 results/runs/
  python3 scripts/11_compare_runs.py --runs a_full.json b_full.json
  python3 scripts/11_compare_runs.py --output results/reports/compare.html
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
        except (json.JSONDecodeError, KeyError):
            print(f"  ⚠ Skipping invalid file: {p}")
    return runs


def run_label(d):
    m = d.get("meta", {})
    return f"{m.get('tool', '?')} / {m.get('model', '?')}"


def fmt_num(n, decimals=0):
    if isinstance(n, float):
        if decimals > 0:
            return f"{n:,.{decimals}f}"
        return f"{n:,.0f}"
    return f"{n:,}"


def pct(a, b):
    if b == 0:
        return "N/A"
    return f"{a / b * 100:.1f}%"


def render_compare_html(runs):
    labels = [run_label(r) for r in runs]
    n = len(runs)

    def td_vals(extractor, fmt_fn=fmt_num, highlight="min"):
        vals = [extractor(r) for r in runs]
        best = min(vals) if highlight == "min" else max(vals)
        cells = ""
        for v in vals:
            cls = ' class="best"' if v == best and n > 1 else ""
            cells += f"<td{cls}>{fmt_fn(v)}</td>"
        return cells

    # Grand totals comparison table
    gt_rows = ""
    gt_metrics = [
        ("总 Token", lambda r: r["grand_totals"]["total_tokens"], "min"),
        ("Input Token", lambda r: r["grand_totals"]["input_tokens"], "min"),
        ("Output Token", lambda r: r["grand_totals"]["output_tokens"], "min"),
        ("Cache Read", lambda r: r["grand_totals"]["cache_read_tokens"], "max"),
        ("Cache Write", lambda r: r["grand_totals"]["cache_write_tokens"], "min"),
        ("人工输入 Token", lambda r: r["grand_totals"]["human_input_tokens"], "min"),
        ("预制规范 Token", lambda r: r["grand_totals"]["spec_context_tokens"], "min"),
        ("总耗时 (秒)", lambda r: r["grand_totals"]["total_duration_seconds"], "min"),
        ("总成本 (USD)", lambda r: r["grand_totals"]["total_cost_usd"], "min"),
        ("总成本 (CNY)", lambda r: r["grand_totals"]["total_cost_cny"], "min"),
        ("代码行数", lambda r: r["grand_totals"]["total_loc"], "max"),
        ("文件数", lambda r: r["grand_totals"]["total_files"], "max"),
        ("迭代次数", lambda r: r["grand_totals"]["total_iterations"], "min"),
        ("API 调用", lambda r: r["grand_totals"]["total_api_calls"], "min"),
    ]
    for name, fn, hl in gt_metrics:
        gt_rows += f"<tr><td>{name}</td>{td_vals(fn, highlight=hl)}</tr>\n"

    # Stage comparison
    stage_rows = ""
    for sid in STAGES:
        stage_rows += f"<tr><td><strong>{sid}</strong></td>"
        for r in runs:
            sa = r.get("stage_aggregates", {}).get(sid, {})
            tok = sa.get("total_tokens", 0)
            dur = sa.get("duration_seconds", 0)
            stage_rows += f"<td>{fmt_num(tok)}<br><small>{dur}s</small></td>"
        stage_rows += "</tr>\n"

    # Efficiency metrics
    eff_rows = ""
    eff_metrics = [
        ("ET-LOC (Token/行)", lambda r: _avg_metric(r, "ET_LOC"), "min"),
        ("ET-FILE (Token/文件)", lambda r: _avg_metric(r, "ET_FILE"), "min"),
        ("ET-TASK (Token/任务)", lambda r: _avg_metric(r, "ET_TASK"), "min"),
        ("ET-AR (Token/AR)", lambda r: _avg_metric(r, "ET_AR"), "min"),
        ("ET-COST-LOC ($/千行)", lambda r: _avg_metric(r, "ET_COST_LOC"), "min"),
        ("Cache 命中率", lambda r: _cache_rate(r), "max"),
        ("PT-DEV (开发占比)", lambda r: _avg_metric(r, "PT_DEV"), "neutral"),
        ("PT-DESIGN (设计占比)", lambda r: _avg_metric(r, "PT_DESIGN"), "neutral"),
    ]
    for name, fn, hl in eff_metrics:
        vals = [fn(r) for r in runs]
        cells = ""
        if hl == "min":
            best = min(vals) if vals else 0
        elif hl == "max":
            best = max(vals) if vals else 0
        else:
            best = None
        for v in vals:
            cls = ' class="best"' if best is not None and v == best and n > 1 else ""
            if isinstance(v, float) and v < 1:
                cells += f"<td{cls}>{v:.1%}</td>"
            else:
                cells += f"<td{cls}>{fmt_num(v, 1)}</td>"
        eff_rows += f"<tr><td>{name}</td>{cells}</tr>\n"

    # Quality metrics
    qual_rows = ""
    qual_metrics = [
        ("代码可用率", lambda r: _avg_quality(r, "code_usability"), "max"),
        ("一致性评分", lambda r: _avg_quality(r, "consistency_score"), "max"),
        ("测试覆盖率", lambda r: _avg_quality(r, "test_coverage"), "max"),
        ("Bug 数", lambda r: _sum_quality(r, "bugs_found"), "min"),
    ]
    for name, fn, hl in qual_metrics:
        vals = [fn(r) for r in runs]
        cells = ""
        best = min(vals) if hl == "min" else max(vals)
        for v in vals:
            cls = ' class="best"' if v == best and n > 1 else ""
            if isinstance(v, float) and v <= 1:
                cells += f"<td{cls}>{v:.1%}</td>"
            else:
                cells += f"<td{cls}>{fmt_num(v)}</td>"
        qual_rows += f"<tr><td>{name}</td>{cells}</tr>\n"

    # Warnings summary
    warn_rows = ""
    for r in runs:
        gt = r["grand_totals"]
        sa = r.get("stage_aggregates", {})
        warnings = []
        cache_rate = gt.get("cache_read_tokens", 0) / max(gt.get("input_tokens", 1), 1)
        if cache_rate < 0.50:
            warnings.append("W-CACHE-LOW")
        dev_rate = sa.get("ST-5", {}).get("total_tokens", 0) / max(gt.get("total_tokens", 1), 1)
        if dev_rate > 0.80:
            warnings.append("W-DEV-SKEW")
        usability = _avg_quality(r, "code_usability")
        if usability < 0.75:
            warnings.append("W-USABILITY")
        warn_rows += f"<td>{'<br>'.join(warnings) if warnings else '无'}</td>"

    headers = "".join(f"<th>{l}</th>" for l in labels)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>SDD-TEE 跨轮次对比报告</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         max-width: 1200px; margin: 0 auto; padding: 20px; background: #f8f9fa; color: #333; }}
  h1 {{ color: #1a73e8; border-bottom: 3px solid #1a73e8; padding-bottom: 10px; }}
  h2 {{ color: #333; margin-top: 30px; border-left: 4px solid #1a73e8; padding-left: 10px; }}
  table {{ border-collapse: collapse; width: 100%; margin: 15px 0; background: #fff;
           box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
  th, td {{ border: 1px solid #ddd; padding: 8px 12px; text-align: right; }}
  th {{ background: #1a73e8; color: #fff; text-align: center; }}
  td:first-child {{ text-align: left; font-weight: 500; background: #f0f4ff; }}
  tr:nth-child(even) {{ background: #f8f9fa; }}
  .best {{ background: #e6f4ea !important; font-weight: bold; color: #137333; }}
  .meta {{ color: #666; font-size: 0.9em; margin-bottom: 20px; }}
  .section {{ background: #fff; padding: 20px; margin: 15px 0; border-radius: 8px;
              box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
  .radar {{ display: flex; flex-wrap: wrap; gap: 10px; justify-content: center; }}
  .radar-item {{ flex: 1; min-width: 200px; max-width: 300px; text-align: center;
                 padding: 15px; background: #f0f4ff; border-radius: 8px; }}
  .radar-val {{ font-size: 1.8em; font-weight: bold; color: #1a73e8; }}
  .radar-label {{ font-size: 0.85em; color: #666; }}
  small {{ color: #999; }}
</style>
</head>
<body>
<h1>SDD-TEE 跨轮次对比报告</h1>
<div class="meta">
  <p>生成时间: {now} | 对比轮次: {n} | 目标项目: agentcube</p>
</div>

<div class="section">
<h2>1. 总量对比</h2>
<table>
<tr><th>指标</th>{headers}</tr>
{gt_rows}
</table>
</div>

<div class="section">
<h2>2. 阶段分布对比</h2>
<table>
<tr><th>阶段</th>{headers}</tr>
{stage_rows}
</table>
</div>

<div class="section">
<h2>3. 效率指标对比</h2>
<table>
<tr><th>指标</th>{headers}</tr>
{eff_rows}
</table>
</div>

<div class="section">
<h2>4. 质量指标对比</h2>
<table>
<tr><th>指标</th>{headers}</tr>
{qual_rows}
</table>
</div>

<div class="section">
<h2>5. 预警汇总</h2>
<table>
<tr><th>轮次</th>{headers}</tr>
<tr><td>触发预警</td>{warn_rows}</tr>
</table>
</div>

<div class="section">
<h2>6. 综合评分雷达</h2>
<div class="radar">
"""

    for r in runs:
        gt = r["grand_totals"]
        lbl = run_label(r)
        # Normalize scores: lower is better for token/cost, higher is better for quality
        token_eff = min(100, max(0, 100 - gt["total_tokens"] / 50000))
        cost_eff = min(100, max(0, 100 - gt["total_cost_usd"] * 5))
        quality = _avg_quality(r, "code_usability") * 100
        cache = gt.get("cache_read_tokens", 0) / max(gt.get("input_tokens", 1), 1) * 100
        speed = min(100, max(0, 100 - gt["total_duration_seconds"] / 360))

        html += f"""
  <div class="radar-item">
    <div style="font-weight: bold; margin-bottom: 10px;">{lbl}</div>
    <div>Token 效率: <span class="radar-val">{token_eff:.0f}</span></div>
    <div>成本效率: <span class="radar-val">{cost_eff:.0f}</span></div>
    <div>代码质量: <span class="radar-val">{quality:.0f}</span></div>
    <div>Cache 利用: <span class="radar-val">{cache:.0f}</span></div>
    <div>执行速度: <span class="radar-val">{speed:.0f}</span></div>
  </div>"""

    html += """
</div>
</div>

<div class="section">
<h2>7. 说明</h2>
<ul>
  <li>绿色高亮 = 该列最优值（对比列 ≥ 2 时生效）</li>
  <li>Token 效率、成本效率、执行速度：越低越好 → 分越高</li>
  <li>代码质量、Cache 利用：越高越好</li>
  <li>数据来源: SDD-TEE 评测框架 (CodeSpec 7-Stage × OpenSpec OPSX)</li>
  <li>测试目标: <a href="https://github.com/ShijunDeng/agentcube">agentcube</a></li>
</ul>
</div>

</body>
</html>"""
    return html


def _avg_metric(r, key):
    ars = r.get("ar_results", [])
    if not ars:
        return 0
    vals = [ar.get("metrics", {}).get(key, 0) for ar in ars]
    return sum(vals) / len(vals)


def _avg_quality(r, key):
    ars = r.get("ar_results", [])
    if not ars:
        return 0
    vals = [ar.get("quality", {}).get(key, 0) for ar in ars]
    return sum(vals) / len(vals)


def _sum_quality(r, key):
    return sum(ar.get("quality", {}).get(key, 0) for ar in r.get("ar_results", []))


def _cache_rate(r):
    gt = r.get("grand_totals", {})
    return gt.get("cache_read_tokens", 0) / max(gt.get("input_tokens", 1), 1)


def main():
    parser = argparse.ArgumentParser(description="SDD-TEE Cross-Run Comparison Report")
    parser.add_argument("--runs", nargs="*", help="Paths to *_full.json files")
    parser.add_argument("--output", default=None, help="Output HTML path")
    parser.add_argument("--data-output", default=None, help="Output comparison JSON")
    args = parser.parse_args()

    if args.runs:
        paths = args.runs
    else:
        pattern = str(BASE / "results" / "runs" / "*_full.json")
        paths = sorted(glob.glob(pattern))

    if not paths:
        print("No *_full.json files found. Run evaluations first.")
        sys.exit(1)

    print(f"[11] Loading {len(paths)} run(s)...")
    runs = load_runs(paths)
    if not runs:
        print("  No valid run data found.")
        sys.exit(1)

    for r in runs:
        print(f"  • {run_label(r)} ({r['_source']})")

    html = render_compare_html(runs)

    out_path = args.output or str(BASE / "results" / "reports" / "compare_report.html")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\n[11] Comparison report → {out_path}")

    if args.data_output:
        summary = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "runs": [{
                "label": run_label(r),
                "source": r["_source"],
                "tool": r["meta"].get("tool"),
                "model": r["meta"].get("model"),
                "total_tokens": r["grand_totals"]["total_tokens"],
                "total_cost_usd": r["grand_totals"]["total_cost_usd"],
                "total_loc": r["grand_totals"]["total_loc"],
                "total_duration": r["grand_totals"]["total_duration_seconds"],
                "cache_rate": _cache_rate(r),
            } for r in runs],
        }
        with open(args.data_output, "w") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        print(f"[11] Comparison data  → {args.data_output}")


if __name__ == "__main__":
    main()
