#!/usr/bin/env python3
"""
SDD-TEE 综合评测报告生成器 v2

基于 CodeSpec 7 阶段工作流 + OpenSpec OPSX 工具链，实现：
- 细粒度 AR 分解（capability / feature 级别）
- ST-0 ~ ST-7 各阶段 Token 消耗追踪
- 5 维指标体系：阶段、角色、效率、质量、阶段分布
- 仪表盘视图：概览、阶段分布、效率分析、质量关联

Usage:
  python3 scripts/07_sdd_tee_report.py --mock    # 生成 mock 数据 + HTML 报告
  python3 scripts/07_sdd_tee_report.py --data X   # 从真实数据生成报告
"""

import argparse
import json
import math
import os
import random
from datetime import datetime, timezone, timedelta
from pathlib import Path

random.seed(42)

# ============================================================================
# AR Decomposition for agentcube — capability/feature level
# ============================================================================

AR_CATALOG = [
    # --- Go Core: CRD Types ---
    {"id": "AR-001", "name": "CRD AgentRuntime 类型定义", "module": "pkg/apis", "lang": "Go",
     "type": "新功能", "size": "S", "est_loc": 180, "est_files": 2, "est_tasks": 3},
    {"id": "AR-002", "name": "CRD CodeInterpreter 类型定义", "module": "pkg/apis", "lang": "Go",
     "type": "新功能", "size": "S", "est_loc": 220, "est_files": 2, "est_tasks": 4},
    {"id": "AR-003", "name": "CRD 共享类型与常量", "module": "pkg/apis", "lang": "Go",
     "type": "新功能", "size": "S", "est_loc": 120, "est_files": 2, "est_tasks": 2},

    # --- Go Core: Workload Manager ---
    {"id": "AR-004", "name": "WorkloadManager HTTP 服务框架", "module": "pkg/workloadmanager", "lang": "Go",
     "type": "新功能", "size": "M", "est_loc": 350, "est_files": 3, "est_tasks": 5},
    {"id": "AR-005", "name": "Sandbox 创建处理器", "module": "pkg/workloadmanager", "lang": "Go",
     "type": "新功能", "size": "M", "est_loc": 450, "est_files": 3, "est_tasks": 6},
    {"id": "AR-006", "name": "Sandbox 删除与生命周期管理", "module": "pkg/workloadmanager", "lang": "Go",
     "type": "新功能", "size": "M", "est_loc": 280, "est_files": 2, "est_tasks": 4},
    {"id": "AR-007", "name": "K8s Reconciler 控制器", "module": "pkg/workloadmanager", "lang": "Go",
     "type": "新功能", "size": "L", "est_loc": 600, "est_files": 4, "est_tasks": 8},
    {"id": "AR-008", "name": "Sandbox GC 定时清理机制", "module": "pkg/workloadmanager", "lang": "Go",
     "type": "新功能", "size": "S", "est_loc": 200, "est_files": 2, "est_tasks": 3},

    # --- Go Core: Router ---
    {"id": "AR-009", "name": "Router HTTP 反向代理核心", "module": "pkg/router", "lang": "Go",
     "type": "新功能", "size": "M", "est_loc": 380, "est_files": 3, "est_tasks": 5},
    {"id": "AR-010", "name": "Router 会话管理", "module": "pkg/router", "lang": "Go",
     "type": "新功能", "size": "M", "est_loc": 300, "est_files": 2, "est_tasks": 4},
    {"id": "AR-011", "name": "Router JWT 认证与签发", "module": "pkg/router", "lang": "Go",
     "type": "新功能", "size": "M", "est_loc": 250, "est_files": 2, "est_tasks": 4},

    # --- Go Core: Store ---
    {"id": "AR-012", "name": "会话存储接口定义", "module": "pkg/store", "lang": "Go",
     "type": "新功能", "size": "S", "est_loc": 150, "est_files": 2, "est_tasks": 3},
    {"id": "AR-013", "name": "Redis 存储实现", "module": "pkg/store", "lang": "Go",
     "type": "新功能", "size": "M", "est_loc": 350, "est_files": 2, "est_tasks": 5},
    {"id": "AR-014", "name": "Valkey 存储实现", "module": "pkg/store", "lang": "Go",
     "type": "新功能", "size": "S", "est_loc": 200, "est_files": 2, "est_tasks": 3},

    # --- Go Core: PicoD ---
    {"id": "AR-015", "name": "PicoD 命令执行 API", "module": "pkg/picod", "lang": "Go",
     "type": "新功能", "size": "M", "est_loc": 320, "est_files": 3, "est_tasks": 4},
    {"id": "AR-016", "name": "PicoD 文件管理 API", "module": "pkg/picod", "lang": "Go",
     "type": "新功能", "size": "M", "est_loc": 350, "est_files": 3, "est_tasks": 5},
    {"id": "AR-017", "name": "PicoD JWT 中间件", "module": "pkg/picod", "lang": "Go",
     "type": "新功能", "size": "S", "est_loc": 150, "est_files": 1, "est_tasks": 2},

    # --- Go Core: Agentd + Binaries ---
    {"id": "AR-018", "name": "Agentd 空闲清理控制器", "module": "pkg/agentd", "lang": "Go",
     "type": "新功能", "size": "S", "est_loc": 180, "est_files": 2, "est_tasks": 3},
    {"id": "AR-019", "name": "CLI 二进制入口 (4 binaries)", "module": "cmd", "lang": "Go",
     "type": "新功能", "size": "M", "est_loc": 400, "est_files": 4, "est_tasks": 4},

    # --- Python: CLI Commands ---
    {"id": "AR-020", "name": "CLI pack 命令", "module": "cmd/cli", "lang": "Python",
     "type": "新功能", "size": "M", "est_loc": 450, "est_files": 3, "est_tasks": 5},
    {"id": "AR-021", "name": "CLI build 命令", "module": "cmd/cli", "lang": "Python",
     "type": "新功能", "size": "M", "est_loc": 380, "est_files": 3, "est_tasks": 5},
    {"id": "AR-022", "name": "CLI publish 命令", "module": "cmd/cli", "lang": "Python",
     "type": "新功能", "size": "L", "est_loc": 550, "est_files": 4, "est_tasks": 7},
    {"id": "AR-023", "name": "CLI invoke/status 命令", "module": "cmd/cli", "lang": "Python",
     "type": "新功能", "size": "M", "est_loc": 300, "est_files": 3, "est_tasks": 4},

    # --- Python: CLI Services ---
    {"id": "AR-024", "name": "DockerService 封装", "module": "cmd/cli", "lang": "Python",
     "type": "新功能", "size": "M", "est_loc": 280, "est_files": 2, "est_tasks": 4},
    {"id": "AR-025", "name": "MetadataService 与数据模型", "module": "cmd/cli", "lang": "Python",
     "type": "新功能", "size": "M", "est_loc": 350, "est_files": 3, "est_tasks": 5},
    {"id": "AR-026", "name": "K8s/AgentCube Provider", "module": "cmd/cli", "lang": "Python",
     "type": "新功能", "size": "M", "est_loc": 400, "est_files": 3, "est_tasks": 5},

    # --- Python: SDK ---
    {"id": "AR-027", "name": "SDK CodeInterpreterClient", "module": "sdk-python", "lang": "Python",
     "type": "新功能", "size": "M", "est_loc": 350, "est_files": 3, "est_tasks": 5},
    {"id": "AR-028", "name": "SDK AgentRuntimeClient", "module": "sdk-python", "lang": "Python",
     "type": "新功能", "size": "M", "est_loc": 250, "est_files": 2, "est_tasks": 4},
    {"id": "AR-029", "name": "SDK HTTP 底层客户端", "module": "sdk-python", "lang": "Python",
     "type": "新功能", "size": "M", "est_loc": 300, "est_files": 3, "est_tasks": 4},

    # --- Infrastructure ---
    {"id": "AR-030", "name": "Helm Chart 模板与 Values", "module": "manifests", "lang": "YAML",
     "type": "新功能", "size": "L", "est_loc": 800, "est_files": 6, "est_tasks": 8},
    {"id": "AR-031", "name": "RBAC 配置 (SA/Role/Binding)", "module": "manifests", "lang": "YAML",
     "type": "新功能", "size": "M", "est_loc": 300, "est_files": 3, "est_tasks": 4},
    {"id": "AR-032", "name": "Dockerfile 多阶段构建 (3 images)", "module": "docker", "lang": "Dockerfile",
     "type": "新功能", "size": "S", "est_loc": 150, "est_files": 3, "est_tasks": 3},
    {"id": "AR-033", "name": "Makefile 构建目标体系", "module": "root", "lang": "Makefile",
     "type": "新功能", "size": "M", "est_loc": 250, "est_files": 1, "est_tasks": 5},
    {"id": "AR-034", "name": "CI/CD GitHub Actions (12 workflows)", "module": ".github", "lang": "YAML",
     "type": "新功能", "size": "L", "est_loc": 620, "est_files": 12, "est_tasks": 12},

    # --- Generated Code ---
    {"id": "AR-035", "name": "client-go 类型客户端生成", "module": "client-go", "lang": "Go",
     "type": "新功能", "size": "L", "est_loc": 1200, "est_files": 20, "est_tasks": 6},

    # --- Integration & Examples ---
    {"id": "AR-036", "name": "Dify 插件集成", "module": "integrations", "lang": "Python",
     "type": "新功能", "size": "M", "est_loc": 400, "est_files": 8, "est_tasks": 5},
    {"id": "AR-037", "name": "PCAP 分析器示例应用", "module": "example", "lang": "Python",
     "type": "新功能", "size": "M", "est_loc": 500, "est_files": 5, "est_tasks": 5},

    # --- Tests ---
    {"id": "AR-038", "name": "Go 单元测试 (workloadmanager)", "module": "pkg/workloadmanager", "lang": "Go",
     "type": "测试", "size": "L", "est_loc": 2000, "est_files": 6, "est_tasks": 8},
    {"id": "AR-039", "name": "Go 单元测试 (router/store/picod)", "module": "pkg", "lang": "Go",
     "type": "测试", "size": "L", "est_loc": 1800, "est_files": 8, "est_tasks": 10},
    {"id": "AR-040", "name": "Python SDK/CLI 测试", "module": "sdk-python/tests", "lang": "Python",
     "type": "测试", "size": "M", "est_loc": 500, "est_files": 4, "est_tasks": 5},
    {"id": "AR-041", "name": "E2E 集成测试", "module": "test/e2e", "lang": "Go",
     "type": "测试", "size": "L", "est_loc": 800, "est_files": 4, "est_tasks": 6},

    # --- Documentation ---
    {"id": "AR-042", "name": "Docusaurus 文档站框架", "module": "docs", "lang": "TypeScript",
     "type": "新功能", "size": "M", "est_loc": 400, "est_files": 8, "est_tasks": 4},
    {"id": "AR-043", "name": "架构设计文档与 API 文档", "module": "docs", "lang": "Markdown",
     "type": "新功能", "size": "M", "est_loc": 600, "est_files": 10, "est_tasks": 5},
]

STAGE_NAMES = {
    "ST-0": "AR 输入",
    "ST-1": "需求澄清 (Proposal)",
    "ST-2": "Spec 增量设计",
    "ST-3": "Design 增量设计",
    "ST-4": "任务拆解 (Tasks)",
    "ST-5": "开发实现 (Apply)",
    "ST-6": "一致性验证 (Verify)",
    "ST-7": "合并归档 (Archive)",
}

OPSX_COMMANDS = {
    "ST-0": "/opsx:new",
    "ST-1": "/opsx:ff → proposal.md",
    "ST-2": "/opsx:ff → specs/",
    "ST-3": "/opsx:ff → design.md",
    "ST-4": "/opsx:ff → tasks.md",
    "ST-5": "/opsx:apply",
    "ST-6": "/opsx:verify",
    "ST-7": "/opsx:archive",
}

SIZE_MULTIPLIERS = {"S": 0.6, "M": 1.0, "L": 1.8}
TYPE_MULTIPLIERS = {"新功能": 1.0, "测试": 0.85, "Bug修复": 0.5, "重构": 0.7}


# ============================================================================
# Mock data generation — calibrated to industry benchmarks
# ============================================================================

def _jitter(base, spread=0.25):
    return int(base * random.uniform(1 - spread, 1 + spread))


def generate_stage_tokens(ar, stage_id):
    """Generate realistic token consumption for a single AR × stage.
    
    Calibration sources:
    - Claude Code avg ~78K tokens/request, 84% cache, 166:1 I/O ratio
    - SDD stage proportions from CodeSpec 7-stage workflow pilot data
    - Industry benchmarks: $0.06-0.24 per request with/without caching
    """
    size_m = SIZE_MULTIPLIERS[ar["size"]]
    type_m = TYPE_MULTIPLIERS.get(ar["type"], 1.0)
    base = size_m * type_m

    profiles = {
        "ST-0": {"input": 3000, "output": 1500, "iters": (1, 1), "dur_s": (5, 15),
                 "human_input": 800, "cache_ratio": 0.3},
        "ST-1": {"input": 18000, "output": 6000, "iters": (1, 3), "dur_s": (30, 90),
                 "human_input": 1200, "cache_ratio": 0.6},
        "ST-2": {"input": 22000, "output": 4500, "iters": (1, 3), "dur_s": (40, 120),
                 "human_input": 500, "cache_ratio": 0.7},
        "ST-3": {"input": 28000, "output": 10000, "iters": (2, 4), "dur_s": (60, 180),
                 "human_input": 800, "cache_ratio": 0.75},
        "ST-4": {"input": 32000, "output": 5000, "iters": (1, 2), "dur_s": (20, 60),
                 "human_input": 300, "cache_ratio": 0.8},
        "ST-5": {"input": 120000, "output": 35000, "iters": (3, 8), "dur_s": (120, 600),
                 "human_input": 2000, "cache_ratio": 0.84},
        "ST-6": {"input": 40000, "output": 6000, "iters": (1, 3), "dur_s": (30, 120),
                 "human_input": 400, "cache_ratio": 0.8},
        "ST-7": {"input": 8000, "output": 2500, "iters": (1, 1), "dur_s": (10, 30),
                 "human_input": 200, "cache_ratio": 0.85},
    }

    p = profiles[stage_id]
    input_tok = _jitter(int(p["input"] * base))
    output_tok = _jitter(int(p["output"] * base))
    cache_read = int(input_tok * random.uniform(p["cache_ratio"] * 0.8, min(p["cache_ratio"] * 1.2, 0.95)))
    cache_write = int(input_tok * random.uniform(0.05, 0.12))
    human_tok = _jitter(int(p["human_input"] * base))
    iters = random.randint(*p["iters"])
    dur = random.randint(*[int(x * base) for x in p["dur_s"]])

    # Spec document tokens as "预制规范" (pre-built spec context)
    spec_ctx_tokens = 0
    if stage_id in ("ST-3", "ST-4", "ST-5", "ST-6"):
        spec_ctx_tokens = _jitter(int(4000 * base))

    return {
        "stage": stage_id,
        "stage_name": STAGE_NAMES[stage_id],
        "opsx_command": OPSX_COMMANDS[stage_id],
        "input_tokens": input_tok,
        "output_tokens": output_tok,
        "cache_read_tokens": cache_read,
        "cache_write_tokens": cache_write,
        "total_tokens": input_tok + output_tok,
        "human_input_tokens": human_tok,
        "spec_context_tokens": spec_ctx_tokens,
        "iterations": iters,
        "duration_seconds": dur,
        "api_calls": iters + random.randint(0, 2),
    }


def generate_ar_data(ar):
    """Generate full 7-stage token data for a single AR."""
    stages = {}
    for sid in STAGE_NAMES:
        stages[sid] = generate_stage_tokens(ar, sid)

    total_input = sum(s["input_tokens"] for s in stages.values())
    total_output = sum(s["output_tokens"] for s in stages.values())
    total_cache_read = sum(s["cache_read_tokens"] for s in stages.values())
    total_cache_write = sum(s["cache_write_tokens"] for s in stages.values())
    total_human = sum(s["human_input_tokens"] for s in stages.values())
    total_spec_ctx = sum(s["spec_context_tokens"] for s in stages.values())
    total_iters = sum(s["iterations"] for s in stages.values())
    total_dur = sum(s["duration_seconds"] for s in stages.values())
    total_calls = sum(s["api_calls"] for s in stages.values())

    actual_loc = _jitter(ar["est_loc"], 0.15)
    actual_files = max(1, _jitter(ar["est_files"], 0.1))
    tasks_count = ar["est_tasks"]

    consistency_score = random.uniform(0.78, 0.98)
    code_usability = random.uniform(0.70, 0.95)
    test_coverage = random.uniform(0.55, 0.92) if ar["type"] == "测试" else random.uniform(0.30, 0.75)
    bugs_found = random.randint(0, max(1, actual_loc // 300))

    pricing_input = 3.0
    pricing_output = 15.0
    pricing_cache_read = 0.30
    pricing_cache_write = 3.75

    input_cost = (total_input - total_cache_read) * pricing_input / 1e6 + total_cache_read * pricing_cache_read / 1e6
    output_cost = total_output * pricing_output / 1e6
    cache_write_cost = total_cache_write * pricing_cache_write / 1e6
    total_cost = input_cost + output_cost + cache_write_cost

    return {
        "ar": ar,
        "stages": stages,
        "totals": {
            "input_tokens": total_input,
            "output_tokens": total_output,
            "cache_read_tokens": total_cache_read,
            "cache_write_tokens": total_cache_write,
            "total_tokens": total_input + total_output,
            "human_input_tokens": total_human,
            "spec_context_tokens": total_spec_ctx,
            "iterations": total_iters,
            "duration_seconds": total_dur,
            "api_calls": total_calls,
            "cost_usd": round(total_cost, 4),
        },
        "output": {
            "actual_loc": actual_loc,
            "actual_files": actual_files,
            "tasks_count": tasks_count,
        },
        "quality": {
            "consistency_score": round(consistency_score, 4),
            "code_usability": round(code_usability, 4),
            "test_coverage": round(test_coverage, 4),
            "bugs_found": bugs_found,
        },
        "metrics": {
            "ET_LOC": round(stages["ST-5"]["total_tokens"] / max(actual_loc, 1), 1),
            "ET_FILE": round(stages["ST-5"]["total_tokens"] / max(actual_files, 1), 0),
            "ET_TASK": round(stages["ST-5"]["total_tokens"] / max(tasks_count, 1), 0),
            "ET_AR": total_input + total_output,
            "ET_TIME": round((total_input + total_output) / max(total_dur / 3600, 0.01), 0),
            "ET_COST_LOC": round(total_cost / max(actual_loc / 1000, 0.01), 4),
            "RT_RATIO": round(total_human / max(total_input + total_output - total_human, 1), 4),
            "RT_ITER": total_iters,
            "QT_COV": round(stages["ST-5"]["total_tokens"] / max(test_coverage * 100, 1), 1),
            "QT_CONSIST": round(stages["ST-6"]["total_tokens"] / max(consistency_score * 100, 1), 1),
            "QT_AVAIL": round(stages["ST-5"]["total_tokens"] / max(code_usability * 100, 1), 1),
            "QT_BUG": round(stages["ST-5"]["total_tokens"] / max(bugs_found, 1), 0),
            "PT_DESIGN": round(sum(stages[s]["total_tokens"] for s in ("ST-1", "ST-2", "ST-3")) / max(total_input + total_output, 1), 4),
            "PT_PLAN": round(sum(stages[s]["total_tokens"] for s in ("ST-0", "ST-4")) / max(total_input + total_output, 1), 4),
            "PT_DEV": round(stages["ST-5"]["total_tokens"] / max(total_input + total_output, 1), 4),
            "PT_VERIFY": round(sum(stages[s]["total_tokens"] for s in ("ST-6", "ST-7")) / max(total_input + total_output, 1), 4),
        },
    }


def generate_mock_data():
    """Generate complete mock evaluation dataset."""
    ts = datetime.now(timezone.utc)
    ar_results = [generate_ar_data(ar) for ar in AR_CATALOG]

    # Aggregates
    grand_input = sum(r["totals"]["input_tokens"] for r in ar_results)
    grand_output = sum(r["totals"]["output_tokens"] for r in ar_results)
    grand_cache_read = sum(r["totals"]["cache_read_tokens"] for r in ar_results)
    grand_cache_write = sum(r["totals"]["cache_write_tokens"] for r in ar_results)
    grand_human = sum(r["totals"]["human_input_tokens"] for r in ar_results)
    grand_spec = sum(r["totals"]["spec_context_tokens"] for r in ar_results)
    grand_dur = sum(r["totals"]["duration_seconds"] for r in ar_results)
    grand_cost = sum(r["totals"]["cost_usd"] for r in ar_results)
    grand_loc = sum(r["output"]["actual_loc"] for r in ar_results)
    grand_files = sum(r["output"]["actual_files"] for r in ar_results)
    grand_tasks = sum(r["output"]["tasks_count"] for r in ar_results)
    grand_iters = sum(r["totals"]["iterations"] for r in ar_results)
    grand_calls = sum(r["totals"]["api_calls"] for r in ar_results)

    # Per-stage aggregates
    stage_agg = {}
    for sid in STAGE_NAMES:
        stage_agg[sid] = {
            "name": STAGE_NAMES[sid],
            "total_tokens": sum(r["stages"][sid]["total_tokens"] for r in ar_results),
            "input_tokens": sum(r["stages"][sid]["input_tokens"] for r in ar_results),
            "output_tokens": sum(r["stages"][sid]["output_tokens"] for r in ar_results),
            "duration_seconds": sum(r["stages"][sid]["duration_seconds"] for r in ar_results),
            "iterations": sum(r["stages"][sid]["iterations"] for r in ar_results),
        }

    # Per-size baselines
    baselines = {}
    for sz in ("S", "M", "L"):
        subset = [r for r in ar_results if r["ar"]["size"] == sz]
        if subset:
            baselines[sz] = {
                "count": len(subset),
                "avg_tokens": int(sum(r["totals"]["total_tokens"] for r in subset) / len(subset)),
                "avg_loc": int(sum(r["output"]["actual_loc"] for r in subset) / len(subset)),
                "avg_cost": round(sum(r["totals"]["cost_usd"] for r in subset) / len(subset), 4),
                "avg_et_loc": round(sum(r["metrics"]["ET_LOC"] for r in subset) / len(subset), 1),
                "avg_duration": int(sum(r["totals"]["duration_seconds"] for r in subset) / len(subset)),
            }

    data = {
        "meta": {
            "generated_at": ts.isoformat(),
            "is_mock": True,
            "framework": "SDD-TEE v2",
            "methodology": "CodeSpec 7-Stage + OpenSpec OPSX",
            "target_project": "agentcube",
            "tool": "cursor-cli",
            "model": "claude-sonnet-4",
            "model_pricing": {"input": 3.0, "output": 15.0, "cache_read": 0.30, "cache_write": 3.75},
        },
        "ar_catalog": AR_CATALOG,
        "ar_results": [{
            "ar_id": r["ar"]["id"],
            "ar_name": r["ar"]["name"],
            "module": r["ar"]["module"],
            "lang": r["ar"]["lang"],
            "type": r["ar"]["type"],
            "size": r["ar"]["size"],
            "stages": r["stages"],
            "totals": r["totals"],
            "output": r["output"],
            "quality": r["quality"],
            "metrics": r["metrics"],
        } for r in ar_results],
        "grand_totals": {
            "ar_count": len(ar_results),
            "input_tokens": grand_input,
            "output_tokens": grand_output,
            "cache_read_tokens": grand_cache_read,
            "cache_write_tokens": grand_cache_write,
            "total_tokens": grand_input + grand_output,
            "human_input_tokens": grand_human,
            "spec_context_tokens": grand_spec,
            "total_duration_seconds": grand_dur,
            "total_cost_usd": round(grand_cost, 2),
            "total_cost_cny": round(grand_cost * 7.25, 2),
            "total_loc": grand_loc,
            "total_files": grand_files,
            "total_tasks": grand_tasks,
            "total_iterations": grand_iters,
            "total_api_calls": grand_calls,
        },
        "stage_aggregates": stage_agg,
        "baselines": baselines,
    }
    return data


# ============================================================================
# HTML Report Renderer
# ============================================================================

def _fmt(n):
    if isinstance(n, float):
        return f"{n:,.2f}"
    return f"{n:,}"


def _pct(part, total):
    return f"{part / total * 100:.1f}%" if total else "0%"


def _bar_svg(items, width=600, height=28):
    """Render a horizontal stacked bar as inline SVG."""
    total = sum(v for _, v, _ in items)
    if total == 0:
        return ""
    svg = f'<svg width="{width}" height="{height}" style="display:block">'
    x = 0
    for label, val, color in items:
        w = val / total * width
        if w > 0:
            svg += f'<rect x="{x:.1f}" y="0" width="{w:.1f}" height="{height}" fill="{color}" rx="3"/>'
            if w > 40:
                svg += f'<text x="{x + w/2:.1f}" y="{height/2 + 4}" text-anchor="middle" fill="#fff" font-size="11">{label}</text>'
            x += w
    svg += '</svg>'
    return svg


def render_html(data):
    gt = data["grand_totals"]
    sa = data["stage_aggregates"]
    bl = data["baselines"]
    ars = data["ar_results"]
    meta = data["meta"]

    # --- Stage distribution pie data ---
    stage_colors = {
        "ST-0": "#78909C", "ST-1": "#42A5F5", "ST-2": "#26C6DA",
        "ST-3": "#66BB6A", "ST-4": "#FFA726", "ST-5": "#EF5350",
        "ST-6": "#AB47BC", "ST-7": "#8D6E63",
    }

    total_tok = gt["total_tokens"]
    stage_bar_items = [(STAGE_NAMES[s].split("(")[0].strip(), sa[s]["total_tokens"], stage_colors[s])
                       for s in STAGE_NAMES]
    stage_bar_svg = _bar_svg(stage_bar_items, width=800, height=32)

    # --- Stage table ---
    stage_rows = ""
    for sid in STAGE_NAMES:
        s = sa[sid]
        pct = s["total_tokens"] / total_tok * 100 if total_tok else 0
        stage_rows += f"""<tr>
            <td><span style="display:inline-block;width:12px;height:12px;background:{stage_colors[sid]};border-radius:2px;margin-right:6px;vertical-align:middle"></span>{sid}</td>
            <td>{STAGE_NAMES[sid]}</td>
            <td>{OPSX_COMMANDS[sid]}</td>
            <td style="text-align:right">{_fmt(s['input_tokens'])}</td>
            <td style="text-align:right">{_fmt(s['output_tokens'])}</td>
            <td style="text-align:right;font-weight:600">{_fmt(s['total_tokens'])}</td>
            <td style="text-align:right">{pct:.1f}%</td>
            <td style="text-align:right">{s['iterations']}</td>
            <td style="text-align:right">{s['duration_seconds'] // 60}m{s['duration_seconds'] % 60}s</td>
        </tr>"""

    # --- AR table ---
    ar_rows = ""
    for r in sorted(ars, key=lambda x: -x["totals"]["total_tokens"]):
        warn = ""
        if r["metrics"]["ET_LOC"] > (bl.get(r["size"], {}).get("avg_et_loc", 999) * 2):
            warn = ' style="background:#fff3e0"'
        ar_rows += f"""<tr{warn}>
            <td><code>{r['ar_id']}</code></td>
            <td>{r['ar_name']}</td>
            <td>{r['module']}</td>
            <td>{r['lang']}</td>
            <td>{r['size']}</td>
            <td style="text-align:right">{_fmt(r['totals']['total_tokens'])}</td>
            <td style="text-align:right">{_fmt(r['output']['actual_loc'])}</td>
            <td style="text-align:right">{r['metrics']['ET_LOC']}</td>
            <td style="text-align:right">${r['totals']['cost_usd']:.3f}</td>
            <td style="text-align:right">{r['quality']['consistency_score']:.0%}</td>
            <td style="text-align:right">{r['quality']['code_usability']:.0%}</td>
        </tr>"""

    # --- Baseline table ---
    bl_rows = ""
    size_labels = {"S": "小型 (<500 LOC)", "M": "中型 (500-2000)", "L": "大型 (>2000)"}
    for sz in ("S", "M", "L"):
        if sz in bl:
            b = bl[sz]
            bl_rows += f"""<tr>
                <td>{size_labels[sz]}</td><td>{b['count']}</td>
                <td style="text-align:right">{_fmt(b['avg_tokens'])}</td>
                <td style="text-align:right">{b['avg_loc']}</td>
                <td style="text-align:right">{b['avg_et_loc']}</td>
                <td style="text-align:right">${b['avg_cost']:.3f}</td>
                <td style="text-align:right">{b['avg_duration'] // 60}m{b['avg_duration'] % 60}s</td>
            </tr>"""

    # --- Role dimension ---
    rt_ai = gt["total_tokens"] - gt["human_input_tokens"]
    rt_human = gt["human_input_tokens"]
    rt_ratio = rt_human / rt_ai if rt_ai else 0
    rt_iter = gt["total_iterations"] / gt["ar_count"] if gt["ar_count"] else 0

    # --- Distribution metrics ---
    design_tok = sum(sa[s]["total_tokens"] for s in ("ST-1", "ST-2", "ST-3"))
    plan_tok = sum(sa[s]["total_tokens"] for s in ("ST-0", "ST-4"))
    dev_tok = sa["ST-5"]["total_tokens"]
    verify_tok = sum(sa[s]["total_tokens"] for s in ("ST-6", "ST-7"))
    peak_stage = max(STAGE_NAMES, key=lambda s: sa[s]["total_tokens"])
    cache_rate = gt["cache_read_tokens"] / max(gt["input_tokens"], 1)

    # --- Efficiency scatter data (Token vs LOC for each AR) ---
    scatter_points = ""
    for r in ars:
        x = r["output"]["actual_loc"]
        y = r["totals"]["total_tokens"]
        max_x = max([r["output"]["actual_loc"] for r in ars] + [1])
        max_y = max([r["totals"]["total_tokens"] for r in ars] + [1])
        cx = min(x / max_x * 540, 540) + 80
        cy = 350 - min(y / max_y * 300, 300)
        color = {"Go": "#00ADD8", "Python": "#3776AB", "YAML": "#CB171E", "Dockerfile": "#384d54",
                 "Makefile": "#427819", "TypeScript": "#3178C6", "Markdown": "#083FA1"}.get(r["lang"], "#999")
        scatter_points += f'<circle cx="{cx:.0f}" cy="{cy:.0f}" r="5" fill="{color}" opacity="0.7"><title>{r["ar_id"]} {r["ar_name"]}\nLOC: {x}, Tokens: {_fmt(y)}</title></circle>\n'

    scatter_svg = f"""<svg width="680" height="380" style="display:block;margin:0 auto">
        <rect x="60" y="10" width="580" height="340" fill="#fafafa" stroke="#ddd"/>
        <text x="340" y="375" text-anchor="middle" font-size="12" fill="#666">实际代码行数 (LOC)</text>
        <text x="15" y="180" text-anchor="middle" font-size="12" fill="#666" transform="rotate(-90,15,180)">Total Tokens</text>
        {scatter_points}
    </svg>"""

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SDD-TEE 综合评测报告</title>
<style>
  :root {{ --bg: #f5f6f8; --card: #fff; --border: #e2e5e9; --primary: #1a73e8;
           --green: #34a853; --red: #ea4335; --orange: #f9ab00; --text: #1f2937; --muted: #6b7280; }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Noto Sans SC', sans-serif;
         background: var(--bg); color: var(--text); line-height: 1.6; font-size: 14px; }}
  .container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
  h1 {{ font-size: 26px; color: var(--primary); margin-bottom: 4px; }}
  h2 {{ font-size: 20px; margin: 28px 0 14px; padding-bottom: 6px; border-bottom: 2px solid var(--primary); }}
  h3 {{ font-size: 16px; margin: 20px 0 10px; color: #374151; }}
  .sub {{ color: var(--muted); font-size: 13px; margin-bottom: 20px; }}
  .card {{ background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 18px; margin-bottom: 16px; }}
  .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; }}
  .stat {{ background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 14px; text-align: center; }}
  .stat .v {{ font-size: 26px; font-weight: 700; color: var(--primary); }}
  .stat .l {{ font-size: 12px; color: var(--muted); margin-top: 2px; }}
  .stat.warn .v {{ color: var(--orange); }}
  .stat.danger .v {{ color: var(--red); }}
  .stat.good .v {{ color: var(--green); }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; margin: 8px 0; }}
  th, td {{ padding: 7px 10px; border: 1px solid var(--border); text-align: left; }}
  th {{ background: #f1f3f5; font-weight: 600; font-size: 12px; white-space: nowrap; }}
  tr:hover td {{ background: #f8f9fa; }}
  .badge {{ display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 600; }}
  .badge-s {{ background: #e8f5e9; color: #2e7d32; }}
  .badge-m {{ background: #e3f2fd; color: #1565c0; }}
  .badge-l {{ background: #fce4ec; color: #c62828; }}
  .toc {{ background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 14px 20px; margin-bottom: 20px; columns: 2; }}
  .toc a {{ color: var(--primary); text-decoration: none; display: block; padding: 2px 0; font-size: 13px; }}
  .toc a:hover {{ text-decoration: underline; }}
  

  .metric-guide {{ margin-top: 12px; padding: 12px; background: #f8f9fa; border-radius: 8px; border: 1px solid #e2e5e9; }}
  .metric-guide h4 {{ font-size: 13px; color: #1a73e8; margin-bottom: 8px; border: none; }}
  .guide-grid {{ display: grid; grid-template-columns: 120px 1fr; gap: 8px; font-size: 12px; }}
  .guide-item-name {{ font-weight: bold; color: #374151; }}
  .guide-item-desc {{ color: #6b7280; }}
  .best-tag {{ color: #34a853; font-weight: bold; }}


  .note {{ background: #fffde7; border-left: 4px solid var(--orange); padding: 10px 14px; margin: 10px 0; border-radius: 0 8px 8px 0; font-size: 13px; }}
  .legend {{ display: flex; gap: 16px; flex-wrap: wrap; font-size: 12px; margin: 8px 0; }}
  .legend span {{ display: flex; align-items: center; gap: 4px; }}
  .legend i {{ display: inline-block; width: 12px; height: 12px; border-radius: 2px; }}
  code {{ background: #f1f3f5; padding: 1px 5px; border-radius: 3px; font-size: 12px; }}
  .footer {{ text-align: center; padding: 20px; color: var(--muted); font-size: 11px; border-top: 1px solid var(--border); margin-top: 24px; }}
  .two-col {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
  @media (max-width: 768px) {{ .two-col {{ grid-template-columns: 1fr; }} .toc {{ columns: 1; }} }}
</style>
</head>
<body>
<div class="container">

<h1>SDD-TEE 综合评测报告</h1>
<p class="sub">
  SDD Token Efficiency Evaluation &mdash; CodeSpec 7-Stage &times; OpenSpec OPSX &nbsp;|&nbsp;
  模型: {meta['model']} &nbsp;|&nbsp; 工具: {meta['tool']} &nbsp;|&nbsp;
  {'<span style="color:var(--orange)">MOCK DATA</span>' if meta.get('is_mock') else '<span style="color:var(--green)">ACTUAL RUN</span>'} &nbsp;|&nbsp;
  {meta.get('run_id', '')} &nbsp;|&nbsp; {meta['generated_at'][:19]}Z
</p>

<div class="toc">
  <a href="#overview">1. 评测概览</a>
  <a href="#stage">2. 阶段维度 (ST-0~ST-7)</a>
  <a href="#role">3. 角色维度 (人 vs AI)</a>
  <a href="#efficiency">4. 效率维度</a>
  <a href="#quality">5. 质量维度</a>
  <a href="#distribution">6. 阶段分布</a>
  <a href="#baselines">7. 基线数据</a>
  <a href="#ar-detail">8. AR 明细</a>
  <a href="#warnings">9. 预警分析</a>
  <a href="#reference">10. 引用与说明</a>
</div>

{"" if meta.get('is_mock') else f'''
<div class="card" style="border-left:4px solid var(--primary)">
  <h3>运行信息</h3>
  <table>
    <tr><th style="width:120px">Run ID</th><td><code>{meta.get("run_id","")}</code></td></tr>
    <tr><th>工具</th><td>{meta["tool"]}</td></tr>
    <tr><th>模型</th><td>{meta["model"]}</td></tr>
    <tr><th>开始时间</th><td>{meta.get("started_at","")}</td></tr>
    <tr><th>结束时间</th><td>{meta.get("completed_at","")}</td></tr>
    <tr><th>Token 追踪</th><td>{meta.get("token_tracking","")}</td></tr>
    <tr><th>预制规范</th><td>{meta.get("spec_tokens_total",0):,} tokens (22 OpenSpec 文件)</td></tr>
  </table>
</div>
'''}

<!-- ===================== 1. OVERVIEW ===================== -->
<h2 id="overview">1. 评测概览</h2>
<div class="stats">
  <div class="stat"><div class="v">{gt['ar_count']}</div><div class="l">AR 需求数</div></div>
  <div class="stat"><div class="v">{_fmt(gt['total_tokens'])}</div><div class="l">Total Tokens</div></div>
  <div class="stat"><div class="v">${gt['total_cost_usd']:.2f}</div><div class="l">总成本 (USD)</div></div>
  <div class="stat"><div class="v">¥{gt['total_cost_cny']:.0f}</div><div class="l">总成本 (CNY)</div></div>
  <div class="stat"><div class="v">{gt['total_loc']:,}</div><div class="l">生成代码行数</div></div>
  <div class="stat"><div class="v">{gt['total_files']}</div><div class="l">生成文件数</div></div>
  <div class="stat"><div class="v">{gt['total_tasks']}</div><div class="l">Task 总数</div></div>
  <div class="stat"><div class="v">{gt['total_iterations']}</div><div class="l">交互总轮数</div></div>
  <div class="stat"><div class="v">{gt['total_api_calls']}</div><div class="l">API 调用次数</div></div>
  <div class="stat"><div class="v">{gt['total_duration_seconds'] // 3600}h{(gt['total_duration_seconds'] % 3600) // 60}m</div><div class="l">总耗时</div></div>
</div>

<div class="card" style="margin-top:12px">
  <h3>Token 类型分布</h3>
  {_bar_svg([
      ("Input", gt["input_tokens"] - gt["cache_read_tokens"], "#42A5F5"),
      ("Cache Read", gt["cache_read_tokens"], "#90CAF9"),
      ("Output", gt["output_tokens"], "#EF5350"),
      ("Cache Write", gt["cache_write_tokens"], "#FFAB91"),
  ], width=900, height=30)}
  <div class="legend" style="margin-top:8px">
    <span><i style="background:#42A5F5"></i> Input (非缓存) {_fmt(gt['input_tokens'] - gt['cache_read_tokens'])}</span>
    <span><i style="background:#90CAF9"></i> Cache Read {_fmt(gt['cache_read_tokens'])}</span>
    <span><i style="background:#EF5350"></i> Output {_fmt(gt['output_tokens'])}</span>
    <span><i style="background:#FFAB91"></i> Cache Write {_fmt(gt['cache_write_tokens'])}</span>
    <span><i style="background:#fff;border:1px solid #ccc"></i> 预制规范 {_fmt(gt['spec_context_tokens'])}</span>
  </div>
  <p style="font-size:12px;color:var(--muted);margin-top:4px">
    Cache 命中率: {_pct(gt['cache_read_tokens'], gt['input_tokens'])} &nbsp;|&nbsp;
    Input/Output 比: {gt['input_tokens'] / max(gt['output_tokens'], 1):.1f}:1 &nbsp;|&nbsp;
    预制规范占 Input: {_pct(gt['spec_context_tokens'], gt['input_tokens'])}
  </p>
</div>

<!-- ===================== 2. STAGE ===================== -->
<h2 id="stage">2. 阶段维度 (ST-0 ~ ST-7)</h2>
<div class="card">
  <h3>各阶段 Token 消耗占比</h3>
  {stage_bar_svg}
  <div class="legend" style="margin-top:8px">
    {"".join(f'<span><i style="background:{stage_colors[s]}"></i> {STAGE_NAMES[s].split("(")[0].strip()} {_pct(sa[s]["total_tokens"], total_tok)}</span>' for s in STAGE_NAMES)}
  </div>
</div>

<div class="card">
  <table>
    <thead><tr><th>阶段</th><th>名称</th><th>OPSX 命令</th><th style="text-align:right">Input</th><th style="text-align:right">Output</th><th style="text-align:right">Total</th><th style="text-align:right">占比</th><th style="text-align:right">迭代</th><th style="text-align:right">耗时</th></tr></thead>
    <tbody>{stage_rows}</tbody>
  </table>
</div>

<!-- ===================== 3. ROLE ===================== -->
<h2 id="role">3. 角色维度（人 vs AI）</h2>
<div class="two-col">
  <div class="card">
    <h3>角色 Token 分布</h3>
    {_bar_svg([("AI", rt_ai, "#42A5F5"), ("Human", rt_human, "#66BB6A")], width=400, height=28)}
    <table style="margin-top:12px">
      <tr><th>指标编码</th><th>指标</th><th style="text-align:right">值</th></tr>
      <tr><td>RT-AI</td><td>AI 消耗 Token 总量</td><td style="text-align:right">{_fmt(rt_ai)}</td></tr>
      <tr><td>RT-HUMAN</td><td>人类输入 Token 总量</td><td style="text-align:right">{_fmt(rt_human)}</td></tr>
      <tr><td>RT-RATIO</td><td>人机 Token 比</td><td style="text-align:right">{rt_ratio:.4f}</td></tr>
      <tr><td>RT-ITER</td><td>平均迭代次数 / AR</td><td style="text-align:right">{rt_iter:.1f}</td></tr>
    </table>
  </div>
  <div class="card">
    <h3>预制规范 Token（单独统计）</h3>
    <div class="stat" style="margin:12px 0"><div class="v">{_fmt(gt['spec_context_tokens'])}</div><div class="l">Spec Context Tokens (标注: 预制规范)</div></div>
    <p style="font-size:12px;color:var(--muted)">
      预制规范指前置工作逆向生成的 OpenSpec 规范文档内容，在 ST-3/ST-4/ST-5/ST-6 阶段作为 input context 注入，
      计入 input tokens 但单独标注，不计入人工输入 (RT-HUMAN)。
    </p>
<div class="metric-guide">
  <h4>角色指标指南:</h4>
  <div class="guide-grid">
    <div class="guide-item-name">RT-RATIO</div><div class="guide-item-desc">人机 Token 比（人工输入 / AI 生成）。<span class="best-tag">越低越好</span>，代表 AI 独立完成度高。</div>
    <div class="guide-item-name">RT-ITER</div><div class="guide-item-desc">平均交互轮数。越低代表模型单次意图理解越准确。</div>
  </div>
</div>
  </div>
</div>

<!-- ===================== 4. EFFICIENCY ===================== -->
<h2 id="efficiency">4. 效率维度</h2>
<div class="stats">
  <div class="stat"><div class="v">{gt['total_tokens'] / max(gt['total_loc'], 1):.0f}</div><div class="l">ET-LOC (Token/LOC)</div></div>
  <div class="stat"><div class="v">{gt['total_tokens'] / max(gt['total_files'], 1):,.0f}</div><div class="l">ET-FILE (Token/File)</div></div>
  <div class="stat"><div class="v">{gt['total_tokens'] / max(gt['total_tasks'], 1):,.0f}</div><div class="l">ET-TASK (Token/Task)</div></div>
  <div class="stat"><div class="v">{gt['total_tokens'] / max(gt['ar_count'], 1):,.0f}</div><div class="l">ET-AR (Token/AR)</div></div>
  <div class="stat"><div class="v">{gt['total_tokens'] / max(gt['total_duration_seconds'] / 3600, 0.01):,.0f}</div><div class="l">ET-TIME (Token/h)</div></div>
  <div class="stat"><div class="v">${gt['total_cost_usd'] / max(gt['total_loc'] / 1000, 0.01):.2f}</div><div class="l">ET-COST-LOC ($/KLOC)</div></div>
</div>
<div class="metric-guide">
  <h4>效率指标指南:</h4>
  <div class="guide-grid">
    <div class="guide-item-name">ET-LOC</div><div class="guide-item-desc">生成每行代码所需的 Token。 <span class="best-tag">越低越好</span>，反映代码逻辑的浓缩度与生成效率。</div>
    <div class="guide-item-name">ET-COST-LOC</div><div class="guide-item-desc">每千行代码的实际金钱成本。受模型定价与缓存命中率共同影响。</div>
  </div>
</div>

<div class="card">
  <h3>Token vs LOC 散点图（按语言着色）</h3>
  {scatter_svg}
  <div class="legend">
    <span><i style="background:#00ADD8"></i> Go</span>
    <span><i style="background:#3776AB"></i> Python</span>
    <span><i style="background:#CB171E"></i> YAML</span>
    <span><i style="background:#3178C6"></i> TypeScript</span>
    <span><i style="background:#427819"></i> Makefile</span>
    <span><i style="background:#384d54"></i> Dockerfile</span>
    <span><i style="background:#083FA1"></i> Markdown</span>
  </div>
</div>

<!-- ===================== 5. QUALITY ===================== -->
<h2 id="quality">5. 质量维度</h2>
<div class="stats">
  <div class="stat good"><div class="v">{sum(r['quality']['consistency_score'] for r in ars) / len(ars):.1%}</div><div class="l">平均 Spec-Code 一致性</div></div>
  <div class="stat good"><div class="v">{sum(r['quality']['code_usability'] for r in ars) / len(ars):.1%}</div><div class="l">平均代码可用率</div></div>
  <div class="stat"><div class="v">{sum(r['quality']['test_coverage'] for r in ars) / len(ars):.1%}</div><div class="l">平均测试覆盖率</div></div>
  <div class="stat warn"><div class="v">{sum(r['quality']['bugs_found'] for r in ars)}</div><div class="l">发现 Bug 总数</div></div>
</div>

<div class="card">
  <table>
    <thead><tr><th>指标</th><th>说明</th><th style="text-align:right">全局值</th></tr></thead>
    <tbody>
      <tr><td>QT-COV</td><td>Token / 测试覆盖率%</td><td style="text-align:right">{sa['ST-5']['total_tokens'] / max(sum(r['quality']['test_coverage'] for r in ars) / len(ars) * 100, 1):,.0f}</td></tr>
      <tr><td>QT-CONSIST</td><td>Token / 一致性得分%</td><td style="text-align:right">{sa['ST-6']['total_tokens'] / max(sum(r['quality']['consistency_score'] for r in ars) / len(ars) * 100, 1):,.0f}</td></tr>
      <tr><td>QT-AVAIL</td><td>Token / 代码可用率%</td><td style="text-align:right">{sa['ST-5']['total_tokens'] / max(sum(r['quality']['code_usability'] for r in ars) / len(ars) * 100, 1):,.0f}</td></tr>
      <tr><td>QT-BUG</td><td>Token / Bug 数 (反向)</td><td style="text-align:right">{sa['ST-5']['total_tokens'] / max(sum(r['quality']['bugs_found'] for r in ars), 1):,.0f}</td></tr>
    </tbody>
  </table>
</div>
<div class="metric-guide">
  <h4>质量指标指南:</h4>
  <div class="guide-grid">
    <div class="guide-item-name">一致性得分</div><div class="guide-item-desc"><span class="best-tag">越高越好</span>。基于跨模块接口调用的准确性评估，反映对复杂架构的把控。</div>
    <div class="guide-item-name">代码可用率</div><div class="guide-item-desc"><span class="best-tag">越高越好</span>。通过编译或静态语法检查的代码占比。</div>
  </div>
</div>

<!-- ===================== 6. DISTRIBUTION ===================== -->
<h2 id="distribution">6. 阶段间 Token 分布</h2>
<div class="stats">
  <div class="stat"><div class="v">{_pct(design_tok, total_tok)}</div><div class="l">PT-DESIGN 设计阶段 (15-30%)</div></div>
  <div class="stat"><div class="v">{_pct(plan_tok, total_tok)}</div><div class="l">PT-PLAN 规划阶段 (5-15%)</div></div>
  <div class="stat"><div class="v">{_pct(dev_tok, total_tok)}</div><div class="l">PT-DEV 开发阶段 (45-65%)</div></div>
  <div class="stat"><div class="v">{_pct(verify_tok, total_tok)}</div><div class="l">PT-VERIFY 验证阶段 (8-18%)</div></div>
  <div class="stat warn"><div class="v">{peak_stage}</div><div class="l">PT-PEAK 峰值阶段</div></div>
  <div class="stat {'good' if cache_rate > 0.7 else 'warn' if cache_rate > 0.5 else 'danger'}"><div class="v">{cache_rate:.0%}</div><div class="l">PT-CACHE 命中率 (&gt;70%)</div></div>
</div>

<div class="card">
  <h3>设计 / 开发 / 验证 Token 分布</h3>
  {_bar_svg([
      ("设计 (ST-1~3)", design_tok, "#42A5F5"),
      ("规划 (ST-0,4)", sa["ST-0"]["total_tokens"] + sa["ST-4"]["total_tokens"], "#FFA726"),
      ("开发 (ST-5)", dev_tok, "#EF5350"),
      ("验证归档 (ST-6,7)", verify_tok, "#AB47BC"),
  ], width=900, height=30)}
  <div class="note" style="margin-top:8px">
    <strong>分布分析：</strong>开发实现阶段 (ST-5) 占 {_pct(dev_tok, total_tok)} 为 Token 消耗主体，
    设计阶段 (ST-1~3) 占 {_pct(design_tok, total_tok)} 表明 SDD 在设计前移上有合理投入，
    验证阶段 (ST-6,7) 占 {_pct(verify_tok, total_tok)} 为质量保障成本。
  </div>
</div>

<!-- ===================== 7. BASELINES ===================== -->
<h2 id="baselines">7. 基线数据（按 AR 规模分层）</h2>
<div class="card">
  <table>
    <thead><tr><th>规模</th><th>AR 数</th><th style="text-align:right">平均 Tokens</th><th style="text-align:right">平均 LOC</th><th style="text-align:right">平均 Token/LOC</th><th style="text-align:right">平均成本</th><th style="text-align:right">平均耗时</th></tr></thead>
    <tbody>{bl_rows}</tbody>
  </table>
  <p style="font-size:12px;color:var(--muted);margin-top:8px">基线用于成本预测和异常预警。新需求 Token 预估 = 基线 × 规模系数 × 复杂度系数。</p>
</div>

<!-- ===================== 8. AR DETAIL ===================== -->
<h2 id="ar-detail">8. AR 需求明细（按 Token 消耗降序）</h2>
<div class="card" style="overflow-x:auto">
  <table>
    <thead><tr><th>AR</th><th>名称</th><th>模块</th><th>语言</th><th>规模</th><th style="text-align:right">Tokens</th><th style="text-align:right">LOC</th><th style="text-align:right">Tok/LOC</th><th style="text-align:right">成本</th><th style="text-align:right">一致性</th><th style="text-align:right">可用率</th></tr></thead>
    <tbody>{ar_rows}</tbody>
  </table>
  <p style="font-size:12px;color:var(--muted);margin-top:4px">橙色背景行: Token/LOC 超过同规模基线 200%（异常标记）</p>
</div>

<!-- ===================== 9. WARNINGS ===================== -->
<h2 id="warnings">9. 预警分析</h2>
<div class="card">
  <table>
    <thead><tr><th>预警规则</th><th>阈值</th><th>触发数量</th><th>相关 AR</th></tr></thead>
    <tbody>"""

    # Warning calculations — all 6 rules from 指标体系 §5
    warnings = []
    for r in ars:
        sz_bl = bl.get(r["size"], {})
        # W-STAGE-BUDGET: 单阶段 Token > 基线 150%
        avg_tok = sz_bl.get("avg_tokens", r["totals"]["total_tokens"])
        if r["totals"]["total_tokens"] > avg_tok * 1.5:
            warnings.append(("yellow", "W-STAGE-BUDGET: 总Token > 基线 150%", r["ar_id"]))
        # W-ET-LOC: Token/LOC > 基线 200%
        avg_et = sz_bl.get("avg_et_loc", r["metrics"]["ET_LOC"])
        if r["metrics"]["ET_LOC"] > avg_et * 2:
            warnings.append(("red", "W-ET-LOC: Token/LOC > 基线 200%", r["ar_id"]))
        # W-USABILITY: 代码可用率 < 75%
        if r["quality"]["code_usability"] < 0.75:
            warnings.append(("orange", "W-USABILITY: 代码可用率 < 75%", r["ar_id"]))
        # W-DEV-SKEW: 开发占比 > 80%
        pt_dev = r["metrics"].get("PT_DEV", 0)
        if pt_dev > 0.80:
            warnings.append(("orange", "W-DEV-SKEW: 开发占比 > 80%", r["ar_id"]))

    # Global warnings
    # W-TOTAL-BUDGET: overall budget check
    if bl:
        expected_total = sum(bl.get(sz, {}).get("avg_tokens", 0) * bl.get(sz, {}).get("count", 0)
                             for sz in ("S", "M", "L"))
        if expected_total > 0 and gt["total_tokens"] > expected_total * 1.2:
            warnings.append(("red", "W-TOTAL-BUDGET: 总Token > 预算 120%", "全局"))
    # W-CACHE-LOW: Cache 命中率 < 50%
    if cache_rate < 0.50:
        warnings.append(("orange", "W-CACHE-LOW: Cache命中率 < 50%", "全局"))

    warn_groups = {}
    for level, rule, ar_id in warnings:
        key = (level, rule)
        warn_groups.setdefault(key, []).append(ar_id)

    for (level, rule), ar_ids in sorted(warn_groups.items()):
        color = {"yellow": "#FFF9C4", "red": "#FFCDD2", "orange": "#FFE0B2"}.get(level, "#FFF9C4")
        html += f'<tr style="background:{color}"><td>{rule}</td><td>{level}</td><td>{len(ar_ids)}</td><td>{"、".join(ar_ids[:5])}{"..." if len(ar_ids) > 5 else ""}</td></tr>\n'

    if not warn_groups:
        html += '<tr><td colspan="4" style="text-align:center;color:var(--green)">无预警触发 (6 条规则全部通过)</td></tr>'

    html += f"""</tbody>
  </table>
</div>

<!-- ===================== 10. REFERENCE ===================== -->
<h2 id="reference">10. 引用与说明</h2>
<div class="card">
  <h3>评测体系说明</h3>
  <table>
    <tr><th style="width:150px">方法论</th><td>CodeSpec 7 阶段工作流 (ST-0 ~ ST-7) + OpenSpec OPSX 工具链</td></tr>
    <tr><th>AR 分解粒度</th><td>capability / feature 级别，共 {gt['ar_count']} 个 AR</td></tr>
    <tr><th>指标体系</th><td>5 维：阶段 (ST)、角色 (RT)、效率 (ET)、质量 (QT)、分布 (PT)</td></tr>
    <tr><th>Token 追踪</th><td>{meta.get('token_tracking', 'LiteLLM Proxy (统一) + 工具原生 (交叉验证)')}</td></tr>
    <tr><th>预制规范处理</th><td>计入 input tokens，标注为"预制规范"单独统计，不计入 RT-HUMAN</td></tr>
    <tr><th>参考基准</th><td>Claude Code ~78K tokens/request, 84% cache, 166:1 I/O ratio (BSWEN 2026)</td></tr>
  </table>

  <h3 style="margin-top:16px">OpenSpec OPSX 阶段对齐</h3>
  <table>
    <thead><tr><th>CodeSpec 阶段</th><th>OPSX 命令</th><th>产物</th><th>Token 追踪</th></tr></thead>
    <tbody>
      {"".join(f'<tr><td>{sid} {STAGE_NAMES[sid]}</td><td><code>{OPSX_COMMANDS[sid]}</code></td><td>{["变更目录脚手架","proposal.md","delta-spec.md","design.md","tasks.md","代码文件","归档 + spec 合并","验证报告"][i]}</td><td>✓</td></tr>' for i, sid in enumerate(STAGE_NAMES))}
    </tbody>
  </table>

  <h3 style="margin-top:16px">关联文档</h3>
  <table>
    <tr><td><code>PROPOSAL.md</code></td><td>评测体系设计文档（方法论 + 指标定义 + 基线方案）</td></tr>
    <tr><td><a href="project_analysis_report.html">目标工程技术解析</a></td><td>agentcube 代码量、技术栈、模块结构详情</td></tr>
  </table>
</div>

</div><!-- .container -->
<div class="footer">
  SDD-TEE v2 (SDD Token Efficiency Evaluation) &mdash; CodeSpec 7-Stage &times; OpenSpec OPSX &nbsp;|&nbsp;
  {meta['generated_at'][:19]}Z &nbsp;|&nbsp; <a href="https://github.com/ShijunDeng/sdd-tee">GitHub</a>
</div>
</body>
</html>"""
    return html


# ============================================================================
# Main
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="SDD-TEE Comprehensive Report Generator v2")
    parser.add_argument("--mock", action="store_true", help="Generate mock data report")
    parser.add_argument("--data", help="Path to real data JSON")
    parser.add_argument("--output", default="results/reports/sdd_tee_report.html")
    parser.add_argument("--data-output", default="results/reports/sdd_tee_report.json")
    args = parser.parse_args()

    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    if args.mock:
        print("[07] Generating mock data...")
        data = generate_mock_data()
    elif args.data:
        with open(args.data) as f:
            data = json.load(f)
    else:
        print("Usage: --mock for mock data, or --data <file> for real data")
        return

    # Schema validation — ensures ALL metrics from design doc are present
    try:
        from schema import validate_report_data, validate_html_report, SchemaError
        print("[07] Validating data against SDD-TEE schema...")
        schema_warnings = validate_report_data(data)
        print(f"[07] Schema: PASS ({len(data.get('ar_results',[]))} ARs)")
        for sw in schema_warnings:
            print(f"[07] WARN: {sw}")
    except SchemaError as e:
        print(f"[07] Schema: FAIL — report may be incomplete!")
        print(str(e))
    except ImportError:
        print("[07] schema.py not found, skipping validation")

    os.makedirs(os.path.dirname(os.path.join(base, args.output)), exist_ok=True)

    json_path = os.path.join(base, args.data_output)
    with open(json_path, 'w') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[07] Data → {json_path}")

    html = render_html(data)
    html_path = os.path.join(base, args.output)
    with open(html_path, 'w') as f:
        f.write(html)
    print(f"[07] HTML → {html_path}")

    # Validate rendered HTML contains all required sections
    try:
        validate_html_report(html)
        print(f"[07] HTML validation: PASS (10 sections, all keywords)")
    except SchemaError as e:
        print(f"[07] HTML validation: FAIL")
        print(str(e))
    except NameError:
        pass

    print(f"[07] Total: {data['grand_totals']['ar_count']} ARs, "
          f"{_fmt(data['grand_totals']['total_tokens'])} tokens, "
          f"${data['grand_totals']['total_cost_usd']:.2f}")


if __name__ == "__main__":
    main()
