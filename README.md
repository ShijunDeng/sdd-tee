# SDD Benchmark — Token Efficiency Baseline

基于 **Specification-Driven Development (SDD)** 的 Token 消耗与开发效率基线测评框架。

通过逆向解析真实开源项目 [agentcube](https://github.com/ShijunDeng/agentcube) 的源码生成 OpenSpec 规范，再用不同 AI Coding 工具端到端完成 SDD 开发，量化各阶段的 **token 消耗、耗时、代码质量**，为后续 Token 提效提供评估基线。

## 流水线架构

```
Stage 0        Stage 1          Stage 2         Stage 3        Stage 4
项目分析  →  规范逆向生成  →  SDD 端到端开发  →  质量验证  →  数据汇总与对比
(全自动)    (spec-gen+LLM)   (OpenSpec+AI)    (全自动)      (CSV/图表)
```

## 快速开始

### 前置依赖

- Node.js ≥ 20.19.0
- Python ≥ 3.10
- Go ≥ 1.21（用于验证阶段）
- AI Coding 工具：`claude`（Claude Code CLI）或 `aider`

### 安装

```bash
make setup
```

### 运行

```bash
# 单次运行（指定工具 + 模型）
make all TOOL=claude-code MODEL=claude-sonnet-4-20250514

# 矩阵运行（所有工具×模型组合）
make matrix

# 仅生成报告
make report
```

### 输出

- `results/runs/` — 每次运行的 JSON 数据（token、耗时、成本）
- `results/reports/summary.csv` — 汇总 CSV
- `results/reports/comparison_report.md` — Markdown 对比报告
- `results/reports/comparison_charts.png` — 可视化对比图表

## 目录结构

```
benchmark/
├── Makefile                    # 顶层编排
├── config.yaml                 # 测评配置（工具、模型、阶段）
├── PROPOSAL.md                 # 方案设计文档
├── scripts/
│   ├── 00_analyze_project.sh   # Stage 0: 项目分析
│   ├── 01_generate_specs.sh    # Stage 1: 规范逆向生成
│   ├── 02_sdd_develop.sh       # Stage 2: SDD 开发 + Token 追踪
│   ├── 03_validate.sh          # Stage 3: 质量验证
│   └── 04_report.py            # Stage 4: 汇总报告 + 图表
├── specs/                      # 逆向生成的 OpenSpec 规范
├── workspaces/                 # 各工具的开发工作空间（运行时生成）
└── results/                    # 测评结果（运行时生成）
```

## Token 追踪

支持双轨追踪：

| 方式 | 说明 |
|------|------|
| LiteLLM Proxy | 统一代理层拦截所有 API 调用，工具无关 |
| 工具原生 | Claude Code OpenTelemetry / Aider session cost |

## 测评维度

| 维度 | 指标 |
|------|------|
| Token 消耗 | input / output / cache tokens（按阶段细分） |
| 成本 | USD（按阶段、按工具×模型） |
| 耗时 | 秒（端到端 & 按阶段） |
| 代码质量 | 文件数比、LOC 比、目录相似度、编译通过率、语法通过率 |

## License

MIT
