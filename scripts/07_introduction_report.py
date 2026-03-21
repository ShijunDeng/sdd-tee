#!/usr/bin/env python3
"""
生成 SDD-TEE 项目介绍章节 HTML 报告。
包含：前置工作（项目解析 + 规范逆向生成）的详细 Token/耗时记录、框架技术架构概览。
此文件为独立的参考文档，可被后续评测报告直接引用。

Usage:
  python3 scripts/07_introduction_report.py [--source-dir /path/to/agentcube]
"""

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Data collection helpers
# ---------------------------------------------------------------------------

def load_json(path):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return None


def load_text(path):
    if os.path.exists(path):
        with open(path) as f:
            return f.read()
    return ""


def count_file(path):
    try:
        with open(path) as f:
            content = f.read()
        return len(content.splitlines()), len(content), len(content.split())
    except Exception:
        return 0, 0, 0


def collect_prerequisite_data(base_dir, source_dir=None):
    """Collect all data needed for the introduction report."""

    data = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "framework": {
            "name": "SDD-TEE",
            "full_name": "SDD Token Efficiency Evaluation",
            "description": "基于规范驱动开发 (Specification-Driven Development) 的 AI Coding Assistant Token 效率评估框架",
            "repo_url": "https://github.com/ShijunDeng/sdd-tee",
        },
        "target_project": {},
        "prerequisites": {
            "project_analysis": {},
            "spec_generation": {},
        },
        "specs": [],
        "framework_architecture": {},
    }

    # --- Target project info ---
    analysis_json = load_json(os.path.join(base_dir, "results/project_analysis/analysis.json"))
    report_json = load_json(os.path.join(base_dir, "results/reports/project_analysis_report.json"))

    if report_json:
        data["target_project"] = {
            "name": "agentcube",
            "repo_url": "https://github.com/ShijunDeng/agentcube.git",
            "total_files": report_json.get("total_files", 275),
            "total_loc": report_json.get("total_loc", 64625),
            "ext_stats": report_json.get("ext_stats", {}),
            "top_dirs": report_json.get("top_dirs", {}),
            "modules": report_json.get("modules", {}),
            "languages": {
                "Go": {"files": report_json.get("go", {}).get("src_files", 0) + report_json.get("go", {}).get("test_files", 0),
                        "loc": report_json.get("go", {}).get("src_loc", 0) + report_json.get("go", {}).get("test_loc", 0)},
                "Python": {"files": report_json.get("python", {}).get("src_files", 0) + report_json.get("python", {}).get("test_files", 0),
                           "loc": report_json.get("python", {}).get("src_loc", 0) + report_json.get("python", {}).get("test_loc", 0)},
                "YAML": {"files": report_json.get("yaml", {}).get("files", 0),
                         "loc": report_json.get("yaml", {}).get("loc", 0)},
                "TypeScript": {"files": report_json.get("ts", {}).get("files", 0),
                               "loc": report_json.get("ts", {}).get("loc", 0)},
            }
        }
    elif analysis_json:
        s = analysis_json.get("stats", {})
        data["target_project"] = {
            "name": "agentcube",
            "repo_url": analysis_json.get("repo_url", ""),
            "total_files": s.get("total_files", 0),
            "total_loc": 64625,
            "languages": {
                "Go": {"files": s.get("go_files", 0), "loc": s.get("go_loc", 0)},
                "Python": {"files": s.get("python_files", 0), "loc": s.get("python_loc", 0)},
                "YAML": {"files": s.get("yaml_files", 0), "loc": s.get("yaml_loc", 0)},
                "TypeScript": {"files": s.get("ts_files", 0), "loc": s.get("ts_loc", 0)},
            }
        }

    # --- Run result (for prerequisite stage timings) ---
    runs_dir = os.path.join(base_dir, "results/runs")
    run_data = None
    if os.path.isdir(runs_dir):
        run_files = sorted([f for f in os.listdir(runs_dir) if f.endswith('.json') and 'validation' not in f])
        if run_files:
            run_data = load_json(os.path.join(runs_dir, run_files[0]))

    if run_data:
        stages = run_data.get("stages", {})
        pa = stages.get("project_analysis", {})
        sg = stages.get("spec_generation", {})

        data["prerequisites"]["project_analysis"] = {
            "duration_seconds": pa.get("duration_seconds", 7),
            "description": pa.get("description", "Clone and analyze target project structure"),
            "notes": pa.get("notes", "Pure script, no LLM tokens"),
            "llm_tokens_used": False,
            "outputs": [
                {"file": "results/project_analysis/analysis.json", "desc": "项目结构分析数据 (JSON)"},
                {"file": "results/project_analysis/file_tree.txt", "desc": "完整文件树"},
                {"file": "results/project_analysis/language_distribution.txt", "desc": "语言分布统计"},
            ],
            "tool": "Shell script (00_analyze_project.sh)",
        }

        data["prerequisites"]["spec_generation"] = {
            "duration_seconds": sg.get("duration_seconds", 194),
            "description": sg.get("description", "Reverse-engineer OpenSpec specifications from source code"),
            "notes": sg.get("notes", ""),
            "llm_tokens_used": True,
            "tool": run_data.get("tool", "cursor-cli"),
            "model": run_data.get("model", "claude-4.6-opus"),
            "process": {
                "method": "3 个并行 subagent 分别处理不同领域",
                "subagents": [
                    {"name": "Go Spec Agent", "scope": "CRD 类型定义、控制器、路由器、会话存储、HTTP API",
                     "input": "Go 源码 (89 files, 17,368 LOC)", "output": "01_go_specification.md"},
                    {"name": "Python Spec Agent", "scope": "CLI 命令树、运行时类、SDK 公共 API、数据模型",
                     "input": "Python 源码 (41 files, 6,889 LOC)", "output": "02_python_specification.md"},
                    {"name": "Infrastructure Spec Agent", "scope": "Helm Chart、RBAC、Dockerfile、Makefile、CI/CD",
                     "input": "YAML/Docker/CI 配置 (50+ files)", "output": "03_infrastructure_specification.md"},
                ],
            },
            "token_estimation": {
                "note": "Cursor CLI 不直接暴露 per-request token 计数；以下为基于模型定价和输出规模的估算",
                "estimated_input_tokens": 85000,
                "estimated_output_tokens": 12000,
                "estimated_total_tokens": 97000,
                "estimation_basis": "3 subagent 各需读取约 20-30K tokens 的源码上下文，产出约 4K tokens 的规范文档",
            },
            "outputs": [],
        }

    # --- Spec file details ---
    specs_dir = os.path.join(base_dir, "specs")
    if os.path.isdir(specs_dir):
        for fname in sorted(os.listdir(specs_dir)):
            if fname.endswith('.md'):
                fpath = os.path.join(specs_dir, fname)
                lines, chars, words = count_file(fpath)
                content = load_text(fpath)

                sections = []
                for line in content.splitlines():
                    if line.startswith('## '):
                        sections.append(line[3:].strip())

                spec_info = {
                    "filename": fname,
                    "path": f"specs/{fname}",
                    "lines": lines,
                    "chars": chars,
                    "words": words,
                    "sections": sections,
                    "content_preview": content[:500] + "..." if len(content) > 500 else content,
                }
                data["specs"].append(spec_info)
                data["prerequisites"]["spec_generation"]["outputs"].append({
                    "file": f"specs/{fname}",
                    "desc": f"规范文档 ({lines} 行, {chars} 字符)",
                })

    # --- Project analysis report info ---
    report_html_path = os.path.join(base_dir, "results/reports/project_analysis_report.html")
    if os.path.exists(report_html_path):
        lines, chars, _ = count_file(report_html_path)
        data["prerequisites"]["project_analysis"]["outputs"].append({
            "file": "results/reports/project_analysis_report.html",
            "desc": f"项目技术解析 HTML 报告 ({lines} 行)",
        })

    # --- Framework architecture ---
    data["framework_architecture"] = {
        "prerequisites": [
            {"id": "P-A", "name": "项目技术解析", "automated": True, "llm_required": True,
             "desc": "分析目标项目的代码量、技术栈、模块结构、API 端点等，生成 HTML 技术报告"},
            {"id": "P-B", "name": "规范逆向生成", "automated": True, "llm_required": True,
             "desc": "从源码逆向工程，生成结构化 OpenSpec 规范文档 (Markdown)"},
        ],
        "benchmark_stages": [
            {"id": "S-0", "name": "SDD 端到端开发", "desc": "基于规范驱动 AI 工具生成完整项目代码",
             "tracks_tokens": True},
            {"id": "S-1", "name": "质量验证", "desc": "对比生成代码与原始项目的结构/规模/语法一致性",
             "tracks_tokens": False},
            {"id": "S-2", "name": "数据汇总", "desc": "聚合 token、耗时、质量指标到 JSON/CSV",
             "tracks_tokens": False},
            {"id": "S-3", "name": "报告生成", "desc": "生成详细 HTML 评测报告（中文）含 token 分阶段明细",
             "tracks_tokens": False},
        ],
        "evaluation_dimensions": [
            {"dim": "Token 消耗", "metrics": "input / output / cache_read / cache_write tokens（按阶段细分）"},
            {"dim": "成本", "metrics": "USD / CNY（按阶段、按工具×模型组合）"},
            {"dim": "耗时", "metrics": "Wall-clock 秒（端到端 & 按阶段）"},
            {"dim": "代码质量", "metrics": "文件数比、LOC 比、目录相似度、文件重叠率、关键文件覆盖、语法通过率"},
            {"dim": "内容效率", "metrics": "有效代码比例、注释比例、样板代码比例、推理/思考 tokens 比例"},
        ],
        "token_tracking": {
            "methods": [
                {"name": "LiteLLM Proxy", "desc": "统一代理层拦截所有 API 调用，工具无关，精确 per-request 记录"},
                {"name": "工具原生", "desc": "Claude Code (OpenTelemetry) / Aider (session cost) / Cursor (有限)"},
            ],
            "recommended": "双轨追踪：LiteLLM Proxy (统一口径) + 工具原生 (交叉验证)",
        },
        "scripts": [
            {"file": "00_analyze_project.sh", "stage": "前置", "desc": "克隆目标仓库，统计文件/LOC/语言分布"},
            {"file": "01_generate_specs.sh", "stage": "前置", "desc": "逆向生成 OpenSpec 规范文档"},
            {"file": "02_sdd_develop.sh", "stage": "评测 S-0", "desc": "驱动 AI 工具执行 SDD 开发流程"},
            {"file": "03_validate.py", "stage": "评测 S-1", "desc": "验证生成代码质量（结构对比、语法检查）"},
            {"file": "04_report.py", "stage": "评测 S-2", "desc": "聚合 CSV/Markdown 汇总报告"},
            {"file": "05_generate_html_report.py", "stage": "评测 S-3", "desc": "生成详细 HTML 评测报告"},
            {"file": "06_project_analysis_report.py", "stage": "前置", "desc": "生成目标项目技术解析 HTML 报告"},
            {"file": "07_introduction_report.py", "stage": "文档", "desc": "生成本介绍章节"},
        ],
        "directory_layout": {
            "sdd-tee/": {
                "Makefile": "顶层编排",
                "config.yaml": "测评配置（工具、模型、阶段）",
                "PROPOSAL.md": "方案设计文档",
                "scripts/": "自动化脚本（前置 + 评测 + 报告）",
                "specs/": "逆向生成的 OpenSpec 规范（一次性产出）",
                "workspaces/": "各评测轮次的生成代码（运行时产生）",
                "results/": {
                    "project_analysis/": "项目分析数据（一次性）",
                    "runs/": "每次评测的 JSON 原始数据",
                    "reports/": "汇总报告、图表、HTML 报告",
                },
            }
        },
    }

    return data


# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------

def render_html(data):
    tp = data["target_project"]
    pa = data["prerequisites"]["project_analysis"]
    sg = data["prerequisites"]["spec_generation"]
    arch = data["framework_architecture"]
    specs = data["specs"]

    # Language bar chart data
    langs = tp.get("languages", {})
    total_loc = tp.get("total_loc", 1)

    lang_bars = ""
    lang_colors = {"Go": "#00ADD8", "Python": "#3776AB", "YAML": "#CB171E", "TypeScript": "#3178C6",
                   "Markdown": "#083FA1", "Other": "#999"}
    for lang, info in sorted(langs.items(), key=lambda x: -x[1].get("loc", 0)):
        loc = info.get("loc", 0)
        pct = loc / total_loc * 100 if total_loc else 0
        color = lang_colors.get(lang, "#999")
        lang_bars += f'<div style="display:flex;align-items:center;margin:4px 0"><span style="width:90px;font-weight:500">{lang}</span><div style="flex:1;background:#f0f0f0;border-radius:4px;height:22px;margin:0 10px"><div style="width:{pct:.1f}%;background:{color};height:100%;border-radius:4px;min-width:2px"></div></div><span style="width:120px;text-align:right;font-size:13px">{loc:,} LOC ({pct:.1f}%)</span></div>\n'

    # Module table
    modules = tp.get("modules", {})
    module_rows = ""
    for mname, minfo in sorted(modules.items(), key=lambda x: -x[1].get("loc", 0)):
        module_rows += f'<tr><td><code>{mname}</code></td><td>{minfo.get("lang","")}</td><td>{minfo.get("desc","")}</td><td style="text-align:right">{minfo.get("files",0)}</td><td style="text-align:right">{minfo.get("loc",0):,}</td></tr>\n'

    # Spec sections
    spec_cards = ""
    total_spec_lines = 0
    total_spec_chars = 0
    for sp in specs:
        total_spec_lines += sp["lines"]
        total_spec_chars += sp["chars"]
        sec_list = "".join(f"<li>{s}</li>" for s in sp["sections"])
        spec_cards += f"""
        <div class="card" style="margin-bottom:16px">
          <h4 style="margin:0 0 8px"><code>{sp['filename']}</code></h4>
          <div style="display:flex;gap:24px;font-size:13px;color:#666;margin-bottom:8px">
            <span>{sp['lines']} 行</span><span>{sp['chars']:,} 字符</span><span>{sp['words']:,} 词</span>
          </div>
          <details><summary style="cursor:pointer;color:#0066cc">章节结构 ({len(sp['sections'])} 节)</summary>
            <ol style="margin:8px 0;padding-left:20px;font-size:13px">{sec_list}</ol>
          </details>
        </div>"""

    # Subagent table for spec generation
    subagent_rows = ""
    for sa in sg.get("process", {}).get("subagents", []):
        subagent_rows += f'<tr><td>{sa["name"]}</td><td>{sa["scope"]}</td><td style="font-size:12px">{sa["input"]}</td><td><code>{sa["output"]}</code></td></tr>\n'

    # Token estimation for spec generation
    te = sg.get("token_estimation", {})

    # Prerequisite outputs
    pa_output_rows = ""
    for o in pa.get("outputs", []):
        pa_output_rows += f'<tr><td><code>{o["file"]}</code></td><td>{o["desc"]}</td></tr>\n'

    sg_output_rows = ""
    for o in sg.get("outputs", []):
        sg_output_rows += f'<tr><td><code>{o["file"]}</code></td><td>{o["desc"]}</td></tr>\n'

    # Framework stages
    prereq_rows = ""
    for p in arch.get("prerequisites", []):
        prereq_rows += f'<tr><td><span class="badge badge-prereq">{p["id"]}</span></td><td>{p["name"]}</td><td>{p["desc"]}</td><td>{"✓" if p["llm_required"] else "—"}</td></tr>\n'

    stage_rows = ""
    for s in arch.get("benchmark_stages", []):
        stage_rows += f'<tr><td><span class="badge badge-stage">{s["id"]}</span></td><td>{s["name"]}</td><td>{s["desc"]}</td><td>{"✓" if s["tracks_tokens"] else "—"}</td></tr>\n'

    # Evaluation dimensions
    dim_rows = ""
    for d in arch.get("evaluation_dimensions", []):
        dim_rows += f'<tr><td style="font-weight:600">{d["dim"]}</td><td>{d["metrics"]}</td></tr>\n'

    # Scripts table
    script_rows = ""
    for sc in arch.get("scripts", []):
        badge_class = "badge-prereq" if "前置" in sc["stage"] else "badge-stage" if "评测" in sc["stage"] else "badge-doc"
        script_rows += f'<tr><td><code>{sc["file"]}</code></td><td><span class="badge {badge_class}">{sc["stage"]}</span></td><td>{sc["desc"]}</td></tr>\n'

    # Top-level dirs
    top_dirs = tp.get("top_dirs", {})
    dir_rows = ""
    for dname, dinfo in sorted(top_dirs.items(), key=lambda x: -x[1].get("loc", 0)):
        dir_rows += f'<tr><td><code>{dname}/</code></td><td style="text-align:right">{dinfo.get("count",0)}</td><td style="text-align:right">{dinfo.get("loc",0):,}</td></tr>\n'

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SDD-TEE 项目介绍与前置工作报告</title>
<style>
  :root {{ --bg: #f8f9fa; --card-bg: #fff; --border: #e0e0e0; --primary: #1a73e8;
           --accent: #34a853; --warn: #ea4335; --text: #202124; --muted: #5f6368; }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
         background: var(--bg); color: var(--text); line-height: 1.6; }}
  .container {{ max-width: 1100px; margin: 0 auto; padding: 24px 20px; }}
  h1 {{ font-size: 28px; margin-bottom: 8px; color: var(--primary); }}
  h2 {{ font-size: 22px; margin: 32px 0 16px; padding-bottom: 8px; border-bottom: 2px solid var(--primary); }}
  h3 {{ font-size: 18px; margin: 24px 0 12px; color: #333; }}
  h4 {{ font-size: 15px; color: #444; }}
  .subtitle {{ color: var(--muted); font-size: 15px; margin-bottom: 24px; }}
  .card {{ background: var(--card-bg); border: 1px solid var(--border); border-radius: 8px; padding: 20px; margin-bottom: 20px; }}
  .card-title {{ font-size: 16px; font-weight: 600; margin-bottom: 12px; }}
  .stat-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; }}
  .stat-box {{ background: var(--card-bg); border: 1px solid var(--border); border-radius: 8px;
               padding: 16px; text-align: center; }}
  .stat-box .value {{ font-size: 28px; font-weight: 700; color: var(--primary); }}
  .stat-box .label {{ font-size: 13px; color: var(--muted); margin-top: 4px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 14px; margin: 12px 0; }}
  th, td {{ padding: 8px 12px; border: 1px solid var(--border); text-align: left; }}
  th {{ background: #f1f3f4; font-weight: 600; font-size: 13px; }}
  tr:hover td {{ background: #f8f9fa; }}
  .badge {{ display: inline-block; padding: 2px 10px; border-radius: 12px; font-size: 12px; font-weight: 600; }}
  .badge-prereq {{ background: #e8f5e9; color: #2e7d32; }}
  .badge-stage {{ background: #e3f2fd; color: #1565c0; }}
  .badge-doc {{ background: #fff3e0; color: #e65100; }}
  .badge-info {{ background: #f3e5f5; color: #7b1fa2; }}
  .note {{ background: #fffde7; border-left: 4px solid #ffc107; padding: 12px 16px; margin: 12px 0;
           border-radius: 0 8px 8px 0; font-size: 13px; }}
  .toc {{ background: var(--card-bg); border: 1px solid var(--border); border-radius: 8px;
          padding: 16px 24px; margin-bottom: 24px; }}
  .toc ol {{ padding-left: 20px; }}
  .toc li {{ margin: 4px 0; }}
  .toc a {{ color: var(--primary); text-decoration: none; }}
  .toc a:hover {{ text-decoration: underline; }}
  .pipeline-flow {{ display: flex; align-items: stretch; gap: 0; margin: 20px 0; flex-wrap: wrap; }}
  .pipeline-step {{ flex: 1; min-width: 140px; padding: 14px; text-align: center; position: relative; }}
  .pipeline-step .step-id {{ font-size: 12px; font-weight: 700; margin-bottom: 4px; }}
  .pipeline-step .step-name {{ font-size: 14px; font-weight: 600; }}
  .pipeline-step .step-desc {{ font-size: 11px; color: #666; margin-top: 4px; }}
  .pipeline-prereq {{ background: #e8f5e9; border: 1px solid #a5d6a7; border-radius: 8px; margin-right: 8px; }}
  .pipeline-bench {{ background: #e3f2fd; border: 1px solid #90caf9; border-radius: 8px; margin-right: 8px; }}
  .arrow {{ display: flex; align-items: center; font-size: 24px; color: #999; padding: 0 4px; }}
  code {{ background: #f1f3f4; padding: 1px 6px; border-radius: 4px; font-size: 13px; }}
  .footer {{ text-align: center; padding: 24px; color: var(--muted); font-size: 12px; border-top: 1px solid var(--border); margin-top: 32px; }}
  @media print {{ body {{ background: #fff; }} .container {{ max-width: 100%; }} }}
</style>
</head>
<body>
<div class="container">

<h1>SDD-TEE 项目介绍与前置工作报告</h1>
<p class="subtitle">SDD Token Efficiency Evaluation &mdash; 前置工作详情、规范文档概览与框架技术架构 &nbsp;|&nbsp; 生成时间：{data['generated_at'][:19]}Z</p>

<div class="toc">
  <strong>目录</strong>
  <ol>
    <li><a href="#overview">框架概述</a></li>
    <li><a href="#target">目标工程技术概况</a></li>
    <li><a href="#prereq">前置工作详情</a>
      <ol>
        <li><a href="#pa">项目技术解析</a></li>
        <li><a href="#sg">规范逆向生成</a></li>
      </ol>
    </li>
    <li><a href="#specs">规范文档概览</a></li>
    <li><a href="#arch">评测框架技术架构</a></li>
    <li><a href="#ref">引用说明</a></li>
  </ol>
</div>

<!-- ================================================================ -->
<h2 id="overview">1. 框架概述</h2>

<div class="card">
  <p><strong>SDD-TEE</strong>（SDD Token Efficiency Evaluation）是一个基于
  <strong>规范驱动开发 (Specification-Driven Development)</strong> 的 AI Coding Assistant Token 效率评估框架。</p>
  <p style="margin-top:12px">核心思路：逆向解析真实开源项目 <a href="https://github.com/ShijunDeng/agentcube">agentcube</a>
  的源码生成结构化规范文档，再用不同的 AI 编码工具（Claude Code、Aider、Cursor 等）× 不同模型组合，
  端到端完成 SDD 开发，<strong>量化各阶段的 Token 消耗、耗时和代码质量</strong>，为后续 Token 提效研究提供评估基线。</p>
  <p style="margin-top:12px;font-size:13px;color:var(--muted)">
    仓库地址：<a href="{data['framework']['repo_url']}">{data['framework']['repo_url']}</a>
  </p>
</div>

<h3>流水线总览</h3>
<div class="pipeline-flow">
  <div class="pipeline-step pipeline-prereq">
    <div class="step-id">P-A</div><div class="step-name">项目技术解析</div><div class="step-desc">一次性</div>
  </div>
  <div class="arrow">&rarr;</div>
  <div class="pipeline-step pipeline-prereq">
    <div class="step-id">P-B</div><div class="step-name">规范逆向生成</div><div class="step-desc">一次性</div>
  </div>
  <div class="arrow">&rArr;</div>
  <div class="pipeline-step pipeline-bench">
    <div class="step-id">S-0</div><div class="step-name">SDD 开发</div><div class="step-desc">核心评测</div>
  </div>
  <div class="arrow">&rarr;</div>
  <div class="pipeline-step pipeline-bench">
    <div class="step-id">S-1</div><div class="step-name">质量验证</div><div class="step-desc">自动对比</div>
  </div>
  <div class="arrow">&rarr;</div>
  <div class="pipeline-step pipeline-bench">
    <div class="step-id">S-2/3</div><div class="step-name">汇总报告</div><div class="step-desc">HTML/CSV</div>
  </div>
</div>
<div class="note">
  <strong>绿色</strong>为一次性前置工作（成果可复用，Token/耗时不计入评测基线）；<strong>蓝色</strong>为每轮评测需执行的阶段。
</div>

<!-- ================================================================ -->
<h2 id="target">2. 目标工程技术概况</h2>

<div class="stat-grid">
  <div class="stat-box"><div class="value">{tp.get('total_files', 0)}</div><div class="label">总文件数</div></div>
  <div class="stat-box"><div class="value">{tp.get('total_loc', 0):,}</div><div class="label">总代码行数 (LOC)</div></div>
  <div class="stat-box"><div class="value">{len(langs)}</div><div class="label">主要编程语言</div></div>
  <div class="stat-box"><div class="value">{len(modules)}</div><div class="label">功能模块</div></div>
</div>

<div class="card" style="margin-top:16px">
  <div class="card-title">语言分布</div>
  {lang_bars}
</div>

<div class="card">
  <div class="card-title">顶层目录规模</div>
  <table>
    <thead><tr><th>目录</th><th style="text-align:right">文件数</th><th style="text-align:right">LOC</th></tr></thead>
    <tbody>{dir_rows}</tbody>
  </table>
</div>

<div class="card">
  <div class="card-title">功能模块清单</div>
  <table>
    <thead><tr><th>模块</th><th>语言</th><th>描述</th><th style="text-align:right">文件</th><th style="text-align:right">LOC</th></tr></thead>
    <tbody>{module_rows}</tbody>
  </table>
  <p style="font-size:12px;color:var(--muted);margin-top:8px">完整技术解析详见
    <a href="project_analysis_report.html">project_analysis_report.html</a></p>
</div>

<!-- ================================================================ -->
<h2 id="prereq">3. 前置工作详情</h2>

<div class="stat-grid">
  <div class="stat-box">
    <div class="value">{pa.get('duration_seconds', 7)}s + {sg.get('duration_seconds', 194)}s</div>
    <div class="label">项目解析 + 规范生成 耗时</div>
  </div>
  <div class="stat-box">
    <div class="value">{pa.get('duration_seconds', 7) + sg.get('duration_seconds', 194)}s</div>
    <div class="label">前置工作总耗时</div>
  </div>
  <div class="stat-box">
    <div class="value">~{te.get('estimated_total_tokens', 97000):,}</div>
    <div class="label">规范生成估算 Token 消耗</div>
  </div>
  <div class="stat-box">
    <div class="value">{total_spec_lines}</div>
    <div class="label">规范文档总行数</div>
  </div>
</div>

<!-- 3.1 项目技术解析 -->
<h3 id="pa">3.1 项目技术解析 <span class="badge badge-prereq">P-A</span></h3>
<div class="card">
  <table>
    <tr><th style="width:140px">耗时</th><td><strong>{pa.get('duration_seconds', 7)} 秒</strong></td></tr>
    <tr><th>LLM Token 消耗</th><td>无（纯脚本执行：git clone + 文件统计）</td></tr>
    <tr><th>执行工具</th><td><code>{pa.get('tool', 'Shell script')}</code></td></tr>
    <tr><th>说明</th><td>{pa.get('description', '')}</td></tr>
    <tr><th>备注</th><td>{pa.get('notes', '')}</td></tr>
  </table>

  <h4 style="margin-top:16px">产出文件</h4>
  <table>
    <thead><tr><th>文件路径</th><th>说明</th></tr></thead>
    <tbody>{pa_output_rows}</tbody>
  </table>

  <div class="note" style="margin-top:12px">
    项目技术解析为一次性工作。报告生成脚本 <code>06_project_analysis_report.py</code> 除统计外还使用 LLM
    生成模块描述等结构化信息，但该过程属于报告美化，不影响评测流程。
  </div>
</div>

<!-- 3.2 规范逆向生成 -->
<h3 id="sg">3.2 规范逆向生成 <span class="badge badge-prereq">P-B</span></h3>
<div class="card">
  <table>
    <tr><th style="width:140px">耗时</th><td><strong>{sg.get('duration_seconds', 194)} 秒</strong>（{sg.get('duration_seconds', 194) // 60}分{sg.get('duration_seconds', 194) % 60}秒）</td></tr>
    <tr><th>LLM Token 消耗</th><td>是（需要 LLM 分析源码、抽取接口规范）</td></tr>
    <tr><th>执行工具</th><td><code>{sg.get('tool', 'cursor-cli')}</code> + <code>{sg.get('model', 'claude-4.6-opus')}</code></td></tr>
    <tr><th>执行方式</th><td>{sg.get('process', {}).get('method', '')}</td></tr>
  </table>

  <h4 style="margin-top:16px">Subagent 执行详情</h4>
  <table>
    <thead><tr><th>Agent</th><th>负责范围</th><th>输入源码</th><th>产出文件</th></tr></thead>
    <tbody>{subagent_rows}</tbody>
  </table>

  <h4 style="margin-top:16px">Token 消耗估算</h4>
  <div class="note">
    <strong>{te.get('note', '')}</strong>
  </div>
  <table style="margin-top:8px">
    <thead><tr><th>指标</th><th style="text-align:right">估算值</th><th>说明</th></tr></thead>
    <tbody>
      <tr><td>Input Tokens</td><td style="text-align:right">~{te.get('estimated_input_tokens', 0):,}</td><td>3 个 subagent 各读取 20-30K tokens 源码上下文</td></tr>
      <tr><td>Output Tokens</td><td style="text-align:right">~{te.get('estimated_output_tokens', 0):,}</td><td>3 份规范文档合计 {total_spec_chars:,} 字符 &asymp; {total_spec_chars // 4:,} tokens</td></tr>
      <tr><td>Total Tokens</td><td style="text-align:right;font-weight:700">~{te.get('estimated_total_tokens', 0):,}</td><td></td></tr>
    </tbody>
  </table>

  <h4 style="margin-top:16px">产出文件</h4>
  <table>
    <thead><tr><th>文件路径</th><th>说明</th></tr></thead>
    <tbody>{sg_output_rows}</tbody>
  </table>
</div>

<!-- ================================================================ -->
<h2 id="specs">4. 规范文档概览</h2>

<div class="stat-grid" style="margin-bottom:16px">
  <div class="stat-box"><div class="value">{len(specs)}</div><div class="label">规范文件数</div></div>
  <div class="stat-box"><div class="value">{total_spec_lines}</div><div class="label">总行数</div></div>
  <div class="stat-box"><div class="value">{total_spec_chars:,}</div><div class="label">总字符数</div></div>
</div>

{spec_cards}

<div class="note">
  规范文档为评测的核心输入，所有 AI 工具 &times; 模型组合在 SDD 开发阶段 (S-0) 均基于相同的规范执行，确保评测公平性。
  规范生成为一次性工作，后续评测直接引用 <code>specs/</code> 目录中的文件。
</div>

<!-- ================================================================ -->
<h2 id="arch">5. 评测框架技术架构</h2>

<h3>5.1 流水线阶段定义</h3>
<div class="card">
  <h4>前置工作（一次性，不计入评测基线）</h4>
  <table>
    <thead><tr><th>编号</th><th>阶段</th><th>说明</th><th>需 LLM</th></tr></thead>
    <tbody>{prereq_rows}</tbody>
  </table>

  <h4 style="margin-top:16px">评测阶段（每轮执行）</h4>
  <table>
    <thead><tr><th>编号</th><th>阶段</th><th>说明</th><th>追踪 Token</th></tr></thead>
    <tbody>{stage_rows}</tbody>
  </table>
</div>

<h3>5.2 评测维度</h3>
<div class="card">
  <table>
    <thead><tr><th style="width:120px">维度</th><th>指标</th></tr></thead>
    <tbody>{dim_rows}</tbody>
  </table>
</div>

<h3>5.3 Token 追踪方案</h3>
<div class="card">
  <table>
    <thead><tr><th>方式</th><th>说明</th></tr></thead>
    <tbody>
      {"".join(f'<tr><td style="font-weight:600">{m["name"]}</td><td>{m["desc"]}</td></tr>' for m in arch.get("token_tracking", {}).get("methods", []))}
    </tbody>
  </table>
  <p style="margin-top:8px;font-size:13px"><strong>推荐策略：</strong>{arch.get("token_tracking", {}).get("recommended", "")}</p>
</div>

<h3>5.4 脚本清单</h3>
<div class="card">
  <table>
    <thead><tr><th>脚本文件</th><th>阶段</th><th>功能</th></tr></thead>
    <tbody>{script_rows}</tbody>
  </table>
</div>

<h3>5.5 支持的工具 &times; 模型矩阵</h3>
<div class="card">
  <table>
    <thead><tr><th>AI Coding 工具</th><th>类型</th><th>自动化友好度</th><th>Token 追踪</th></tr></thead>
    <tbody>
      <tr><td>Claude Code</td><td>CLI (headless)</td><td style="color:var(--accent)">★★★★★</td><td>OpenTelemetry + SDK</td></tr>
      <tr><td>Aider</td><td>CLI</td><td style="color:var(--accent)">★★★★★</td><td>Session cost file</td></tr>
      <tr><td>Cursor CLI</td><td>IDE (Agent mode)</td><td>★★★☆☆</td><td>有限（不暴露 per-request）</td></tr>
    </tbody>
  </table>
  <table style="margin-top:12px">
    <thead><tr><th>模型</th><th>提供商</th><th>Input $/MTok</th><th>Output $/MTok</th></tr></thead>
    <tbody>
      <tr><td>Claude Sonnet 4</td><td>Anthropic</td><td>$3.00</td><td>$15.00</td></tr>
      <tr><td>Claude Opus 4</td><td>Anthropic</td><td>$15.00</td><td>$75.00</td></tr>
      <tr><td>GPT-4.1</td><td>OpenAI</td><td>$2.00</td><td>$8.00</td></tr>
    </tbody>
  </table>
</div>

<!-- ================================================================ -->
<h2 id="ref">6. 引用说明</h2>

<div class="card">
  <p>本文档为 SDD-TEE 评测框架的<strong>独立介绍章节</strong>，包含所有一次性前置工作的详情。后续各轮评测报告可通过以下方式引用：</p>
  <table style="margin-top:12px">
    <thead><tr><th>引用项</th><th>文件路径</th><th>说明</th></tr></thead>
    <tbody>
      <tr><td>本介绍章节</td><td><code>results/reports/introduction.html</code></td><td>框架概述 + 前置工作 Token/耗时 + 规范概览</td></tr>
      <tr><td>项目技术解析</td><td><code>results/reports/project_analysis_report.html</code></td><td>目标工程详细技术报告</td></tr>
      <tr><td>Go 规范</td><td><code>specs/01_go_specification.md</code></td><td>Go 源码逆向规范</td></tr>
      <tr><td>Python 规范</td><td><code>specs/02_python_specification.md</code></td><td>Python 源码逆向规范</td></tr>
      <tr><td>基础设施规范</td><td><code>specs/03_infrastructure_specification.md</code></td><td>K8s/Docker/CI 逆向规范</td></tr>
      <tr><td>项目分析数据</td><td><code>results/project_analysis/analysis.json</code></td><td>原始分析 JSON</td></tr>
    </tbody>
  </table>
  <p style="margin-top:12px;font-size:13px;color:var(--muted)">
    评测报告模板见 <a href="mock_report.html">mock_report.html</a>（模拟数据预览版）。
  </p>
</div>

</div><!-- .container -->

<div class="footer">
  SDD-TEE (SDD Token Efficiency Evaluation) &mdash; 生成时间 {data['generated_at'][:19]}Z &nbsp;|&nbsp;
  <a href="https://github.com/ShijunDeng/sdd-tee">GitHub</a>
</div>
</body>
</html>"""
    return html


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="SDD-TEE Introduction Report Generator")
    parser.add_argument("--source-dir", default=None,
                        help="Path to cloned agentcube source (for live analysis)")
    parser.add_argument("--output", default="results/reports/introduction.html",
                        help="Output HTML file path")
    parser.add_argument("--data-output", default="results/reports/introduction.json",
                        help="Output JSON data file path")
    args = parser.parse_args()

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    print(f"[07] Collecting prerequisite data from {base_dir} ...")
    data = collect_prerequisite_data(base_dir, args.source_dir)

    os.makedirs(os.path.dirname(os.path.join(base_dir, args.output)), exist_ok=True)

    json_path = os.path.join(base_dir, args.data_output)
    with open(json_path, 'w') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[07] Data saved → {json_path}")

    html = render_html(data)
    html_path = os.path.join(base_dir, args.output)
    with open(html_path, 'w') as f:
        f.write(html)
    print(f"[07] HTML report saved → {html_path}")


if __name__ == "__main__":
    main()
