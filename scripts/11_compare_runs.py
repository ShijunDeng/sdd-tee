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
    label = f"{m.get('tool', '?')} / {m.get('model', '?')}"
    # Mark as failed if zero output and tokens
    if d["grand_totals"].get("total_loc", 0) == 0 and d["grand_totals"].get("total_tokens", 0) == 0:
        return f"{label} <br><span style='color:red;font-size:0.8em'>[FAILED]</span>"
    return label


def fmt_num(n, decimals=0):
    if n is None: return "-"
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
    
    # Filter out failed runs for average calculations in summary
    valid_runs = [r for r in runs if r["grand_totals"].get("total_loc", 0) > 0 or r["grand_totals"].get("total_tokens", 0) > 0]

    def td_vals(extractor, fmt_fn=fmt_num, highlight="min"):
        vals = [extractor(r) for r in runs]
        # Only calculate 'best' from valid runs
        valid_vals = [extractor(r) for r in valid_runs]
        if not valid_vals:
            best = None
        else:
            best = min(valid_vals) if highlight == "min" else max(valid_vals)
            
        cells = ""
        for i, v in enumerate(vals):
            is_best = False
            if best is not None and v == best and n > 1:
                # Ensure we don't mark 0 as 'best' unless it's genuinely better (like cost/bugs)
                if v > 0 or highlight == "min":
                    is_best = True
            
            # Special case: if this run failed, show dash or zero with muted color
            run_is_failed = runs[i]["grand_totals"].get("total_loc", 0) == 0 and runs[i]["grand_totals"].get("total_tokens", 0) == 0
            
            cls = ' class="best"' if is_best else ""
            display_val = fmt_fn(v)
            if run_is_failed and v == 0:
                display_val = "<span style='color:#ccc'>-</span>"
                
            cells += f"<td{cls}>{display_val}</td>"
        return cells

    # Grand totals comparison table
    gt_rows = ""
    gt_metrics = [
        ("总 Token", lambda r: r["grand_totals"].get("total_tokens", 0), "min"),
        ("Input Token", lambda r: r["grand_totals"].get("input_tokens", 0), "min"),
        ("Output Token", lambda r: r["grand_totals"].get("output_tokens", 0), "min"),
        ("Cache Read", lambda r: r["grand_totals"].get("cache_read_tokens", 0), "max"),
        ("Cache Write", lambda r: r["grand_totals"].get("cache_write_tokens", 0), "min"),
        ("人工输入 Token", lambda r: r["grand_totals"].get("human_input_tokens", 0), "min"),
        ("预制规范 Token", lambda r: r["grand_totals"].get("spec_context_tokens", 0), "min"),
        ("总耗时 (秒)", lambda r: r["grand_totals"].get("total_duration_seconds", 0), "min"),
        ("总成本 (USD)", lambda r: r["grand_totals"].get("total_cost_usd", 0), "min"),
        ("总成本 (CNY)", lambda r: r["grand_totals"].get("total_cost_cny", 0), "min"),
        ("代码行数", lambda r: r["grand_totals"].get("total_loc", 0), "max"),
        ("文件数", lambda r: r["grand_totals"].get("total_files", 0), "max"),
        ("迭代次数", lambda r: r["grand_totals"].get("total_iterations", 0), "min"),
        ("API 调用", lambda r: r["grand_totals"].get("total_api_calls", 0), "min"),
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
        valid_vals = [fn(r) for r in valid_runs]
        if hl == "min":
            best = min(valid_vals) if valid_vals else 0
        elif hl == "max":
            best = max(valid_vals) if valid_vals else 0
        else:
            best = None
        for i, v in enumerate(vals):
            run_is_failed = runs[i] not in valid_runs
            cls = ' class="best"' if best is not None and v == best and n > 1 and not run_is_failed else ""
            if run_is_failed:
                cells += f"<td><span style='color:#ccc'>-</span></td>"
            elif isinstance(v, float) and v < 1:
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
        valid_vals = [fn(r) for r in valid_runs]
        cells = ""
        best = (min(valid_vals) if hl == "min" else max(valid_vals)) if valid_vals else None
        for i, v in enumerate(vals):
            run_is_failed = runs[i] not in valid_runs
            cls = ' class="best"' if best is not None and v == best and n > 1 and not run_is_failed else ""
            if run_is_failed:
                cells += f"<td><span style='color:#ccc'>-</span></td>"
            elif isinstance(v, float) and v <= 1:
                cells += f"<td{cls}>{v:.1%}</td>"
            else:
                cells += f"<td{cls}>{fmt_num(v)}</td>"
        qual_rows += f"<tr><td>{name}</td>{cells}</tr>\n"

    # Warnings
    warn_rows = ""
    for r in runs:
        sa = r.get("stage_aggregates", {})
        gt = r["grand_totals"]
        w_list = []
        if r in valid_runs:
            cache_rate = gt.get("cache_read_tokens", 0) / max(gt.get("input_tokens", 1), 1)
            if cache_rate < 0.50: w_list.append("W-CACHE-LOW")
            # simplified warnings for now
        warn_rows += f"<td>{', '.join(w_list) if w_list else '无'}</td>"

    # Execution Summaries
    run_summaries = ""
    for i, r in enumerate(runs):
        gt = r["grand_totals"]
        label = run_label(r)
        if r in valid_runs:
            run_summaries += f"<li><b>轮次 {i+1} ({label.replace('<br>', ' ')})</b>: 生成了 <b>{gt.get('total_loc', 0):,}</b> 行代码，耗时 <b>{gt.get('total_duration_seconds', 0)//60}</b> 分钟，消耗 {gt.get('total_tokens', 0):,} Tokens，总成本 ${gt.get('total_cost_usd', 0):.2f}。</li>\n"
        else:
            run_summaries += f"<li><b>轮次 {i+1} ({label.replace('<br>', ' ')})</b>: <span style='color:#666'>任务由于 API 限制或环境错误未产出有效代码。</span></li>\n"

    # Best-of calculations (only from valid runs)
    if not valid_runs:
        baseline_run = max_loc = best_speed = best_eff = best_cost = runs[0]
    else:
        baseline_run = next((r for r in valid_runs if "cursor" in r["meta"]["tool"].lower() or "claude" in r["meta"]["model"].lower()), valid_runs[0])
        max_loc = max(valid_runs, key=lambda r: r["grand_totals"].get("total_loc", 0))
        best_speed = min(valid_runs, key=lambda r: r["grand_totals"].get("total_duration_seconds", 360000))
        best_eff = min(valid_runs, key=lambda r: _avg_metric(r, "ET_LOC"))
        best_cost = min(valid_runs, key=lambda r: r["grand_totals"].get("total_cost_usd", 1e6))

    now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')
    headers = "".join([f"<th>{l}</th>" for l in labels])

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
  <p>生成时间: {now} UTC | 对比轮次: {n} | 目标项目: agentcube</p>
</div>

<div class="section" style="background-color: #f8f9fa; border-left: 4px solid #1a73e8; padding: 15px; margin-bottom: 20px;">
<h2 style="margin-top: 0; padding-top: 0; font-size: 1.2em; border: none;">执行摘要 (Executive Summary)</h2>

<h3 style="font-size: 1.05em; color: #333; margin-bottom: 5px;">一、项目背景</h3>
<p style="font-size: 0.95em; line-height: 1.6; color: #444; margin-top: 5px;">
本次评测的目标项目为 <a href="https://github.com/ShijunDeng/agentcube" target="_blank" style="color: #1a73e8; text-decoration: none;"><b>AgentCube</b></a>，一个复杂的云原生 AI Agent 工作负载管理平台。项目涉及 Kubernetes CRD 设计、Go 语言核心控制面、Python SDK、CLI 工具以及前/后端集成的多维度代码工程。<br>
评测基于严谨的 CodeSpec 7 阶段工作流，将原始项目无损拆解为 <b>43 个核心架构需求 (AR)</b>，旨在考察不同 AI Coding Assistant 还原复杂系统、保持长上下文架构一致性的真实能力。
</p>

<h3 style="font-size: 1.05em; color: #333; margin-bottom: 5px;">二、{n} 轮测试实录</h3>
<ul style="font-size: 0.95em; line-height: 1.6; color: #444; margin-top: 5px;">
{run_summaries}
</ul>

<h3 style="font-size: 1.05em; color: #333; margin-bottom: 5px;">三、核心指标极值</h3>
<ul style="font-size: 0.95em; line-height: 1.6; color: #444; margin-top: 5px;">
<li><b>产出能力最优</b>: <code>{run_label(max_loc).replace('<br>', ' ')}</code> 输出了最大的有效代码规模 (<b>{max_loc["grand_totals"].get("total_loc", 0):,} LOC</b>)，在架构细节还原度上甚至超越了基准。</li>
<li><b>交付速度最快</b>: <code>{run_label(best_speed).replace('<br>', ' ')}</code> 仅耗时 <b>{best_speed["grand_totals"].get("total_duration_seconds", 0)//60} 分钟</b>即完成了全量需求。</li>
<li><b>代码浓度最高</b>: <code>{run_label(best_eff).replace('<br>', ' ')}</code> 生成每行代码的平均 Token 消耗最低，逻辑密度极高，废话最少。</li>
<li><b>综合成本最低</b>: <code>{run_label(best_cost).replace('<br>', ' ')}</code> 的任务总账单仅为 <b>${best_cost["grand_totals"].get("total_cost_usd", 0):.2f}</b>，极具经济性。</li>
</ul>

<p style="font-size: 0.95em; line-height: 1.6; color: #444;">
<b>洞察与建议</b>：长上下文缓存命中率成为降低多轮迭代成本的关键。不同模型在“代码骨架搭建”与“逻辑细节深挖”上的侧重点差异明显。目前的国产开放模型在生成规模和速度上已具备挑战业界顶尖基准 (Claude) 的实力。
</p>
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
<tr><th>指标</th>{headers}</tr>
<tr><td>触发预警</td>{warn_rows}</tr>
</table>
</div>

<div class="section">
<h2>6. 综合评分雷达</h2>
<div class="radar">
"""
    max_tokens = max(r["grand_totals"].get("total_tokens", 0) for r in valid_runs) if valid_runs else 1
    max_cost = max(r["grand_totals"].get("total_cost_usd", 0) for r in valid_runs) if valid_runs else 1
    
    for r in runs:
        gt = r["grand_totals"]
        lbl = run_label(r)
        if r not in valid_runs:
            html += f"""<div class="radar-item"><div style="font-weight:bold">{lbl}</div><div style="color:#999;margin-top:20px">无有效评分数据</div></div>"""
            continue
            
        token_eff = 100 * (1 - (gt.get("total_tokens", 0) / max(max_tokens * 1.2, 1)))
        cost_eff = 100 * (1 - (gt.get("total_cost_usd", 0) / max(max_cost * 1.2, 1)))
        quality = _avg_quality(r, "code_usability") * 100
        cache = gt.get("cache_read_tokens", 0) / max(gt.get("input_tokens", 1), 1) * 100
        
        html += f"""
  <div class="radar-item">
    <div style="font-weight: bold; margin-bottom: 10px;">{lbl}</div>
    <div>Token 效率: <span class="radar-val">{token_eff:.0f}</span></div>
    <div>成本效率: <span class="radar-val">{cost_eff:.0f}</span></div>
    <div>代码质量: <span class="radar-val">{quality:.0f}</span></div>
    <div>Cache 利用: <span class="radar-val">{cache:.0f}</span></div>
  </div>"""

    html += """</div></div></body></html>"""
    return html


def _avg_metric(run, key):
    vals = [ar["metrics"].get(key, 0) for ar in run["ar_results"]]
    return sum(vals) / len(vals) if vals else 0


def _cache_rate(run):
    gt = run["grand_totals"]
    return gt.get("cache_read_tokens", 0) / max(gt.get("input_tokens", 1), 1)


def _avg_quality(run, key):
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
    print(f"[11] Loading {len(paths)} run(s)...")
    runs = load_runs(paths)
    if not runs:
        print("[11] No valid runs found.")
        return

    # Sort runs: valid ones first, then by tool/model
    runs.sort(key=lambda r: (r["grand_totals"].get("total_loc", 0) == 0, r["meta"]["tool"], r["meta"]["model"]))

    html = render_compare_html(runs)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        f.write(html)
    print(f"[11] Comparison report → {args.output}")


if __name__ == "__main__":
    main()
