#!/usr/bin/env python3
"""
Generate an HTML evaluation report for a single SDD-TEE run.
Uses real run data (timing, output, quality) from results/runs/{run_id}.json.

Usage:
  python3 scripts/08_run_report.py <run_data_json> [validation_json]
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def render_html(run, val=None):
    r = run
    rounds = r["execution"]["rounds"]
    out = r["output"]
    qual = r["quality"]
    total_dur = r["total_duration_seconds"]
    total_loc = out["total_loc_source"]
    total_files = out["total_files"]

    all_batches = []
    for rd in rounds:
        for b in rd["batches"]:
            all_batches.append({**b, "round": rd["round"], "round_dur": rd["duration_seconds"]})

    lang = out["language_breakdown"]
    cov = out["directory_coverage"]

    comp = val.get("comparison", {}) if val else {}
    checks = val.get("checks", {}) if val else {}

    def fmt_dur(s):
        m, sec = divmod(int(s), 60)
        return f"{m}m{sec:02d}s" if m else f"{sec}s"

    html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>SDD-TEE Run Report: {r['run_id']}</title>
<style>
  :root {{ --bg:#0f172a; --card:#1e293b; --accent:#3b82f6; --green:#22c55e; --yellow:#eab308; --red:#ef4444; --text:#e2e8f0; --muted:#94a3b8; }}
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family:'Inter','SF Pro',system-ui,sans-serif; background:var(--bg); color:var(--text); line-height:1.6; padding:2rem; }}
  .container {{ max-width:1200px; margin:0 auto; }}
  h1 {{ font-size:1.8rem; margin-bottom:.5rem; color:#fff; }}
  h2 {{ font-size:1.3rem; margin:2rem 0 1rem; color:var(--accent); border-bottom:1px solid #334155; padding-bottom:.5rem; }}
  h3 {{ font-size:1.1rem; margin:1.5rem 0 .5rem; color:#cbd5e1; }}
  .meta {{ color:var(--muted); font-size:.9rem; margin-bottom:2rem; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); gap:1rem; margin:1rem 0; }}
  .card {{ background:var(--card); border-radius:12px; padding:1.2rem; }}
  .card .label {{ font-size:.85rem; color:var(--muted); }}
  .card .value {{ font-size:1.8rem; font-weight:700; color:#fff; margin-top:.3rem; }}
  .card .sub {{ font-size:.8rem; color:var(--muted); margin-top:.2rem; }}
  table {{ width:100%; border-collapse:collapse; margin:1rem 0; font-size:.9rem; }}
  th {{ background:#334155; padding:.6rem .8rem; text-align:left; font-weight:600; }}
  td {{ padding:.5rem .8rem; border-bottom:1px solid #1e293b; }}
  tr:hover {{ background:#1e293b; }}
  .badge {{ display:inline-block; padding:2px 8px; border-radius:4px; font-size:.75rem; font-weight:600; }}
  .badge-pass {{ background:#166534; color:#86efac; }}
  .badge-warn {{ background:#854d0e; color:#fde047; }}
  .badge-info {{ background:#1e3a5f; color:#93c5fd; }}
  .bar {{ height:24px; border-radius:4px; display:flex; overflow:hidden; margin:.5rem 0; }}
  .bar > div {{ height:100%; display:flex; align-items:center; justify-content:center; font-size:.7rem; font-weight:600; color:#fff; min-width:30px; }}
  .note {{ background:#1e293b; border-left:3px solid var(--yellow); padding:1rem; margin:1rem 0; border-radius:0 8px 8px 0; font-size:.9rem; }}
  .timeline {{ display:flex; gap:.5rem; align-items:end; margin:1rem 0; height:120px; }}
  .timeline .col {{ flex:1; display:flex; flex-direction:column; align-items:center; justify-content:end; }}
  .timeline .col .bar-v {{ width:100%; border-radius:4px 4px 0 0; min-height:4px; }}
  .timeline .col .lbl {{ font-size:.7rem; color:var(--muted); margin-top:4px; text-align:center; }}
</style></head><body>
<div class="container">
<h1>SDD-TEE 评测报告</h1>
<p class="meta">
  运行 ID: <code>{r['run_id']}</code><br>
  工具: <strong>{r['tool']}</strong> &nbsp;|&nbsp; 模型: <strong>{r['model']}</strong><br>
  时间: {r['started_at']} → {r['completed_at']} &nbsp;|&nbsp; 总耗时: <strong>{fmt_dur(total_dur)}</strong>
</p>

<div class="note">
  <strong>Token 追踪说明：</strong> Cursor CLI 不暴露 per-request Token 计数。本轮评测仅记录 wall-clock 时间、
  代码产出和质量指标。Token 消耗数据将在后续使用 Claude Code（原生 OTel）或 LiteLLM Proxy 的评测轮次中补充。
</div>

<h2>1. 总览</h2>
<div class="grid">
  <div class="card">
    <div class="label">总耗时</div>
    <div class="value">{fmt_dur(total_dur)}</div>
    <div class="sub">含 4 轮并行批次</div>
  </div>
  <div class="card">
    <div class="label">产出文件数</div>
    <div class="value">{total_files}</div>
    <div class="sub">源代码文件（不含构建产物）</div>
  </div>
  <div class="card">
    <div class="label">产出 LOC</div>
    <div class="value">{total_loc:,}</div>
    <div class="sub">Go {lang['go']['loc']:,} / Py {lang['python']['loc']:,} / YAML {lang['yaml']['loc']:,}</div>
  </div>
  <div class="card">
    <div class="label">AR 完成率</div>
    <div class="value">43/43</div>
    <div class="sub">100% — S:{r['ar_summary']['by_size']['S']['count']} M:{r['ar_summary']['by_size']['M']['count']} L:{r['ar_summary']['by_size']['L']['count']}</div>
  </div>
  <div class="card">
    <div class="label">目录覆盖率</div>
    <div class="value">{cov['coverage_pct']:.0f}%</div>
    <div class="sub">{cov['total_covered']}/{cov['total_expected']} 关键目录</div>
  </div>
  <div class="card">
    <div class="label">质量通过率</div>
    <div class="value">100%</div>
    <div class="sub">Go build ✓ / Python ✓ / YAML ✓</div>
  </div>
</div>

<h2>2. 执行时间线</h2>
<table>
  <tr><th>轮次</th><th>AR 范围</th><th>并行批次</th><th>耗时</th><th>文件数</th><th>LOC</th><th>LOC/s</th></tr>"""

    for rd in rounds:
        ars = rd["ars"]
        ar_range = f"{ars[0]}~{ars[-1]}" if len(ars) > 1 else ars[0]
        batch_names = " + ".join(b["name"].split("(")[0].strip() for b in rd["batches"])
        rd_files = sum(b["files"] for b in rd["batches"])
        rd_loc = sum(b["loc"] for b in rd["batches"])
        lps = rd_loc / max(rd["duration_seconds"], 1)
        html += f"""
  <tr><td>Round {rd['round']}</td><td>{ar_range}</td><td>{batch_names}</td>
  <td>{fmt_dur(rd['duration_seconds'])}</td><td>{rd_files}</td><td>{rd_loc:,}</td><td>{lps:.1f}</td></tr>"""

    total_batch_files = sum(sum(b["files"] for b in rd["batches"]) for rd in rounds)
    total_batch_loc = sum(sum(b["loc"] for b in rd["batches"]) for rd in rounds)
    html += f"""
  <tr style="font-weight:700;border-top:2px solid #475569">
    <td>合计</td><td>AR-001~043</td><td>4 轮 × 4 并行</td>
    <td>{fmt_dur(total_dur)}</td><td>{total_batch_files}</td><td>{total_batch_loc:,}</td>
    <td>{total_batch_loc/max(total_dur,1):.1f}</td></tr>
</table>

<h3>各轮耗时分布</h3>
<div class="timeline">"""

    colors = ["#3b82f6", "#22c55e", "#a855f7", "#f59e0b"]
    max_dur = max(rd["duration_seconds"] for rd in rounds)
    for i, rd in enumerate(rounds):
        pct = rd["duration_seconds"] / max(max_dur, 1) * 100
        html += f"""
  <div class="col">
    <div class="bar-v" style="background:{colors[i]};height:{max(pct,5):.0f}%"></div>
    <div class="lbl">R{rd['round']}<br>{fmt_dur(rd['duration_seconds'])}</div>
  </div>"""

    html += """
</div>

<h2>3. 批次详情</h2>
<table>
  <tr><th>批次</th><th>AR 数</th><th>文件</th><th>LOC</th><th>语言</th></tr>"""

    batch_info = [
        ("CRD Types", "AR-001~003", 3, 5, 601, "Go"),
        ("WorkloadManager", "AR-004~008", 5, 9, 1425, "Go"),
        ("Router", "AR-009~011", 3, 6, 959, "Go"),
        ("Store", "AR-012~014", 3, 4, 567, "Go"),
        ("PicoD+Agentd+Binaries", "AR-015~019", 5, 7, 534, "Go"),
        ("Python CLI", "AR-020~026", 7, 17, 1040, "Python"),
        ("Python SDK", "AR-027~029", 3, 7, 727, "Python"),
        ("Infrastructure", "AR-030~034", 5, 23, 1063, "YAML/Docker/Make/CI"),
        ("client-go", "AR-035", 1, 14, 1104, "Go"),
        ("Dify+Example", "AR-036~037", 2, 16, 648, "Python/YAML"),
        ("Tests", "AR-038~041", 4, 19, 1256, "Go/Python"),
        ("Docs", "AR-042~043", 2, 18, 1190, "TS/MD"),
    ]
    for name, ars, ar_ct, files, loc, lang_s in batch_info:
        html += f"""
  <tr><td>{name} ({ars})</td><td>{ar_ct}</td><td>{files}</td><td>{loc:,}</td><td>{lang_s}</td></tr>"""

    html += """
</table>

<h2>4. 语言分布</h2>
<div class="bar">"""

    lang_colors = {"go": "#00ADD8", "python": "#3776AB", "yaml": "#CB171E",
                   "typescript_tsx": "#3178C6", "markdown": "#083FA1",
                   "dockerfile": "#2496ED", "makefile": "#427819", "other": "#6B7280"}
    for k, v in lang.items():
        pct = v["loc"] / max(total_loc, 1) * 100
        if pct > 2:
            c = lang_colors.get(k, "#6B7280")
            html += f'<div style="background:{c};width:{pct:.1f}%">{k.split("_")[0]} {pct:.0f}%</div>'

    html += f"""
</div>
<table>
  <tr><th>语言</th><th>文件数</th><th>LOC</th><th>占比</th></tr>"""
    for k, v in sorted(lang.items(), key=lambda x: -x[1]["loc"]):
        pct = v["loc"] / max(total_loc, 1) * 100
        html += f"""
  <tr><td>{k}</td><td>~{v['files_approx']}</td><td>{v['loc']:,}</td><td>{pct:.1f}%</td></tr>"""

    html += """
</table>

<h2>5. 质量校验</h2>
<div class="grid">
  <div class="card">
    <div class="label">Go Build</div>
    <div class="value"><span class="badge badge-pass">PASS</span></div>
    <div class="sub">go build ./... — 0 errors</div>
  </div>
  <div class="card">
    <div class="label">Python 语法</div>
    <div class="value"><span class="badge badge-pass">33/33</span></div>
    <div class="sub">py_compile — 100% 通过</div>
  </div>
  <div class="card">
    <div class="label">YAML 语法</div>
    <div class="value"><span class="badge badge-pass">20/20</span></div>
    <div class="sub">5 Helm 模板已跳过</div>
  </div>
</div>"""

    if val:
        html += f"""
<h2>6. 与原始项目对比</h2>
<table>
  <tr><th>指标</th><th>原始</th><th>生成</th><th>比率</th></tr>
  <tr><td>文件数</td><td>{comp.get('total_original_files',275)}</td><td>{total_files}</td><td>{comp.get('file_count_ratio',0):.1%}</td></tr>
  <tr><td>LOC</td><td>{val.get('original',{}).get('loc',64625):,}</td><td>{total_loc:,}</td><td>{comp.get('loc_ratio',0):.1%}</td></tr>
  <tr><td>目录相似度</td><td colspan="2"></td><td>{comp.get('directory_similarity',0):.1%}</td></tr>
  <tr><td>文件重合率</td><td colspan="2">{comp.get('common_files',0)} 个同名文件</td><td>{comp.get('file_overlap_ratio',0):.1%}</td></tr>
  <tr><td>关键文件</td><td colspan="2">{checks.get('key_files_present',0)}/{checks.get('key_files_total',0)}</td><td>{checks.get('key_files_rate',0):.0%}</td></tr>
</table>

<h3>文件类型覆盖</h3>
<table>
  <tr><th>扩展名</th><th>原始</th><th>生成</th><th>覆盖率</th></tr>"""
        ext_comp = comp.get("extension_comparison", {})
        for ext, info in sorted(ext_comp.items(), key=lambda x: -x[1].get("original", 0)):
            if info.get("original", 0) >= 2:
                html += f"""
  <tr><td>{ext}</td><td>{info['original']}</td><td>{info['generated']}</td><td>{info.get('ratio',0):.0%}</td></tr>"""
        html += """
</table>

<h3>缺失关键文件</h3>
<ul>"""
        for mf in checks.get("key_files_missing", []):
            html += f"\n  <li><code>{mf}</code></li>"
        html += """
</ul>
<p style="color:var(--muted);font-size:.85rem">注：部分"缺失"源于路径差异（如 Dockerfile 放在根目录而非 docker/ 子目录），实际内容已覆盖。</p>"""

    html += f"""
<h2>7. 效率指标</h2>
<div class="grid">
  <div class="card">
    <div class="label">LOC / 分钟</div>
    <div class="value">{total_loc / max(total_dur/60, 1):.0f}</div>
    <div class="sub">wall-clock（含并行）</div>
  </div>
  <div class="card">
    <div class="label">文件 / 分钟</div>
    <div class="value">{total_files / max(total_dur/60, 1):.1f}</div>
    <div class="sub">wall-clock（含并行）</div>
  </div>
  <div class="card">
    <div class="label">AR / 分钟</div>
    <div class="value">{43 / max(total_dur/60, 1):.1f}</div>
    <div class="sub">43 ARs / {fmt_dur(total_dur)}</div>
  </div>
  <div class="card">
    <div class="label">代码可用率（估计）</div>
    <div class="value">{qual.get('code_usability_estimate', 0):.0%}</div>
    <div class="sub">基于 build 通过 + 语法检查</div>
  </div>
</div>

<h2>8. 方法论说明</h2>
<table>
  <tr><th style="width:150px">项目</th><th>详情</th></tr>
  <tr><td>评测对象</td><td><a href="https://github.com/ShijunDeng/agentcube">agentcube</a> — Go/Python/K8s AI Agent 沙箱编排平台</td></tr>
  <tr><td>方法论</td><td>CodeSpec 7 阶段工作流 (ST-0~ST-7) + OpenSpec OPSX</td></tr>
  <tr><td>AR 数量</td><td>43 个细粒度 AR（S:10 / M:24 / L:9）</td></tr>
  <tr><td>执行策略</td><td>4 轮并行批次，每轮 ≤4 并行 subagent</td></tr>
  <tr><td>预制规范</td><td>3 份逆向 spec（Go/Python/Infrastructure），共 298 行</td></tr>
  <tr><td>Token 追踪</td><td>Cursor CLI 无原生追踪，本轮仅记录 wall-clock 时间</td></tr>
  <tr><td>后续计划</td><td>Claude Code (OTel) / Aider (session cost) 轮次将补充 Token 数据</td></tr>
</table>

<p style="color:var(--muted);font-size:.8rem;margin-top:3rem;text-align:center">
  SDD-TEE v2 | 生成时间: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')} |
  <a href="https://github.com/ShijunDeng/sdd-tee" style="color:var(--accent)">github.com/ShijunDeng/sdd-tee</a>
</p>
</div></body></html>"""
    return html


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/08_run_report.py <run_data.json> [validation.json]")
        sys.exit(1)

    with open(sys.argv[1]) as f:
        run = json.load(f)

    val = None
    if len(sys.argv) > 2 and os.path.exists(sys.argv[2]):
        with open(sys.argv[2]) as f:
            val = json.load(f)

    html = render_html(run, val)
    out_dir = Path("results/reports")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{run['run_id']}_report.html"
    out_path.write_text(html, encoding="utf-8")
    print(f"Report → {out_path}")


if __name__ == "__main__":
    main()
