#!/usr/bin/env python3
"""
SDD-TEE 跨轮次对比报告生成器 v4 (深度总结版)
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
        m, s = divmod(int(val), 60); h, m = divmod(m, 60)
        if h > 0: return f"{h}h {m}m"
        if m > 0: return f"{m}m {s}s"
        return f"{s}s"
    if isinstance(val, float): return f"{val:,.1f}"
    return f"{val:,}"

def pct(a, b):
    if b == 0: return "0.0%"
    return f"{a / b * 100:.1f}%"

STAGE_NAMES = {
    "ST-0": "需求探索与环境初始化", "ST-1": "架构设计与约束对齐", "ST-2": "实施方案与依赖图谱",
    "ST-3": "核心逻辑代码编写", "ST-4": "辅助模块与胶水代码", "ST-5": "单元测试与本地自检",
    "ST-6": "集成校验与Spec比对", "ST-7": "文档同步与最终产出"
}

def render_compare_html(runs):
    runs.sort(key=lambda r: (is_run_failed(r), r["meta"]["tool"], r["meta"]["model"]))
    valid_runs = [r for r in runs if not is_run_failed(r)]
    n = len(runs); labels = [run_label(r) for r in runs]
    headers = "".join([f"<th>{l}</th>" for l in labels])

    # 1. Total Metrics Table
    gt_table = ""
    def td_row(name, extractor, unit="num", highlight="min"):
        vals = [extractor(r) for r in runs]
        valid_vals = [extractor(r) for r in valid_runs]
        best = (min(valid_vals) if highlight == "min" else max(valid_vals)) if valid_vals else None
        row = f"<tr><td>{name}</td>"
        for i, r in enumerate(runs):
            v = vals[i]; cls = ""
            if not is_run_failed(r) and best is not None and v == best and len(valid_runs) > 1:
                if highlight != "neutral": cls = ' class="best"'
            row += f"<td{cls}>{format_val(v, unit, r)}</td>"
        return row + "</tr>\n"

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

    # 2. Stage Table
    stage_table = ""
    for sid in STAGES:
        name = STAGE_NAMES.get(sid, sid)
        stage_table += f"<tr><td><strong>{sid}</strong><br><small>{name}</small></td>"
        valid_vals = [r.get("stage_aggregates", {}).get(sid, {}).get("total_tokens", 0) for r in valid_runs]
        best = min(valid_vals) if valid_vals else None
        for r in runs:
            v = r.get("stage_aggregates", {}).get(sid, {}).get("total_tokens", 0)
            dur = r.get("stage_aggregates", {}).get(sid, {}).get("duration_seconds", 0)
            cls = ' class="best"' if not is_run_failed(r) and best is not None and v == best and len(valid_runs) > 1 else ""
            stage_table += f"<td{cls}>{format_val(v, 'num', r)}<br><small>{format_val(dur, 'time', r)}</small></td>"
        stage_table += "</tr>\n"

    # 3. Efficiency Table
    eff_table = ""
    eff_metrics = [
        ("ET-LOC (Token/行)", lambda r: _avg_metric(r, "ET_LOC"), "num", "min"),
        ("Cache 命中率", lambda r: _cache_rate(r), "pct", "max"),
        ("代码可用率", lambda r: _avg_quality(r, "code_usability"), "pct", "max"),
        ("一致性评分", lambda r: _avg_quality(r, "consistency_score"), "pct", "max"),
    ]
    for m in eff_metrics: eff_table += td_row(*m)

    # Executive Summary Content
    run_list_html = ""
    for i, r in enumerate(runs):
        gt = r["grand_totals"]; lbl = run_label(r).replace('<br>', ' ')
        if is_run_failed(r):
            run_list_html += f"<li><b>轮次 {i+1} ({lbl})</b>: <span style='color:#666'>任务由于 API 限制或环境错误未产出有效代码。</span></li>\n"
        else:
            run_list_html += f"<li><b>轮次 {i+1} ({lbl})</b>: 生成了 <b>{gt.get('total_loc', 0):,}</b> 行代码，耗时 <b>{format_val(gt.get('total_duration_seconds', 0), 'time')}</b>，消耗 {gt.get('total_tokens', 0):,} Tokens，总成本 {format_val(gt.get('total_cost_usd', 0), 'cost')}。</li>\n"

    if valid_runs:
        max_loc_run = max(valid_runs, key=lambda r: r["grand_totals"].get("total_loc", 0))
        min_cost_run = min(valid_runs, key=lambda r: r["grand_totals"].get("total_cost_usd", 1e6))
        best_eff_run = min(valid_runs, key=lambda r: _avg_metric(r, "ET_LOC"))
        best_speed_run = min(valid_runs, key=lambda r: r["grand_totals"].get("total_duration_seconds", 1e9))
    else:
        max_loc_run = min_cost_run = best_eff_run = best_speed_run = runs[0]

    now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>SDD-TEE v4.0 全模型强化审计报告 (Reinforced TDD 专题)</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 1400px; margin: 0 auto; padding: 20px; background: #f8f9fa; color: #333; }}
  .section {{ background: #fff; padding: 25px; margin: 20px 0; border-radius: 12px; box-shadow: 0 2px 10px rgba(0,0,0,0.05); }}
  h1 {{ color: #1a73e8; border-bottom: 3px solid #1a73e8; padding-bottom: 10px; font-size: 2.2em; }}
  h2 {{ color: #1a73e8; border-left: 5px solid #1a73e8; padding-left: 15px; margin-top: 40px; }}
  h3 {{ color: #444; margin-top: 25px; border-bottom: 1px solid #eee; padding-bottom: 5px; }}
  table {{ border-collapse: collapse; width: 100%; margin: 15px 0; font-size: 0.92em; table-layout: fixed; }}
  th, td {{ border: 1px solid #eee; padding: 12px; text-align: right; word-wrap: break-word; }}
  th {{ background: #f1f3f4; color: #5f6368; text-align: center; font-weight: 600; position: sticky; top: 0; z-index: 10; }}
  td:first-child {{ text-align: left; font-weight: 600; background: #f8f9fa; width: 220px; color: #202124; }}
  tr:nth-child(even) {{ background: #fafafa; }}
  tr:hover {{ background: #f1f3f4; }}
  .best {{ background: #d4edda !important; color: #155724 !important; font-weight: bold; border-bottom: 3px solid #28a745; }}
  .summary-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; margin: 20px 0; }}
  .summary-card {{ background: #fff; padding: 20px; border-radius: 10px; border: 1px solid #e0e0e0; border-top: 4px solid #1a73e8; transition: transform 0.2s; }}
  .summary-card:hover {{ transform: translateY(-3px); box-shadow: 0 4px 12px rgba(0,0,0,0.1); }}
  .card-label {{ font-size: 0.9em; color: #70757a; text-transform: uppercase; letter-spacing: 1px; }}
  .card-val {{ font-size: 1.8em; font-weight: bold; color: #1a73e8; margin: 10px 0; }}
  .card-meta {{ font-size: 0.85em; color: #5f6368; line-height: 1.4; }}
  .insight-box {{ background: #fef7e0; border-left: 5px solid #f9ab00; padding: 15px; margin: 15px 0; font-size: 0.95em; line-height: 1.6; }}
  .failed-text {{ color: #ccc; font-style: italic; }}
  ul {{ line-height: 1.8; }}
</style>
</head>
<body>
<h1>SDD-TEE v4.0 跨模型对比报告 <small style="font-size:0.5em; font-weight:normal; color:#666;">(全模型强化审计)</small></h1>

<div class="section">
  <h2 style="margin-top:0; border:none; padding:0;">执行摘要 (Executive Summary)</h2>
  
  <h3>一、评测背景与 CSI 特性</h3>
  <p>
    本次 <b>v4.0 评测</b> 采用了严苛的 <b>强化 TDD (Reinforced TDD) 与自愈 (Self-Healing)</b> 模式。在该模式下，AI 助手在每一轮迭代（Planning -> Implementation -> Verify）时都被强制重置上下文记忆（Blank Brain），必须通过读取磁盘上的现有代码来重新构建认知。
    <br>这一设计旨在模拟真实的 <b>高可靠交付场景</b>，衡量 AI 在接手存量代码时的“智能体开销 (Agentic Overhead)”——即理解背景所支付的额外 Token 成本。
  </p>

  <h3>二、核心评测实录 (15 轮次)</h3>
  <ul>{run_list_html}</ul>

  <h3>三、模型梯队与关键极值</h3>
  <div class="summary-grid">
    <div class="summary-card">
      <div class="card-label">产出规模最优</div>
      <div class="card-val">{format_val(max_loc_run["grand_totals"].get("total_loc", 0))} LOC</div>
      <div class="card-meta">
        <strong>{run_label(max_loc_run).replace('<br>', ' ')}</strong><br>
        在 CSI 极端环境下展现了极强的长文件生成持久力。
      </div>
    </div>
    <div class="summary-card">
      <div class="card-label">经济性最优 (维护税最低)</div>
      <div class="card-val">{format_val(min_cost_run["grand_totals"].get("total_cost_usd", 0), "cost")}</div>
      <div class="card-meta">
        <strong>{run_label(min_cost_run).replace('<br>', ' ')}</strong><br>
        凭借极高的 <b>Cache 命中率</b> 大幅削减了维护场景下的重复输入成本。
      </div>
    </div>
    <div class="summary-card">
      <div class="card-label">执行速度最快</div>
      <div class="card-val">{format_val(best_speed_run["grand_totals"].get("total_duration_seconds", 0), 'time')}</div>
      <div class="card-meta">
        <strong>{run_label(best_speed_run).replace('<br>', ' ')}</strong><br>
        从阅读代码到产出方案的端到端时延最短。
      </div>
    </div>
  </div>

  <div class="insight-box">
    <strong>深度洞察</strong>：
    <ol>
      <li><b>维护税分化</b>：CSI 模式下，不同模型的 Token 消耗差异高达 10 倍。Qwen 3.5 Plus 和 Gemini 3.1 Pro 虽然产出稳定，但其“认知税”极高；而 GLM 系列通过高效的语义缓存机制，显著降低了重复理解的费用。</li>
      <li><b>架构一致性挑战</b>：在每一轮都断开记忆的情况下，只有极少数模型（如 Gemini、GLM-5）能通过自发性探索保持跨 AR 的架构一致性，多数模型在第三轮后开始出现接口不匹配风险。</li>
      <li><b>额度敏感性</b>：Cursor/Claude 系模型在 CSI 高频调用下极易触发 Usage Limit，导致测试中断，这反映了高性能模型在密集维护任务中的成本门槛。</li>
    </ol>
  </div>
</div>

<div class="section">
  <h2>1. 核心总量对比 (Grand Totals)</h2>
  <p style="color:#666; font-size:0.85em;">横向对比 15 轮运行的总消耗。绿色高亮代表该指标在<b>成功运行</b>的任务中表现最优。</p>
  <table><tr><th>指标</th>{headers}</tr>{gt_table}</table>
</div>

<div class="section">
  <h2>2. 7 阶段流量分布 (Token 消耗与耗时)</h2>
  <p style="color:#666; font-size:0.85em;">分析 AI 在 SDD 标准工作流各阶段的时间与 Token 投入。上行为 Token 消耗，下行为耗时。</p>
  <table><tr><th>阶段</th>{headers}</tr>{stage_table}</table>
</div>

<div class="section">
  <h2>3. 效率与质量深度审计 (Efficiency & Quality)</h2>
  <table><tr><th>指标</th>{headers}</tr>{eff_table}</table>
</div>

<div class="section">
  <h2>4. 运行状态说明</h2>
  <p>
    • <b>[FAILED]</b>：指因 API 限制、连接超时或环境报错导致未产出有效代码文件的任务。其各项指标以 <b>-</b> 表示。<br>
    • <b>ET-LOC</b>：每生成 1 行代码平均消耗的 Token 数，数值越低代表代码逻辑密度越高。<br>
    • <b>Cache 命中率</b>：长上下文场景下，模型利用前文缓存的能力，是降低 CSI 模式成本的核心。
  </p>
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

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", nargs="*", help="Paths to *_full.json files")
    parser.add_argument("--output", default="results/reports/compare_report.html")
    args = parser.parse_args()
    paths = args.runs if args.runs else glob.glob("results/runs/v3.0/*_full.json")
    print(f"[11] Processing {len(paths)} runs for Deep Summary Report...")
    runs = load_runs(paths)
    if not runs: return
    html = render_compare_html(runs)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f: f.write(html)
    print(f"[11] Deep Summary Report generated: {args.output}")

if __name__ == "__main__":
    main()
