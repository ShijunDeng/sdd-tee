#!/usr/bin/env python3
"""
生成 SDD Benchmark HTML 详细报告。
支持真实数据和模拟数据两种模式。

Usage:
  python3 scripts/05_generate_html_report.py --mock          # 模拟数据预览
  python3 scripts/05_generate_html_report.py --data results/runs/xxx.json  # 真实数据
"""

import argparse
import json
import random
import os
from datetime import datetime, timezone
from pathlib import Path


def generate_mock_data():
    """生成模拟测评数据，用于报表确认。"""

    def _mock_stage(name, desc, dur_range, input_range, output_range,
                    cache_ratio=0.3, files_range=(0, 0), loc_range=(0, 0)):
        dur = random.randint(*dur_range)
        input_tok = random.randint(*input_range)
        output_tok = random.randint(*output_range)
        cache_read = int(input_tok * random.uniform(cache_ratio * 0.5, cache_ratio * 1.5))
        cache_write = int(input_tok * random.uniform(0.05, 0.15))
        files = random.randint(*files_range)
        loc = random.randint(*loc_range)

        # 模拟 API 调用明细
        api_calls = []
        remaining_input = input_tok
        remaining_output = output_tok
        call_idx = 0
        while remaining_input > 0 or remaining_output > 0:
            call_idx += 1
            ci = min(remaining_input, random.randint(2000, 30000))
            co = min(remaining_output, random.randint(500, 8000))
            remaining_input -= ci
            remaining_output -= co
            api_calls.append({
                "call_id": call_idx,
                "input_tokens": ci,
                "output_tokens": co,
                "cache_read_tokens": int(ci * random.uniform(0, cache_ratio * 2)),
                "cache_write_tokens": int(ci * random.uniform(0, 0.1)),
                "duration_ms": random.randint(800, 15000),
                "tool_calls": random.randint(0, 5),
                "status": "success"
            })

        # 有效内容分析
        total_output_chars = output_tok * 4  # 粗估每token ~4字符
        code_chars = int(total_output_chars * random.uniform(0.4, 0.7))
        comment_chars = int(total_output_chars * random.uniform(0.05, 0.15))
        boilerplate_chars = int(total_output_chars * random.uniform(0.1, 0.2))
        thinking_chars = total_output_chars - code_chars - comment_chars - boilerplate_chars

        return {
            "name": name,
            "description": desc,
            "duration_seconds": dur,
            "tokens": {
                "input_tokens": input_tok,
                "output_tokens": output_tok,
                "cache_read_tokens": cache_read,
                "cache_write_tokens": cache_write,
                "total_tokens": input_tok + output_tok
            },
            "cost": {
                "input_cost_usd": round(input_tok / 1_000_000 * 3.0, 4),
                "output_cost_usd": round(output_tok / 1_000_000 * 15.0, 4),
                "cache_read_cost_usd": round(cache_read / 1_000_000 * 0.3, 4),
                "cache_write_cost_usd": round(cache_write / 1_000_000 * 3.75, 4),
                "total_cost_usd": 0  # 下面计算
            },
            "content_produced": {
                "files_created": files,
                "lines_of_code": loc,
                "total_output_chars": total_output_chars,
                "effective_code_chars": code_chars,
                "comment_chars": comment_chars,
                "boilerplate_chars": boilerplate_chars,
                "thinking_reasoning_chars": thinking_chars,
                "effective_ratio": round(code_chars / max(total_output_chars, 1), 4)
            },
            "api_calls": api_calls,
            "api_call_count": len(api_calls)
        }

    # 计算总成本
    def _calc_cost(stage):
        c = stage["cost"]
        c["total_cost_usd"] = round(
            c["input_cost_usd"] + c["output_cost_usd"] +
            c["cache_read_cost_usd"] + c["cache_write_cost_usd"], 4
        )
        return stage

    stages = [
        _calc_cost(_mock_stage(
            "规划阶段", "基于规范文档生成实现计划和任务分解",
            (30, 90), (20000, 60000), (5000, 20000),
            cache_ratio=0.1, files_range=(1, 3), loc_range=(100, 500)
        )),
        _calc_cost(_mock_stage(
            "Go核心类型实现", "CRD 类型定义、API 注册、DeepCopy 生成",
            (60, 180), (40000, 120000), (15000, 50000),
            cache_ratio=0.3, files_range=(8, 15), loc_range=(800, 2000)
        )),
        _calc_cost(_mock_stage(
            "Go业务逻辑实现", "控制器、路由器、会话存储、工作负载管理器",
            (120, 360), (80000, 250000), (30000, 100000),
            cache_ratio=0.4, files_range=(15, 30), loc_range=(2000, 5000)
        )),
        _calc_cost(_mock_stage(
            "Python CLI实现", "Typer CLI 工具、运行时管理、服务层",
            (60, 180), (30000, 100000), (10000, 40000),
            cache_ratio=0.35, files_range=(10, 20), loc_range=(800, 2000)
        )),
        _calc_cost(_mock_stage(
            "Python SDK实现", "CodeInterpreter/AgentRuntime 客户端 SDK",
            (40, 120), (25000, 80000), (8000, 30000),
            cache_ratio=0.35, files_range=(8, 15), loc_range=(500, 1500)
        )),
        _calc_cost(_mock_stage(
            "Kubernetes配置实现", "Helm Charts、CRD YAML、RBAC、Dockerfile",
            (30, 90), (15000, 50000), (5000, 20000),
            cache_ratio=0.25, files_range=(10, 20), loc_range=(500, 1500)
        )),
        _calc_cost(_mock_stage(
            "CI/CD与文档", "GitHub Actions、README、设计文档",
            (30, 90), (10000, 40000), (5000, 15000),
            cache_ratio=0.2, files_range=(10, 25), loc_range=(300, 1000)
        )),
        _calc_cost(_mock_stage(
            "测试代码生成", "Go 单元测试、Python pytest、E2E 测试",
            (60, 180), (40000, 120000), (15000, 50000),
            cache_ratio=0.4, files_range=(10, 20), loc_range=(1000, 3000)
        )),
        _calc_cost(_mock_stage(
            "代码审查与修复", "编译检查、语法检查、修复问题",
            (30, 120), (30000, 80000), (5000, 20000),
            cache_ratio=0.5, files_range=(0, 5), loc_range=(0, 500)
        )),
    ]

    total_input = sum(s["tokens"]["input_tokens"] for s in stages)
    total_output = sum(s["tokens"]["output_tokens"] for s in stages)
    total_cache_read = sum(s["tokens"]["cache_read_tokens"] for s in stages)
    total_cache_write = sum(s["tokens"]["cache_write_tokens"] for s in stages)
    total_cost = sum(s["cost"]["total_cost_usd"] for s in stages)
    total_dur = sum(s["duration_seconds"] for s in stages)
    total_files = sum(s["content_produced"]["files_created"] for s in stages)
    total_loc = sum(s["content_produced"]["lines_of_code"] for s in stages)
    total_api_calls = sum(s["api_call_count"] for s in stages)

    return {
        "run_id": "mock_cursor-cli_claude-sonnet-4_20260321T120000Z",
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "is_mock": True,
        "project": {
            "name": "agentcube",
            "repo_url": "https://github.com/ShijunDeng/agentcube.git",
            "original_files": 275,
            "original_loc": 64625,
            "languages": ["Go", "Python", "YAML", "TypeScript"]
        },
        "tool": {
            "name": "cursor-cli",
            "display_name": "Cursor CLI (Agent 模式)",
            "version": "1.0.x"
        },
        "model": {
            "id": "claude-sonnet-4-20250514",
            "display_name": "Claude Sonnet 4",
            "provider": "Anthropic",
            "pricing": {
                "input_per_mtok_usd": 3.0,
                "output_per_mtok_usd": 15.0,
                "cache_read_per_mtok_usd": 0.3,
                "cache_write_per_mtok_usd": 3.75
            }
        },
        "stages": stages,
        "totals": {
            "duration_seconds": total_dur,
            "duration_display": f"{total_dur // 60}分{total_dur % 60}秒",
            "input_tokens": total_input,
            "output_tokens": total_output,
            "cache_read_tokens": total_cache_read,
            "cache_write_tokens": total_cache_write,
            "total_tokens": total_input + total_output,
            "total_cost_usd": round(total_cost, 4),
            "total_cost_cny": round(total_cost * 7.25, 2),
            "api_call_count": total_api_calls,
            "files_generated": total_files,
            "loc_generated": total_loc
        },
        "quality": {
            "files_generated": total_files,
            "loc_generated": total_loc,
            "original_files": 275,
            "original_loc": 64625,
            "file_count_ratio": round(total_files / 275, 4),
            "loc_ratio": round(total_loc / 64625, 4),
            "directory_similarity": round(random.uniform(0.85, 0.95), 4),
            "file_overlap_ratio": round(random.uniform(0.65, 0.80), 4),
            "key_files_rate": 1.0,
            "python_syntax_rate": 1.0,
            "yaml_syntax_rate": 1.0,
            "go_build_pass": random.choice([True, False])
        }
    }


def render_html(data):
    """渲染 HTML 报告。"""
    stages = data["stages"]
    totals = data["totals"]
    project = data["project"]
    tool = data["tool"]
    model = data["model"]
    quality = data["quality"]
    is_mock = data.get("is_mock", False)

    # 阶段颜色
    stage_colors = [
        "#4C78A8", "#F58518", "#E45756", "#72B7B2",
        "#54A24B", "#EECA3B", "#B279A2", "#FF9DA6", "#9D755D"
    ]

    def fmt_tokens(n):
        if n >= 1_000_000:
            return f"{n/1_000_000:.2f}M"
        if n >= 1_000:
            return f"{n/1_000:.1f}K"
        return str(n)

    def fmt_cost(usd):
        return f"${usd:.4f}"

    def fmt_pct(ratio):
        return f"{ratio * 100:.1f}%"

    def fmt_dur(s):
        if s >= 3600:
            return f"{s//3600}时{(s%3600)//60}分{s%60}秒"
        if s >= 60:
            return f"{s//60}分{s%60}秒"
        return f"{s}秒"

    # 构建阶段汇总行
    stage_rows = ""
    for i, s in enumerate(stages):
        color = stage_colors[i % len(stage_colors)]
        t = s["tokens"]
        c = s["cost"]
        cp = s["content_produced"]
        stage_rows += f"""
        <tr>
          <td><span style="display:inline-block;width:12px;height:12px;background:{color};border-radius:2px;margin-right:6px;vertical-align:middle;"></span>{s['name']}</td>
          <td class="num">{fmt_dur(s['duration_seconds'])}</td>
          <td class="num">{fmt_tokens(t['input_tokens'])}</td>
          <td class="num">{fmt_tokens(t['output_tokens'])}</td>
          <td class="num">{fmt_tokens(t['cache_read_tokens'])}</td>
          <td class="num">{fmt_tokens(t['total_tokens'])}</td>
          <td class="num">{fmt_cost(c['total_cost_usd'])}</td>
          <td class="num">{cp['files_created']}</td>
          <td class="num">{cp['lines_of_code']:,}</td>
          <td class="num">{fmt_pct(cp['effective_ratio'])}</td>
        </tr>"""

    # 阶段详情卡片
    stage_detail_cards = ""
    for i, s in enumerate(stages):
        color = stage_colors[i % len(stage_colors)]
        t = s["tokens"]
        c = s["cost"]
        cp = s["content_produced"]

        # API 调用明细（最多显示前10条）
        api_rows = ""
        for call in s["api_calls"][:15]:
            api_rows += f"""
            <tr>
              <td class="num">#{call['call_id']}</td>
              <td class="num">{call['input_tokens']:,}</td>
              <td class="num">{call['output_tokens']:,}</td>
              <td class="num">{call['cache_read_tokens']:,}</td>
              <td class="num">{call['duration_ms']:,}ms</td>
              <td class="num">{call['tool_calls']}</td>
              <td><span class="badge-ok">{call['status']}</span></td>
            </tr>"""
        remaining = len(s["api_calls"]) - 15
        if remaining > 0:
            api_rows += f'<tr><td colspan="7" style="text-align:center;color:#888;">...还有 {remaining} 条调用记录</td></tr>'

        # 产出内容构成条
        total_chars = max(cp["total_output_chars"], 1)
        code_pct = cp["effective_code_chars"] / total_chars * 100
        comment_pct = cp["comment_chars"] / total_chars * 100
        boiler_pct = cp["boilerplate_chars"] / total_chars * 100
        think_pct = cp["thinking_reasoning_chars"] / total_chars * 100

        stage_detail_cards += f"""
    <div class="card" id="stage-{i}">
      <h3 style="border-left:4px solid {color};padding-left:12px;">{s['name']}</h3>
      <p class="desc">{s['description']}</p>

      <div class="metrics-grid">
        <div class="metric-box">
          <div class="metric-label">耗时</div>
          <div class="metric-value">{fmt_dur(s['duration_seconds'])}</div>
        </div>
        <div class="metric-box">
          <div class="metric-label">API调用次数</div>
          <div class="metric-value">{s['api_call_count']}</div>
        </div>
        <div class="metric-box">
          <div class="metric-label">输入Token</div>
          <div class="metric-value">{t['input_tokens']:,}</div>
        </div>
        <div class="metric-box">
          <div class="metric-label">输出Token</div>
          <div class="metric-value">{t['output_tokens']:,}</div>
        </div>
        <div class="metric-box">
          <div class="metric-label">缓存读取Token</div>
          <div class="metric-value">{t['cache_read_tokens']:,}</div>
        </div>
        <div class="metric-box">
          <div class="metric-label">总Token</div>
          <div class="metric-value">{t['total_tokens']:,}</div>
        </div>
        <div class="metric-box">
          <div class="metric-label">费用</div>
          <div class="metric-value">{fmt_cost(c['total_cost_usd'])}</div>
        </div>
        <div class="metric-box">
          <div class="metric-label">生成文件数</div>
          <div class="metric-value">{cp['files_created']}</div>
        </div>
        <div class="metric-box">
          <div class="metric-label">生成代码行数</div>
          <div class="metric-value">{cp['lines_of_code']:,}</div>
        </div>
      </div>

      <h4>费用明细</h4>
      <table class="detail-table">
        <tr><th>类别</th><th>Token数</th><th>单价($/MToken)</th><th>费用($)</th><th>占比</th></tr>
        <tr><td>输入Token</td><td class="num">{t['input_tokens']:,}</td><td class="num">{model['pricing']['input_per_mtok_usd']}</td><td class="num">{fmt_cost(c['input_cost_usd'])}</td><td class="num">{fmt_pct(c['input_cost_usd']/max(c['total_cost_usd'],0.0001))}</td></tr>
        <tr><td>输出Token</td><td class="num">{t['output_tokens']:,}</td><td class="num">{model['pricing']['output_per_mtok_usd']}</td><td class="num">{fmt_cost(c['output_cost_usd'])}</td><td class="num">{fmt_pct(c['output_cost_usd']/max(c['total_cost_usd'],0.0001))}</td></tr>
        <tr><td>缓存读取</td><td class="num">{t['cache_read_tokens']:,}</td><td class="num">{model['pricing']['cache_read_per_mtok_usd']}</td><td class="num">{fmt_cost(c['cache_read_cost_usd'])}</td><td class="num">{fmt_pct(c['cache_read_cost_usd']/max(c['total_cost_usd'],0.0001))}</td></tr>
        <tr><td>缓存写入</td><td class="num">{t['cache_write_tokens']:,}</td><td class="num">{model['pricing']['cache_write_per_mtok_usd']}</td><td class="num">{fmt_cost(c['cache_write_cost_usd'])}</td><td class="num">{fmt_pct(c['cache_write_cost_usd']/max(c['total_cost_usd'],0.0001))}</td></tr>
        <tr class="total-row"><td><b>合计</b></td><td class="num"><b>{t['total_tokens']:,}</b></td><td></td><td class="num"><b>{fmt_cost(c['total_cost_usd'])}</b></td><td class="num"><b>100%</b></td></tr>
      </table>

      <h4>输出内容构成分析</h4>
      <div class="stacked-bar">
        <div style="width:{code_pct:.1f}%;background:#54A24B;" title="有效代码: {fmt_pct(code_pct/100)}"></div>
        <div style="width:{comment_pct:.1f}%;background:#4C78A8;" title="注释: {fmt_pct(comment_pct/100)}"></div>
        <div style="width:{boiler_pct:.1f}%;background:#EECA3B;" title="模板/样板代码: {fmt_pct(boiler_pct/100)}"></div>
        <div style="width:{think_pct:.1f}%;background:#E45756;" title="推理/思考: {fmt_pct(think_pct/100)}"></div>
      </div>
      <div class="bar-legend">
        <span><span class="dot" style="background:#54A24B;"></span>有效代码 {fmt_pct(code_pct/100)}</span>
        <span><span class="dot" style="background:#4C78A8;"></span>注释 {fmt_pct(comment_pct/100)}</span>
        <span><span class="dot" style="background:#EECA3B;"></span>模板/样板 {fmt_pct(boiler_pct/100)}</span>
        <span><span class="dot" style="background:#E45756;"></span>推理/思考 {fmt_pct(think_pct/100)}</span>
      </div>

      <h4>Token效率指标</h4>
      <div class="metrics-grid">
        <div class="metric-box">
          <div class="metric-label">每行代码消耗Token</div>
          <div class="metric-value">{round(t['total_tokens']/max(cp['lines_of_code'],1), 1)}</div>
        </div>
        <div class="metric-box">
          <div class="metric-label">每文件消耗Token</div>
          <div class="metric-value">{round(t['total_tokens']/max(cp['files_created'],1)):,}</div>
        </div>
        <div class="metric-box">
          <div class="metric-label">有效输出率</div>
          <div class="metric-value">{fmt_pct(cp['effective_ratio'])}</div>
        </div>
        <div class="metric-box">
          <div class="metric-label">每秒生成Token</div>
          <div class="metric-value">{round(t['output_tokens']/max(s['duration_seconds'],1), 1)}</div>
        </div>
      </div>

      <details>
        <summary>API 调用明细（共 {s['api_call_count']} 次）</summary>
        <table class="detail-table">
          <tr><th>序号</th><th>输入Token</th><th>输出Token</th><th>缓存读取</th><th>耗时</th><th>工具调用</th><th>状态</th></tr>
          {api_rows}
        </table>
      </details>
    </div>"""

    # 总成本饼图数据 (CSS实现)
    cost_by_stage = [(s["name"], s["cost"]["total_cost_usd"]) for s in stages]
    cost_by_stage.sort(key=lambda x: -x[1])

    cost_bar_items = ""
    for i, (name, cost) in enumerate(cost_by_stage):
        pct = cost / max(totals["total_cost_usd"], 0.0001) * 100
        color = stage_colors[stages.index(next(s for s in stages if s["name"] == name)) % len(stage_colors)]
        cost_bar_items += f"""
        <div class="cost-bar-row">
          <span class="cost-bar-label">{name}</span>
          <div class="cost-bar-track">
            <div class="cost-bar-fill" style="width:{pct:.1f}%;background:{color};"></div>
          </div>
          <span class="cost-bar-value">{fmt_cost(cost)} ({fmt_pct(pct/100)})</span>
        </div>"""

    mock_banner = ""
    if is_mock:
        mock_banner = '<div class="mock-banner">⚠ 本报告使用模拟数据生成，仅用于确认报表格式和内容</div>'

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SDD Benchmark 测评报告 — {project['name']}</title>
<style>
  :root {{ --bg: #f8f9fa; --card: #fff; --border: #e0e0e0; --text: #333; --muted: #888; }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Noto Sans SC', sans-serif; background: var(--bg); color: var(--text); line-height: 1.6; }}
  .container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
  h1 {{ font-size: 1.8em; margin-bottom: 8px; }}
  h2 {{ font-size: 1.3em; margin: 24px 0 12px; border-bottom: 2px solid #4C78A8; padding-bottom: 6px; }}
  h3 {{ font-size: 1.15em; margin: 16px 0 8px; }}
  h4 {{ font-size: 1em; margin: 14px 0 8px; color: #555; }}
  .card {{ background: var(--card); border-radius: 8px; padding: 20px; margin: 16px 0; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
  .desc {{ color: var(--muted); font-size: 0.9em; margin-bottom: 12px; }}
  .mock-banner {{ background: #FFF3CD; border: 1px solid #FFEEBA; color: #856404; padding: 12px 20px; border-radius: 6px; margin-bottom: 16px; font-weight: 600; text-align: center; font-size: 1.05em; }}
  .meta-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; margin: 12px 0; }}
  .meta-item {{ font-size: 0.9em; }}
  .meta-item .label {{ color: var(--muted); }}
  .metrics-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 10px; margin: 12px 0; }}
  .metric-box {{ background: #f4f6f8; border-radius: 6px; padding: 12px; text-align: center; }}
  .metric-label {{ font-size: 0.78em; color: var(--muted); margin-bottom: 4px; }}
  .metric-value {{ font-size: 1.2em; font-weight: 700; color: #333; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.88em; margin: 8px 0; }}
  th {{ background: #f0f2f5; padding: 8px 10px; text-align: left; font-weight: 600; border-bottom: 2px solid var(--border); }}
  td {{ padding: 7px 10px; border-bottom: 1px solid #eee; }}
  .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .total-row {{ background: #f9f9f9; font-weight: 600; }}
  .badge-ok {{ background: #d4edda; color: #155724; padding: 2px 8px; border-radius: 10px; font-size: 0.82em; }}
  .stacked-bar {{ display: flex; height: 24px; border-radius: 4px; overflow: hidden; margin: 8px 0; }}
  .stacked-bar > div {{ height: 100%; }}
  .bar-legend {{ display: flex; gap: 16px; font-size: 0.82em; color: #555; flex-wrap: wrap; }}
  .dot {{ display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 4px; vertical-align: middle; }}
  .cost-bar-row {{ display: flex; align-items: center; margin: 6px 0; font-size: 0.88em; }}
  .cost-bar-label {{ width: 160px; flex-shrink: 0; }}
  .cost-bar-track {{ flex: 1; height: 18px; background: #eee; border-radius: 3px; margin: 0 10px; overflow: hidden; }}
  .cost-bar-fill {{ height: 100%; border-radius: 3px; transition: width 0.3s; }}
  .cost-bar-value {{ width: 160px; text-align: right; flex-shrink: 0; font-variant-numeric: tabular-nums; }}
  .summary-box {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; }}
  .summary-item {{ background: var(--card); border-radius: 8px; padding: 16px; text-align: center; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
  .summary-item .big {{ font-size: 1.6em; font-weight: 700; color: #4C78A8; }}
  .summary-item .label {{ font-size: 0.82em; color: var(--muted); margin-top: 4px; }}
  details {{ margin: 10px 0; }}
  summary {{ cursor: pointer; color: #4C78A8; font-weight: 600; padding: 4px 0; }}
  details[open] summary {{ margin-bottom: 8px; }}
  @media (max-width: 768px) {{
    .metrics-grid {{ grid-template-columns: repeat(2, 1fr); }}
    .cost-bar-label, .cost-bar-value {{ width: 100px; font-size: 0.8em; }}
  }}
</style>
</head>
<body>
<div class="container">

{mock_banner}

<h1>SDD Benchmark 测评报告</h1>
<p class="desc">基于规范驱动开发 (Specification-Driven Development) 的 Token 效率基线测评</p>

<div class="card">
  <div class="meta-grid">
    <div class="meta-item"><span class="label">目标项目：</span><a href="{project['repo_url']}">{project['name']}</a></div>
    <div class="meta-item"><span class="label">原始规模：</span>{project['original_files']} 文件 / {project['original_loc']:,} 行代码</div>
    <div class="meta-item"><span class="label">CLI 工具：</span>{tool['display_name']}</div>
    <div class="meta-item"><span class="label">模型：</span>{model['display_name']} ({model['provider']})</div>
    <div class="meta-item"><span class="label">测评时间：</span>{data['timestamp']}</div>
    <div class="meta-item"><span class="label">运行ID：</span><code style="font-size:0.85em">{data['run_id']}</code></div>
  </div>
</div>

<h2>一、总体概览</h2>

<div class="summary-box">
  <div class="summary-item"><div class="big">{totals['duration_display']}</div><div class="label">总耗时</div></div>
  <div class="summary-item"><div class="big">{fmt_tokens(totals['total_tokens'])}</div><div class="label">总Token消耗</div></div>
  <div class="summary-item"><div class="big">{fmt_cost(totals['total_cost_usd'])}</div><div class="label">总费用 (≈¥{totals['total_cost_cny']})</div></div>
  <div class="summary-item"><div class="big">{totals['api_call_count']}</div><div class="label">API调用次数</div></div>
  <div class="summary-item"><div class="big">{totals['files_generated']}</div><div class="label">生成文件数</div></div>
  <div class="summary-item"><div class="big">{totals['loc_generated']:,}</div><div class="label">生成代码行数</div></div>
</div>

<h2>二、各阶段概览</h2>

<div class="card" style="overflow-x:auto;">
<table>
  <thead>
    <tr>
      <th>阶段</th><th class="num">耗时</th>
      <th class="num">输入Token</th><th class="num">输出Token</th><th class="num">缓存读取</th><th class="num">总Token</th>
      <th class="num">费用($)</th>
      <th class="num">文件</th><th class="num">代码行</th><th class="num">有效率</th>
    </tr>
  </thead>
  <tbody>
    {stage_rows}
    <tr class="total-row">
      <td><b>合计</b></td>
      <td class="num"><b>{fmt_dur(totals['duration_seconds'])}</b></td>
      <td class="num"><b>{fmt_tokens(totals['input_tokens'])}</b></td>
      <td class="num"><b>{fmt_tokens(totals['output_tokens'])}</b></td>
      <td class="num"><b>{fmt_tokens(totals['cache_read_tokens'])}</b></td>
      <td class="num"><b>{fmt_tokens(totals['total_tokens'])}</b></td>
      <td class="num"><b>{fmt_cost(totals['total_cost_usd'])}</b></td>
      <td class="num"><b>{totals['files_generated']}</b></td>
      <td class="num"><b>{totals['loc_generated']:,}</b></td>
      <td></td>
    </tr>
  </tbody>
</table>
</div>

<h2>三、费用分布</h2>

<div class="card">
  <h4>按阶段费用排名</h4>
  {cost_bar_items}
</div>

<h2>四、各阶段详细分析</h2>

{stage_detail_cards}

<h2>五、质量评估</h2>

<div class="card">
  <div class="metrics-grid">
    <div class="metric-box"><div class="metric-label">文件覆盖率</div><div class="metric-value">{fmt_pct(quality['file_count_ratio'])}</div></div>
    <div class="metric-box"><div class="metric-label">代码行覆盖率</div><div class="metric-value">{fmt_pct(quality['loc_ratio'])}</div></div>
    <div class="metric-box"><div class="metric-label">目录相似度</div><div class="metric-value">{fmt_pct(quality['directory_similarity'])}</div></div>
    <div class="metric-box"><div class="metric-label">文件重叠率</div><div class="metric-value">{fmt_pct(quality['file_overlap_ratio'])}</div></div>
    <div class="metric-box"><div class="metric-label">关键文件覆盖</div><div class="metric-value">{fmt_pct(quality['key_files_rate'])}</div></div>
    <div class="metric-box"><div class="metric-label">Python语法通过</div><div class="metric-value">{fmt_pct(quality['python_syntax_rate'])}</div></div>
    <div class="metric-box"><div class="metric-label">YAML语法通过</div><div class="metric-value">{fmt_pct(quality['yaml_syntax_rate'])}</div></div>
    <div class="metric-box"><div class="metric-label">Go编译通过</div><div class="metric-value">{'✅ 是' if quality.get('go_build_pass') else '❌ 否'}</div></div>
  </div>
</div>

<h2>六、Token 效率总结</h2>

<div class="card">
  <div class="metrics-grid">
    <div class="metric-box"><div class="metric-label">每行代码消耗Token</div><div class="metric-value">{round(totals['total_tokens']/max(totals['loc_generated'],1), 1)}</div></div>
    <div class="metric-box"><div class="metric-label">每文件消耗Token</div><div class="metric-value">{round(totals['total_tokens']/max(totals['files_generated'],1)):,}</div></div>
    <div class="metric-box"><div class="metric-label">每分钟生成代码行</div><div class="metric-value">{round(totals['loc_generated']/(totals['duration_seconds']/60), 1)}</div></div>
    <div class="metric-box"><div class="metric-label">每美元生成代码行</div><div class="metric-value">{round(totals['loc_generated']/max(totals['total_cost_usd'],0.001))}</div></div>
    <div class="metric-box"><div class="metric-label">输入输出Token比</div><div class="metric-value">{round(totals['input_tokens']/max(totals['output_tokens'],1), 2)}:1</div></div>
    <div class="metric-box"><div class="metric-label">缓存命中率</div><div class="metric-value">{fmt_pct(totals['cache_read_tokens']/max(totals['input_tokens'],1))}</div></div>
  </div>
</div>

<div class="card" style="margin-top:24px;text-align:center;color:var(--muted);font-size:0.85em;">
  生成时间：{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')} ｜
  工具：SDD Benchmark Framework ｜
  <a href="https://github.com/ShijunDeng/sdd-benchmark">GitHub</a>
</div>

</div>
</body>
</html>"""
    return html


def main():
    parser = argparse.ArgumentParser(description="SDD Benchmark HTML Report Generator")
    parser.add_argument("--mock", action="store_true", help="使用模拟数据生成预览报告")
    parser.add_argument("--data", type=str, help="使用真实数据 JSON 文件")
    parser.add_argument("--output", type=str, default=None, help="输出 HTML 文件路径")
    args = parser.parse_args()

    if args.mock:
        data = generate_mock_data()
        output_default = "results/reports/mock_report.html"
    elif args.data:
        with open(args.data) as f:
            data = json.load(f)
        output_default = f"results/reports/{Path(args.data).stem}_report.html"
    else:
        parser.print_help()
        return

    output = args.output or output_default
    os.makedirs(os.path.dirname(output), exist_ok=True)

    html = render_html(data)
    with open(output, "w") as f:
        f.write(html)
    print(f"报告已生成: {output}")


if __name__ == "__main__":
    main()
