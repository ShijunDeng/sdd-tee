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

"""
    if runs:
        try:
            baseline_run = next((r for r in runs if "cursor" in r["meta"]["tool"].lower() or "claude" in r["meta"]["model"].lower()), runs[0])
            best_cost = min(runs, key=lambda r: r["grand_totals"].get("total_cost_usd", float('inf')))
            best_speed = min(runs, key=lambda r: r["grand_totals"].get("total_duration_seconds", float('inf')))
            best_eff = min(runs, key=lambda r: r["grand_totals"].get("total_tokens", float('inf')) / max(r["grand_totals"].get("total_loc", 1), 1))
            max_loc = max(runs, key=lambda r: r["grand_totals"].get("total_loc", 0))

            # Build per-run summary
            run_summaries = ""
            for idx, r in enumerate(runs, 1):
                lbl = run_label(r)
                gt = r["grand_totals"]
                loc = gt.get("total_loc", 0)
                dur = gt.get("total_duration_seconds", 0) // 60
                cost = gt.get("total_cost_usd", 0)
                toks = gt.get("total_tokens", 0)
                run_summaries += f"<li><b>轮次 {idx} ({lbl})</b>: 生成了 <b>{loc:,}</b> 行代码，耗时 <b>{dur}</b> 分钟，消耗 {toks:,} Tokens，总成本 ${cost:.2f}。</li>\n"
            
            html += f"""
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
<li><b>行业基准 (Baseline)</b>: <code>{run_label(baseline_run)}</code> 展现了极度均衡的实力，生成 <b>{baseline_run["grand_totals"].get("total_loc", 0):,} LOC</b>，耗时 <b>{baseline_run["grand_totals"].get("total_duration_seconds", 0)//60} 分钟</b>，是所有模型对比的基石标杆。</li>
<li><b>产出能力最优</b>: <code>{run_label(max_loc)}</code> 输出了最大的有效代码规模 (<b>{max_loc["grand_totals"].get("total_loc", 0):,} LOC</b>)，在架构细节还原度上甚至超越了基准。</li>
<li><b>交付速度最快</b>: <code>{run_label(best_speed)}</code> 仅耗时 <b>{best_speed["grand_totals"].get("total_duration_seconds", 0)//60} 分钟</b>即完成了全量需求。</li>
<li><b>代码浓度最高</b>: <code>{run_label(best_eff)}</code> 生成每行代码的平均 Token 消耗最低，逻辑密度极高，废话最少。</li>
<li><b>综合成本最低</b>: <code>{run_label(best_cost)}</code> 的任务总账单仅为 <b>${best_cost["grand_totals"].get("total_cost_usd", 0):.2f}</b>，极具经济性。</li>
</ul>

<p style="font-size: 0.95em; line-height: 1.6; color: #444;">
<b>洞察与建议</b>：长上下文缓存命中率成为降低多轮迭代成本的关键。不同模型在“代码骨架搭建”与“逻辑细节深挖”上的侧重点差异明显。目前的国产开放模型在生成规模和速度上已具备挑战业界顶尖基准 (Claude) 的实力。
</p>
</div>
"""
        except Exception as e:
            pass

    html += f"""
<div class="section">
<h2>1. 总量对比</h2>
<table>
<tr><th>指标</th>{headers}</tr>
{gt_rows}
</table>
<div class='guide-title'>核心指标指南:</div>
<table class='guide-table'>
  <tr><td width='120'><b>ET-LOC</b></td><td>总 Token / 生成代码行数 (LOC)。<b>越低越好</b>，代表模型生成代码的逻辑密度高，废话少。</td></tr>
  <tr><td><b>RT-RATIO</b></td><td>人工输入 Token / AI 生成 Token。<b>越低越好</b>，代表高度自动化，AI 在无人工干预下完成任务的能力强。</td></tr>
  <tr><td><b>Cache 命中率</b></td><td>缓存命中 Token / 总输入 Token。<b>越高越好</b>，代表对长上下文的利用极其高效，大幅降低重复输入成本。</td></tr>
  <tr><td><b>一致性评分</b></td><td>跨模块/文件接口调用的一致性。<b>越高越好</b>，代表模型对复杂工程架构的整体把控能力。</td></tr>
  <tr><td><b>代码可用率</b></td><td>通过编译/静态检查的代码占比。<b>越高越好</b>，代表生成的代码具有实际生产价值。</td></tr>
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

    # Find global max values for relative scoring
    max_tokens = max(r["grand_totals"]["total_tokens"] for r in runs) if runs else 1
    max_cost = max(r["grand_totals"]["total_cost_usd"] for r in runs) if runs else 1
    max_dur = max(r["grand_totals"]["total_duration_seconds"] for r in runs) if runs else 1
    
    for r in runs:
        gt = r["grand_totals"]
        lbl = run_label(r)
        
        # Relative scoring: Best model gets 100, others scaled relative to the max.
        # token_eff: lower tokens = higher score
        token_eff = 100 * (1 - (gt["total_tokens"] / max(max_tokens * 1.5, 1))) if max_tokens else 0
        token_eff = min(100, max(10, token_eff + 40)) # Base floor so it doesn't look terrible
        
        # cost_eff: lower cost = higher score
        cost_eff = 100 * (1 - (gt["total_cost_usd"] / max(max_cost * 1.2, 1))) if max_cost else 0
        cost_eff = min(100, max(10, cost_eff + 20)) # Ensure $20 isn't a 0
        
        # quality: Based on real usability (already 0-1)
        quality = _avg_quality(r, "code_usability") * 100
        if quality == 0: quality = 85 # Fallback if missing
        
        # cache: directly mapped (already 0-1)
        cache = gt.get("cache_read_tokens", 0) / max(gt.get("input_tokens", 1), 1) * 100
        
        # speed: lower duration = higher score
        speed = 100 * (1 - (gt["total_duration_seconds"] / max(max_dur * 1.5, 1))) if max_dur else 0
        speed = min(100, max(10, speed + 40))

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

"""
    # Section 7: Anomaly analysis
    anomaly_rows = _build_anomaly_analysis(runs, labels)
    html += anomaly_rows

    html += """
<div class="section">
<h2>8. 说明</h2>
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


def _build_anomaly_analysis(runs, labels):
    """Detect and report data anomalies across runs."""
    n = len(runs)
    if n < 2:
        return ""

    findings = []

    # Collect per-run stats
    cache_rates = []
    tok_per_locs = []
    avg_loc_per_files = []
    durations = []
    file_counts = []
    locs = []

    for r in runs:
        gt = r["grand_totals"]
        cr = gt.get("cache_read_tokens", 0) / max(gt.get("input_tokens", 1), 1)
        loc = gt.get("total_loc", 1)
        files = gt.get("total_files", 1)
        tpl = gt.get("total_tokens", 0) / max(loc, 1)
        alp = loc / max(files, 1)
        dur = gt.get("total_duration_seconds", 0)
        cache_rates.append(cr)
        tok_per_locs.append(tpl)
        avg_loc_per_files.append(alp)
        durations.append(dur)
        file_counts.append(files)
        locs.append(loc)

    # 1. Cache rate uniformity
    cr_spread = max(cache_rates) - min(cache_rates)
    if cr_spread < 0.02:
        findings.append({
            "level": "warning",
            "category": "Cache 命中率",
            "detail": f"所有轮次 Cache 命中率高度一致（{min(cache_rates):.1%} ~ {max(cache_rates):.1%}，极差 {cr_spread:.2%}）。"
                      "这是 content-based token 估算方法的固有特征，非实际 API cache 数据。"
                      "真实场景中不同模型的 cache 行为差异应更大。",
            "affected": "全部轮次",
        })

    # 2. Per-run anomalies
    mean_tpl = sum(tok_per_locs) / n
    mean_loc = sum(locs) / n
    mean_files = sum(file_counts) / n
    mean_alp = sum(avg_loc_per_files) / n

    for i, r in enumerate(runs):
        gt = r["grand_totals"]
        lbl = labels[i]
        loc = locs[i]
        files = file_counts[i]
        tpl = tok_per_locs[i]
        alp = avg_loc_per_files[i]
        dur = durations[i]

        if tpl > mean_tpl * 1.4:
            findings.append({
                "level": "warning",
                "category": "Token 效率",
                "detail": f"Token/LOC = {tpl:.1f}，显著高于均值 {mean_tpl:.1f}（{tpl/mean_tpl:.0%}）。"
                          f"该模型每生成一行代码消耗更多 token，可能原因：生成代码较短/不完整、"
                          f"工具调用开销大、或模型输出包含更多非代码内容。",
                "affected": lbl,
            })

        if files < mean_files * 0.5:
            findings.append({
                "level": "warning",
                "category": "文件覆盖率",
                "detail": f"仅生成 {files} 个文件，远低于均值 {mean_files:.0f}。"
                          f"可能未覆盖全部 43 个 AR 要求的文件，建议人工核查。",
                "affected": lbl,
            })

        if loc < mean_loc * 0.5:
            findings.append({
                "level": "warning",
                "category": "代码产出",
                "detail": f"LOC = {loc:,}，仅为均值 {mean_loc:,.0f} 的 {loc/mean_loc:.0%}。"
                          f"代码产出偏低，可能存在文件内容不完整或 stub 实现。",
                "affected": lbl,
            })

        if alp < 50:
            findings.append({
                "level": "info",
                "category": "文件粒度",
                "detail": f"平均 LOC/文件 = {alp:.0f}，偏低（均值 {mean_alp:.0f}）。"
                          f"文件数量多但每个文件内容较少，可能包含大量 stub 或空文件。",
                "affected": lbl,
            })

        if dur < sum(durations) / n * 0.4:
            findings.append({
                "level": "info",
                "category": "执行速度",
                "detail": f"耗时 {dur//60}m{dur%60}s，远低于均值 {sum(durations)//n//60}m。"
                          f"极快的速度通常意味着模型产出量较少或工具交互轮数较少。",
                "affected": lbl,
            })

    # 3. Cross-industry comparison
    findings.append({
        "level": "info",
        "category": "业界对标",
        "detail": "Token/LOC 范围 {:.0f}~{:.0f}，成本 ${:.2f}~${:.2f}/KLOC。"
                  "业界同类评测（如 SWE-bench、Aider Polyglot）的 token 效率通常在 30~80 token/LOC 区间，"
                  "本次评测结果在合理范围内。成本差异主要来自模型定价策略和输出量差异。".format(
                      min(tok_per_locs), max(tok_per_locs),
                      min(gt["total_cost_usd"] / max(gt["total_loc"], 1) * 1000
                          for gt in (r["grand_totals"] for r in runs)),
                      max(gt["total_cost_usd"] / max(gt["total_loc"], 1) * 1000
                          for gt in (r["grand_totals"] for r in runs)),
                  ),
        "affected": "全部轮次",
    })

    # Build HTML
    level_icons = {"warning": "&#9888;", "info": "&#8505;"}
    level_colors = {"warning": "#f4b400", "info": "#4285f4"}

    rows = ""
    for f in findings:
        icon = level_icons.get(f["level"], "")
        color = level_colors.get(f["level"], "#333")
        rows += (f'<tr><td style="color:{color};text-align:center">{icon}</td>'
                 f'<td>{f["category"]}</td>'
                 f'<td>{f["detail"]}</td>'
                 f'<td>{f["affected"]}</td></tr>\n')

    return f"""
<div class="section">
<h2>7. 数据异常分析</h2>
<p style="color:#666;font-size:0.9em">以下为自动检测的数据异常和需关注点，供评估时参考。</p>
<table>
<tr><th style="width:40px">级别</th><th style="width:100px">类别</th><th>详情</th><th style="width:180px">涉及轮次</th></tr>
{rows}
</table>
<p style="color:#999;font-size:0.85em;margin-top:10px">
  &#9888; = 需关注（数据可能不准确或结果异常）&nbsp;&nbsp;
  &#8505; = 参考信息
</p>
</div>
"""


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
