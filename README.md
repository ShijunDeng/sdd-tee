# SDD-TEE — SDD Token Efficiency Evaluation

基于 **CodeSpec 7 阶段工作流** 与 **OpenSpec OPSX 工具链**的 AI Coding Assistant Token 效率评估框架。

通过将真实开源项目 [agentcube](https://github.com/ShijunDeng/agentcube) 拆解为 **43 个细粒度 AR（分配需求）**，
每个 AR 走完整的 SDD 流程（`/opsx:new` → `/opsx:ff` → `/opsx:apply` → `/opsx:verify` → `/opsx:archive`），
**量化 8 个阶段（ST-0~ST-7）× 5 个维度的 Token 消耗**，为 Token 提效研究提供评估基线。

## 评测体系

### 5 维指标体系

| 维度 | 编码 | 指标示例 |
|------|------|----------|
| 阶段维度 | ST-0 ~ ST-7 | 各阶段 Input/Output/Cache Tokens、迭代数、耗时 |
| 角色维度 | RT-AI / RT-HUMAN | AI Token、人工输入 Token、人机比、预制规范（单独标注） |
| 效率维度 | ET-LOC / ET-FILE / ET-TASK | Token/LOC、Token/File、Token/Task、Token/AR、Token/h |
| 质量维度 | QT-COV / QT-CONSIST | Token/覆盖率、Token/一致性、Token/可用率、Token/Bug |
| 分布维度 | PT-DESIGN / PT-DEV | 设计/开发/验证阶段占比、峰值阶段 |

### CodeSpec 7 阶段 × OpenSpec OPSX 对齐

```
ST-0  /opsx:new     → 变更目录脚手架
ST-1  /opsx:ff      → proposal.md       (需求澄清)
ST-2  /opsx:ff      → delta-spec.md     (Spec 增量设计)
ST-3  /opsx:ff      → design.md         (Design 增量设计)
ST-4  /opsx:ff      → tasks.md          (任务拆解)
ST-5  /opsx:apply   → 代码文件           (开发实现)
ST-6  /opsx:verify  → 验证报告           (一致性验证)
ST-7  /opsx:archive → 归档 + spec 合并   (合并归档)
```

## 前置工作（一次性）

以下为一次性前置准备，成果可在所有评测中复用，Token/耗时不计入评测基线。

| 前置项 | 产出 |
|--------|------|
| 项目技术解析 | [`results/reports/project_analysis_report.html`](results/reports/project_analysis_report.html) |
| 规范逆向生成 | `specs/` 目录（10 个 capability，22 份 OpenSpec 规范） |

## 快速开始

```bash
# 安装 OpenSpec CLI
npm install -g @fission-ai/openspec@latest

# 初始化项目
cd your-workspace && openspec init

# 生成 mock 报告（预览）
python3 scripts/07_sdd_tee_report.py --mock

# 运行评测（单个工具 × 模型）
make run TOOL=claude-code MODEL=claude-sonnet-4-20250514

# 生成综合报告
make report
```

## 目录结构

```
sdd-tee/
├── config.yaml                 # 评测配置（工具、模型、AR 列表）
├── Makefile                    # 评测编排
├── PROPOSAL.md                 # v2 评测体系设计文档
├── scripts/
│   ├── 01_analyze_project.sh   # 前置：项目结构分析
│   ├── 02_generate_specs.sh    # 前置：规范逆向生成
│   ├── 03_sdd_develop.sh       # 评测：SDD 开发驱动（OpenSpec OPSX）
│   ├── 04_validate.py          # 评测：代码质量验证
│   ├── 05_aggregate.py         # 评测：CSV/Markdown 汇总
│   ├── 06_project_report.py    # 前置：项目技术解析 HTML 报告
│   └── 07_sdd_tee_report.py    # 评测：综合 HTML 报告（5 维指标）
├── specs/                      # 逆向生成的 OpenSpec 规范（capability-based，一次性产出）
│   ├── project.md              # 项目上下文（技术栈、架构、约定）
│   ├── {capability}/spec.md    # 需求规范（SHALL/MUST + GIVEN/WHEN/THEN 场景）
│   └── {capability}/design.md  # 技术设计（类型定义、接口、常量、路由）
├── workspaces/                 # 各评测轮次的生成代码
└── results/
    ├── project_analysis/       # 项目分析原始数据
    ├── runs/                   # 每次评测的 JSON 原始数据
    └── reports/                # HTML 报告与图表
```

## Token 追踪

| 方式 | 说明 |
|------|------|
| LiteLLM Proxy | 统一代理层拦截所有 API 调用，精确 per-request 记录 |
| 工具原生 | Claude Code (OpenTelemetry) / Aider (session cost) |
| 预制规范 | Spec 文档计入 input tokens，标注为"预制规范"单独统计 |

## 参考基准

| 来源 | 数据 |
|------|------|
| BSWEN 2026 (100M tokens tracked) | Claude Code ~78K tokens/request, 84% cache, 166:1 I/O |
| Iterathon 2026 | Claude Sonnet $0.08/task, Gemini $0.15/task |
| SWE-AGI 2026 | Frontier models 68-86% on spec-driven construction |

## License

MIT
