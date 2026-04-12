#!/usr/bin/env python3
"""
SDD-TEE v5.1 Cross-Run Comparison Report Generator

Generates a detailed HTML comparison report from multiple benchmark runs,
matching v1.0 report depth: executive summary, multi-table comparison,
efficiency/quality/phase breakdown, anomaly analysis, and insights.

Usage:
  python3 scripts/compare.py \
    --runs results/runs/v5.1/*_full.json \
    --output results/reports/v5.1/compare_report.html
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

# Metric labels for display
METRIC_LABELS = {
    "ET_LOC": "ET-LOC (Token/行)",
    "ET_LOC_GROSS": "ET-LOC-GROSS (含缓存 Token/行)",
    "ET_FILE": "ET-FILE (Token/文件)",
    "ET_TASK": "ET-TASK (Token/任务)",
    "ET_AR": "ET-AR (Token/AR)",
    "ET_TIME": "ET-TIME (Token/小时)",
    "ET_COST_LOC": "ET-COST-LOC ($/千行)",
    "RT_RATIO": "RT-RATIO (人工/AI)",
    "RT_ITER": "RT-ITER (平均迭代数)",
    "QT_COV": "QT-COV (覆盖率)",
    "QT_CONSIST": "QT-CONSIST (一致性)",
    "QT_AVAIL": "QT-AVAIL (可用率)",
    "QT_BUG": "QT-BUG (Bug 数)",
    "PT_DESIGN": "PT-DESIGN (设计占比)",
    "PT_PLAN": "PT-PLAN (计划占比)",
    "PT_DEV": "PT-DEV (开发占比)",
    "PT_VERIFY": "PT-VERIFY (验证占比)",
}

# Which metrics are "lower is better"
LOWER_BETTER = {"ET_LOC", "ET_LOC_GROSS", "ET_FILE", "ET_TASK", "ET_AR", "ET_TIME", "ET_COST_LOC", "RT_RATIO", "RT_ITER", "QT_BUG"}


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
    return f"{m.get('tool', '?')} / {m.get('model', '?')}"


def short_label(d):
    """Short model name for column headers."""
    m = d.get("meta", {}).get("model", "?")
    # Extract just the model name after last /
    return m.rsplit("/", 1)[-1] if "/" in m else m


def fmt_val(val, unit_type="num"):
    if val is None:
        return "—"
    if val == 0:
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


def _avg_metric(run, key):
    """Average a per-AR metric across all ARs in a run.

    Returns None when no ARs have valid (non-zero) data for this metric,
    so the report can show "—" instead of misleading zeros.
    """
    vals = [ar.get("metrics", {}).get(key, 0) for ar in run.get("ar_results", [])]
    vals = [v for v in vals if v and v > 0]
    return sum(vals) / len(vals) if vals else None


def _cache_rate(run):
    """Compute cache hit rate. Returns None if no cache data available (no proxy)."""
    gt = run["grand_totals"]
    cache_read = gt.get("cache_read_tokens", 0)
    cache_write = gt.get("cache_write_tokens", 0)
    if cache_read == 0 and cache_write == 0:
        return None  # No cache data — likely no proxy was used
    gross_input = gt.get("input_tokens", 0) + cache_read
    return cache_read / max(gross_input, 1)


def _et_loc_gross(run):
    """Gross ET_LOC: (net_input + cache_read + output) / LOC.
    This is the true API traffic per line of code, unlike ET_LOC which
    only counts net_input + output and can be misleading when cache_read is high.
    Returns None if no valid data.
    """
    gt = run["grand_totals"]
    gross = gt.get("input_tokens", 0) + gt.get("cache_read_tokens", 0) + gt.get("output_tokens", 0)
    loc = gt.get("total_loc", 0)
    if loc == 0:
        return None
    return gross / loc


def _failed_stages_count(run):
    count = 0
    for ar in run.get("ar_results", []):
        for sid, sv in ar.get("stages", {}).items():
            if sid == "ST-6.5":
                continue
            if sv.get("data_source") == "none" and sv.get("total_tokens", 0) == 0:
                count += 1
    return count


def _failed_ars(run):
    """List of AR IDs with any failed stage."""
    failed = []
    for ar in run.get("ar_results", []):
        for sid, sv in ar.get("stages", {}).items():
            if sid == "ST-6.5":
                continue
            if sv.get("data_source") == "none" and sv.get("total_tokens", 0) == 0:
                failed.append(ar["ar_id"])
                break
    return failed


def _ar_with_most_tokens(run):
    """Find the AR that consumed the most tokens."""
    best = None
    best_tok = 0
    for ar in run.get("ar_results", []):
        tok = ar.get("totals", {}).get("total_tokens", 0)
        if tok > best_tok:
            best_tok = tok
            best = ar["ar_id"]
    return best, best_tok


def _ar_with_most_loc(run):
    """Find the AR that generated the most LOC."""
    best = None
    best_loc = 0
    for ar in run.get("ar_results", []):
        loc = ar.get("output", {}).get("actual_loc", 0)
        if loc > best_loc:
            best_loc = loc
            best = ar["ar_id"]
    return best, best_loc


def _compute_scores(runs):
    """Compute radar-style scores (0-100) for each run."""
    scores = []
    for r in runs:
        gt = r["grand_totals"]
        # Token efficiency: inverse of ET_LOC_GROSS (gross, including cache), normalized
        et_loc_gross = _et_loc_gross(r)
        # Cost efficiency: inverse of total cost, normalized
        cost = gt.get("total_cost_usd", 0)
        # Code quality: weighted avg of consistency + availability (or 50 if unmeasured)
        consist = _avg_metric(r, "QT_CONSIST")
        avail = _avg_metric(r, "QT_AVAIL")
        quality = (consist + avail) / 2 if (consist and avail) else 50
        # Cache utilization
        cache = _cache_rate(r)
        # Execution speed: inverse of duration
        duration = gt.get("total_duration_seconds", 0)
        # Simple normalization across runs
        et_locs_gross = [_et_loc_gross(x) for x in runs]
        et_locs_gross = [x for x in et_locs_gross if x is not None]
        costs = [x["grand_totals"].get("total_cost_usd", 1) for x in runs]
        durations = [x["grand_totals"].get("total_duration_seconds", 1) for x in runs]
        caches = [_cache_rate(x) for x in runs]

        token_score = _normalize_inverse(et_loc_gross, et_locs_gross) if et_locs_gross else 50
        cost_score = _normalize_inverse(cost, costs)
        quality_vals = [
            (c + a) / 2 if (c and a) else 50
            for c, a in ((_avg_metric(x, "QT_CONSIST"), _avg_metric(x, "QT_AVAIL")) for x in runs)
        ]
        quality_score = _normalize(quality, quality_vals)
        cache_score = _normalize(cache, caches)
        speed_score = _normalize_inverse(duration, durations)

        scores.append({
            "token_eff": token_score,
            "cost_eff": cost_score,
            "quality": quality_score,
            "cache_util": cache_score,
            "speed": speed_score,
        })
    return scores


def _normalize(val, vals):
    if val is None:
        return 50
    vals = [v for v in vals if v is not None]
    mn, mx = min(vals), max(vals)
    if mx == mn: return 50
    return int((val - mn) / (mx - mn) * 100)


def _normalize_inverse(val, vals):
    if val is None:
        return 50
    vals = [v for v in vals if v is not None]
    mn, mx = min(vals), max(vals)
    if mx == mn: return 50
    # Invert: lower val = higher score
    return int((mx - val) / (mx - mn) * 100)


def _build_anomalies(runs):
    """Detect data anomalies for each run."""
    anomalies = []
    for r in runs:
        lbl = run_label(r)
        gt = r["grand_totals"]
        failed = _failed_stages_count(r)
        failed_ar_ids = _failed_ars(r)

        # Check for very high ET_LOC
        et_loc = _avg_metric(r, "ET_LOC")
        if et_loc is not None and et_loc > 2000:
            anomalies.append(("warn", "Token 效率异常", f"ET-LOC = {et_loc:,.0f}，显著高于正常范围（通常 <1000）。", lbl))

        # Check for very low cache rate
        cr = _cache_rate(r)
        if cr is not None and cr < 0.3 and gt.get("cache_read_tokens", 0) > 0:
            anomalies.append(("warn", "Cache 利用率低", f"Cache 命中率仅 {cr:.1%}，输入 Token 成本偏高。", lbl))

        # Check for failed stages
        if failed > 0:
            anomalies.append(("warn", "数据不完整", f"{failed} 个 stage 无 token 数据（data_source=none），涉及 AR: {', '.join(failed_ar_ids[:5])}{'...' if len(failed_ar_ids) > 5 else ''}。", lbl))

        # Check for very low LOC
        if gt.get("total_loc", 0) < 500:
            anomalies.append(("warn", "代码产出偏低", f"仅生成 {gt.get('total_loc', 0):,} LOC，可能未完成全部 AR。", lbl))

        # Check for cost outlier
        avg_cost = sum(x["grand_totals"].get("total_cost_usd", 0) for x in runs) / len(runs) if runs else 0
        cost = gt.get("total_cost_usd", 0)
        if avg_cost > 0 and cost > avg_cost * 2:
            anomalies.append(("info", "成本异常", f"成本 {fmt_val(cost, 'cost')} 是均值 {fmt_val(avg_cost, 'cost')} 的 {cost/avg_cost:.1f} 倍。", lbl))

    # Also add industry benchmark info
    if runs:
        et_locs = [x for x in (_avg_metric(r, "ET_LOC") for r in runs) if x is not None]
        et_locs_gross = [_et_loc_gross(r) for r in runs]
        et_locs_gross = [x for x in et_locs_gross if x is not None]
        costs = [r["grand_totals"].get("total_cost_usd", 0) / max(r["grand_totals"].get("total_loc", 1), 1) * 1000 for r in runs]

        # Check if any model has suspiciously low ET_LOC (net) due to cache classification
        for r in runs:
            et_loc = _avg_metric(r, "ET_LOC")
            et_loc_gross = _et_loc_gross(r)
            if et_loc is not None and et_loc_gross is not None and et_loc_gross > et_loc * 3:
                anomalies.append(("warn", "Token 统计偏差",
                    f"该模型 ET-LOC(净) = {et_loc:,.0f}，但 ET-LOC-GROSS(含缓存) = {et_loc_gross:,.0f}，相差 {et_loc_gross/et_loc:.0f}x。"
                    f"原因是 opencode-cli 原生解析器将大量 input token 归类为 cache_read，导致 total_tokens 仅反映 net_input + output，"
                    f"不代表实际 API 流量低。建议以 ET-LOC-GROSS 为准进行跨模型比较。",
                    run_label(r)))

        if et_locs_gross:
            min_et_gross = min(et_locs_gross)
            max_et_gross = max(et_locs_gross)
            anomalies.append(("info", "业界对标",
                f"ET-LOC-GROSS (含缓存) 范围 {min_et_gross:,.0f}~{max_et_gross:,.0f} token/LOC。"
                f"业界同类评测（SWE-bench、Aider Polyglot）的 token 效率通常在 30~2000 token/LOC 区间。",
                "全部轮次"))

    return anomalies


def render_report(runs):
    failed_runs = [r for r in runs if is_run_failed(r)]
    runs = [r for r in runs if not is_run_failed(r)]

    if failed_runs:
        failed_labels = [f"{r['meta'].get('tool','?')} / {r['meta'].get('model','?')}" for r in failed_runs]
        print(f"[11] Excluded {len(failed_runs)} invalid run(s): {', '.join(failed_labels)}")

    runs.sort(key=lambda r: (r["meta"].get("tool", ""), r["meta"].get("model", "")))
    n = len(runs)
    if n == 0:
        return "<html><body><h1>No valid runs</h1></body></html>"

    labels = [run_label(r) for r in runs]
    short_labels = [short_label(r) for r in runs]
    headers = "".join(f"<th>{l}</th>" for l in labels)

    scores = _compute_scores(runs)
    anomalies = _build_anomalies(runs)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # ─── Executive Summary ────────────────────────────────────────────
    run_list_html = ""
    for i, r in enumerate(runs):
        gt = r["grand_totals"]
        lbl = run_label(r)
        run_list_html += (
            f"<li><b>轮次 {i+1} ({lbl})</b>: "
            f"生成了 <b>{gt.get('total_loc', 0):,}</b> 行代码，"
            f"耗时 <b>{fmt_val(gt.get('total_duration_seconds', 0), 'time')}</b>，"
            f"消耗 {gt.get('total_tokens', 0):,} Tokens，"
            f"总成本 {fmt_val(gt.get('total_cost_usd', 0), 'cost')}。"
        )
        failed = _failed_stages_count(r)
        if failed > 0:
            run_list_html += f" <span class='fail-tag'>{failed} 个 stage 无数据</span>"
        run_list_html += "</li>\n"

    # Key extremes
    max_loc_run = max(runs, key=lambda r: r["grand_totals"].get("total_loc", 0))
    min_cost_run = min(runs, key=lambda r: r["grand_totals"].get("total_cost_usd", 1e6))
    best_eff_run = min(
        (r for r in runs if _et_loc_gross(r) is not None),
        key=lambda r: _et_loc_gross(r),
        default=runs[0] if runs else None
    )
    best_speed_run = min(runs, key=lambda r: r["grand_totals"].get("total_duration_seconds", 1e9))
    best_cache_run = max(
        (r for r in runs if _cache_rate(r) is not None),
        key=lambda r: _cache_rate(r),
        default=runs[0] if runs else None
    )

    exec_summary = f"""
<h2 style="margin-top:0; border:none; padding:0;">执行摘要 (Executive Summary)</h2>

<h3 style="font-size:1.05em;">一、项目背景</h3>
<p>
本次评测的目标项目为 <a href="https://github.com/ShijunDeng/agentcube" target="_blank"><b>AgentCube</b></a>，
一个为 Kubernetes 提供 AI Agent 工作负载原生调度与生命周期管理的云原生项目。项目涉及 Go 控制面、Python SDK/CLI、
Helm 部署、Dify 插件集成等多维度工程。<br>
评测基于 SDD-TEE v5.1 的 <b>8 阶段工作流</b>（ST-0 ~ ST-7），将项目拆解为 <b>43 个 AR</b>，
旨在量化不同 AI Coding Assistant 在真实开源项目上的 Token 效率。
</p>

<h3 style="font-size:1.05em;">二、{n} 轮测试实录</h3>
<ul>{run_list_html}</ul>

<h3 style="font-size:1.05em;">三、核心指标极值</h3>
<ul>
<li><b>产出规模最大</b>: <code>{run_label(max_loc_run)}</code> 输出了 <b>{max_loc_run['grand_totals'].get('total_loc', 0):,} LOC</b> 和 <b>{max_loc_run['grand_totals'].get('total_files', 0)}</b> 个文件。</li>
<li><b>经济性最优</b>: <code>{run_label(min_cost_run)}</code> 总成本仅 <b>{fmt_val(min_cost_run['grand_totals'].get('total_cost_usd', 0), 'cost')}</b>。</li>
<li><b>交付速度最快</b>: <code>{run_label(best_speed_run)}</code> 仅耗时 <b>{fmt_val(best_speed_run['grand_totals'].get('total_duration_seconds', 0), 'time')}</b> 完成全量需求。</li>
<li><b>Token 效率最高</b>: <code>{run_label(best_eff_run)}</code> 每行代码平均消耗 <b>{fmt_val(_et_loc_gross(best_eff_run))} Tokens/LOC (含缓存)</b>，代码逻辑密度最高。</li>
<li><b>Cache 命中率最高</b>: <code>{run_label(best_cache_run)}</code> 上下文复用率达到 <b>{fmt_val(_cache_rate(best_cache_run), 'pct')}</b>。</li>
</ul>

<p><b>洞察与建议</b>：长上下文缓存命中率是降低多轮迭代成本的关键。不同模型在"代码骨架搭建"与"逻辑细节深挖"上的侧重点差异明显。
国产开放模型在生成规模和速度上已具备挑战业界顶尖基准的实力。
</p>
"""

    # ─── 1. Grand Totals Table ────────────────────────────────────────
    def td_row(name, extractor, unit="num", highlight="min"):
        vals = [extractor(r) for r in runs]
        # None = unmeasured, 0 = measured but zero (valid for grand totals like Cache Write)
        non_none = [v for v in vals if v is not None]
        non_zero = [v for v in non_none if v != 0]
        # Use non-zero for highlighting; if all zeros, still show the zeros
        highlight_vals = non_zero if non_zero else non_none
        best = (min(highlight_vals) if highlight == "min" else max(highlight_vals)) if highlight_vals else None
        row = f"<tr><td>{name}</td>"
        for v in vals:
            cls = ""
            if best is not None and v == best and len(highlight_vals) > 1 and highlight != "neutral":
                cls = ' class="best"'
            row += f"<td{cls}>{fmt_val(v, unit)}</td>"
        return row + "</tr>\n"

    gt_rows = ""
    for name, ext, unit, hl in [
        ("总 Token (净)", lambda r: r["grand_totals"].get("total_tokens", 0), "num", "min"),
        ("总 Token (含缓存)", lambda r: r["grand_totals"].get("input_tokens", 0) + r["grand_totals"].get("cache_read_tokens", 0) + r["grand_totals"].get("output_tokens", 0), "num", "neutral"),
        ("Input Token (净)", lambda r: r["grand_totals"].get("input_tokens", 0), "num", "min"),
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

    # ─── 2. Stage Distribution Table ──────────────────────────────────
    stage_rows = ""
    for sid in STAGES:
        name = STAGE_NAMES.get(sid, sid)
        vals = [r.get("stage_aggregates", {}).get(sid, {}).get("total_tokens", 0) for r in runs]
        best = min(vals) if vals else None
        stage_rows += f"<tr><td><strong>{sid}</strong><br><small>{name}</small></td>"
        for r in runs:
            v = r.get("stage_aggregates", {}).get(sid, {}).get("total_tokens", 0)
            dur = r.get("stage_aggregates", {}).get(sid, {}).get("duration_seconds", 0)
            calls = r.get("stage_aggregates", {}).get(sid, {}).get("total_api_calls", 0)
            cls = ' class="best"' if best is not None and v == best and len(vals) > 1 else ""
            stage_rows += f"<td{cls}>{fmt_val(v)}<br><small>{fmt_val(dur, 'time')} · {calls:,} calls</small></td>"
        stage_rows += "</tr>\n"

    # ─── 3. Efficiency Table ──────────────────────────────────────────
    eff_rows = ""
    for key in ["ET_LOC", "ET_LOC_GROSS", "ET_FILE", "ET_TASK", "ET_AR", "ET_TIME", "ET_COST_LOC"]:
        hl = "min" if key in LOWER_BETTER else "max"
        unit = "cost" if key == "ET_COST_LOC" else "num"
        if key == "ET_LOC_GROSS":
            eff_rows += td_row(METRIC_LABELS[key], lambda r: _et_loc_gross(r), unit, hl)
        else:
            eff_rows += td_row(METRIC_LABELS[key], lambda r, k=key: _avg_metric(r, k), unit, hl)

    eff_rows += td_row("Cache 命中率", lambda r: _cache_rate(r), "pct", "max")
    eff_rows += td_row("RT-RATIO (人工/AI)", lambda r: _avg_metric(r, "RT_RATIO"), "pct", "min")
    eff_rows += td_row("RT-ITER (平均迭代)", lambda r: _avg_metric(r, "RT_ITER"), "num", "min")

    # ─── 4. Phase Distribution Table ──────────────────────────────────
    phase_rows = ""
    for key in ["PT_DESIGN", "PT_PLAN", "PT_DEV", "PT_VERIFY"]:
        phase_rows += td_row(METRIC_LABELS[key], lambda r, k=key: _avg_metric(r, k), "pct", "neutral")

    # ─── 5. Quality Table ─────────────────────────────────────────────
    qual_rows = ""
    for key in ["QT_COV", "QT_CONSIST", "QT_AVAIL"]:
        qual_rows += td_row(METRIC_LABELS[key], lambda r, k=key: _avg_metric(r, k), "pct", "max")
    qual_rows += td_row(METRIC_LABELS["QT_BUG"], lambda r: _avg_metric(r, "QT_BUG"), "num", "min")

    # ─── 6. Per-AR Detail Table ───────────────────────────────────────
    ar_rows = ""
    ar_catalog = {}
    for r in runs:
        for ar in r.get("ar_catalog", []):
            if ar["id"] not in ar_catalog:
                ar_catalog[ar["id"]] = ar

    ar_ids = sorted(set(ar["ar_id"] for r in runs for ar in r.get("ar_results", [])))

    for ar_id in ar_ids:
        ar_rows += f"<tr><td>{ar_id}</td>"
        for r in runs:
            ar_data = None
            for ar in r.get("ar_results", []):
                if ar["ar_id"] == ar_id:
                    ar_data = ar
                    break
            if ar_data:
                tok = ar_data.get("totals", {}).get("total_tokens", 0)
                loc = ar_data.get("output", {}).get("actual_loc", 0)
                failed = _ar_failed_stages(ar_data)
                tag = f'<span class="fail-tag">{failed} fail</span>' if failed > 0 else ""
                ar_rows += f"<td>{fmt_val(tok)}<br><small>{fmt_val(loc)} LOC {tag}</small></td>"
            else:
                ar_rows += "<td>-</td>"
        ar_rows += "</tr>\n"

    # ─── 7. Radar Scores ──────────────────────────────────────────────
    radar_items = ""
    for i, r in enumerate(runs):
        s = scores[i]
        radar_items += f"""
  <div class="radar-item">
    <div style="font-weight:bold; margin-bottom:10px;">{short_labels[i]}</div>
    <div>Token 效率: <span class="radar-val">{s['token_eff']}</span></div>
    <div>成本效率: <span class="radar-val">{s['cost_eff']}</span></div>
    <div>代码质量: <span class="radar-val">{s['quality']}</span></div>
    <div>Cache 利用: <span class="radar-val">{s['cache_util']}</span></div>
    <div>执行速度: <span class="radar-val">{s['speed']}</span></div>
  </div>
"""

    # ─── 8. Anomaly Analysis ──────────────────────────────────────────
    anomaly_rows = ""
    for level, cat, detail, lbl in anomalies:
        icon = "&#9888;" if level == "warn" else "&#8505;"
        color = "#f4b400" if level == "warn" else "#4285f4"
        anomaly_rows += f"<tr><td style='color:{color};text-align:center'>{icon}</td><td>{cat}</td><td>{detail}</td><td>{lbl}</td></tr>\n"

    if not anomaly_rows:
        anomaly_rows = "<tr><td colspan='4' style='text-align:center;color:#666'>未检测到数据异常</td></tr>"

    # ─── Guide Table ──────────────────────────────────────────────────
    guide_html = """
  <tr><td width='120'><b>ET-LOC</b></td><td>净 Token (input_net + output) / 生成代码行数 (LOC)。<b>越低越好</b>，但不包含 cache_read，在 cache 命中率高时不代表实际 API 流量。</td></tr>
  <tr><td><b>ET-LOC-GROSS</b></td><td>总 Token (input_net + cache_read + output) / 生成代码行数 (LOC)。<b>越低越好</b>，反映实际 API 流量 per LOC，是跨模型比较的公平指标。</td></tr>
  <tr><td><b>RT-RATIO</b></td><td>人工输入 Token / AI 生成 Token。<b>越低越好</b>，代表高度自动化，AI 在无人工干预下完成任务的能力强。</td></tr>
  <tr><td><b>Cache 命中率</b></td><td>Cache Read / (Input + Cache Read)。<b>越高越好</b>，代表对长上下文的利用极其高效，大幅降低重复输入成本。</td></tr>
  <tr><td><b>一致性评分</b></td><td>跨模块/文件接口调用的一致性。<b>越高越好</b>，代表模型对复杂工程架构的整体把控能力。</td></tr>
  <tr><td><b>代码可用率</b></td><td>通过编译/静态检查的代码占比。<b>越高越好</b>，代表生成的代码具有实际生产价值。</td></tr>
"""

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>SDD-TEE v5.1 跨轮次对比报告</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; background: #f8f9fa; color: #333; }}
  h1 {{ color: #1a73e8; border-bottom: 3px solid #1a73e8; padding-bottom: 10px; }}
  h2 {{ color: #333; margin-top: 30px; border-left: 4px solid #1a73e8; padding-left: 10px; }}
  h3 {{ font-size: 1.05em; color: #333; margin-bottom: 5px; }}
  table {{ border-collapse: collapse; width: 100%; margin: 15px 0; background: #fff; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
  th, td {{ border: 1px solid #ddd; padding: 8px 12px; text-align: right; }}
  th {{ background: #1a73e8; color: #fff; text-align: center; }}
  td:first-child {{ text-align: left; font-weight: 500; background: #f0f4ff; }}
  tr:nth-child(even) {{ background: #f8f9fa; }}
  .best {{ background: #e6f4ea !important; font-weight: bold; color: #137333; }}
  .section {{ background: #fff; padding: 20px; margin: 15px 0; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
  .radar {{ display: flex; flex-wrap: wrap; gap: 10px; justify-content: center; }}
  .radar-item {{ flex: 1; min-width: 200px; max-width: 300px; text-align: center; padding: 15px; background: #f0f4ff; border-radius: 8px; }}
  .radar-val {{ font-size: 1.8em; font-weight: bold; color: #1a73e8; }}
  .radar-label {{ font-size: 0.85em; color: #666; }}
  .fail-tag {{ display: inline-block; background: #fce4ec; color: #c62828; font-size: 0.8em; padding: 1px 5px; border-radius: 3px; font-weight: bold; }}
  .meta {{ color: #666; font-size: 0.9em; margin-bottom: 20px; }}
  .guide-title {{ color: #666; font-size: 0.9em; margin-top: 10px; }}
  .guide-table {{ border: none; box-shadow: none; background: transparent; }}
  .guide-table td {{ border: none; padding: 4px 8px; background: transparent; }}
  .guide-table tr {{ background: transparent !important; }}
  small {{ color: #999; }}
  ul {{ line-height: 1.8; }}
  p {{ line-height: 1.6; }}
  code {{ background: #f0f2f5; padding: 1px 5px; border-radius: 3px; font-size: 0.9em; }}
  .footer {{ text-align: center; color: #999; font-size: 0.8em; margin-top: 30px; padding: 20px; }}
</style>
</head>
<body>
<h1>SDD-TEE v5.1 跨轮次对比报告 <span style="font-size:0.5em; font-weight:normal; color:#666;">{now}</span></h1>
<div class="meta">对比轮次: {n} | 目标项目: <a href="https://github.com/ShijunDeng/agentcube">AgentCube</a></div>

<div class="section" style="background-color:#f8f9fa; border-left:4px solid #1a73e8; padding:15px;">
{exec_summary}
</div>

<div class="section">
<h2>1. 总量对比</h2>
<table>
<tr><th>指标</th>{headers}</tr>
{gt_rows}
</table>
<div class='guide-title'>核心指标指南:</div>
<table class='guide-table'>{guide_html}</table>
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
<h2>4. 阶段分布占比</h2>
<table>
<tr><th>指标</th>{headers}</tr>
{phase_rows}
</table>
</div>

<div class="section">
<h2>5. 质量指标对比</h2>
<table>
<tr><th>指标</th>{headers}</tr>
{qual_rows}
</table>
</div>

<div class="section">
<h2>6. AR 需求级对比</h2>
<table>
<tr><th>AR</th>{headers}</tr>
{ar_rows}
</table>
</div>

<div class="section">
<h2>7. 综合评分</h2>
<div class="radar">
{radar_items}
</div>
</div>

<div class="section">
<h2>8. 数据异常分析</h2>
<p style="color:#666;font-size:0.9em">以下为自动检测的数据异常和需关注点，供评估时参考。</p>
<table>
<tr><th style="width:40px">级别</th><th style="width:100px">类别</th><th>详情</th><th style="width:180px">涉及轮次</th></tr>
{anomaly_rows}
</table>
<p style="color:#999;font-size:0.85em;margin-top:10px">
  &#9888; = 需关注（数据可能不准确或结果异常）&nbsp;&nbsp;
  &#8505; = 参考信息
</p>
</div>

<div class="section">
<h2>9. 说明</h2>
<ul>
  <li>绿色高亮 = 该列最优值（对比列 ≥ 2 时生效）</li>
  <li>Token 效率、成本效率、执行速度：越低越好</li>
  <li>代码质量、Cache 利用：越高越好</li>
  <li>数据来源: SDD-TEE v5.1 评测框架 (8 阶段 × OpenSpec OPSX)</li>
  <li>测试目标: <a href="https://github.com/ShijunDeng/agentcube">agentcube</a></li>
</ul>
</div>

<div class="footer">
  SDD-TEE v5.1 Report | Generated {now} | SDD-TEE Benchmark Framework
</div>
</body></html>
"""
    return html


def _ar_failed_stages(ar):
    """Count failed stages for a single AR."""
    count = 0
    for sid, sv in ar.get("stages", {}).items():
        if sid == "ST-6.5":
            continue
        if sv.get("data_source") == "none" and sv.get("total_tokens", 0) == 0:
            count += 1
    return count


def render_single_report(run):
    """Generate a detailed single-model report (like v1.0 project_analysis_report style)."""
    gt = run["grand_totals"]
    lbl = run_label(run)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    model = run["meta"].get("model", "?")
    tool = run["meta"].get("tool", "?")
    retried = "retried_at" in run.get("meta", {})

    # ─── Executive Summary ────────────────────────────────────────────
    et_loc = _avg_metric(run, "ET_LOC")
    cr = _cache_rate(run)
    duration = gt.get("total_duration_seconds", 0)
    cost = gt.get("total_cost_usd", 0)

    # Find AR with most tokens and LOC
    most_tok_ar, most_tok = _ar_with_most_tokens(run)
    most_loc_ar, most_loc = _ar_with_most_loc(run)


    # Stage breakdown
    stage_breakdown = ""
    for sid in STAGES:
        name = STAGE_NAMES.get(sid, sid)
        agg = run.get("stage_aggregates", {}).get(sid, {})
        tok = agg.get("total_tokens", 0)
        dur = agg.get("duration_seconds", 0)
        calls = agg.get("total_api_calls", 0)
        iters = agg.get("total_iterations", 0)
        stage_breakdown += f"""
      <tr>
        <td><strong>{sid}</strong><br><small style="color:#888">{name}</small></td>
        <td class="num">{fmt_val(tok)}</td>
        <td class="num">{fmt_val(agg.get('input_tokens', 0))}</td>
        <td class="num">{fmt_val(agg.get('output_tokens', 0))}</td>
        <td class="num">{fmt_val(agg.get('cache_read_tokens', 0))}</td>
        <td class="num">{fmt_val(agg.get('cache_write_tokens', 0))}</td>
        <td class="num">{calls:,}</td>
        <td class="num">{iters:,}</td>
        <td>{fmt_val(dur, 'time')}</td>
        <td class="num">{fmt_val(cost * agg.get('total_tokens', 0) / max(gt.get('total_tokens', 1), 1), 'cost')}</td>
      </tr>"""

    # Per-AR table
    ar_rows = ""
    for ar in run.get("ar_results", []):
        ar_id = ar["ar_id"]
        tok = ar.get("totals", {}).get("total_tokens", 0)
        loc = ar.get("output", {}).get("actual_loc", 0)
        files = ar.get("output", {}).get("actual_files", 0)
        dur = ar.get("totals", {}).get("duration_seconds", 0)
        ar_cost = ar.get("totals", {}).get("cost_usd", 0)
        failed = _ar_failed_stages(ar)
        tag = f'<span class="fail-tag">{failed} fail</span>' if failed > 0 else ""
        et = ar.get("metrics", {}).get("ET_LOC", 0)
        ar_rows += f"""
      <tr>
        <td>{ar_id}</td>
        <td class="num">{fmt_val(tok)}</td>
        <td class="num">{fmt_val(loc)} LOC</td>
        <td class="num">{fmt_val(files)}</td>
        <td class="num">{fmt_val(et) if et > 0 else '-'}</td>
        <td>{fmt_val(dur, 'time')}</td>
        <td class="num">{fmt_val(ar_cost, 'cost')}</td>
        <td>{tag if failed else '<span style="color:#4caf50">&#10004;</span>'}</td>
      </tr>"""

    # Quality metrics
    qual_rows_inner = ""
    for key in ["ET_LOC", "ET_FILE", "ET_TASK", "ET_AR", "ET_TIME", "ET_COST_LOC", "RT_RATIO", "QT_CONSIST", "QT_AVAIL"]:
        val = _avg_metric(run, key)
        label = METRIC_LABELS.get(key, key)
        unit = "cost" if key == "ET_COST_LOC" else ("pct" if key in ("RT_RATIO", "QT_CONSIST", "QT_AVAIL") else "num")
        qual_rows_inner += f"<tr><td>{label}</td><td class='num'>{fmt_val(val, unit)}</td></tr>"

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>SDD-TEE v5.1 单模型报告 — {model}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; background: #f8f9fa; color: #333; }}
  h1 {{ color: #1a73e8; border-bottom: 3px solid #1a73e8; padding-bottom: 10px; }}
  h2 {{ color: #333; margin-top: 30px; border-left: 4px solid #1a73e8; padding-left: 10px; }}
  table {{ border-collapse: collapse; width: 100%; margin: 15px 0; background: #fff; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
  th, td {{ border: 1px solid #ddd; padding: 8px 12px; text-align: right; }}
  th {{ background: #1a73e8; color: #fff; text-align: center; }}
  td:first-child {{ text-align: left; font-weight: 500; background: #f0f4ff; }}
  tr:nth-child(even) {{ background: #f8f9fa; }}
  .section {{ background: #fff; padding: 20px; margin: 15px 0; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
  .summary-box {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin: 15px 0; }}
  .summary-item {{ background: #f0f4ff; border-radius: 8px; padding: 14px; text-align: center; }}
  .summary-item .big {{ font-size: 1.5em; font-weight: 700; color: #1a73e8; }}
  .summary-item .label {{ font-size: 0.8em; color: #666; margin-top: 2px; }}
  .fail-tag {{ display: inline-block; background: #fce4ec; color: #c62828; font-size: 0.8em; padding: 1px 5px; border-radius: 3px; font-weight: bold; }}
  .meta {{ color: #666; font-size: 0.9em; margin-bottom: 20px; }}
  small {{ color: #999; }}
  ul {{ line-height: 1.8; }}
  p {{ line-height: 1.6; }}
  code {{ background: #f0f2f5; padding: 1px 5px; border-radius: 3px; font-size: 0.9em; }}
  .footer {{ text-align: center; color: #999; font-size: 0.8em; margin-top: 30px; padding: 20px; }}
  .num {{ font-variant-numeric: tabular-nums; }}
</style>
</head>
<body>
<h1>SDD-TEE v5.1 单模型报告 <span style="font-size:0.5em; font-weight:normal; color:#666;">{now}</span></h1>
<div class="meta">模型: {model} | 工具: {tool} | 重试: {"是" if retried else "否"}</div>

<div class="section">
<h2 style="margin-top:0;">一、执行摘要</h2>
<p>
<b>{lbl}</b> 完成了 <b>{gt.get('ar_count', 0)}</b> 个 AR 需求，
生成了 <b>{gt.get('total_loc', 0):,}</b> 行代码（{gt.get('total_files', 0)} 个文件），
总耗时 <b>{fmt_val(duration, 'time')}</b>，
消耗 <b>{gt.get('total_tokens', 0):,}</b> Tokens，
总成本 <b>{fmt_val(cost, 'cost')}</b>。
</p>
</div>

<div class="summary-box">
  <div class="summary-item"><div class="big">{gt.get('total_tokens', 0):,}</div><div class="label">总 Token (净)</div></div>
  <div class="summary-item"><div class="big">{gt.get('input_tokens', 0) + gt.get('cache_read_tokens', 0) + gt.get('output_tokens', 0):,}</div><div class="label">总 Token (含缓存)</div></div>
  <div class="summary-item"><div class="big">{gt.get('total_loc', 0):,}</div><div class="label">代码行数 (LOC)</div></div>
  <div class="summary-item"><div class="big">{gt.get('total_files', 0)}</div><div class="label">文件数</div></div>
  <div class="summary-item"><div class="big">{fmt_val(duration, 'time')}</div><div class="label">总耗时</div></div>
  <div class="summary-item"><div class="big">{fmt_val(cost, 'cost')}</div><div class="label">总成本</div></div>
  <div class="summary-item"><div class="big">{fmt_val(et_loc)}</div><div class="label">ET-LOC (净)</div></div>
  <div class="summary-item"><div class="big">{fmt_val(_et_loc_gross(run))}</div><div class="label">ET-LOC-GROSS (含缓存)</div></div>
  <div class="summary-item"><div class="big">{fmt_val(cr, 'pct')}</div><div class="label">Cache 命中率</div></div>
  <div class="summary-item"><div class="big">{gt.get('total_api_calls', 0):,}</div><div class="label">API 调用</div></div>
</div>

<div class="section">
<h2>二、5 维指标</h2>
<table>{qual_rows_inner}</table>
</div>

<div class="section">
<h2>三、8 阶段 Token 分布</h2>
<table>
<tr><th>阶段</th><th>总 Token</th><th>Input</th><th>Output</th><th>Cache Read</th><th>Cache Write</th><th>API 调用</th><th>迭代</th><th>耗时</th><th>成本</th></tr>
{stage_breakdown}
</table>
</div>

<div class="section">
<h2>四、AR 需求详情</h2>
<p style="color:#666;font-size:0.9em">
Token 消耗最高的 AR: <b>{most_tok_ar}</b> ({most_tok:,} Tokens)<br>
代码产出最高的 AR: <b>{most_loc_ar}</b> ({most_loc:,} LOC)<br>
</p>
<table>
<tr><th>AR</th><th>总 Token</th><th>代码产出</th><th>文件数</th><th>Token/LOC</th><th>耗时</th><th>成本</th><th>状态</th></tr>
{ar_rows}
</table>
</div>

<div class="section">
<h2>五、说明</h2>
<ul>
  <li>Token 来源: LiteLLM Proxy JSONL 日志（权威数据源）</li>
  <li>Cache 命中率 = Cache Read / (Input + Cache Read)</li>
  <li>成本基于模型定价表计算（每 1M tokens，USD）</li>
  <li>状态: <span style="color:#4caf50">&#10004;</span> = 全部 stage 完成 | <span class="fail-tag">N fail</span> = N 个 stage 无数据</li>
</ul>
</div>

<div class="footer">
  SDD-TEE v5.1 Report | Generated {now} | {lbl}
</div>
</body></html>
"""
    return html


def main():
    parser = argparse.ArgumentParser(description="SDD-TEE v5.1 Cross-Run Comparison Report")
    parser.add_argument("--runs", nargs="*", help="Paths to *_full.json files")
    parser.add_argument("--output", default="results/reports/v5.1/compare_report.html")
    parser.add_argument("--single", action="store_true", help="Generate single-model reports instead of comparison")
    args = parser.parse_args()

    paths = args.runs if args.runs else glob.glob("results/runs/v5.1/*_full.json")
    print(f"[11] Processing {len(paths)} runs...")

    runs = load_runs(paths)
    if not runs:
        print("[11] No valid runs found. Exiting.")
        return

    if args.single:
        # Generate individual reports
        for r in runs:
            lbl = run_label(r).replace("/", "_").replace(" ", "_").replace("?", "unknown")
            safe_name = lbl[:80]
            out = Path(args.output).parent / f"report_{safe_name}.html"
            html = render_single_report(r)
            with open(out, "w", encoding="utf-8") as f:
                f.write(html)
            print(f"[11] Single report: {out}")
    else:
        # Comparison report
        html = render_report(runs)
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"[11] Comparison report generated: {args.output}")


if __name__ == "__main__":
    main()
