# SDD-TEE — SDD Token Efficiency Evaluation

基于 **Specification-Driven Development (SDD)** 的 Token 效率评估框架。

通过逆向解析真实开源项目 [agentcube](https://github.com/ShijunDeng/agentcube) 的源码生成 OpenSpec 规范，再用不同 AI Coding 工具端到端完成 SDD 开发，量化各阶段的 **token 消耗、耗时、代码质量**，为 Token 提效提供评估基线。

## 前置工作（一次性）

以下两项为一次性的前置准备，成果可在后续所有评测中复用，其耗时和 token 消耗不计入 benchmark。
详细的 Token 消耗、耗时及框架技术细节见 **[项目介绍与前置工作报告](results/reports/introduction.html)**。

| 前置项 | 说明 | 产出 |
|--------|------|------|
| 项目技术解析 | 分析目标项目的代码量、技术栈、模块结构 | [`project_analysis_report.html`](results/reports/project_analysis_report.html) |
| 规范逆向生成 | 从源码逆向生成 OpenSpec 规范文档 | `specs/` 目录 |
| **综合介绍** | **前置工作详情 + 框架技术架构 + 规范概览** | [`introduction.html`](results/reports/introduction.html) |

## 评测流水线

```
Stage 0           Stage 1            Stage 2          Stage 3
SDD 端到端开发  →  质量验证        →  数据汇总      →  报告生成
(OpenSpec+AI)     (全自动对比)      (CSV/JSON)       (HTML/图表)
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
sdd-tee/
├── Makefile                    # 顶层编排
├── config.yaml                 # 测评配置（工具、模型、阶段）
├── PROPOSAL.md                 # 方案设计文档
├── scripts/
│   ├── 00_analyze_project.sh   # 前置: 项目分析（一次性）
│   ├── 01_generate_specs.sh    # 前置: 规范逆向生成（一次性）
│   ├── 02_sdd_develop.sh       # 评测: SDD 开发 + Token 追踪
│   ├── 03_validate.py          # 评测: 质量验证
│   ├── 04_report.py            # 评测: 汇总报告 + 图表
│   ├── 05_generate_html_report.py  # 评测: 详细 HTML 报告
│   ├── 06_project_analysis_report.py  # 前置: 项目技术解析（一次性）
│   └── 07_introduction_report.py  # 文档: 介绍章节生成
├── specs/                      # 逆向生成的 OpenSpec 规范（一次性产出，可复用）
├── workspaces/                 # 各工具的开发工作空间（运行时生成）
└── results/                    # 测评结果（运行时生成）
    ├── project_analysis/       # 项目分析数据（一次性）
    ├── runs/                   # 每次评测的 JSON 数据
    └── reports/                # 汇总报告与图表
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
