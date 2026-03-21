#!/usr/bin/env python3
"""
生成目标项目技术解析 HTML 报告。
Usage: python3 scripts/06_project_analysis_report.py [source_dir] [output_file]
"""

import os
import sys
import json
from datetime import datetime, timezone
from pathlib import Path
from collections import defaultdict


def analyze(source_dir):
    """Deep analysis of the target project."""

    EXCLUDE_DIRS = {'.git', 'node_modules', '__pycache__', '.mypy_cache', 'vendor'}

    def walk(d):
        for root, dirs, files in os.walk(d):
            dirs[:] = [x for x in dirs if x not in EXCLUDE_DIRS]
            for f in files:
                yield os.path.join(root, f)

    def ext(path):
        e = os.path.splitext(path)[1]
        return e if e else '(无扩展名)'

    def loc(path):
        try:
            with open(path, errors='ignore') as f:
                return sum(1 for _ in f)
        except Exception:
            return 0

    def rel(path):
        return os.path.relpath(path, source_dir)

    # ---- basic stats ----
    all_files = list(walk(source_dir))
    total_files = len(all_files)
    total_loc = sum(loc(f) for f in all_files)

    ext_stats = defaultdict(lambda: {'count': 0, 'loc': 0})
    for f in all_files:
        e = ext(f)
        ext_stats[e]['count'] += 1
        ext_stats[e]['loc'] += loc(f)

    # ---- Go analysis ----
    go_files = [f for f in all_files if f.endswith('.go')]
    go_test_files = [f for f in go_files if f.endswith('_test.go')]
    go_src_files = [f for f in go_files if not f.endswith('_test.go')]
    go_src_loc = sum(loc(f) for f in go_src_files)
    go_test_loc = sum(loc(f) for f in go_test_files)

    go_pkgs = set()
    for f in go_src_files:
        go_pkgs.add(os.path.dirname(rel(f)))

    # ---- Python analysis ----
    py_files = [f for f in all_files if f.endswith('.py')]
    py_test_files = [f for f in py_files if '/test' in f or 'test_' in os.path.basename(f)]
    py_src_files = [f for f in py_files if f not in py_test_files]
    py_src_loc = sum(loc(f) for f in py_src_files)
    py_test_loc = sum(loc(f) for f in py_test_files)

    # ---- YAML ----
    yaml_files = [f for f in all_files if f.endswith(('.yaml', '.yml'))]
    yaml_loc = sum(loc(f) for f in yaml_files)

    # ---- Docs ----
    md_files = [f for f in all_files if f.endswith('.md')]
    md_loc = sum(loc(f) for f in md_files)

    # ---- TS/TSX ----
    ts_files = [f for f in all_files if f.endswith(('.ts', '.tsx'))]
    ts_loc = sum(loc(f) for f in ts_files)

    # ---- Dir tree depth-1 ----
    top_dirs = defaultdict(lambda: {'count': 0, 'loc': 0})
    for f in all_files:
        r = rel(f)
        top = r.split('/')[0] if '/' in r else '(root)'
        top_dirs[top]['count'] += 1
        top_dirs[top]['loc'] += loc(f)

    # ---- module-level LOC ----
    module_loc = {}
    module_map = {
        'pkg/workloadmanager': ('Go', '工作负载管理器 — HTTP API、Sandbox 创建/GC、控制器'),
        'pkg/router': ('Go', '路由器 — 反向代理、会话管理、JWT 认证'),
        'pkg/store': ('Go', '会话存储 — Redis/Valkey 双后端'),
        'pkg/picod': ('Go', 'PicoD — Sandbox 内守护进程（执行命令、文件管理）'),
        'pkg/apis/runtime/v1alpha1': ('Go', 'CRD 类型定义 — AgentRuntime、CodeInterpreter'),
        'pkg/agentd': ('Go', 'AgentD — Sandbox 空闲清理控制器'),
        'pkg/common/types': ('Go', '共享 DTO — 请求/响应类型'),
        'pkg/api': ('Go', 'API 错误处理'),
        'client-go': ('Go', '生成的 K8s 客户端 — Clientset、Informers、Listers'),
        'cmd/router': ('Go', 'Router 二进制入口'),
        'cmd/workload-manager': ('Go', 'WorkloadManager 二进制入口'),
        'cmd/agentd': ('Go', 'AgentD 二进制入口'),
        'cmd/picod': ('Go', 'PicoD 二进制入口'),
        'cmd/cli/agentcube': ('Python', 'CLI 工具 — pack/build/publish/invoke/status'),
        'sdk-python/agentcube': ('Python', 'Python SDK — CodeInterpreterClient、AgentRuntimeClient'),
        'integrations/dify-plugin': ('Python', 'Dify 插件集成'),
        'example/pcap-analyzer': ('Python', '示例：PCAP 分析器 (FastAPI + LangGraph)'),
        'cmd/cli/examples': ('Python', '示例 Agent (hello-agent、math-agent)'),
        'manifests/charts/base': ('YAML', 'Helm Chart — 部署模板、RBAC、CRD'),
        'docs': ('Markdown/TS', '文档站 (Docusaurus) + 设计文档 + 开发指南'),
        '.github/workflows': ('YAML', 'CI/CD — 12 个 GitHub Actions 工作流'),
        'docker': ('Dockerfile', '容器镜像 — workloadmanager、router、picod'),
    }

    for mod_path, (lang, desc) in module_map.items():
        full = os.path.join(source_dir, mod_path)
        if os.path.exists(full):
            m_files = list(walk(full))
            m_loc = sum(loc(f) for f in m_files)
            m_count = len(m_files)
            src_loc_only = sum(loc(f) for f in m_files
                               if not f.endswith(('_test.go', '.pyc'))
                               and '/test' not in f
                               and 'test_' not in os.path.basename(f))
            module_loc[mod_path] = {
                'lang': lang, 'desc': desc,
                'files': m_count, 'loc': m_loc, 'src_loc': src_loc_only
            }

    return {
        'total_files': total_files,
        'total_loc': total_loc,
        'ext_stats': dict(sorted(ext_stats.items(), key=lambda x: -x[1]['loc'])),
        'go': {'src_files': len(go_src_files), 'test_files': len(go_test_files),
               'src_loc': go_src_loc, 'test_loc': go_test_loc, 'packages': sorted(go_pkgs)},
        'python': {'src_files': len(py_src_files), 'test_files': len(py_test_files),
                   'src_loc': py_src_loc, 'test_loc': py_test_loc},
        'yaml': {'files': len(yaml_files), 'loc': yaml_loc},
        'docs': {'md_files': len(md_files), 'md_loc': md_loc},
        'ts': {'files': len(ts_files), 'loc': ts_loc},
        'top_dirs': dict(sorted(top_dirs.items(), key=lambda x: -x[1]['loc'])),
        'modules': module_loc,
    }


def render_html(data, source_dir):
    d = data
    modules = d['modules']

    def bar(val, max_val, color='#4C78A8'):
        pct = min(val / max(max_val, 1) * 100, 100)
        return f'<div style="background:#eee;border-radius:3px;height:16px;width:100%;"><div style="background:{color};height:100%;width:{pct:.1f}%;border-radius:3px;"></div></div>'

    # Language pie (CSS bar)
    lang_data = [
        ('Go（源码）', d['go']['src_loc'], '#00ADD8'),
        ('Go（测试）', d['go']['test_loc'], '#5DC9E2'),
        ('Python（源码）', d['python']['src_loc'], '#3776AB'),
        ('Python（测试）', d['python']['test_loc'], '#7CB1D9'),
        ('YAML/Helm', d['yaml']['loc'], '#CB171E'),
        ('Markdown/文档', d['docs']['md_loc'], '#083FA1'),
        ('TypeScript/CSS', d['ts']['loc'], '#3178C6'),
    ]
    total_code = sum(x[1] for x in lang_data)
    lang_bars = ""
    for name, val, color in lang_data:
        if val == 0:
            continue
        pct = val / max(total_code, 1) * 100
        lang_bars += f"""
        <div class="lang-row">
          <span class="lang-name"><span class="dot" style="background:{color};"></span>{name}</span>
          <div class="lang-bar-track"><div class="lang-bar-fill" style="width:{pct:.1f}%;background:{color};"></div></div>
          <span class="lang-val">{val:,} 行 ({pct:.1f}%)</span>
        </div>"""

    # Ext table
    ext_rows = ""
    for ext_name, st in list(d['ext_stats'].items())[:20]:
        ext_rows += f"<tr><td><code>{ext_name}</code></td><td class='num'>{st['count']}</td><td class='num'>{st['loc']:,}</td></tr>"

    # Module table
    max_mod_loc = max((m['src_loc'] for m in modules.values()), default=1)
    mod_rows = ""
    for path, m in sorted(modules.items(), key=lambda x: -x[1]['src_loc']):
        mod_rows += f"""
        <tr>
          <td><code>{path}</code></td>
          <td>{m['lang']}</td>
          <td>{m['desc']}</td>
          <td class="num">{m['files']}</td>
          <td class="num">{m['src_loc']:,}</td>
          <td style="width:180px">{bar(m['src_loc'], max_mod_loc, '#4C78A8')}</td>
        </tr>"""

    # Top-dir table
    max_dir_loc = max((v['loc'] for v in d['top_dirs'].values()), default=1)
    dir_rows = ""
    for dname, st in list(d['top_dirs'].items())[:15]:
        dir_rows += f"""
        <tr>
          <td><code>{dname}/</code></td>
          <td class="num">{st['count']}</td>
          <td class="num">{st['loc']:,}</td>
          <td style="width:180px">{bar(st['loc'], max_dir_loc, '#54A24B')}</td>
        </tr>"""

    # Features & CRDs
    features = [
        ("AgentRuntime CRD", "自定义 AI Agent 运行时资源，支持 PodTemplate 定义、会话超时、最大会话时长"),
        ("CodeInterpreter CRD", "代码解释器资源，支持预热池 (WarmPool)、PicoD 认证模式、沙箱模板"),
        ("Workload Manager", "HTTP API 服务：创建/删除 Sandbox、TokenReview 认证、h2c HTTP/2、垃圾回收"),
        ("Router 反向代理", "基于会话的反向代理：自动创建会话、JWT 授权、并发控制(信号量)、最后活动时间追踪"),
        ("Redis/Valkey 会话存储", "双后端支持：Redis（默认）和 Valkey，ZSET 过期/活动索引，JSON 序列化"),
        ("PicoD 沙箱守护进程", "Sandbox 内执行引擎：命令执行(60s超时)、文件上传/下载/列表、RSA JWT 认证"),
        ("AgentD 空闲清理", "基于 controller-runtime 的 Sandbox 空闲检测与自动清理（15分钟超时）"),
        ("Python CLI (kubectl-agentcube)", "5 个子命令：pack(打包)、build(构建)、publish(发布)、invoke(调用)、status(状态)"),
        ("Python SDK", "CodeInterpreterClient + AgentRuntimeClient，支持上下文管理器，连接池"),
        ("Helm Chart 部署", "一键部署：Router + WorkloadManager + 可选 Volcano Scheduler，完整 RBAC"),
        ("Dify 插件集成", "Dify 平台代码解释器工具插件，支持会话复用"),
        ("CI/CD 管线", "12 个 GitHub Actions：构建、发布(ghcr.io)、E2E、lint、测试覆盖、代码生成校验等"),
        ("SandboxWarmPool 预热", "CodeInterpreter 预创建 Sandbox 池，通过 SandboxClaim 快速分配"),
        ("JWT 身份认证", "Router ↔ PicoD 之间的 RSA-2048 密钥对管理，自动创建 K8s Secret"),
        ("多架构镜像构建", "Dockerfile 支持 CGO_ENABLED=0 + TARGETARCH/TARGETOS 多平台构建"),
    ]
    feat_rows = ""
    for i, (name, desc) in enumerate(features, 1):
        feat_rows += f"<tr><td class='num'>{i}</td><td><b>{name}</b></td><td>{desc}</td></tr>"

    api_rows = """
        <tr><td>Router</td><td>GET</td><td><code>/health/live</code></td><td>存活探针</td></tr>
        <tr><td>Router</td><td>GET</td><td><code>/health/ready</code></td><td>就绪探针</td></tr>
        <tr><td>Router</td><td>GET/POST</td><td><code>/v1/namespaces/:ns/agent-runtimes/:name/invocations/*path</code></td><td>Agent 调用</td></tr>
        <tr><td>Router</td><td>GET/POST</td><td><code>/v1/namespaces/:ns/code-interpreters/:name/invocations/*path</code></td><td>代码解释器调用</td></tr>
        <tr><td>WorkloadMgr</td><td>GET</td><td><code>/health</code></td><td>健康检查</td></tr>
        <tr><td>WorkloadMgr</td><td>POST</td><td><code>/v1/agent-runtime</code></td><td>创建 AgentRuntime Sandbox</td></tr>
        <tr><td>WorkloadMgr</td><td>DELETE</td><td><code>/v1/agent-runtime/sessions/:sessionId</code></td><td>删除 Sandbox</td></tr>
        <tr><td>WorkloadMgr</td><td>POST</td><td><code>/v1/code-interpreter</code></td><td>创建 CodeInterpreter Sandbox</td></tr>
        <tr><td>WorkloadMgr</td><td>DELETE</td><td><code>/v1/code-interpreter/sessions/:sessionId</code></td><td>删除 Sandbox</td></tr>
        <tr><td>PicoD</td><td>POST</td><td><code>/api/execute</code></td><td>执行命令</td></tr>
        <tr><td>PicoD</td><td>POST</td><td><code>/api/files</code></td><td>上传文件</td></tr>
        <tr><td>PicoD</td><td>GET</td><td><code>/api/files</code></td><td>列出目录</td></tr>
        <tr><td>PicoD</td><td>GET</td><td><code>/api/files/*path</code></td><td>下载文件</td></tr>
        <tr><td>PicoD</td><td>GET</td><td><code>/health</code></td><td>健康检查</td></tr>
    """

    cli_rows = """
        <tr><td><code>pack</code></td><td>打包 Agent 工作空间：生成 Dockerfile、元数据文件</td><td>--workspace, --agent-name, --language, --entrypoint, --port</td></tr>
        <tr><td><code>build</code></td><td>构建 Docker 镜像：自动版本递增</td><td>--workspace, --proxy, --cloud-provider</td></tr>
        <tr><td><code>publish</code></td><td>发布到集群：AgentRuntime CR 或 K8s Deployment</td><td>--provider (agentcube|k8s), --image-url, --namespace, --node-port</td></tr>
        <tr><td><code>invoke</code></td><td>调用 Agent：HTTP POST + 会话管理</td><td>--payload, --header, --provider</td></tr>
        <tr><td><code>status</code></td><td>查询 Agent 部署状态</td><td>--provider</td></tr>
    """

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AgentCube 技术解析报告</title>
<style>
  :root {{ --bg: #f8f9fa; --card: #fff; --border: #e0e0e0; --text: #333; --muted: #888; }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Noto Sans SC', sans-serif; background: var(--bg); color: var(--text); line-height: 1.6; }}
  .container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
  h1 {{ font-size: 1.8em; margin-bottom: 4px; }}
  h2 {{ font-size: 1.3em; margin: 28px 0 12px; border-bottom: 2px solid #4C78A8; padding-bottom: 6px; }}
  h3 {{ font-size: 1.1em; margin: 16px 0 8px; }}
  .card {{ background: var(--card); border-radius: 8px; padding: 20px; margin: 14px 0; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
  .desc {{ color: var(--muted); font-size: 0.92em; }}
  .summary-box {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; }}
  .summary-item {{ background: var(--card); border-radius: 8px; padding: 14px; text-align: center; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
  .summary-item .big {{ font-size: 1.5em; font-weight: 700; color: #4C78A8; }}
  .summary-item .label {{ font-size: 0.8em; color: var(--muted); margin-top: 2px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.88em; margin: 8px 0; }}
  th {{ background: #f0f2f5; padding: 8px 10px; text-align: left; font-weight: 600; border-bottom: 2px solid var(--border); }}
  td {{ padding: 7px 10px; border-bottom: 1px solid #eee; }}
  .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .lang-row {{ display: flex; align-items: center; margin: 5px 0; font-size: 0.88em; }}
  .lang-name {{ width: 140px; flex-shrink: 0; }}
  .lang-bar-track {{ flex: 1; height: 16px; background: #eee; border-radius: 3px; margin: 0 10px; overflow: hidden; }}
  .lang-bar-fill {{ height: 100%; border-radius: 3px; }}
  .lang-val {{ width: 160px; text-align: right; flex-shrink: 0; font-variant-numeric: tabular-nums; }}
  .dot {{ display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 5px; vertical-align: middle; }}
  .arch-svg {{ text-align: center; margin: 16px 0; }}
  .arch-svg svg {{ max-width: 100%; }}
  code {{ background: #f0f2f5; padding: 1px 5px; border-radius: 3px; font-size: 0.9em; }}
  @media (max-width: 768px) {{ .lang-name {{ width: 100px; }} .lang-val {{ width: 120px; }} }}
</style>
</head>
<body>
<div class="container">

<h1>AgentCube 技术解析报告</h1>
<p class="desc">
  目标仓库：<a href="https://github.com/ShijunDeng/agentcube">github.com/ShijunDeng/agentcube</a>
  ｜ 分析时间：{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}
</p>

<h2>一、项目概述</h2>
<div class="card">
  <p><b>AgentCube</b> 是 <a href="https://github.com/volcano-sh/volcano">Volcano</a> 社区的子项目，为 Kubernetes 提供 AI Agent 工作负载的原生调度与生命周期管理。解决传统批处理/推理系统无法满足的 Agent 特有需求：间歇性活动、亚秒级响应延迟、跨会话状态持久化。</p>
  <p style="margin-top:8px;">核心能力：<b>极低延迟调度</b>、<b>有状态生命周期管理</b>（智能休眠/恢复）、<b>高密度资源利用</b>（预热池 + 性能隔离）、<b>命令式 API</b>。</p>
</div>

<h2>二、规模概览</h2>

<div class="summary-box">
  <div class="summary-item"><div class="big">{d['total_files']}</div><div class="label">总文件数</div></div>
  <div class="summary-item"><div class="big">{d['total_loc']:,}</div><div class="label">总代码行数</div></div>
  <div class="summary-item"><div class="big">{d['go']['src_files']}</div><div class="label">Go 源文件</div></div>
  <div class="summary-item"><div class="big">{d['go']['src_loc']:,}</div><div class="label">Go 源码行数</div></div>
  <div class="summary-item"><div class="big">{d['python']['src_files']}</div><div class="label">Python 源文件</div></div>
  <div class="summary-item"><div class="big">{d['python']['src_loc']:,}</div><div class="label">Python 源码行数</div></div>
  <div class="summary-item"><div class="big">{d['go']['test_files'] + d['python']['test_files']}</div><div class="label">测试文件</div></div>
  <div class="summary-item"><div class="big">{d['go']['test_loc'] + d['python']['test_loc']:,}</div><div class="label">测试代码行数</div></div>
  <div class="summary-item"><div class="big">{len(d['go']['packages'])}</div><div class="label">Go 包数量</div></div>
  <div class="summary-item"><div class="big">15</div><div class="label">核心特性数</div></div>
  <div class="summary-item"><div class="big">14</div><div class="label">HTTP API 端点</div></div>
  <div class="summary-item"><div class="big">5</div><div class="label">CLI 命令</div></div>
</div>

<h2>三、语言构成</h2>
<div class="card">
  {lang_bars}
</div>

<h2>四、系统架构</h2>
<div class="card">
<pre style="font-size:0.85em;line-height:1.5;overflow-x:auto;background:#f8f9fa;padding:12px;border-radius:6px;">
┌──────────────────────────────────────────────────────────────────┐
│                        客户端 / SDK                              │
│  (Python SDK: CodeInterpreterClient, AgentRuntimeClient)         │
│  (CLI: kubectl-agentcube pack/build/publish/invoke/status)       │
└──────────────┬───────────────────────────────────────────────────┘
               │ HTTP (x-agentcube-session-id)
               ▼
┌──────────────────────────────────┐
│         Router (Go/Gin)          │  ← 反向代理 + JWT 签发
│  /v1/namespaces/:ns/             │     并发控制 (信号量)
│    agent-runtimes/:name/inv/*    │     会话自动创建/复用
│    code-interpreters/:name/inv/* │
└──────────┬───────────┬───────────┘
           │           │ 会话数据
           │           ▼
           │    ┌──────────────┐
           │    │ Redis/Valkey │  ← 会话存储 (ZSET 索引)
           │    └──────────────┘
           │ HTTP (Bearer Token)
           ▼
┌──────────────────────────────────┐
│    Workload Manager (Go/Gin)     │  ← 控制面 API
│  POST /v1/agent-runtime          │     Sandbox 生命周期
│  POST /v1/code-interpreter       │     GC (15s周期/16批次)
│  TokenReview 认证                │     WarmPool 管理
└──────────┬───────────────────────┘
           │ K8s API
           ▼
┌──────────────────────────────────┐
│     Kubernetes API Server        │
│  ┌─────────────┐ ┌────────────┐ │
│  │ AgentRuntime │ │CodeInterp. │ │  ← 自定义 CRD
│  │     CRD      │ │    CRD     │ │
│  └─────────────┘ └────────────┘ │
│  ┌─────────────┐ ┌────────────┐ │
│  │  Sandbox    │ │SandboxClaim│ │  ← agent-sandbox CRD
│  │  (Pod)      │ │ (WarmPool) │ │
│  └──────┬──────┘ └────────────┘ │
└─────────┼────────────────────────┘
          │
          ▼
┌──────────────────────────────────┐
│     PicoD (Sandbox 内守护进程)    │
│  POST /api/execute  (命令执行)    │  ← RSA JWT 认证
│  POST /api/files    (文件上传)    │     workspace 沙箱隔离
│  GET  /api/files    (目录列表)    │     60s 执行超时
│  GET  /api/files/*  (文件下载)    │
└──────────────────────────────────┘

辅助组件:
  AgentD — Sandbox 空闲清理控制器 (15min 超时自动删除)
  Volcano Scheduler — 可选的集群调度器
</pre>
</div>

<h2>五、功能模块详情</h2>
<div class="card" style="overflow-x:auto;">
  <table>
    <thead><tr><th>模块路径</th><th>语言</th><th>说明</th><th class="num">文件</th><th class="num">源码行</th><th>规模</th></tr></thead>
    <tbody>{mod_rows}</tbody>
  </table>
</div>

<h2>六、核心特性列表</h2>
<div class="card" style="overflow-x:auto;">
  <table>
    <thead><tr><th class="num">#</th><th>特性</th><th>说明</th></tr></thead>
    <tbody>{feat_rows}</tbody>
  </table>
</div>

<h2>七、HTTP API 端点</h2>
<div class="card" style="overflow-x:auto;">
  <table>
    <thead><tr><th>组件</th><th>方法</th><th>路径</th><th>说明</th></tr></thead>
    <tbody>{api_rows}</tbody>
  </table>
</div>

<h2>八、CLI 命令</h2>
<div class="card" style="overflow-x:auto;">
  <table>
    <thead><tr><th>命令</th><th>说明</th><th>主要参数</th></tr></thead>
    <tbody>{cli_rows}</tbody>
  </table>
</div>

<h2>九、技术栈</h2>
<div class="card">
  <h3>Go (后端核心)</h3>
  <table>
    <tr><td>语言版本</td><td>Go 1.24.4 (toolchain 1.24.9)</td></tr>
    <tr><td>Web 框架</td><td>Gin + h2c HTTP/2</td></tr>
    <tr><td>Kubernetes</td><td>k8s.io/client-go v0.34.1, controller-runtime v0.22.2, agent-sandbox v0.1.1</td></tr>
    <tr><td>认证</td><td>golang-jwt/jwt v5 (RSA-2048 RS256)</td></tr>
    <tr><td>存储</td><td>go-redis v9, valkey-go v1.0.69</td></tr>
    <tr><td>日志</td><td>klog/v2</td></tr>
    <tr><td>测试</td><td>testify, miniredis, gomonkey</td></tr>
    <tr><td>构建</td><td>CGO_ENABLED=0, 多架构 (linux/amd64, linux/arm64)</td></tr>
  </table>

  <h3 style="margin-top:16px;">Python (CLI + SDK)</h3>
  <table>
    <tr><td>语言版本</td><td>Python ≥ 3.10</td></tr>
    <tr><td>CLI 框架</td><td>Typer + Rich</td></tr>
    <tr><td>数据校验</td><td>Pydantic ≥ 2.0</td></tr>
    <tr><td>HTTP 客户端</td><td>httpx (CLI), requests (SDK)</td></tr>
    <tr><td>容器</td><td>docker SDK ≥ 6.0</td></tr>
    <tr><td>K8s</td><td>kubernetes ≥ 28.0 (可选)</td></tr>
    <tr><td>JWT</td><td>PyJWT ≥ 2.0 + cryptography</td></tr>
  </table>

  <h3 style="margin-top:16px;">基础设施</h3>
  <table>
    <tr><td>容器运行时</td><td>Docker / Containerd</td></tr>
    <tr><td>编排</td><td>Kubernetes ≥ 1.24</td></tr>
    <tr><td>部署</td><td>Helm 3</td></tr>
    <tr><td>镜像仓库</td><td>ghcr.io/volcano-sh/*</td></tr>
    <tr><td>CI/CD</td><td>GitHub Actions (12 工作流)</td></tr>
    <tr><td>文档</td><td>Docusaurus 3 (TypeScript)</td></tr>
    <tr><td>代码生成</td><td>controller-gen v0.17.2, k8s.io/code-generator v0.34.1</td></tr>
  </table>
</div>

<h2>十、目录结构</h2>
<div class="card" style="overflow-x:auto;">
  <table>
    <thead><tr><th>目录</th><th class="num">文件数</th><th class="num">代码行</th><th>规模</th></tr></thead>
    <tbody>{dir_rows}</tbody>
  </table>
</div>

<h2>十一、文件类型分布</h2>
<div class="card" style="overflow-x:auto;">
  <table>
    <thead><tr><th>扩展名</th><th class="num">文件数</th><th class="num">代码行</th></tr></thead>
    <tbody>{ext_rows}</tbody>
  </table>
</div>

<div class="card" style="margin-top:24px;text-align:center;color:var(--muted);font-size:0.85em;">
  分析来源：<a href="https://github.com/ShijunDeng/agentcube">github.com/ShijunDeng/agentcube</a> ｜
  生成时间：{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} ｜
  <a href="https://github.com/ShijunDeng/sdd-benchmark">SDD Benchmark Framework</a>
</div>

</div>
</body>
</html>"""
    return html


def main():
    source_dir = sys.argv[1] if len(sys.argv) > 1 else "/tmp/agentcube-benchmark-source"
    output_file = sys.argv[2] if len(sys.argv) > 2 else "results/reports/project_analysis_report.html"

    print(f"分析目录: {source_dir}")
    data = analyze(source_dir)

    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    html = render_html(data, source_dir)
    with open(output_file, 'w') as f:
        f.write(html)
    print(f"报告已生成: {output_file}")

    # Also save JSON
    json_file = output_file.replace('.html', '.json')
    with open(json_file, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"数据已保存: {json_file}")


if __name__ == "__main__":
    main()
