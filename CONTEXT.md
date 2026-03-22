# SDD-TEE 项目上下文快照

> 生成时间: 2026-03-22T10:00:00Z
> 最新 commit: `5882b35 Fix Gemini 3.1 Pro estimated data structure and update report`
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
| 3 | opencode-cli | bailian-coding-plan/kimi-k2.5 | `..._AVERAGED` | 598,365 | 59 | 11,018 | 102m47s | $12.11 |
| 4 | opencode-cli | opencode/minimax-m2.5-free | `..._20260321T170726Z` | 885,287 | 185 | 20,380 | 102m55s | $19.66 |
| 5 | opencode-cli | bailian-coding-plan/qwen3.5-plus | `..._20260321T190016Z` | 754,346 | 108 | 16,237 | 79m41s | $16.21 |
| 6 | gemini-cli | gemini-3.1-pro-preview | `..._20260322T113247Z` | 0 | 164 | 25,186 | ~75m | $0.00 |
| 6 | gemini-cli | gemini-3.1-pro-preview |  | 0 | 0 | 0 | ~60m |  |

> **注意**: 
> 1. Kimi K2.5 的结果为两轮测试的平均值 (`..._AVERAGED`)。
> 2. Gemini 3.1 Pro 已完成实测，替换了之前的预估数据。
> 3. 汇总报告 `compare_report.html` 已更新。

### 进行中的任务

| 项目 | 命令 | 状态 |
|------|------|------|
| Claude Code 评测 | `make run TOOL=claude-code MODEL=claude-sonnet-4-20250514` | 待开始 |

## 4. 文件结构 (v2.0 归档升级)

```
/home/dsj/benchmark/
├── config.yaml                     # 评测配置
├── Makefile                        # 评测编排
├── CONTEXT.md                      # 上下文快照
├── scripts/                        # 评测脚本集 (包含最新的 V3 真实性看护脚本)
├── specs/                          # 10 capability OpenSpec 规范
├── workspaces/                     # 运行空间
│   └── v1.0/                       # 归档的旧版生成代码
└── results/
    ├── runs/                       # 当前 (v2.0) 正在进行的评测 JSON + 日志
    │   └── v1.0/                   # 归档的 v1.0 评测数据
    └── reports/
        └── v1.0/                   # 归档的 v1.0 评测报告 (如 compare_report.html)
```

## 5. 关键修复与变更 (本会话)

1. **V3 真实性看护架构**: 引入了 `03_sdd_develop_v3.sh`，强制执行 Session 隔离、LOC Delta 门禁检测及自动重试惩罚机制，确保生成代码的真实性，防止模型偷懒（Stub 敷衍）。
2. **数据全面归档**: 之前的无门禁约束的数据（如 Cursor, Qwen, Kimi v1.0）现已全部移至 `v1.0/` 目录下。
3. **版本切换**: 后续产生的所有经过严格看护测试的数据，将被标记为 `v2.0` 测试数据集。

## 6. 恢复步骤

```bash
# 执行 Claude Code 评测
make run TOOL=claude-code MODEL=claude-sonnet-4-20250514
make collect
make report
make compare
```
