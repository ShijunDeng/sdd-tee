# SDD-TEE 项目上下文快照

> 生成时间: 2026-03-22T08:45:00Z
> 最新 commit: `1812b68 Remove anomalous 7th evaluation run and revert summary reports to 6 valid runs`
> 分支: main | 远端: github.com:ShijunDeng/sdd-tee.git

---

## 1. 项目定位

SDD-TEE (SDD Token Efficiency Evaluation) — 基于 **CodeSpec 7 阶段工作流 × OpenSpec OPSX** 的 AI Coding Assistant Token 效率评估框架。

目标：将真实项目 [agentcube](https://github.com/ShijunDeng/agentcube.git) 拆解为 43 个 AR，用 4 种 CLI 工具分别走完 SDD 全流程，量化 Token 消耗，建立基线。

## 2. 核心任务文件

- **`task.md`** — 原始需求（不提交到 git）
- **`docs/SDD开发Token消耗度量指标体系设计方案.md`** — 5 维指标体系设计方案
- **`config.yaml`** — 评测配置（工具、模型、AR 列表、预警阈值）
- **`PROPOSAL.md`** — v2 评测体系设计文档

## 3. 当前工程状态

### 已完成

| 项目 | 状态 | 说明 |
|------|------|------|
| 项目技术解析 | ✅ | `scripts/01_analyze_project.sh` + `scripts/06_project_report.py` |
| 规范逆向生成 | ✅ | `specs/` 目录，10 capabilities × (spec.md + design.md) |
| 评测体系设计 | ✅ | 8 阶段 × 5 维 × 16 指标 |
| 数据合约层 | ✅ | `scripts/schema.py` — Single Source of Truth |
| 环境预检 | ✅ | `scripts/preflight.py` — 7 维检查，43 项通过 |
| 4 工具适配 | ✅ | cursor-cli / claude-code / gemini-cli / opencode-cli 全部适配 |
| 可重入性保障 | ✅ | preflight + schema + selftest + requirements.txt |

### 已完成的评测轮次 (有效)

| # | 工具 | 模型 | Run ID | Tokens | 文件 | LOC | 耗时 | 成本 |
|---|------|------|--------|--------|------|-----|------|------|
| 1 | cursor-cli | claude-4.6-opus-high-thinking | `..._20260321T090515Z` | 896,885 | 174 | 19,115 | 93m10s | $19.99 |
| 2 | opencode-cli | bailian-coding-plan/glm-5 | `..._20260321T114208Z` | 852,964 | 124 | 18,099 | 105m26s | $18.83 |
| 3 | opencode-cli | bailian-coding-plan/kimi-k2.5 | `..._20260321T141458Z` | 613,651 | 64 | 11,525 | 105m14s | $12.51 |
| 4 | opencode-cli | opencode/minimax-m2.5-free | `..._20260321T170726Z` | 885,287 | 185 | 20,380 | 102m55s | $19.66 |
| 5 | opencode-cli | bailian-coding-plan/qwen3.5-plus | `..._20260321T190016Z` | 754,346 | 108 | 16,237 | 79m41s | $16.21 |

> **注意**: 
> 1. 原第 6 轮 (gemini-cli) 和第 7 轮 (cursor-cli) 因数据异常（耗时过短、配额耗尽导致 Round 4 中断）已被手动删除。
> 2. 汇总报告 `compare_report.html` 目前基于上述 5 轮有效数据生成。

### 进行中的任务

| 项目 | 命令 | 状态 |
|------|------|------|
| Gemini 3.1 Pro 重测 | `make run TOOL=gemini-cli MODEL=gemini-3.1-pro-preview` | 后台执行中 (PID: 580607) |
| Claude Code 评测 | `make run TOOL=claude-code MODEL=claude-sonnet-4-20250514` | 待开始 |

## 4. 文件结构

```
/home/dsj/benchmark/
├── config.yaml                     # 评测配置
├── Makefile                        # 评测编排
├── CONTEXT.md                      # ← 本文件（上下文快照）
├── scripts/                        # 评测脚本集
├── specs/                          # 10 capability OpenSpec 规范
├── workspaces/                     # 运行空间 (有效轮次)
│   ├── cursor-cli_claude-4.6-opus-high-thinking_20260321T090515Z/
│   ├── opencode-cli_bailian-coding-plan_glm-5_20260321T114208Z/
│   ├── opencode-cli_bailian-coding-plan_kimi-k2.5_20260321T141458Z/
│   ├── opencode-cli_opencode_minimax-m2.5-free_20260321T170726Z/
│   └── opencode-cli_bailian-coding-plan_qwen3.5-plus_20260321T190016Z/
└── results/
    ├── runs/                       # 5 轮有效 JSON + 日志
    └── reports/
        ├── compare_report.html     # 5 轮对比报告
        └── {run_id}_report.html    # 单轮报告
```

## 5. 关键修复与变更 (本会话)

1. **清理异常数据**: 识别并删除了两个无效评测轮次，防止其污染基线数据。
2. **处理 Gemini 配额**: 针对 `TerminalQuotaError` 进行了多次排查，目前在用户确认配额解决后已重新启动后台流水线。
3. **流水线稳定性**: 将 `make run` 封装在 `nohup` 中并在后台执行，以应对长时间生成导致的 SSH 超时问题。
4. **文档同步**: 持续更新 `CONTEXT.md` 确保其作为 Single Source of Truth 的准确性。

## 6. 恢复步骤

```bash
# 查看后台评测进度
tail -f pipeline.log

# 评测完成后手动执行数据处理（如果流水线中断）
make collect
make report
make compare
```
